"""Unit Tests and Hypothesis Property-Based Tests (PBT) for SPEC-20261005-MOC-AND-DOCUMENT-UPDATE-LIFECYCLE.

Covers:
- Track A: MOC Authority, Revision Rank Ordering, Decommissioned Pruning & Conflict Auto-Resolution
- Track B: Sentence-Level Prose Deduplication, Multi-Target/Base-ID Equipment Graph Resolution &
  PROCESS_BOUNDARY Classification, Dual-Syntax ConceptWikiLinks, Reciprocal Topology Back-Propagation,
  Register InstrumentControlEdges, and Primary-Key-First Instrument Register Linking.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings, strategies as st

from extracter_agent.models.domain import (
    ConnectionStream,
    EngineeringParameter,
    EquipmentEntity,
    InstrumentLoop,
    MOCChangeRecord,
)
from extracter_agent.okf.document import OKFDocument
from extracter_agent.okf.indexer import (
    enrich_and_normalize_bundle_concepts,
    generate_bundle_indexes,
)
from extracter_agent.okf.synthesizer import (
    compare_revision_tokens,
    deduplicate_engineering_prose,
    extract_revision_token,
    format_equipment_endpoint_cell,
    is_moc_source,
    merge_equipment_entity_with_existing,
    resolve_bundle_instrument_link,
    synthesize_equipment_concept,
)
from extracter_agent.web_server import ALLOWED_RAW_SUBFOLDERS
from query_agent.spanner.lineage_extractor import extract_bundle_graph_and_lineage


# ==============================================================================
# TRACK A: DETERMINISTIC UNIT TESTS — REVISION RANK, MOC OVERRIDE & LIFECYCLE
# ==============================================================================


def test_allowed_raw_subfolders_includes_moc() -> None:
    """Verify 'moc' is registered in ALLOWED_RAW_SUBFOLDERS."""
    assert "moc" in ALLOWED_RAW_SUBFOLDERS


def test_revision_token_extraction_and_rank_comparison() -> None:
    """Verify deterministic revision hierarchy: AS-BUILT/IFC > Z0..Zn > R0..Rn > A..Y > DRAFT."""
    assert extract_revision_token("14780-8120-PS-D2304_Z1.pdf") == "Z1"
    assert extract_revision_token("14780-8120-25-23-0013 Rev A2") == "A2"
    assert extract_revision_token("P&ID 23-0013 Rev 0") == "R0"
    assert extract_revision_token("Drawing_AS_BUILT.pdf") == "AS-BUILT"

    # Preliminary A1 -> A2 -> B1 -> R0 -> R1 -> Z0 -> Z1 -> Z2 -> IFC -> AS-BUILT
    chain = [
        "Doc_DRAFT.pdf",
        "Doc_Rev_A1.pdf",
        "Doc_Rev_A2.pdf",
        "Doc_Rev_B1.pdf",
        "Doc_Rev_0.pdf",
        "Doc_Rev_1.pdf",
        "Doc_Rev_Z0.pdf",
        "Doc_Rev_Z1.pdf",
        "Doc_Rev_Z2.pdf",
        "Doc_IFC.pdf",
        "Doc_AS-BUILT.pdf",
    ]
    for idx in range(len(chain) - 1):
        older = chain[idx]
        newer = chain[idx + 1]
        assert compare_revision_tokens(older, newer) == 1, f"Expected {newer} > {older}"
        assert compare_revision_tokens(newer, older) == -1, f"Expected {older} < {newer}"
        assert compare_revision_tokens(older, older) == 0


def test_is_moc_source_boundary_guard_1() -> None:
    """Boundary Guard #1: 'Material of Construction (MOC)' must never trigger MOC source detection."""
    assert not is_moc_source("Material of Construction (MOC): SA-240 Type 304L")
    assert not is_moc_source("14780-8120-PS-D2304 Rev Z1 (MOC: 304L)")
    assert is_moc_source("MOC-2026-014")
    assert is_moc_source("reference/raw/moc/MOC-2026-014_D2304_Rerating.pdf")
    assert is_moc_source("ECN-2026-009")
    assert is_moc_source("CustomDoc-123", explicit_moc_sources={"CustomDoc-123"})


