"""Step 4 Unit and Property-Based Tests: Unified FastAPI Server, Manifest Cache, Jobs API & SSE.

Covers SPEC-20261120-UNIFIED-WORKBENCH-V2 Step 4.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from query_agent.models.schemas import OkfConceptNode
from query_agent.spanner.repository import SpannerGraphRepository
from scripts.pipeline_job_runner import run_pipeline
from unified_web.jobs import PipelineJobDispatcher
from unified_web.manifest import BundleManifestStore
from unified_web.models import ALLOWED_GEMINI_MODELS
from unified_web.security import IAP_ISSUER, PURGE_CONFIRM_HEADER, PURGE_CONFIRM_VALUE
from unified_web.server import create_unified_app


def _make_sample_repo() -> SpannerGraphRepository:
    repo = SpannerGraphRepository(use_in_memory=True)
    for i in range(1, 16):
        cid = f"equipment/D-{2300 + i}"
        repo._mem_concepts[cid] = OkfConceptNode(
            concept_id=cid,
            category="equipment",
            name=f"Drum D-{2300 + i}",
            description=f"Reflux vessel {i}",
            unit="Unit 23",
            has_conflict=(i == 4),
            conflict_count=(1 if i == 4 else 0),
            body_markdown=f"# Drum D-{2300 + i}\n\nDesign Pressure: 15 barg",
            md5_hash=f"md5-{i}",
        )
    return repo


def _setup_bundle_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, n_okf: int = 12) -> Path:
    bundle_dir = tmp_path / "okf_bundle"
    eq_dir = bundle_dir / "equipment"
    eq_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, n_okf + 1):
        (eq_dir / f"V-{1000 + i}.md").write_text(
            f"---\ntitle: Vessel V-{1000 + i}\ntype: Equipment\nsources:\n  - resource: pid/sample.pdf\n---\n# Vessel V-{1000 + i}\n",
            encoding="utf-8",
        )
    raw_dir = tmp_path / "raw" / "pid"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "sample.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")

    monkeypatch.setenv("USE_GCS_STORAGE", "false")
    monkeypatch.setenv("OUTPUT_BUNDLE_DIR", str(bundle_dir))
    monkeypatch.setenv("REFERENCE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("IAP_JWT_ENFORCEMENT", "false")
    monkeypatch.setenv("QUERY_WEB_TEST_FAST_AGENT", "true")
    monkeypatch.setenv("JOB_STATUS_DIR", str(tmp_path / "job_status"))
    return bundle_dir


def test_unified_healthz_models_and_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _setup_bundle_env(monkeypatch, tmp_path)
    repo = _make_sample_repo()
    app = create_unified_app(repo=repo, manifest_store=BundleManifestStore())
    client = TestClient(app)

    h = client.get("/healthz")
    assert h.status_code == 200
    hd = h.json()
    assert hd["status"] == "healthy"
    assert hd["defaults"]["extractor"] == "gemini-4-carbon"
    assert hd["defaults"]["query"] == "gemini-4-hydrogen"

    m = client.get("/api/models")
    assert m.status_code == 200
    md = m.json()
    assert [x["id"] for x in md["allowed_models"]] == list(ALLOWED_GEMINI_MODELS)
    assert md["defaults"]["extractor"] == "gemini-4-carbon"
    assert md["defaults"]["query"] == "gemini-4-hydrogen"

    s = client.get("/api/status")
    assert s.status_code == 200
    sd = s.json()
    assert sd["okf_file_count"] == 12
    assert sd["raw_pdf_count"] == 1
    assert sd["models"]["extractor_default"] == "gemini-4-carbon"
    assert sd["models"]["query_default"] == "gemini-4-hydrogen"


def test_manifest_paginated_files_and_search(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _setup_bundle_env(monkeypatch, tmp_path, n_okf=15)
    store = BundleManifestStore()
    app = create_unified_app(repo=_make_sample_repo(), manifest_store=store)
    client = TestClient(app)

    p1 = client.get("/api/files?kind=okf&limit=6&offset=0").json()
    p2 = client.get("/api/files?kind=okf&limit=6&offset=6").json()
    p3 = client.get("/api/files?kind=okf&limit=6&offset=12").json()
    assert p1["okf_file_count"] == 15
    assert len(p1["okf_files"]) == 6
    assert p1["pagination"]["okf_has_more"] is True
    assert len(p2["okf_files"]) == 6
    assert len(p3["okf_files"]) == 3
    assert p3["pagination"]["okf_has_more"] is False

    search = client.get("/api/files?kind=okf&q=V-1012").json()
    assert search["pagination"]["okf_filtered_total"] == 1
    assert search["okf_files"][0]["concept_id"] == "equipment/V-1012"


def test_pipeline_job_cloud_run_v2_dispatch_idempotency_hitl_and_degraded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _setup_bundle_env(monkeypatch, tmp_path)
    monkeypatch.setenv("CLOUD_RUN_JOBS_EXECUTION_MODE", "cloud_run_job")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "engineering-kg-demo")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "asia-southeast1")

    captured_requests: list[dict[str, Any]] = []

    def _mock_transport(request: httpx.Request) -> httpx.Response:
        captured_requests.append(
            {"url": str(request.url), "body": json.loads(request.content.decode("utf-8"))}
        )
        return httpx.Response(
            200,
            json={"metadata": {"name": "projects/engineering-kg-demo/locations/asia-southeast1/jobs/okf-pipeline-job/executions/exec-1"}},
        )

    dispatcher = PipelineJobDispatcher(
        http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(_mock_transport)),
        token_provider=lambda: "fake-adc-token",
    )
    app = create_unified_app(repo=_make_sample_repo(), manifest_store=BundleManifestStore(), job_dispatcher=dispatcher)
    client = TestClient(app)

    # 1. Trigger sync job with idempotency key
    r1 = client.post(
        "/api/jobs/run",
        headers={"X-Idempotency-Key": "sync-key-00001"},
        json={"job_mode": "sync", "sync_mode": "FULL_MIRROR", "model": "gemini-4-carbon"},
    )
    assert r1.status_code == 202
    d1 = r1.json()
    assert d1["job_mode"] == "sync"
    assert d1["execution_backend"] == "cloud_run_job"
    assert d1["idempotent_replay"] is False
    assert len(captured_requests) == 1
    env_sent = {
        e["name"]: e["value"]
        for e in captured_requests[0]["body"]["overrides"]["containerOverrides"][0]["env"]
    }
    assert env_sent["JOB_MODE"] == "sync"
    assert env_sent["GEMINI_MODEL"] == "gemini-4-carbon"

    # 2. Same idempotency key returns replay without launching a second Cloud Run Job
    r2 = client.post(
        "/api/jobs/run",
        headers={"X-Idempotency-Key": "sync-key-00001"},
        json={"job_mode": "sync", "sync_mode": "FULL_MIRROR", "model": "gemini-4-carbon"},
    )
    assert r2.status_code == 200
    assert r2.json()["execution_id"] == d1["execution_id"]
    assert r2.json()["idempotent_replay"] is True
    assert len(captured_requests) == 1

    # 3. Purge without HITL confirmation header MUST be rejected (HTTP 400)
    r_bad = client.post(
        "/api/jobs/run",
        headers={"X-Idempotency-Key": "purge-key-00002"},
        json={"job_mode": "sync", "purge": True},
    )
    assert r_bad.status_code == 400

    # 4. Purge WITH exact HITL header + idempotency key succeeds
    r_ok = client.post(
        "/api/jobs/run",
        headers={
            "X-Idempotency-Key": "purge-key-00003",
            PURGE_CONFIRM_HEADER: PURGE_CONFIRM_VALUE,
        },
        json={"job_mode": "extract_and_sync", "purge": True, "model": "gemini-4-neon"},
    )
    assert r_ok.status_code == 202
    assert r_ok.json()["purge"] is True
    assert r_ok.json()["model"] == "gemini-4-neon"

    # 5. Upstream 503 degraded mode when Cloud Run Jobs API fails
    failing_dispatcher = PipelineJobDispatcher(
        http_client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(503, text="Backend unavailable"))
        ),
        token_provider=lambda: "fake-adc-token",
    )
    fail_app = create_unified_app(
        repo=_make_sample_repo(),
        manifest_store=BundleManifestStore(),
        job_dispatcher=failing_dispatcher,
    )
    r_deg = TestClient(fail_app).post("/api/jobs/run", json={"job_mode": "sync"})
    assert r_deg.status_code == 503
    assert r_deg.json()["status"] == "UPSTREAM_UNAVAILABLE_DEGRADED"


def test_pipeline_job_runner_end_to_end_extract_and_sync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _setup_bundle_env(monkeypatch, tmp_path, n_okf=4)
    res = run_pipeline(
        job_mode="extract_and_sync",
        model="gemini-4-carbon",
        sync_mode="FULL_MIRROR",
        purge=False,
        dry_run_extract=True,
        use_in_memory_spanner=True,
        execution_id="exec-local-test-01",
    )
    assert res["status"] == "SUCCEEDED"
    assert res["percent"] == 100.0
    assert res["spanner_counts"]["total_concepts"] >= 4


def test_unified_lazy_hierarchy_parallel_concept_and_sse_stream(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _setup_bundle_env(monkeypatch, tmp_path)
    app = create_unified_app(repo=_make_sample_repo(), manifest_store=BundleManifestStore())
    client = TestClient(app)

    summ = client.get("/api/spanner/hierarchy/summary")
    assert summ.status_code == 200
    assert summ.json()["total_equipment"] == 15

    items = client.get("/api/spanner/hierarchy/items?limit=5&offset=0&q=D-2304")
    assert items.status_code == 200
    assert items.json()["total"] == 1
    assert items.json()["items"][0]["canonical_tag"] == "D-2304"

    concept = client.get("/api/spanner/concept/equipment/D-2304")
    assert concept.status_code == 200
    assert concept.json()["concept"]["concept_id"] == "equipment/D-2304"

    # SSE streaming endpoint with selectable model & X-Accel-Buffering: no
    with client.stream(
        "POST",
        "/api/query/chat/stream",
        json={"question": "Inspect D-2304", "focus_tag": "D-2304", "model": "gemini-4-hydrogen"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("x-accel-buffering") == "no"
        body = "".join(resp.iter_text())
        assert "event: start" in body
        assert "event: done" in body
        assert "gemini-4-hydrogen" in body

    # Disallowed model rejected with 400
    bad_model = client.post(
        "/api/query/chat/stream",
        json={"question": "Inspect D-2304", "model": "gemini-99-fake"},
    )
    assert bad_model.status_code == 400


def test_iap_jwt_middleware_enforcement(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _setup_bundle_env(monkeypatch, tmp_path)
    monkeypatch.setenv("IAP_JWT_ENFORCEMENT", "true")

    app = create_unified_app(
        repo=_make_sample_repo(),
        manifest_store=BundleManifestStore(),
        iap_verifier=lambda tok, audience=None: {
            "iss": IAP_ISSUER,
            "email": "plant.lead@example.com",
            "sub": "sub-1",
        },
    )
    client = TestClient(app)
    # /healthz always bypasses IAP for Cloud Run probes
    assert client.get("/healthz").status_code == 200
    # Missing IAP header rejected
    assert client.get("/api/status").status_code == 401
    # Valid IAP header succeeds
    ok = client.get("/api/status", headers={"x-goog-iap-jwt-assertion": "signed.jwt.value"})
    assert ok.status_code == 200
    assert ok.json()["principal"] == "plant.lead@example.com"


@settings(max_examples=25)
@given(
    limit=st.integers(min_value=1, max_value=10),
    offset=st.integers(min_value=0, max_value=20),
)
def test_pbt_manifest_pagination_bounds(limit: int, offset: int) -> None:
    store = BundleManifestStore()
    fake_manifest = {
        "sync_version": "abc123",
        "generated_at": "2026-11-20T00:00:00Z",
        "raw_pdf_count": 5,
        "okf_file_count": 12,
        "conflict_count": 0,
        "raw_subfolders": {"pid": 5},
        "okf_categories": {"equipment": 12},
        "raw_pdfs": [{"relative_path": f"pid/p{i}.pdf", "subfolder": "pid", "file_name": f"p{i}.pdf", "size_bytes": 100} for i in range(5)],
        "okf_files": [{"concept_id": f"equipment/E-{i}", "category": "equipment", "title": f"E-{i}", "has_conflict": False} for i in range(12)],
    }
    store._manifest = fake_manifest
    store._cached_at = 1e12
    store._cached_bundle_dir = str(Path("build/okf_bundle").resolve())
    # Bypass directory comparison by patching get_manifest directly on instance
    store.get_manifest = lambda force_refresh=False: fake_manifest  # type: ignore[method-assign]

    res = store.query_paginated_files(kind="okf", limit=limit, offset=offset)
    expected_len = max(0, min(limit, 12 - offset))
    assert len(res["okf_files"]) == expected_len
    assert res["pagination"]["okf_has_more"] == ((offset + expected_len) < 12)
