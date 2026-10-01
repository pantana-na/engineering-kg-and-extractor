"""Property-Based Tests (PBT) for core models using Hypothesis.

Verifies mathematical invariants across generated fuzzed input spaces.
"""

from hypothesis import given
from hypothesis import strategies as st

from extracter_agent.models.intent import IntentCategory
from extracter_agent.models.okf import OKFActor, OKFFrontmatter, derive_trust_tier


@given(
    type_name=st.text(min_size=1).filter(lambda s: bool(s.strip())),
    title=st.one_of(st.none(), st.text(max_size=100)),
    tag_list=st.lists(st.text(min_size=1, max_size=30), max_size=10),
)
def test_pbt_okf_frontmatter_invariants(type_name, title, tag_list):
    """Invariant: Any valid non-empty type produces a valid OKFFrontmatter."""
    fm = OKFFrontmatter(type=type_name, title=title, tags=tag_list)
    assert fm.type == type_name
    assert fm.tags == tag_list
    # Serialization round-trip invariant
    data = fm.model_dump()
    reconstructed = OKFFrontmatter(**data)
    assert reconstructed.type == fm.type
    assert reconstructed.tags == fm.tags


@given(
    machine_actors=st.lists(
        st.text(min_size=1, max_size=20).map(lambda s: f"process:{s}"),
        max_size=5,
    ),
    human_name=st.text(min_size=1, max_size=20),
    include_human=st.booleans(),
)
def test_pbt_trust_tier_invariants(machine_actors, human_name, include_human):
    """Invariant: If ANY verifier starts with human:, tier is human-reviewed.

    If no human: verifier exists and there are machine verifiers, tier is
    machine-confirmed.
    If empty, tier is unverified.
    """
    verified_list = [OKFActor(by=m, at="2026-06-16T00:00:00Z") for m in machine_actors]
    if include_human:
        verified_list.append(
            OKFActor(by=f"human:{human_name}", at="2026-06-16T00:00:00Z")
        )

    fm = OKFFrontmatter(type="TestConcept", verified=verified_list)
    tier = derive_trust_tier(fm)

    if include_human:
        assert tier == "human-reviewed"
    elif machine_actors:
        assert tier == "machine-confirmed"
    else:
        assert tier == "unverified"


@given(raw_text=st.text())
def test_pbt_intent_enum_membership(raw_text):
    """Invariant: Only strings matching declared IntentCategory are members."""
    valid_values = {c.value for c in IntentCategory}
    if raw_text in valid_values:
        assert IntentCategory(raw_text).value == raw_text
    else:
        try:
            IntentCategory(raw_text)
            assert False, f"Unexpectedly accepted invalid intent: {raw_text}"
        except ValueError:
            pass