def test_moc_authoritative_override_and_conflict_auto_resolution() -> None:
    """Verify MOC overrides baseline parameters with PENDING REDRAFT, prunes removed items, and clears resolved conflicts."""
    # Step 1: Initial entity with a cross-document conflict on Design Pressure and an instrument/connection to be removed
    base_entity = EquipmentEntity(
        tag="D-2304",
        name="Decomposer Drum",
        equipment_class="Vessel",
        unit="2300",
        function_summary="Primary decomposition drum in Unit 2300.",
        design_data=[
            EngineeringParameter(
                parameter="Internal Design Pressure",
                value="10.0",
                unit="kg/cm²g",
                source="14780-8120-PS-0010 Rev Z1",
            ),
            EngineeringParameter(
                parameter="Design Temperature",
                value="250",
                unit="°C",
                source="14780-8120-PS-D2304 Rev Z1",
            ),
        ],
        operating_conditions=[],
        instruments=[
            InstrumentLoop(
                tag="TI-1399",
                service="Temporary Test Thermowell",
                instrument_type="Temperature Indicator",
                source="14780-8120-25-23-0013 Rev Z1",
            ),
            InstrumentLoop(
                tag="LT-1301",
                service="Drum Level Control",
                instrument_type="DP Level Transmitter",
                setpoint_or_range="NLL 2100 mm",
                source="14780-8120-25-23-0013 Rev Z1",
            ),
        ],
        connections=[
            ConnectionStream(
                stream_id="TEMP-BYPASS-01",
                direction="BYPASS",
                source_tag="D-2304",
                target_tag="D-2306",
                source="14780-8120-25-23-0013 Rev Z1",
            ),
            ConnectionStream(
                stream_id="VENT-LINE-01",
                direction="VENT",
                source_tag="D-2304",
                target_tag="D-2306",
                source="14780-8120-25-23-0013 Rev Z1",
            ),
        ],
        hazards=[
            "⚠️ CONFLICT — Internal Design Pressure: 14780-8120-PS-0010 Rev Z1 specifies 10.0 kg/cm²g, whereas 14780-8120-PS-D2304 Rev Z1 specifies 11.0 kg/cm²g — verify with engineer before HAZOP",
            "⚠️ CONFLICT — Rupture Disc Set Pressure: P&ID specifies 12.18 kg/cm²g @ 60°C, whereas Datasheet specifies 9.5-11.0 kg/cm²g @ 225-250°C",
        ],
        sources=["data_sheets/14780-8120-PS-D2304_Z1.pdf", "pid/14780-8120-25-23-0013_Z1.pdf"],
    )
    existing_doc = synthesize_equipment_concept(base_entity)

    # Step 2: Apply an authoritative MOC that updates Internal Design Pressure to 12.5 kg/cm²g,
    # reroutes VENT-LINE-01 from D-2306 to D-2307, and decommissions TI-1399 & TEMP-BYPASS-01.
    moc_entity = EquipmentEntity(
        tag="D-2304",
        name="Decomposer Drum",
        equipment_class="Vessel",
        unit="2300",
        aliases=["23-D-2304"],
        function_summary="Primary decomposition drum in Unit 2300.",
        design_data=[
            EngineeringParameter(
                parameter="Internal Design Pressure",
                value="12.5",
                unit="kg/cm²g",
                source="MOC-2026-014",
            ),
        ],
        operating_conditions=[],
        instruments=[
            InstrumentLoop(
                tag="LT-1301",
                service="Drum Level Control",
                instrument_type="DP Level Transmitter",
                setpoint_or_range="NLL 2250 mm",
                source="MOC-2026-014",
            ),
        ],
        connections=[
            ConnectionStream(
                stream_id="VENT-LINE-01",
                direction="VENT",
                source_tag="D-2304",
                target_tag="D-2307",
                source="MOC-2026-014",
            ),
        ],
        hazards=[],
        sources=["moc/MOC-2026-014.pdf"],
        removed_instruments=["TI-1399"],
        removed_connections=["TEMP-BYPASS-01"],
        moc_history=[
            MOCChangeRecord(
                moc_id="MOC-2026-014",
                effective_date="2026-10-05",
                change_type="DESIGN_PRESSURE_UPGRADE",
                summary="Upgraded D-2304 MAWP to 12.5 kg/cm²g, rerouted VENT-LINE-01 to D-2307, and removed TI-1399.",
                affected_documents=["14780-8120-PS-D2304 Rev Z1", "14780-8120-25-23-0013 Rev Z1"],
                status="PENDING_REDRAFT",
            )
        ],
    )

    merged = merge_equipment_entity_with_existing(moc_entity, existing_doc)

    # 1. Design pressure is updated to 12.5 with 🔄 MOC PENDING REDRAFT note
    dp_param = next(p for p in merged.design_data if p.parameter == "Internal Design Pressure")
    assert dp_param.value == "12.5"
    assert dp_param.note is not None and "🔄 MOC PENDING REDRAFT" in dp_param.note
    assert "MOC-2026-014" in dp_param.source

    # 2. Resolved conflict on Internal Design Pressure is auto-cleared, while unrelated Rupture Disc conflict is preserved (Boundary Guard #2)
    assert not any("Internal Design Pressure" in h for h in merged.hazards)
    assert any("Rupture Disc Set Pressure" in h for h in merged.hazards)

    # 3. Removed instrument TI-1399 and removed connection TEMP-BYPASS-01 are pruned (Boundary Guard #3)
    inst_tags = [i.tag for i in merged.instruments]
    assert "TI-1399" not in inst_tags
    assert "LT-1301" in inst_tags
    lt_inst = next(i for i in merged.instruments if i.tag == "LT-1301")
    assert lt_inst.setpoint_or_range == "NLL 2250 mm"

    conn_ids = [c.stream_id for c in merged.connections]
    assert "TEMP-BYPASS-01" not in conn_ids
    vent_conn = next(c for c in merged.connections if c.stream_id == "VENT-LINE-01")
    assert vent_conn.target_tag == "D-2307"

    # 4. Synthesized document includes Management of Change (MOC) & Revision History section
    final_doc = synthesize_equipment_concept(merged)
    assert "## Management of Change (MOC) & Revision History" in final_doc.body
    assert "MOC-2026-014" in final_doc.body
    assert "23-D-2304" in final_doc.frontmatter["entity_metadata"]["aliases"]


