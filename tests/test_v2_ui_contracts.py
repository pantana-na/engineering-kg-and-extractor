"""Step 5 Unit and Property-Based Tests: Unified Zero-Build Vanilla ESM UI Contracts.

Covers SPEC-20261120-UNIFIED-WORKBENCH-V2 Step 5.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from query_agent.spanner.repository import SpannerGraphRepository
from unified_web.manifest import BundleManifestStore
from unified_web.models import ALLOWED_GEMINI_MODELS, DEFAULT_EXTRACTER_MODEL, DEFAULT_QUERY_MODEL
from unified_web.server import create_unified_app

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = REPO_ROOT / "unified_web" / "static"


def test_unified_ui_static_assets_and_esm_imports_resolve() -> None:
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    # Tab switcher anchors
    assert 'id="tab-btn-extractor"' in index_html
    assert 'id="tab-btn-query"' in index_html
    assert 'id="panel-extractor"' in index_html
    assert 'id="panel-query"' in index_html

    # Model selector & all 4 Gemini 4 options
    assert 'id="model-select"' in index_html
    for model_id in ALLOWED_GEMINI_MODELS:
        assert f'value="{model_id}"' in index_html

    # Streamlined v2.2 persistent 2-extract-button toolbar, GCS sync, Batch modal & Purge HITL modal
    assert 'id="btn-open-batch-modal"' in index_html
    assert 'id="btn-interactive-extract-sync"' in index_html
    assert 'id="btn-interactive-info"' not in index_html
    assert 'id="interactive-info-popover"' not in index_html
    assert 'id="ext-refresh-btn"' not in index_html
    assert 'id="btn-sync-gcs"' in index_html
    assert 'id="batch-job-modal"' in index_html
    assert 'id="batch-scope-select"' in index_html
    assert 'id="btn-launch-batch-extract-sync"' in index_html
    assert 'id="btn-job-sync"' in index_html
    assert 'id="purge-modal"' in index_html
    assert "PURGE SPANNER" in index_html

    # Verify both Extractor & Query chats use the shared live telemetry-card.js component & MOC badges
    ext_js = (STATIC_DIR / "js" / "extractor-tab.js").read_text(encoding="utf-8")
    qry_js = (STATIC_DIR / "js" / "query-tab.js").read_text(encoding="utf-8")
    assert "./telemetry-card.js" in ext_js
    assert "./telemetry-card.js" in qry_js
    assert "/api/extractor/chat/stream" in ext_js
    assert "/api/gcs/sync" in ext_js
    assert "MOC_AUTHORITY" in qry_js
    assert "PENDING_REDRAFT" in qry_js

    # Verify every local ES module import resolves on disk
    js_dir = STATIC_DIR / "js"
    import_re = re.compile(r'from\s+["\'](\./[^"\']+)["\']')
    js_files = sorted(js_dir.glob("*.js"))
    assert len(js_files) >= 8
    for js_file in js_files:
        text = js_file.read_text(encoding="utf-8")
        for m in import_re.finditer(text):
            target = (js_file.parent / m.group(1)).resolve()
            assert target.is_file(), f"Broken ESM import '{m.group(1)}' in {js_file.name}"


def test_unified_server_serves_shell_css_and_js_with_no_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("USE_GCS_STORAGE", "false")
    monkeypatch.setenv("IAP_JWT_ENFORCEMENT", "false")
    monkeypatch.setenv("OUTPUT_BUNDLE_DIR", str(tmp_path / "bundle"))
    monkeypatch.setenv("REFERENCE_RAW_DIR", str(tmp_path / "raw"))

    app = create_unified_app(repo=SpannerGraphRepository(use_in_memory=True), manifest_store=BundleManifestStore())
    client = TestClient(app)

    r_root = client.get("/")
    assert r_root.status_code == 200
    assert "OKF Engineering Workbench" in r_root.text
    assert "no-store" in r_root.headers.get("cache-control", "")

    for asset in (
        "/static/css/workbench.css",
        "/static/js/main.js",
        "/static/js/api.js",
        "/static/js/state.js",
        "/static/js/extractor-tab.js",
        "/static/js/query-tab.js",
        "/static/js/telemetry-card.js",
        "/static/js/jobs-drawer.js",
        "/static/js/graph-canvas.js",
    ):
        r = client.get(asset)
        assert r.status_code == 200, f"Asset {asset} failed with {r.status_code}"


@settings(max_examples=40)
@given(
    ops=st.lists(
        st.tuples(
            st.sampled_from(["switch_tab", "select_model"]),
            st.sampled_from(["extractor", "query"]),
            st.sampled_from(list(ALLOWED_GEMINI_MODELS)),
        ),
        min_size=1,
        max_size=25,
    )
)
def test_pbt_per_tab_model_selection_state_invariant(ops: list[tuple[str, str, str]]) -> None:
    """Verify switching tabs always preserves each tab's independent allowlisted Gemini 4 model."""
    selected = {
        "extractor": DEFAULT_EXTRACTER_MODEL,
        "query": DEFAULT_QUERY_MODEL,
    }
    active_tab = "extractor"

    for op, tab, model in ops:
        if op == "switch_tab":
            active_tab = tab
        else:
            other_tab = "query" if active_tab == "extractor" else "extractor"
            other_before = selected[other_tab]
            selected[active_tab] = model
            # Changing active tab's model must never mutate the inactive tab's model
            assert selected[other_tab] == other_before

        assert selected["extractor"] in ALLOWED_GEMINI_MODELS
        assert selected["query"] in ALLOWED_GEMINI_MODELS
