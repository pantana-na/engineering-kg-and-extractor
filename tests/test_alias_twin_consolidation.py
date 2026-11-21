"""Deterministic unit tests and Hypothesis Property-Based Tests for Step 3 (P1-B):
Data-driven alias twin resolution, unit-slug coalescing, and corpus-wide link rewriting.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from extracter_agent.okf.document import OKFDocument
from extracter_agent.okf.indexer import consolidate_alias_twins, generate_bundle_indexes
from extracter_agent.tools.okf_tools import (
    generate_equipment_okf_tool,
    generate_okf_concept_tool,
)


def _assert_zero_broken_links(bundle_dir: Path) -> None:
    broken: list[tuple[str, str]] = []
    for md in sorted(bundle_dir.rglob("*.md")):
        txt = md.read_text(encoding="utf-8")
        for m in re.finditer(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)", txt):
            lnk = m.group(1)
            if lnk.startswith(("http://", "https://", "gs://", "mailto:")):
                continue
            t1 = (md.parent / lnk).resolve()
            t2 = (bundle_dir / lnk.lstrip("/")).resolve()
            if not (
                t1.exists()
                or t1.with_suffix(".md").exists()
                or t2.exists()
                or t2.with_suffix(".md").exists()
            ):
                broken.append((md.relative_to(bundle_dir).as_posix(), lnk))
    assert not broken, f"Broken internal Markdown links: {broken}"


def test_write_time_bidirectional_equipment_alias_coalescing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify both prose-first->tag-second and tag-first->prose-second equipment coalescing."""
    monkeypatch.setenv("USE_GCS_STORAGE", "false")

    # --- Order A: Prose service name extracted FIRST, Canonical ISA tag extracted SECOND ---
    bundle_a = tmp_path / "bundle_prose_first"
    res_p1 = generate_equipment_okf_tool(
        tag="Overhead Splitter",
        name="Overhead Splitter",
        equipment_class="Column",
        unit="Unit 10",
        function_summary="Separates light overhead vapors from feed mixture.",
        design_data=[],
        operating_conditions=[
            {"parameter": "Top Temperature", "value": "92", "unit": "degC", "source": "OM-10.pdf"}
        ],
        connections=[],
        hazards=["Prevent rapid depressurization during startup."],
        source_files=["operating_manuals/OM-10.pdf"],
        output_bundle_dir=str(bundle_a),
    )
    assert res_p1["status"] == "success"
    assert (bundle_a / "equipment" / "Overhead_Splitter.md").exists()

    # Cross-file Markdown link pointing to the prose concept before the datasheet arrives
    (bundle_a / "hazop").mkdir(parents=True, exist_ok=True)
    hazop_file = bundle_a / "hazop" / "node-01.md"
    hazop_file.write_text(
        "---\ntype: HAZOP Node\ntitle: Node 1\ndescription: Splitter study.\n---\n\n"
        "## Deviations\n"
        "- High pressure in [Overhead Splitter](/equipment/Overhead_Splitter.md#operating-conditions) "
        "and [[equipment/Overhead_Splitter]].\n",
        encoding="utf-8",
    )

    # Datasheet arrives later with canonical ISA tag C-101
    res_p2 = generate_equipment_okf_tool(
        tag="C-101",
        name="Overhead Splitter",
        equipment_class="Distillation Column",
        unit="10",
        function_summary="Primary fractionation column in Unit 10.",
        design_data=[
            {"parameter": "Design Pressure", "value": "12.5", "unit": "barg", "source": "DS-C101.pdf"}
        ],
        operating_conditions=[],
        connections=[],
        hazards=[],
        source_files=["data_sheets/DS-C101.pdf"],
        output_bundle_dir=str(bundle_a),
    )
    assert res_p2["status"] == "success"
    assert res_p2["merged_with_existing"] is True
    assert not (bundle_a / "equipment" / "Overhead_Splitter.md").exists()
    c101_path = bundle_a / "equipment" / "C-101.md"
    assert c101_path.exists()

    c101_doc = OKFDocument.parse(c101_path.read_text(encoding="utf-8"))
    assert c101_doc.frontmatter["entity_metadata"]["tag"] == "C-101"
    assert "Overhead Splitter" in c101_doc.frontmatter["entity_metadata"]["aliases"]
    assert "12.5" in c101_doc.body
    assert "92" in c101_doc.body
    assert "Prevent rapid depressurization" in c101_doc.body

    hazop_text = hazop_file.read_text(encoding="utf-8")
    assert "/equipment/C-101.md#operating-conditions" in hazop_text
    assert "[[equipment/C-101]]" in hazop_text
    _assert_zero_broken_links(bundle_a)

    # --- Order B: Canonical ISA tag extracted FIRST, plural prose service name extracted SECOND ---
    bundle_b = tmp_path / "bundle_tag_first"
    generate_equipment_okf_tool(
        tag="SR-10-0001",
        name="Adiabatic Calorimeter",
        equipment_class="Analyzer",
        unit="10",
        function_summary="Bench-scale thermal runaway screening instrument.",
        design_data=[
            {"parameter": "Max Cell Pressure", "value": "150", "unit": "barg", "source": "DS-SR10.pdf"}
        ],
        operating_conditions=[],
        connections=[],
        hazards=[],
        source_files=["data_sheets/DS-SR10.pdf"],
        output_bundle_dir=str(bundle_b),
    )
    res_b2 = generate_equipment_okf_tool(
        tag="Adiabatic Calorimeters",
        name="Adiabatic Calorimeters",
        equipment_class="Equipment",
        unit="Unit 1000",
        function_summary="Used to determine onset temperature prior to batch charging.",
        design_data=[],
        operating_conditions=[
            {"parameter": "Scan Rate", "value": "0.02", "unit": "degC/min", "source": "STD-PHA.pdf"}
        ],
        connections=[],
        hazards=["Calibrate pressure transducer before each test."],
        source_files=["standards/STD-PHA.pdf"],
        output_bundle_dir=str(bundle_b),
    )
    assert res_b2["status"] == "success"
    assert res_b2["merged_with_existing"] is True
    assert not (bundle_b / "equipment" / "Adiabatic_Calorimeters.md").exists()
    sr_doc = OKFDocument.parse((bundle_b / "equipment" / "SR-10-0001.md").read_text(encoding="utf-8"))
    assert sr_doc.frontmatter["entity_metadata"]["tag"] == "SR-10-0001"
    assert "Adiabatic Calorimeters" in sr_doc.frontmatter["entity_metadata"]["aliases"]
    assert "150" in sr_doc.body
    assert "0.02" in sr_doc.body
    _assert_zero_broken_links(bundle_b)