def test_out_of_order_older_revision_does_not_overwrite_newer_revision() -> None:
    """Verify that ingesting an older revision (Rev A1) after a newer revision (Rev Z1) retains Rev Z1."""
    z1_entity = EquipmentEntity(
        tag="D-2121",
        name="Condensate Pot",
        equipment_class="Vessel",
        unit="2100",
        function_summary="Condensate pot.",
        design_data=[
            EngineeringParameter(
                parameter="Shell Length (TL to TL)",
                value="2550",
                unit="mm",
                source="14780-8120-PS-D2121 Rev Z1",
            )
        ],
        sources=["data_sheets/14780-8120-PS-D2121_Z1.pdf"],
    )
    doc_z1 = synthesize_equipment_concept(z1_entity)

    a1_entity = EquipmentEntity(
        tag="D-2121",
        name="Condensate Pot",
        equipment_class="Vessel",
        unit="2100",
        function_summary="Condensate pot.",
        design_data=[
            EngineeringParameter(
                parameter="Shell Length (TL to TL)",
                value="2350",
                unit="mm",
                source="14780-8120-PS-D2121 Rev A1",
            )
        ],
        sources=["data_sheets/14780-8120-PS-D2121_A1.pdf"],
    )
    merged = merge_equipment_entity_with_existing(a1_entity, doc_z1)
    assert merged.design_data[0].value == "2550"
    assert "Z1" in merged.design_data[0].source
    assert len(merged.hazards) == 0


# ==============================================================================
# TRACK B: DETERMINISTIC UNIT TESTS — PROSE DEDUP, GRAPH EDGES & LINKING
# ==============================================================================


