"""Step 2 Unit and Property-Based Tests: Gemini 4 Allowlist, IAP Security, HITL Gate & Spanner v2.

Covers SPEC-20261120-UNIFIED-WORKBENCH-V2 Step 2.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from query_agent.models.schemas import OkfConceptNode
from query_agent.spanner.catalog_sync import DataplexCatalogAndLineageSync
from query_agent.spanner.repository import SpannerGraphRepository
from unified_web.models import (
    ALLOWED_GEMINI_MODELS,
    DEFAULT_EXTRACTER_MODEL,
    DEFAULT_QUERY_MODEL,
    PipelineJobMode,
    PipelineJobRequest,
    SpannerSyncMode,
    get_default_extracter_model,
    get_default_query_model,
    validate_gemini_model,
)
from unified_web.security import (
    IAP_ISSUER,
    PURGE_CONFIRM_VALUE,
    SlidingWindowRateLimiter,
    clear_iap_jwk_cache,
    enforce_purge_hitl_gate,
    resolve_expected_iap_audience,
    verify_iap_jwt_assertion,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ==============================================================================
# Deterministic Unit Tests
# ==============================================================================


def test_gemini_4_model_allowlist_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXTRACTER_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("QUERY_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("ALLOWED_GEMINI_MODELS", raising=False)

    assert DEFAULT_EXTRACTER_MODEL == "gemini-4-carbon"
    assert DEFAULT_QUERY_MODEL == "gemini-4-hydrogen"
    assert get_default_extracter_model() == "gemini-4-carbon"
    assert get_default_query_model() == "gemini-4-hydrogen"
    assert set(ALLOWED_GEMINI_MODELS) == {
        "gemini-4-carbon",
        "gemini-4-hydrogen",
        "gemini-4-argon",
        "gemini-4-neon",
    }

    for model_id in ALLOWED_GEMINI_MODELS:
        assert validate_gemini_model(model_id, default=DEFAULT_QUERY_MODEL) == model_id
    assert validate_gemini_model(None, default=DEFAULT_EXTRACTER_MODEL) == "gemini-4-carbon"
    assert validate_gemini_model("", default=DEFAULT_QUERY_MODEL) == "gemini-4-hydrogen"

    with pytest.raises(ValueError, match="Unsupported Gemini model"):
        validate_gemini_model("gemini-1.5-pro-latest", default=DEFAULT_QUERY_MODEL)


def test_pipeline_job_request_validation() -> None:
    req = PipelineJobRequest(
        job_mode=PipelineJobMode.EXTRACT_AND_SYNC,
        model="gemini-4-neon",
        sync_mode=SpannerSyncMode.FULL_MIRROR,
        purge=False,
        target_subfolder="pid",
        target_files=["pid/ML101620329-part-1.pdf"],
    )
    assert req.model == "gemini-4-neon"
    assert req.target_subfolder == "pid"

    with pytest.raises(ValidationError):
        PipelineJobRequest(job_mode="sync", model="evil-model")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        PipelineJobRequest(job_mode="extract", target_subfolder="../etc")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        PipelineJobRequest(job_mode="extract", target_files=["../secret.pdf"])


def test_iap_jwt_verification_and_purge_hitl_gate() -> None:
    def _valid_verifier(token: str, audience: str | None = None) -> dict[str, Any]:
        return {
            "iss": IAP_ISSUER,
            "email": "engineer@example.com",
            "sub": "accounts.google.com:12345",
        }

    principal = verify_iap_jwt_assertion("valid.jwt.token", verifier=_valid_verifier)
    assert principal.email == "engineer@example.com"
    assert principal.auth_mode == "iap_jwt"

    with pytest.raises(HTTPException) as exc_missing:
        verify_iap_jwt_assertion("", verifier=_valid_verifier)
    assert exc_missing.value.status_code == 401

    with pytest.raises(HTTPException) as exc_wrong_iss:
        verify_iap_jwt_assertion(
            "bad.iss.token",
            verifier=lambda tok, audience=None: {"iss": "https://evil.example.com", "email": "x@y.com"},
        )
    assert exc_wrong_iss.value.status_code == 401

    # Purge HITL gate
    enforce_purge_hitl_gate(purge=False, confirm_header=None, idempotency_key=None)
    enforce_purge_hitl_gate(
        purge=True,
        confirm_header=PURGE_CONFIRM_VALUE,
        idempotency_key="idem-12345678",
    )
    with pytest.raises(HTTPException) as exc_no_confirm:
        enforce_purge_hitl_gate(purge=True, confirm_header="", idempotency_key="idem-12345678")
    assert exc_no_confirm.value.status_code == 400

    with pytest.raises(HTTPException) as exc_no_idem:
        enforce_purge_hitl_gate(purge=True, confirm_header=PURGE_CONFIRM_VALUE, idempotency_key="short")
    assert exc_no_idem.value.status_code == 400


def test_iap_jwt_real_es256_jwk_cryptographic_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify real ES256 JWK Set cryptographic verification via PyJWT + strict audience checks."""
    import json
    import time

    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import ec

    clear_iap_jwk_cache()

    # Auto-derived Cloud Run Native IAP audience
    monkeypatch.delenv("IAP_JWT_AUDIENCE", raising=False)
    monkeypatch.setenv("K_SERVICE", "okf-engineering-workbench")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "435347747480")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "asia-southeast1")
    expected_aud = resolve_expected_iap_audience()
    assert expected_aud == "/projects/435347747480/locations/asia-southeast1/services/okf-engineering-workbench"

    # Generate ephemeral ES256 (P-256) keypair and construct RFC 7517 JWK Set
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(pyjwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "test-iap-kid-1"
    public_jwk["alg"] = "ES256"
    public_jwk["use"] = "sig"
    jwks_payload = {"keys": [public_jwk]}

    now = int(time.time())
    valid_token = pyjwt.encode(
        {
            "iss": IAP_ISSUER,
            "aud": expected_aud,
            "email": "admin@pantana.altostrat.com",
            "sub": "accounts.google.com:987654321",
            "iat": now,
            "exp": now + 600,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "test-iap-kid-1"},
    )

    principal = verify_iap_jwt_assertion(
        valid_token,
        jwks_provider=lambda force_refresh=False: jwks_payload,
    )
    assert principal.email == "admin@pantana.altostrat.com"
    assert principal.subject == "accounts.google.com:987654321"
    assert principal.auth_mode == "iap_jwt"

    # Wrong audience must be rejected (cross-service replay protection)
    wrong_aud_token = pyjwt.encode(
        {
            "iss": IAP_ISSUER,
            "aud": "/projects/435347747480/locations/asia-southeast1/services/other-service",
            "email": "admin@pantana.altostrat.com",
            "sub": "accounts.google.com:987654321",
            "iat": now,
            "exp": now + 600,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "test-iap-kid-1"},
    )
    with pytest.raises(HTTPException) as exc_aud:
        verify_iap_jwt_assertion(
            wrong_aud_token,
            jwks_provider=lambda force_refresh=False: jwks_payload,
        )
    assert exc_aud.value.status_code == 401

    # Expired token must be rejected
    expired_token = pyjwt.encode(
        {
            "iss": IAP_ISSUER,
            "aud": expected_aud,
            "email": "admin@pantana.altostrat.com",
            "sub": "accounts.google.com:987654321",
            "iat": now - 1200,
            "exp": now - 600,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "test-iap-kid-1"},
    )
    with pytest.raises(HTTPException) as exc_exp:
        verify_iap_jwt_assertion(
            expired_token,
            jwks_provider=lambda force_refresh=False: jwks_payload,
        )
    assert exc_exp.value.status_code == 401

    # Wrong signing key must be rejected
    other_key = ec.generate_private_key(ec.SECP256R1())
    forged_token = pyjwt.encode(
        {
            "iss": IAP_ISSUER,
            "aud": expected_aud,
            "email": "attacker@evil.example",
            "sub": "accounts.google.com:000",
            "iat": now,
            "exp": now + 600,
        },
        other_key,
        algorithm="ES256",
        headers={"kid": "test-iap-kid-1"},
    )
    with pytest.raises(HTTPException) as exc_sig:
        verify_iap_jwt_assertion(
            forged_token,
            jwks_provider=lambda force_refresh=False: jwks_payload,
        )
    assert exc_sig.value.status_code == 401


def test_sliding_window_rate_limiter() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    limiter.check("user@example.com")
    limiter.check("user@example.com")
    with pytest.raises(HTTPException) as exc_rl:
        limiter.check("user@example.com")
    assert exc_rl.value.status_code == 429


def test_spanner_ddl_v2_native_embedding_and_indexes() -> None:
    schema_sql = (REPO_ROOT / "query_agent" / "spanner" / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE VECTOR INDEX IF NOT EXISTS idx_okf_chunks_vec" in schema_sql
    assert "WHERE embedding IS NOT NULL" in schema_sql
    assert "distance_type = 'COSINE'" in schema_sql
    assert "idx_process_conn_from" in schema_sql
    assert "idx_inst_ctrl_source_concept" in schema_sql

    repo = SpannerGraphRepository(
        project_id="engineering-kg-demo",
        instance_id="okf-knowledge-spanner",
        database_id="okf_knowledge_graph",
        use_in_memory=True,
    )
    model_ddl = repo.build_native_embedding_model_ddl()
    assert "CREATE OR REPLACE MODEL OkfTextEmbeddingModel" in model_ddl
    assert "//aiplatform.googleapis.com/projects/engineering-kg-demo/" in model_ddl
    assert "text-embedding-005" in model_ddl

    res = repo.ensure_schema_v2()
    assert res["status"] == "DRY_RUN_IN_MEMORY"
    assert res["ddl_count"] == 11


def test_hybrid_rrf_search_uses_json_options_and_isolated_snapshots_on_ann_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test (Rule 13 RCA #11): verify JSON OPTIONS syntax and isolated snapshots preventing poisoned transaction-begin timeouts."""
    repo = SpannerGraphRepository(
        project_id="engineering-kg-demo",
        instance_id="okf-knowledge-spanner",
        database_id="okf_knowledge_graph",
        use_in_memory=False,
    )
    repo.native_embedding_mode = "native_ml_predict"
    monkeypatch.setattr(repo, "embed_query", lambda q: [0.1] * 768)

    snapshot_instances: list[int] = []
    executed_sqls: list[str] = []

    class _FakeSnapshot:
        def __init__(self, snap_id: int) -> None:
            self.snap_id = snap_id
            self.poisoned = False

        def __enter__(self) -> "_FakeSnapshot":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def execute_sql(self, sql: str, params: Any = None, param_types: Any = None) -> list[tuple[Any, ...]]:
            if self.poisoned:
                raise ValueError("Timed out waiting for transaction to begin.")
            executed_sqls.append(sql)
            if "APPROX_COSINE_DISTANCE" in sql:
                self.poisoned = True
                raise RuntimeError("400 ANN index building")
            if "COSINE_DISTANCE" in sql:
                return [
                    ("chunk-1", "equipment/S-2B", "Tank S-2B", "equipment", "U1", "Design", "MAWP 10 barg", False, 0.12)
                ]
            if "SEARCH(s.ChunkTokens" in sql:
                return [
                    ("chunk-1", "equipment/S-2B", "Tank S-2B", "equipment", "U1", "Design", "MAWP 10 barg", False, 4.5)
                ]
            return []

    class _FakeDatabase:
        def snapshot(self, multi_use: bool = False) -> _FakeSnapshot:
            assert multi_use is False, "Each hybrid_rrf_search stage must open an isolated fresh snapshot"
            sid = len(snapshot_instances) + 1
            snapshot_instances.append(sid)
            return _FakeSnapshot(sid)

    monkeypatch.setattr(repo, "_get_database", lambda: _FakeDatabase())

    hits = repo.hybrid_rrf_search("S-2B conflict lineage", top_k=5)
    assert len(hits) == 1
    assert hits[0].concept_id == "equipment/S-2B"
    assert repo.last_vector_search_mode == "EXACT_COSINE_FALLBACK"
    assert len(snapshot_instances) == 3  # 1: ANN attempt, 2: exact COSINE fallback, 3: FTS SEARCH
    assert "OPTIONS => JSON '{\"num_leaves_to_search\": 50}'" in executed_sqls[0]
    assert "FORCE_INDEX=idx_okf_chunks_vec" in executed_sqls[0]


def test_spanner_lazy_hierarchy_summary_and_paginated_items() -> None:
    repo = SpannerGraphRepository(use_in_memory=True)
    for i in range(1, 26):
        cid = f"equipment/P-{2300 + i}"
        repo._mem_concepts[cid] = OkfConceptNode(
            concept_id=cid,
            category="equipment",
            name=f"Pump P-{2300 + i}",
            description=f"Process pump service {i}",
            unit="Unit 23",
            has_conflict=(i % 5 == 0),
            conflict_count=(1 if i % 5 == 0 else 0),
            body_markdown="# Pump",
            md5_hash=f"hash{i}",
        )
    repo._mem_concepts["hazards/h2s"] = OkfConceptNode(
        concept_id="hazards/h2s",
        category="hazards",
        name="Hydrogen Sulfide Hazard",
        description="Toxic gas exposure hazard",
        unit="Unit 23",
        has_conflict=False,
        conflict_count=0,
        body_markdown="# H2S",
        md5_hash="hash_h2s",
    )

    summary = repo.get_equipment_hierarchy_summary()
    assert summary["total_concepts"] == 26
    assert summary["total_equipment"] == 25
    assert summary["total_conflicts"] == 5
    # Summary must NOT embed full item lists
    for u in summary["units"]:
        for cls in u["classes"]:
            assert "items" not in cls

    page1 = repo.get_equipment_hierarchy_items(category="equipment", limit=10, offset=0)
    page2 = repo.get_equipment_hierarchy_items(category="equipment", limit=10, offset=10)
    page3 = repo.get_equipment_hierarchy_items(category="equipment", limit=10, offset=20)
    assert page1["total"] == 25
    assert page1["has_more"] is True
    assert len(page1["items"]) == 10
    assert len(page2["items"]) == 10
    assert len(page3["items"]) == 5
    assert page3["has_more"] is False

    # Search & conflicts_only filters
    search_res = repo.get_equipment_hierarchy_items(q="sulfide")
    assert search_res["total"] == 1
    assert search_res["items"][0]["concept_id"] == "hazards/h2s"

    conf_res = repo.get_equipment_hierarchy_items(conflicts_only=True)
    assert conf_res["total"] == 5


def test_openlineage_run_ids_are_dynamic_uuids(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted_ids: list[str] = []

    class FakeLineageClient:
        def process_open_lineage_run_event(self, request: dict[str, Any]) -> None:
            emitted_ids.append(request["open_lineage"]["run"]["runId"])

    import google.cloud.datacatalog_lineage_v1 as lineage_mod

    monkeypatch.setattr(lineage_mod, "LineageClient", FakeLineageClient)
    syncer = DataplexCatalogAndLineageSync(project_id="engineering-kg-demo")
    assert syncer._emit_openlineage_events() == 2
    assert syncer._emit_openlineage_events() == 2
    assert len(emitted_ids) == 4
    assert len(set(emitted_ids)) == 4
    for rid in emitted_ids:
        uuid.UUID(rid)


# ==============================================================================
# Generative Property-Based Tests (Hypothesis)
# ==============================================================================


@settings(max_examples=40)
@given(raw_model=st.text(min_size=1, max_size=40).filter(lambda s: s.strip() and s.strip() not in ALLOWED_GEMINI_MODELS))
def test_pbt_unlisted_models_always_rejected(raw_model: str) -> None:
    with pytest.raises(ValueError):
        validate_gemini_model(raw_model, default=DEFAULT_QUERY_MODEL)


@settings(max_examples=40)
@given(
    confirm_hdr=st.text(max_size=30).filter(lambda s: s.strip() != PURGE_CONFIRM_VALUE),
    idem_key=st.text(max_size=30),
)
def test_pbt_purge_without_exact_hitl_confirmation_always_rejected(
    confirm_hdr: str,
    idem_key: str,
) -> None:
    with pytest.raises(HTTPException) as exc:
        enforce_purge_hitl_gate(purge=True, confirm_header=confirm_hdr, idempotency_key=idem_key)
    assert exc.value.status_code == 400


@settings(max_examples=30)
@given(
    n_items=st.integers(min_value=0, max_value=45),
    page_size=st.integers(min_value=1, max_value=15),
)
def test_pbt_hierarchy_pagination_partitions_items_without_duplicates(
    n_items: int,
    page_size: int,
) -> None:
    repo = SpannerGraphRepository(use_in_memory=True)
    for i in range(n_items):
        cid = f"equipment/V-{1000 + i}"
        repo._mem_concepts[cid] = OkfConceptNode(
            concept_id=cid,
            category="equipment",
            name=f"Vessel V-{1000 + i}",
            unit="Unit 10",
            body_markdown="# Vessel",
            md5_hash=f"h{i}",
        )

    collected: list[str] = []
    offset = 0
    while True:
        page = repo.get_equipment_hierarchy_items(limit=page_size, offset=offset)
        assert page["total"] == n_items
        collected.extend(item["concept_id"] for item in page["items"])
        if not page["has_more"]:
            break
        offset += page_size

    assert len(collected) == n_items
    assert len(set(collected)) == n_items