def test_ambiguous_generic_name_and_conflicting_units_never_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify strict safety guards: ambiguous multi-tag names and conflicting numeric units never merge."""
    monkeypatch.setenv("USE_GCS_STORAGE", "false")
    bundle = tmp_path / "bundle_guards"

    # Two distinct canonical ISA tags sharing the same generic service name "Sample Receiver"
    for eq_tag in ("V-101", "V-102"):
        generate_equipment_okf_tool(
            tag=eq_tag,
            name="Sample Receiver",
            equipment_class="Vessel",
            unit="10",
            function_summary=f"Dedicated sample pot {eq_tag}.",
            design_data=[{"parameter": "Volume", "value": "50", "unit": "L", "source": f"DS-{eq_tag}.pdf"}],
            operating_conditions=[],
            connections=[],
            hazards=[],
            source_files=[f"data_sheets/DS-{eq_tag}.pdf"],
            output_bundle_dir=str(bundle),
        )

    # Prose "Sample Receiver" must NOT arbitrarily merge into V-101 or V-102
    generate_equipment_okf_tool(
        tag="Sample Receiver",
        name="Sample Receiver",
        equipment_class="Vessel",
        unit="10",
        function_summary="Generic sample receiver handling note.",
        design_data=[],
        operating_conditions=[],
        connections=[],
        hazards=["Purge with inert gas before opening."],
        source_files=["operating_manuals/OM-SAMPLING.pdf"],
        output_bundle_dir=str(bundle),
    )
    assert (bundle / "equipment" / "V-101.md").exists()
    assert (bundle / "equipment" / "V-102.md").exists()
    assert (bundle / "equipment" / "Sample_Receiver.md").exists()

    # Conflicting unit numbers: E-105 in Unit 10 vs prose "Feed Preheater" in Unit 20
    generate_equipment_okf_tool(
        tag="E-105",
        name="Feed Preheater",
        equipment_class="Heat Exchanger",
        unit="10",
        function_summary="Unit 10 shell-and-tube preheater.",
        design_data=[],
        operating_conditions=[],
        connections=[],
        hazards=[],
        source_files=["data_sheets/DS-E105.pdf"],
        output_bundle_dir=str(bundle),
    )
    generate_equipment_okf_tool(
        tag="Feed Preheater",
        name="Feed Preheater",
        equipment_class="Heat Exchanger",
        unit="20",
        function_summary="Unit 20 preheater.",
        design_data=[],
        operating_conditions=[],
        connections=[],
        hazards=[],
        source_files=["operating_manuals/OM-20.pdf"],
        output_bundle_dir=str(bundle),
    )
    assert (bundle / "equipment" / "E-105.md").exists()
    assert (bundle / "equipment" / "Feed_Preheater.md").exists()

    # Batch consolidate_alias_twins must also keep both ambiguous and unit-conflicting files untouched
    rewrites = consolidate_alias_twins(bundle)
    assert rewrites == {}
    assert (bundle / "equipment" / "Sample_Receiver.md").exists()
    assert (bundle / "equipment" / "Feed_Preheater.md").exists()


def test_unit_domain_slug_coalescing_and_protected_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify live and batch coalescing of `units/*` twins plus `protected_paths` Golden Parity locks."""
    monkeypatch.setenv("USE_GCS_STORAGE", "false")

    # 1. Live write-time coalescing via generate_okf_concept_tool
    bundle_live = tmp_path / "bundle_units_live"
    generate_okf_concept_tool(
        concept_id="units/reaction-section",
        concept_type="Process Unit",
        title="Reaction Section",
        description="Core catalytic reaction section.",
        tags=["unit", "reaction"],
        sources=["pfd/PFD-1000.pdf"],
        body_markdown="## Process Overview\n\nPrimary exothermic reactor train.\n",
        output_bundle_dir=str(bundle_live),
    )
    res_u2 = generate_okf_concept_tool(
        concept_id="units/unit-1000-reaction-section",
        concept_type="Process Unit",
        title="Unit 1000 Reaction Section",
        description="Detailed operating boundaries.",
        tags=["unit-1000"],
        sources=["operating_manuals/OM-1000.pdf"],
        body_markdown="## Safety Interlocks\n\n- High temperature trip TAHH-1001.\n",
        output_bundle_dir=str(bundle_live),
    )
    assert res_u2["merged_with_existing"] is True
    assert res_u2["concept_id"] == "units/reaction-section"
    assert not (bundle_live / "units" / "unit-1000-reaction-section.md").exists()
    merged_text = (bundle_live / "units" / "reaction-section.md").read_text(encoding="utf-8")
    assert "Primary exothermic reactor train." in merged_text
    assert "TAHH-1001" in merged_text

    # Distinct unit number (Unit 2000 vs Unit 1000) when Unit 1000 is recorded in entity_metadata
    bundle_multi = tmp_path / "bundle_units_multi"
    generate_okf_concept_tool(
        concept_id="units/unit-1000-purification-section",
        concept_type="Process Unit",
        title="Unit 1000 Purification",
        description="Unit 1000 purification train.",
        tags=["unit-1000"],
        sources=["pfd/PFD-1000.pdf"],
        body_markdown="## Overview\n\nUnit 1000 train.\n",
        entity_metadata={"unit": "1000"},
        output_bundle_dir=str(bundle_multi),
    )
    generate_okf_concept_tool(
        concept_id="units/unit-2000-purification-section",
        concept_type="Process Unit",
        title="Unit 2000 Purification",
        description="Unit 2000 purification train.",
        tags=["unit-2000"],
        sources=["pfd/PFD-2000.pdf"],
        body_markdown="## Overview\n\nUnit 2000 train.\n",
        entity_metadata={"unit": "2000"},
        output_bundle_dir=str(bundle_multi),
    )
    assert (bundle_multi / "units" / "unit-1000-purification-section.md").exists()
    assert (bundle_multi / "units" / "unit-2000-purification-section.md").exists()

    # 2. Batch consolidate_alias_twins with protected_paths lock
    bundle_prot = tmp_path / "bundle_protected"
    (bundle_prot / "units").mkdir(parents=True)
    for fname, title, src, sec_body in (
        ("alpha-unit.md", "Alpha Unit", "pfd/PFD-A.pdf", "## Overview\n\nBase alpha unit.\n"),
        ("unit-3000-alpha.md", "Unit 3000 Alpha", "pfd/PFD-3000.pdf", "## Equipment\n\nMain column.\n"),
        ("unit-3000-alpha-section.md", "Unit 3000 Alpha Section", "om/OM-3000.pdf", "## Trips\n\nTrip Z-3001.\n"),
    ):
        doc = OKFDocument(
            frontmatter={
                "type": "Process Unit",
                "title": title,
                "description": title,
                "tags": ["units"],
                "sources": [{"id": "src-1", "resource": f"reference/raw/{src}", "title": src.split("/")[-1]}],
            },
            body=sec_body,
        )
        (bundle_prot / "units" / fname).write_text(doc.serialize(), encoding="utf-8")

    overview_md = bundle_prot / "overview.md"
    overview_md.write_text(
        "---\ntype: Overview\ntitle: Plant\ndescription: Plant.\n---\n\n"
        "See [Alpha Section](/units/unit-3000-alpha-section.md).\n",
        encoding="utf-8",
    )

    rewrites = consolidate_alias_twins(
        bundle_prot,
        protected_paths={"units/alpha-unit.md", "units/unit-3000-alpha.md"},
    )
    assert rewrites == {"units/unit-3000-alpha-section.md": "units/unit-3000-alpha.md"}
    assert (bundle_prot / "units" / "alpha-unit.md").exists()
    assert (bundle_prot / "units" / "unit-3000-alpha.md").exists()
    assert not (bundle_prot / "units" / "unit-3000-alpha-section.md").exists()
    assert "Trip Z-3001." in (bundle_prot / "units" / "unit-3000-alpha.md").read_text(encoding="utf-8")
    assert "(/units/unit-3000-alpha.md)" in overview_md.read_text(encoding="utf-8")
    _assert_zero_broken_links(bundle_prot)