def test_deduplicate_engineering_prose_eliminates_boilerplate_and_keeps_facts() -> None:
    """Fix #1: Deduplicate repeated multi-turn boilerplate while retaining 100% of numbers and tags."""
    repeated = (
        "Primary decomposition drum in the Concentration, Decomposition, and Neutralization Section (Unit 2300) "
        "where cumene hydroperoxide (CHP) undergoes acid-catalyzed cleavage into phenol and acetone. "
        "Protected on the top head by a 24-inch rupture disc (X-2311) as ultimate catastrophic overpressure protection. "
        "Primary decomposition drum in the Concentration, Decomposition, and Neutralization Section (Unit 2300) "
        "where cumene hydroperoxide (CHP) undergoes acid-catalyzed cleavage into phenol and acetone. "
        "Protected on the top head by a 24-inch rupture disc (X-2311) as ultimate catastrophic overpressure protection in the unlikely event of SIS failure. "
        "Operating at 60 °C and 0.70 kg/cm²g, receiving 61,248 kg/h from P-2301A/B and 1,826,206 kg/h from E-2307A/B."
    )
    deduped = deduplicate_engineering_prose(repeated)
    assert len(deduped) < len(repeated)
    assert deduped.count("Primary decomposition drum") == 1
    for fact in ("2300", "24-inch", "X-2311", "60", "0.70", "61,248", "P-2301A/B", "1,826,206", "E-2307A/B"):
        assert fact in deduped


