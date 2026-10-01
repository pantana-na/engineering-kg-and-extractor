"""Property-Based Tests (PBT) for ADK agent guardrails using Hypothesis."""

from hypothesis import given
from hypothesis import strategies as st

from extracter_agent.agent.guardrails import check_prompt_security

prohibited_tokens = [
    "ignore previous instructions",
    "disregard all previous instructions",
    "system prompt override",
    "bypass security",
    "delete all files",
    "rm -rf /",
]

safe_chars = st.characters(whitelist_categories=("L", "N", "Z"))


@given(
    prefix=st.text(alphabet=safe_chars, max_size=50),
    bad_token=st.sampled_from(prohibited_tokens),
    suffix=st.text(alphabet=safe_chars, max_size=50),
)
def test_pbt_guardrail_injection_detection_invariant(prefix, bad_token, suffix):
    """Invariant: Any prompt containing a prohibited token is strictly intercepted."""
    prompt = f"{prefix} {bad_token} {suffix}"
    check = check_prompt_security(prompt)
    assert check["filterMatchState"] == "MATCH_FOUND"
    assert check["violation_type"] == "PROMPT_INJECTION"


@given(benign_prompt=st.text(alphabet=safe_chars, min_size=1, max_size=100))
def test_pbt_guardrail_benign_clean_invariant(benign_prompt):
    """Invariant: Clean alphanumeric prompts never trigger false-positive blocks."""
    # Only evaluate if none of the prohibited strings accidentally appear
    if not any(token in benign_prompt.lower() for token in prohibited_tokens):
        check = check_prompt_security(benign_prompt)
        assert check["filterMatchState"] == "NO_MATCH"
        assert check["violation_type"] is None


@given(
    field=st.sampled_from([
        "parameter",
        "value",
        "unit",
        "source",
        "stream_id",
        "temperature",
        "pressure",
        "flow_rate",
        "description",
        "tag",
        "service",
        "instrument_type",
        "location",
        "setpoint_or_range",
        "interlock_or_alarm",
        "function_summary",
        "hazards",
        "source_files",
    ])
)
def test_pbt_orchestrator_prompt_schema_coverage_invariant(field):
    """Invariant: 100% of required entity schema attributes are documented in the orchestrator instructions."""
    from extracter_agent.agent.orchestrator import ORCHESTRATOR_INSTRUCTIONS

    assert field in ORCHESTRATOR_INSTRUCTIONS


@given(query=st.text(alphabet=safe_chars, min_size=1, max_size=30))
def test_pbt_search_raw_documents_invariants(query):
    """Invariant: Searching raw documents is exception-safe and all returned paths exist."""
    from extracter_agent.config import get_config
    from extracter_agent.pdf.processor import search_raw_documents

    cfg = get_config()
    results = search_raw_documents(query=query, raw_dir=cfg.reference_raw_dir)
    assert isinstance(results, list)
    for res in results:
        assert "file_name" in res
        assert "subfolder" in res
        full_path = cfg.reference_raw_dir / res["subfolder"] / res["file_name"]
        assert full_path.exists()


@given(
    infra_region=st.sampled_from(["asia-southeast1", "us-central1", "europe-west1", "asia-east1"]),
    gemini_loc=st.sampled_from(["global", "us-central1"]),
)
def test_pbt_gemini_location_decoupled_from_infra_region(infra_region, gemini_loc):
    """Invariant: Gemini model endpoint location is strictly governed by GEMINI_LOCATION, independent of GOOGLE_CLOUD_LOCATION."""
    import os
    from unittest.mock import patch

    from extracter_agent.agent.orchestrator import create_extracter_agent
    from extracter_agent.config import get_config

    with patch.dict(
        os.environ,
        {
            "GOOGLE_CLOUD_LOCATION": infra_region,
            "GEMINI_LOCATION": gemini_loc,
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
        },
        clear=False,
    ):
        cfg = get_config()
        assert cfg.google_cloud_location == infra_region
        assert cfg.gemini_location == gemini_loc
        agent = create_extracter_agent()
        assert agent.model.client_kwargs == {"location": gemini_loc}