_ADJ_POOL = ["Overhead", "Bottoms", "Feed", "Recycle", "Quench", "Solvent", "Stripper", "Flash"]
_NOUN_POOL = ["Separator", "Condenser", "Reboiler", "Accumulator", "Scrubber", " Vaporizer", "Coalescer"]
_UNIT_DOMAINS = ["reaction", "distillation", "recovery", "neutralization", "absorption"]


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    equip_specs=st.lists(
        st.tuples(
            st.sampled_from(["C", "D", "E", "P", "V"]),
            st.integers(min_value=101, max_value=899),
            st.sampled_from(_ADJ_POOL),
            st.sampled_from([n.strip() for n in _NOUN_POOL]),
            st.integers(min_value=10, max_value=950),
            st.booleans(),  # whether to emit a prose service-name twin
            st.booleans(),  # whether to pluralize the prose twin stem
        ),
        min_size=1,
        max_size=5,
        unique_by=lambda t: (t[2], t[3]),  # unique (adj, noun) service names across ISA tags
    ),
    unit_domains=st.lists(
        st.tuples(
            st.sampled_from(_UNIT_DOMAINS),
            st.sampled_from(["1100", "1200", "1400", "1500"]),
            st.booleans(),  # whether to emit redundant unit-XXXX-<dom>-section twin
        ),
        min_size=1,
        max_size=3,
        unique_by=lambda u: u[0],
    ),
)
def test_pbt_consolidate_alias_twins_idempotent_lossless_and_zero_broken_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    equip_specs: list[tuple[str, int, str, str, int, bool, bool]],
    unit_domains: list[tuple[str, str, bool]],
) -> None:
    """Property-Based Test: consolidate_alias_twins is idempotent, preserves 100% of parameters/sources,
    and leaves 0 broken internal Markdown links across randomized OKF bundles.
    """
    monkeypatch.setenv("USE_GCS_STORAGE", "false")
    bundle_dir = tmp_path / f"pbt_{ abs(hash((tuple(equip_specs), tuple(unit_domains)))) }"
    (bundle_dir / "equipment").mkdir(parents=True, exist_ok=True)
    (bundle_dir / "units").mkdir(parents=True, exist_ok=True)
    (bundle_dir / "hazop").mkdir(parents=True, exist_ok=True)

    cross_links: list[str] = []
    expected_equip_tokens: dict[str, list[str]] = {}
    expected_unit_tokens: dict[str, list[str]] = {}

    # Write canonical ISA equipment files + optional prose twins directly on disk (simulating multi-worker race)
    for idx, (prefix, num, adj, noun, pval, has_twin, pluralize_twin) in enumerate(equip_specs):
        isa_tag = f"{prefix}-{num}"
        service_name = f"{adj} {noun}"
        isa_src = f"data_sheets/DS-{isa_tag}.pdf"
        isa_val = f"{pval}.5"

        isa_doc = OKFDocument(
            frontmatter={
                "type": "Equipment Concept",
                "title": f"{isa_tag} — {service_name}",
                "description": f"{service_name} in Unit 10.",
                "tags": ["equipment"],
                "sources": [{"id": "src-1", "resource": f"reference/raw/{isa_src}", "title": f"DS-{isa_tag}.pdf"}],
                "entity_metadata": {
                    "tag": isa_tag,
                    "name": service_name,
                    "equipment_class": "Vessel",
                    "unit": "10",
                },
            },
            body=(
                f"## Function\n{service_name} primary vessel.\n\n"
                f"## Design Data\n"
                f"| Parameter | Value | Unit | Source |\n"
                f"| :--- | :--- | :--- | :--- |\n"
                f"| Design Pressure | {isa_val} | barg | DS-{isa_tag}.pdf |\n"
            ),
        )
        (bundle_dir / "equipment" / f"{isa_tag}.md").write_text(isa_doc.serialize(), encoding="utf-8")
        expected_equip_tokens[isa_tag] = [isa_val, f"DS-{isa_tag}.pdf"]
        cross_links.append(f"- Canonical ref [{isa_tag}](/equipment/{isa_tag}.md)")

        if has_twin:
            twin_noun = f"{noun}s" if pluralize_twin else noun
            twin_label = f"{adj} {twin_noun}"
            twin_stem = f"{adj}_{twin_noun}"
            twin_src = f"operating_manuals/OM-{idx}.pdf"
            twin_temp = f"{100 + idx}"
            twin_doc = OKFDocument(
                frontmatter={
                    "type": "Equipment Concept",
                    "title": twin_label,
                    "description": f"Operating notes for {twin_label}.",
                    "tags": ["equipment", "manual"],
                    "sources": [{"id": "src-1", "resource": f"reference/raw/{twin_src}", "title": f"OM-{idx}.pdf"}],
                    "entity_metadata": {
                        "tag": twin_label,
                        "name": twin_label,
                        "equipment_class": "Equipment",
                        "unit": "Unit 1000",
                    },
                },
                body=(
                    f"## Function\nStartup guidance for {twin_label}.\n\n"
                    f"## Operating Conditions\n"
                    f"| Parameter | Value | Unit | Source |\n"
                    f"| :--- | :--- | :--- | :--- |\n"
                    f"| Max Startup Temp | {twin_temp} | degC | OM-{idx}.pdf |\n"
                ),
            )
            (bundle_dir / "equipment" / f"{twin_stem}.md").write_text(twin_doc.serialize(), encoding="utf-8")
            expected_equip_tokens[isa_tag].extend([twin_temp, f"OM-{idx}.pdf"])
            cross_links.append(f"- Twin ref [{twin_label}](/equipment/{twin_stem}.md)")
            cross_links.append(f"- Relative twin ref [{twin_label}](../equipment/{twin_stem}.md#operating-conditions)")

    # Write unit concepts + optional numbered unit-XXXX-<dom>-section twins
    for u_idx, (dom, unum, has_u_twin) in enumerate(unit_domains):
        base_slug = f"{dom}-section"
        u_marker_a = f"MARKER_BASE_{dom.upper()}_{u_idx}"
        u_doc_a = OKFDocument(
            frontmatter={
                "type": "Process Unit",
                "title": f"{dom.title()} Section",
                "description": f"{dom.title()} process overview.",
                "tags": ["units", dom],
                "sources": [{"id": "src-1", "resource": f"reference/raw/pfd/PFD-{unum}.pdf", "title": f"PFD-{unum}.pdf"}],
            },
            body=f"## Process Overview\n\n{u_marker_a}\n",
        )
        (bundle_dir / "units" / f"{base_slug}.md").write_text(u_doc_a.serialize(), encoding="utf-8")
        expected_unit_tokens[base_slug] = [u_marker_a, f"PFD-{unum}.pdf"]

        if has_u_twin:
            twin_u_slug = f"unit-{unum}-{dom}-section"
            u_marker_b = f"MARKER_TWIN_{dom.upper()}_{u_idx}"
            u_doc_b = OKFDocument(
                frontmatter={
                    "type": "Process Unit",
                    "title": f"Unit {unum} {dom.title()} Section",
                    "description": f"Unit {unum} operating limits.",
                    "tags": ["units", f"unit-{unum}"],
                    "sources": [{"id": "src-1", "resource": f"reference/raw/om/OM-{unum}.pdf", "title": f"OM-{unum}.pdf"}],
                },
                body=f"## Safety Interlocks\n\n- {u_marker_b}\n",
            )
            (bundle_dir / "units" / f"{twin_u_slug}.md").write_text(u_doc_b.serialize(), encoding="utf-8")
            expected_unit_tokens[base_slug].extend([u_marker_b, f"OM-{unum}.pdf"])
            cross_links.append(f"- Unit twin ref [Unit {unum}](/units/{twin_u_slug}.md)")

    (bundle_dir / "hazop" / "study.md").write_text(
        "---\ntype: HAZOP Study\ntitle: Cross Links\ndescription: Links.\n---\n\n"
        "## Linked Concepts\n" + "\n".join(cross_links) + "\n",
        encoding="utf-8",
    )

    # Pass 1: Consolidate & generate indexes
    consolidate_alias_twins(bundle_dir, protected_paths=set())
    generate_bundle_indexes(bundle_dir)

    snapshot_1 = {
        p.relative_to(bundle_dir).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(bundle_dir.rglob("*.md"))
    }

    # Invariant 1: Idempotency — second consolidation returns {} and changes zero bytes
    rewrites_2 = consolidate_alias_twins(bundle_dir, protected_paths=set())
    assert rewrites_2 == {}
    snapshot_2 = {
        p.relative_to(bundle_dir).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(bundle_dir.rglob("*.md"))
    }
    assert snapshot_2 == snapshot_1

    # Invariant 2: Lossless preservation of all canonical + twin parameters & sources
    for isa_tag, req_tokens in expected_equip_tokens.items():
        merged_txt = snapshot_1[f"equipment/{isa_tag}.md"]
        for tok in req_tokens:
            assert tok in merged_txt, f"Missing '{tok}' in consolidated equipment/{isa_tag}.md"

    for base_slug, req_tokens in expected_unit_tokens.items():
        merged_u_txt = snapshot_1[f"units/{base_slug}.md"]
        for tok in req_tokens:
            assert tok in merged_u_txt, f"Missing '{tok}' in consolidated units/{base_slug}.md"

    # Invariant 3: Zero broken internal Markdown links across the entire bundle
    _assert_zero_broken_links(bundle_dir)