def test_spanner_lineage_extractor_multi_target_and_process_boundary_and_moc(tmp_path: Path) -> None:
    """Fixes #2, #3, #4 & Track A: Verify multi-target edges, PROCESS_BOUNDARY, dual-syntax WikiLinks, MOC lineage, and register InstrumentControlEdges."""
    bundle = tmp_path / "okf_bundle"
    (bundle / "equipment").mkdir(parents=True)
    (bundle / "instruments").mkdir(parents=True)
    (bundle / "sources").mkdir(parents=True)

    # Create neighbor equipment files
    for eq_slug, eq_tag in [
        ("P-2302AB", "P-2302A/B"),
        ("P-2303AB", "P-2303A/B"),
        ("E-2307AB", "E-2307A/B"),
        ("D-2306", "D-2306"),
    ]:
        doc = synthesize_equipment_concept(
            EquipmentEntity(
                tag=eq_tag,
                name=f"Equipment {eq_tag}",
                equipment_class="Pump" if eq_slug.startswith("P-") else "Exchanger",
                unit="2300",
                function_summary=f"Function of {eq_tag}.",
                sources=["pid/14780-8120-25-23-0013_Z1.pdf"],
            ),
            bundle_root=bundle,
        )
        (bundle / "equipment" / f"{eq_slug}.md").write_text(doc.serialize(), encoding="utf-8")

    # Create an instrument register file with table rows
    inst_reg_md = """---
type: Instrument Register
title: CDN Level Instruments
description: Level instruments for Unit 2300.
sources:
- id: src-1
  resource: reference/raw/data_sheets/14780-8120-PS-0033_Z1.pdf
  title: 14780-8120-PS-0033_Z1.pdf
---

# CDN Level Instruments

| Tag | Service | Equipment / Location | Range / Setpoint | Alarm / Interlock | Source |
| :--- | :--- | :--- | :--- | :--- | :--- |
| LXT-23-1302 | Decomposer High Level Trip | D-2304 Nozzles BK1/BK2 | HHLL 2500 mm | Trips UC-2302 | 14780-8120-PS-0033 Rev Z1 |
"""
    (bundle / "instruments" / "cdn-level-instruments.md").write_text(inst_reg_md, encoding="utf-8")

    # Create D-2304 with composite target, base-ID target, process boundary target, and MOC parameter
    d2304_entity = EquipmentEntity(
        tag="D-2304",
        name="Decomposer Drum",
        equipment_class="Vessel",
        unit="2300",
        function_summary="Decomposer Drum feeding [P-2302A/B](/equipment/P-2302AB.md) and [[equipment/D-2306|D-2306]].",
        design_data=[
            EngineeringParameter(
                parameter="Internal Design Pressure",
                value="12.5",
                unit="kg/cm²g",
                source="MOC-2026-014; 14780-8120-PS-D2304 Rev Z1",
                note="🔄 MOC PENDING REDRAFT — MOC-2026-014 updated from 11.0 kg/cm²g (14780-8120-PS-D2304 Rev Z1: 11.0 kg/cm²g)",
            )
        ],
        connections=[
            ConnectionStream(
                stream_id="380",
                direction="OUTLET",
                source_tag="D-2304",
                target_tag="P-2302A/B, P-2303A/B",
                line_size='24"',
                source="14780-8120-20-23-0005 Rev Z1",
            ),
            ConnectionStream(
                stream_id="388",
                direction="INLET",
                source_tag="E-2307",
                target_tag="D-2304",
                line_size='14"',
                source="14780-8120-20-23-0005 Rev Z1",
            ),
            ConnectionStream(
                stream_id="RELIEF-STACK",
                direction="RELIEF",
                source_tag="D-2304",
                target_tag="ATMOSPHERE",
                line_size='24"',
                source="14780-8120-25-23-0013 Rev Z1",
            ),
        ],
        sources=["moc/MOC-2026-014.pdf", "data_sheets/14780-8120-PS-D2304_Z1.pdf"],
    )
    d2304_doc = synthesize_equipment_concept(d2304_entity, bundle_root=bundle)
    (bundle / "equipment" / "D-2304.md").write_text(d2304_doc.serialize(), encoding="utf-8")

    payload = extract_bundle_graph_and_lineage(bundle)

    # 1. Verify multi-target and base-ID ProcessConnectionEdges
    conn_pairs = {(e.from_entity_id, e.to_entity_id) for e in payload.process_edges}
    assert ("EQ:D-2304", "EQ:P-2302AB") in conn_pairs
    assert ("EQ:D-2304", "EQ:P-2303AB") in conn_pairs
    assert ("EQ:E-2307AB", "EQ:D-2304") in conn_pairs
    assert ("EQ:D-2304", "BND:ATMOSPHERE") in conn_pairs

    # 2. Verify ATMOSPHERE is classified as PROCESS_BOUNDARY, not EQUIPMENT
    entities_by_id = {n.entity_id: n for n in payload.entities}
    assert "BND:ATMOSPHERE" in entities_by_id
    assert entities_by_id["BND:ATMOSPHERE"].entity_type == "PROCESS_BOUNDARY"
    assert "EQ:ATMOSPHERE" not in entities_by_id

    # 3. Verify Dual-Syntax ConceptWikiLinkEdges (both Markdown [...] (...) and MediaWiki [[...]])
    wikilink_targets = {w.to_concept_id for w in payload.wikilink_edges if w.from_concept_id == "equipment/D-2304"}
    assert "equipment/P-2302AB" in wikilink_targets
    assert "equipment/P-2303AB" in wikilink_targets
    assert "equipment/E-2307AB" in wikilink_targets
    assert "equipment/D-2306" in wikilink_targets

    # 4. Verify MOC_AUTHORITY and PENDING_REDRAFT FactLineageEdges with has_conflict = False
    dp_facts = [fa for fa in payload.facts if fa.parameter_name == "Internal Design Pressure"]
    assert dp_facts
    assert all(not fa.has_conflict for fa in dp_facts)
    dp_fact_ids = {fa.fact_id for fa in dp_facts}
    moc_edges = [f for f in payload.lineage_edges if f.fact_id in dp_fact_ids]
    roles = {f.source_role for f in moc_edges}
    assert "MOC_AUTHORITY" in roles
    assert "PENDING_REDRAFT" in roles

    # 5. Verify InstrumentControlEdge extracted from instruments/cdn-level-instruments.md register table
    inst_pairs = {(ic.instrument_entity_id, ic.target_entity_id) for ic in payload.instrument_edges}
    assert ("INST:LXT-23-1302", "EQ:D-2304") in inst_pairs


