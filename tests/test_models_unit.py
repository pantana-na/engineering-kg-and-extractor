"""Unit tests for core models and configuration."""

import pytest
from pydantic import ValidationError

from extracter_agent.config import get_config
from extracter_agent.models.intent import IntentCategory, IntentClassificationResult
from extracter_agent.models.okf import (
    OKFConceptStatus,
    OKFFrontmatter,
    derive_trust_tier,
)


def test_okf_frontmatter_requires_type():
    """OKF v0.2 §11: type is strictly required."""
    with pytest.raises(ValidationError):
        OKFFrontmatter()  # missing type

    fm = OKFFrontmatter(type="Equipment Concept", title="V-2301")
    assert fm.type == "Equipment Concept"
    assert fm.title == "V-2301"
    assert fm.status == OKFConceptStatus.STABLE


def test_verified_normalization():
    """OKF v0.2 §5.2: bare mapping or list of mappings are both accepted."""
    # Bare mapping
    fm1 = OKFFrontmatter(
        type="Hazard",
        verified={"by": "human:expert", "at": "2026-06-16T00:00:00Z"},
    )
    assert len(fm1.verified) == 1
    assert fm1.verified[0].by == "human:expert"

    # List of mappings
    fm2 = OKFFrontmatter(
        type="Hazard",
        verified=[
            {"by": "process:validator", "at": "2026-06-16T00:00:00Z"},
            {"by": "human:senior_eng", "at": "2026-06-17T00:00:00Z"},
        ],
    )
    assert len(fm2.verified) == 2


def test_trust_tier_derivation():
    """OKF v0.2 §5.3: trust tier classification logic."""
    # Unverified
    assert derive_trust_tier(OKFFrontmatter(type="Concept")) == "unverified"

    # Machine-confirmed
    fm_machine = OKFFrontmatter(
        type="Concept",
        verified=[{"by": "process:ci-cd", "at": "2026-06-16T00:00:00Z"}],
    )
    assert derive_trust_tier(fm_machine) == "machine-confirmed"

    # Human-reviewed
    fm_human = OKFFrontmatter(
        type="Concept",
        verified=[
            {"by": "process:ci-cd", "at": "2026-06-16T00:00:00Z"},
            {"by": "human:john_doe", "at": "2026-06-17T00:00:00Z"},
        ],
    )
    assert derive_trust_tier(fm_human) == "human-reviewed"


def test_intent_classification_result_validation():
    """Intent classification result model validation."""
    res = IntentClassificationResult(
        intent=IntentCategory.EXTRACT_DOCUMENT,
        confidence=0.98,
        reasoning="User requested PDF extraction of V-2301 data sheet",
        target_entities=["V-2301"],
        raw_sources=["reference/raw/data_sheets/PS-V2301.pdf"],
    )
    assert res.intent == IntentCategory.EXTRACT_DOCUMENT
    assert res.confidence == 0.98
    assert len(res.target_entities) == 1


def test_app_config_defaults(monkeypatch):
    """Test application config defaults when environment overrides are unset."""
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GIT_REPO_URL", raising=False)
    monkeypatch.delenv("DEPLOYMENT_TARGET", raising=False)
    cfg = get_config()
    assert cfg.google_cloud_project == "your-gcp-project-id"
    assert cfg.git_repo_url == "https://github.com/pantana-na/engineering-kg-and-extractor.git"
    assert cfg.deployment_target == "agent_runtime"