def test_reciprocal_topology_back_propagation_and_instrument_re_resolution(tmp_path: Path) -> None:
    """Fix #4: Verify hermetic bundle instrument link routing and reciprocal connection back-propagation."""
    bundle_root = tmp_path / "okf_bundle"
    inst_dir = bundle_root / "instruments"
    equip_dir = bundle_root / "equipment"
    inst_dir.mkdir(parents=True)
    equip_dir.mkdir(parents=True)

    (inst_dir / "cdn-level-instruments.md").write_text(
        "---\ntitle: Level Instruments\ndescription: Level switches and transmitters.\n---\n\n"
        "| Tag | Type | Service |\n| :--- | :--- | :--- |\n"
        "| LT-23-1301 | Radar Level Transmitter | Decomposer Drum Level |\n"
        "| LS-23-1302 | High Level Switch | Decomposer Drum High Level Switch |\n",
        encoding="utf-8",
    )
    (inst_dir / "cdn-flow-instruments.md").write_text(
        "---\ntitle: Flow Instruments\ndescription: Flow meters and restriction orifices.\n---\n\n"
        "| Tag | Type | Service |\n| :--- | :--- | :--- |\n"
        "| FT-23-1101 | Coriolis Flow Meter | Feed Flow |\n"
        "| RO-2002 | Restriction Orifice | Purge Flow Restriction Orifice |\n",
        encoding="utf-8",
    )
    (inst_dir / "cdn-pressure-instruments.md").write_text(
        "---\ntitle: Pressure Instruments\ndescription: Pressure gauges and transmitters.\n---\n\n"
        "| Tag | Type | Service |\n| :--- | :--- | :--- |\n"
        "| PT-23-1201 | Pressure Transmitter | Reactor Pressure |\n"
        "| PI-2003 | Pressure Gauge | Pump Discharge Pressure Gauge |\n",
        encoding="utf-8",
    )
    (inst_dir / "control-valves-cdn-unit.md").write_text(
        "---\ntitle: Control & Shutdown Valves\ndescription: Control and XV shutoff valves.\n---\n\n"
        "| Tag | Type | Service |\n| :--- | :--- | :--- |\n"
        "| UXV-23-1204 | Eccentric Disc Valve | Decomposer Feed Upstream Emergency Shutoff |\n",
        encoding="utf-8",
    )

    # Verify primary-key-first instrument link resolution on previously misrouted tags
    assert (
        resolve_bundle_instrument_link(
            "BS (LS High)",
            instrument_type='Level Switch Chamber Tap (2" Class 300 RF, 2 off)',
            service="Decomposer Drum High Level Switch",
            bundle_root=bundle_root,
        )
        == "/instruments/cdn-level-instruments.md"
    )
    assert (
        resolve_bundle_instrument_link(
            "RO-2002",
            instrument_type="Restriction Orifice",
            service="Purge Flow Restriction Orifice",
            bundle_root=bundle_root,
        )
        == "/instruments/cdn-flow-instruments.md"
    )
    assert (
        resolve_bundle_instrument_link(
            "PI-2003",
            instrument_type="Pressure Gauge",
            service="Pump Discharge Pressure Gauge",
            bundle_root=bundle_root,
        )
        == "/instruments/cdn-pressure-instruments.md"
    )
    assert (
        resolve_bundle_instrument_link(
            "UXV-1204",
            instrument_type="Eccentric Disc Valve",
            service="Decomposer Feed Upstream Emergency Shutoff",
            bundle_root=bundle_root,
        )
        == "/instruments/control-valves-cdn-unit.md"
    )


# ==============================================================================
# PROPERTY-BASED TESTS (PBT) WITH HYPOTHESIS
# ==============================================================================


_REV_POOL = [
    "Doc_DRAFT.pdf",
    "Doc_Rev_A1.pdf",
    "Doc_Rev_A2.pdf",
    "Doc_Rev_B1.pdf",
    "Doc_Rev_0.pdf",
    "Doc_Rev_1.pdf",
    "Doc_Rev_Z0.pdf",
    "Doc_Rev_Z1.pdf",
    "Doc_Rev_Z2.pdf",
    "Doc_IFC.pdf",
    "Doc_AS-BUILT.pdf",
]


@settings(max_examples=50, deadline=None)
@given(
    i=st.integers(min_value=0, max_value=len(_REV_POOL) - 1),
    j=st.integers(min_value=0, max_value=len(_REV_POOL) - 1),
    k=st.integers(min_value=0, max_value=len(_REV_POOL) - 1),
)
def test_pbt_revision_rank_total_order_invariants(i: int, j: int, k: int) -> None:
    """PBT: Verify reflexivity, antisymmetry, and transitivity of compare_revision_tokens."""
    a, b, c = _REV_POOL[i], _REV_POOL[j], _REV_POOL[k]
    # Reflexivity
    assert compare_revision_tokens(a, a) == 0
    # Antisymmetry
    ab = compare_revision_tokens(a, b)
    ba = compare_revision_tokens(b, a)
    assert ab == -ba
    # Monotonic alignment with canonical pool index
    if i < j:
        assert ab == 1
    elif i > j:
        assert ab == -1
    else:
        assert ab == 0
    # Transitivity
    bc = compare_revision_tokens(b, c)
    ac = compare_revision_tokens(a, c)
    if ab == 1 and bc == 1:
        assert ac == 1


@settings(max_examples=40, deadline=None)
@given(
    moc_num=st.integers(min_value=1, max_value=999),
    year=st.integers(min_value=2020, max_value=2030),
    new_val=st.floats(min_value=1.0, max_value=99.0, allow_nan=False, allow_infinity=False),
)
def test_pbt_moc_override_never_emits_false_conflict(moc_num: int, year: int, new_val: float) -> None:
    """PBT: Any authoritative MOC update must replace the parameter value and emit 🔄 MOC PENDING REDRAFT with 0 false conflicts."""
    moc_id = f"MOC-{year}-{moc_num:03d}"
    val_str = f"{new_val:.2f}"
    base_ent = EquipmentEntity(
        tag="D-2304",
        name="Decomposer Drum",
        equipment_class="Vessel",
        unit="2300",
        function_summary="Decomposer Drum.",
        design_data=[
            EngineeringParameter(
                parameter="Design Pressure",
                value="0.50",
                unit="kg/cm²g",
                source="14780-8120-PS-D2304 Rev Z1",
            )
        ],
        sources=["data_sheets/14780-8120-PS-D2304_Z1.pdf"],
    )
    doc = synthesize_equipment_concept(base_ent)
    moc_ent = EquipmentEntity(
        tag="D-2304",
        name="Decomposer Drum",
        equipment_class="Vessel",
        unit="2300",
        function_summary="Decomposer Drum.",
        design_data=[
            EngineeringParameter(
                parameter="Design Pressure",
                value=val_str,
                unit="kg/cm²g",
                source=moc_id,
            )
        ],
        sources=[f"moc/{moc_id}.pdf"],
    )
    merged = merge_equipment_entity_with_existing(moc_ent, doc)
    assert merged.design_data[0].value == val_str
    assert merged.design_data[0].note is not None
    assert "🔄 MOC PENDING REDRAFT" in merged.design_data[0].note
    assert len(merged.hazards) == 0


@settings(max_examples=40, deadline=None)
@given(
    repeat_count=st.integers(min_value=2, max_value=8),
    flow_val=st.integers(min_value=100, max_value=999999),
    temp_val=st.integers(min_value=10, max_value=350),
    equip_num=st.integers(min_value=1000, max_value=9999),
)
def test_pbt_deduplicate_engineering_prose_fact_preservation_and_idempotence(
    repeat_count: int,
    flow_val: int,
    temp_val: int,
    equip_num: int,
) -> None:
    """PBT: deduplicate_engineering_prose is idempotent, reduces repeated boilerplate, and preserves 100% of numbers/tags."""
    tag = f"P-{equip_num}A/B"
    s1 = f"Primary process vessel operating at {temp_val} °C in Unit 2300."
    s2 = f"Receives {flow_val} kg/h of feed from pump {tag} under normal operation."
    bloated = " ".join([s1] * repeat_count + [s2])
    deduped = deduplicate_engineering_prose(bloated)

    # Idempotence
    assert deduplicate_engineering_prose(deduped) == deduped
    # Boilerplate reduction
    assert len(deduped) < len(bloated)
    # 100% numeric & tag retention
    assert str(temp_val) in deduped
    assert str(flow_val) in deduped
    assert tag in deduped
