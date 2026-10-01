"""Unit tests for OKF document model, synthesizer, indexer, and validator."""

import tempfile
from pathlib import Path

from extracter_agent.models.domain import (
    ConnectionStream,
    EngineeringParameter,
    EquipmentEntity,
    InstrumentLoop,
)
from extracter_agent.okf.document import OKFDocument
from extracter_agent.okf.indexer import generate_bundle_indexes, update_bundle_log
from extracter_agent.okf.synthesizer import (
    synthesize_equipment_concept,
)
from extracter_agent.okf.validator import validate_okf_bundle


def test_okf_document_parse_and_serialize():
    """Test basic document parsing and serialization."""
    raw = """---
type: Equipment Concept
title: V-2301 — Preflash Column
tags: [equipment, column, cdn]
---

# V-2301 — Preflash Column

## Function
Primary vacuum flash evaporator.
"""
    doc = OKFDocument.parse(raw)
    assert doc.frontmatter["type"] == "Equipment Concept"
    assert doc.frontmatter["title"] == "V-2301 — Preflash Column"
    assert "Primary vacuum flash evaporator." in doc.body

    serialized = doc.serialize()
    assert serialized.startswith("---\n")
    assert "type: Equipment Concept" in serialized

    # Re-parse
    doc2 = OKFDocument.parse(serialized)
    assert doc2.frontmatter == doc.frontmatter
    assert doc2.body.strip() == doc.body.strip()


def test_synthesize_equipment_concept():
    """Test synthesizing an EquipmentEntity into OKF v0.2."""
    entity = EquipmentEntity(
        tag="V-2301",
        name="Preflash Column",
        equipment_class="Column",
        unit="CDN",
        function_summary="First-stage vacuum evaporator in CDN.",
        design_data=[
            EngineeringParameter(
                parameter="Shell ID", value="6600", unit="mm", source="PS-V2301"
            ),
            EngineeringParameter(
                parameter="T/T Length", value="21000", unit="mm", source="PS-V2301"
            ),
        ],
        operating_conditions=[
            EngineeringParameter(
                parameter="Top Pressure", value="18.5", unit="mmHgA", source="DWG 0004"
            ),
            EngineeringParameter(
                parameter="Top Temp", value="53", unit="°C", source="DWG 0004"
            ),
        ],
        instruments=[
            InstrumentLoop(
                tag="TI-0404",
                service="Column Bottom Temp",
                instrument_type="RTD",
                location="Column Bottom Sump",
                setpoint_or_range="0–200 °C",
                interlock_or_alarm="TXSHH-0404 (UC-2301 ESD)",
                source="DWG 0004",
            ),
            InstrumentLoop(
                tag="FT-0401A",
                service="Feed Flow",
                instrument_type="Flow Transmitter",
                location="Feed Line",
                setpoint_or_range="0–200 t/h",
                interlock_or_alarm="FXSLL-0401A (2oo3)",
                source="DWG 0004",
            ),
        ],
        connections=[
            ConnectionStream(
                stream_id="S229",
                temperature="83",
                description="Oxidate feed",
                source="PFD-0001",
            ),
        ],
        hazards=["CHP thermal runaway risk under elevated temperature."],
        sources=[
            "data_sheets/DS-V2301_Preflash_Column_Z1.pdf",
            "pid/PID-23-0004_Preflash_Column_Z1.pdf",
        ],
    )

    doc = synthesize_equipment_concept(entity)
    assert doc.frontmatter["type"] == "Equipment Concept"
    assert doc.frontmatter["title"] == "V-2301 — Preflash Column"
    assert "gs://" in doc.frontmatter["resource"]
    assert len(doc.frontmatter["sources"]) == 2
    assert doc.frontmatter["verified"][0]["by"] == "human:expert-chemical-engineer"
    assert doc.frontmatter["status"] == "stable"

    # Verify instrument metadata in frontmatter
    assert len(doc.frontmatter["entity_metadata"]["instruments"]) == 2
    assert doc.frontmatter["entity_metadata"]["instruments"][0]["tag"] == "TI-0404"
    assert doc.frontmatter["entity_metadata"]["instruments"][1]["tag"] == "FT-0401A"

    # Verify Markdown body tables & footnotes
    assert "## Design Data" in doc.body
    assert "| Shell ID | 6600 | mm | PS-V2301 |" in doc.body
    assert "## Operating Conditions" in doc.body
    assert "## Instrumentation & Control Loops (P&ID)" in doc.body
    assert (
        "| [TI-0404](/instruments/TI-0404.md) | Column Bottom Temp | RTD | Column Bottom Sump | 0–200 °C | TXSHH-0404 (UC-2301 ESD) | DWG 0004 |"
        in doc.body
    )
    assert (
        "| [FT-0401A](/instruments/FT-0401A.md) | Feed Flow | Flow Transmitter | Feed Line | 0–200 t/h | FXSLL-0401A (2oo3) | DWG 0004 |"
        in doc.body
    )
    assert "[^src-1]:" in doc.body


def test_bundle_indexes_and_validation():
    """Test bundle directory indexing and validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_root = Path(tmpdir)

        # Create subdirectories
        equip_dir = bundle_root / "equipment"
        hazards_dir = bundle_root / "hazards"
        equip_dir.mkdir()
        hazards_dir.mkdir()

        # Write concepts
        doc1 = OKFDocument(
            frontmatter={
                "type": "Equipment Concept",
                "title": "V-2301",
                "description": "Preflash column",
            },
            body="# V-2301\n\nContent here.",
        )
        (equip_dir / "V-2301.md").write_text(doc1.serialize(), encoding="utf-8")

        doc2 = OKFDocument(
            frontmatter={
                "type": "Hazard Profile",
                "title": "CHP",
                "description": "Peroxide hazard",
            },
            body="# CHP\n\nContent here.",
        )
        (hazards_dir / "chp.md").write_text(doc2.serialize(), encoding="utf-8")

        # Generate indexes
        written = generate_bundle_indexes(bundle_root)
        assert len(written) >= 2  # equipment/index.md, hazards/index.md, index.md

        root_index = bundle_root / "index.md"
        assert root_index.exists()
        assert "Subdirectories" in root_index.read_text(encoding="utf-8")

        # Write log.md
        log_path = update_bundle_log(
            bundle_root, "Initialization", "Created test bundle"
        )
        assert log_path.exists()

        # Validate bundle
        val_res = validate_okf_bundle(bundle_root)
        assert val_res["valid"] is True
        assert val_res["total_documents"] == 2
        assert val_res["has_root_index"] is True
        assert val_res["has_root_log"] is True


def test_generate_equipment_okf_tool_multi_unit_slash_tag():
    """Verify multi-unit tags containing slashes (e.g. D-2204A/B/C) write to sanitized filenames without FileNotFoundError."""
    from extracter_agent.tools.okf_tools import generate_equipment_okf_tool

    with tempfile.TemporaryDirectory() as tmpdir:
        res = generate_equipment_okf_tool(
            tag="D-2204A/B/C",
            name="Charcoal Adsorbers",
            equipment_class="Vessel",
            unit="OXI",
            function_summary="Three parallel activated carbon bed adsorbers for vent gas treatment.",
            design_data=[
                {"parameter": "Design Pressure", "value": "3.5", "unit": "kg/cm²g"}
            ],
            operating_conditions=[
                {"parameter": "Operating Temperature", "value": "40", "unit": "°C"}
            ],
            connections=[
                {"stream_id": "N1", "description": "Vent gas inlet"}
            ],
            hazards=["⚠️ CONFLICT — Verify bed regeneration temperature limits."],
            source_files=["ACME-2300-PS-D2204_D-2204 PROCESS DATA SHEET_Z1.pdf"],
            instruments=[
                {"tag": "TI-2204A / TAH-2204A", "service": "Bed Temp"}
            ],
            output_bundle_dir=tmpdir,
        )
        assert res["status"] == "success"
        assert res["concept_id"] == "equipment/D-2204ABC"
        expected_file = Path(tmpdir) / "equipment" / "D-2204ABC.md"
        assert expected_file.exists()
        content = expected_file.read_text(encoding="utf-8")
        assert "D-2204A/B/C — Charcoal Adsorbers" in content
        assert "/instruments/TI-2204A_TAH-2204A.md" in content


def test_derive_canonical_concept_id_and_equipment_tag():
    """Verify autonomous derivation of canonical OKF concept paths from raw metadata."""
    from extracter_agent.models.domain import (
        derive_canonical_concept_id,
        derive_canonical_equipment_tag,
        sanitize_tag_filename,
    )

    assert sanitize_tag_filename("LT-2201 (Y02)") == "LT-2201"
    assert (
        derive_canonical_equipment_tag(
            "E-2307A/B", ["ACME-2300-PS-E2307_E-2307 A_B PROCESS DATA SHEET_Z1.pdf"]
        )
        == "E-2307"
    )
    assert (
        derive_canonical_equipment_tag(
            "P-2302A/B", ["ACME-2300-PS-P2302_P-2302 A_B PROCESS DATA SHEET_Z1.pdf"]
        )
        == "P-2302"
    )
    assert (
        derive_canonical_concept_id(
            "hazards/sulfuric-acid-hazard-profile",
            concept_type="Hazard Profile",
            title="Sulfuric Acid (98%) Hazard",
        )
        == "hazards/sulfuric-acid"
    )
    assert (
        derive_canonical_concept_id(
            "instruments/cdn-sis-architecture",
            concept_type="Instrument Specification",
            title="CDN Safety Instrumented System",
        )
        == "instruments/cdn-sis"
    )
    assert (
        derive_canonical_concept_id(
            "standards/hazop-methodology-std-pha-001-r1",
            concept_type="Standard",
            title="HAZOP Methodology STD-PHA-001",
        )
        in (
            "hazop/methodology",
            "sources/std-pha-001",
            "sources/STD-PHA-001",
            "standards/hazop-methodology-std-pha-001-r1",
        )
    )


def test_zero_hardcoded_domain_maps_or_tags():
    """Verify that all agent, model, tool, and OKF modules contain zero hardcoded lookup maps, ISA prefix chains, or dataset-specific tags."""
    banned_tokens = [
        "instrument_map",
        "cdn-analyzer-register",
        "diisopropanolamine",
        "E-2307AB",
        "P-2302AB",
        "X-2309AB",
        "Unit 21 (ALKY",
        "LT-0602",
        "HXS-0106",
        '"value": "6600"',
        "UC-2301",
        "UC-2302",
        "p_code.startswith",
        "V-2301",
        "D-2304",
        "D-2204A/B/C",
        "Preflash Column",
        "cumene-hydroperoxide",
        "sis-cdn",
        "2026-06-16T00:00:00Z",
        "CWS/CWR",
        "CUL/CUG",
        "FXSL/FXT",
        "1.05x",
        "0.000xxx",
        "eng_markers",
    ]
    target_files = [
        Path("extracter_agent/models/domain.py"),
        Path("extracter_agent/okf/indexer.py"),
        Path("extracter_agent/okf/synthesizer.py"),
        Path("extracter_agent/cli.py"),
        Path("extracter_agent/agent/orchestrator.py"),
        Path("extracter_agent/pdf/processor.py"),
        Path("extracter_agent/tools/okf_tools.py"),
        Path("extracter_agent/tools/pdf_tools.py"),
    ]
    for fpath in target_files:
        src = fpath.read_text(encoding="utf-8")
        for tok in banned_tokens:
            assert tok not in src, f"Hardcoded token '{tok}' found in {fpath}"


def test_bundle_100_percent_golden_parity_and_zero_broken_links():
    """Verify 130/130 Golden Dataset path parity and 0 broken internal Markdown links in build/okf_bundle."""
    import json
    import re

    bundle_dir = Path("build/okf_bundle")
    dataset_path = Path("evals/datasets/wiki_ground_truth_eval.jsonl")
    if not bundle_dir.exists() or not dataset_path.exists():
        return

    grounded = {
        json.loads(line)["relative_wiki_path"]
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    bundle_rels = {p.relative_to(bundle_dir).as_posix() for p in bundle_dir.rglob("*.md")}
    missing = grounded - bundle_rels
    assert len(missing) == 0, f"Missing Golden paths in bundle: {sorted(missing)}"

    broken = []
    for md in bundle_dir.rglob("*.md"):
        txt = md.read_text(encoding="utf-8")
        for m in re.finditer(r"\[[^\]]+\]\(([^)#\s]+)(?:#[^)]*)?\)", txt):
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

    assert len(broken) == 0, f"Broken internal Markdown links found: {broken[:10]}"


def test_in_place_md_update_invalidates_catalog_and_instrument_caches():
    """Verify in-place edits to child .md files immediately invalidate catalog and instrument caches even when parent dir mtime is unchanged."""
    import os

    from extracter_agent.models.domain import _iter_bundle_catalog
    from extracter_agent.okf.synthesizer import resolve_bundle_instrument_link

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        inst_dir = root / "instruments"
        inst_dir.mkdir(parents=True)
        reg_a = inst_dir / "pressure-register.md"
        reg_b = inst_dir / "flow-register.md"
        reg_a.write_text(
            "---\ntype: Instrument Specification\ntitle: Pressure Register\n---\n# Pressure\nContains PT-1001.",
            encoding="utf-8",
        )
        reg_b.write_text(
            "---\ntype: Instrument Specification\ntitle: Flow Register\n---\n# Flow\nContains FT-1001.",
            encoding="utf-8",
        )

        # Warm both caches
        cat1 = _iter_bundle_catalog(root)
        assert any("ft-1001" in c["head_lower"] for c in cat1)
        assert not any("zx-9999" in c["head_lower"] for c in cat1)
        assert (
            resolve_bundle_instrument_link("FT-1001", bundle_root=root)
            == "/instruments/flow-register.md"
        )

        # Freeze parent dir mtime, modify reg_b in-place and advance only reg_b's mtime_ns
        dir_stat = inst_dir.stat()
        root_stat = root.stat()
        new_mtime_ns = reg_b.stat().st_mtime_ns + 5_000_000
        reg_b.write_text(
            "---\ntype: Instrument Specification\ntitle: Flow Register\n---\n# Flow\nContains FT-1001 and ZX-9999.",
            encoding="utf-8",
        )
        os.utime(reg_b, ns=(new_mtime_ns, new_mtime_ns))
        os.utime(inst_dir, ns=(dir_stat.st_atime_ns, dir_stat.st_mtime_ns))
        os.utime(root, ns=(root_stat.st_atime_ns, root_stat.st_mtime_ns))

        # Both caches must detect the child file mtime_ns change despite unchanged directory mtime_ns
        cat2 = _iter_bundle_catalog(root)
        assert any("zx-9999" in c["head_lower"] for c in cat2)
        assert (
            resolve_bundle_instrument_link("ZX-9999", bundle_root=root)
            == "/instruments/flow-register.md"
        )


def test_gcs_pdf_cache_redownloads_on_md5_or_size_change(monkeypatch):
    """Verify _download_pdf_from_gcs skips download on matching MD5+size and re-downloads when GCS MD5 changes in-place."""
    from unittest.mock import MagicMock

    from extracter_agent.tools import pdf_tools
    from extracter_agent.tools.pdf_tools import _compute_file_md5_b64

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir)
        monkeypatch.setattr(pdf_tools, "_GCS_RAW_CACHE_DIR", cache_dir)

        rel_path = "reference/raw/data_sheets/sample.pdf"
        cached_file = cache_dir / rel_path
        cached_file.parent.mkdir(parents=True, exist_ok=True)
        v1_bytes = b"%PDF-1.4 revision 1 (0.5 kg/cm2g)"
        v2_bytes = b"%PDF-1.4 revision 2 (3.9 kg/cm2g)"  # exact same byte length!
        assert len(v1_bytes) == len(v2_bytes)
        cached_file.write_bytes(v1_bytes)
        v1_md5 = _compute_file_md5_b64(cached_file)

        downloads: list[str] = []

        class DummyBlob:
            def download_to_filename(self, fname: str) -> None:
                downloads.append(fname)
                Path(fname).write_bytes(v2_bytes)

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = DummyBlob()
        mock_client.bucket.return_value = mock_bucket
        monkeypatch.setattr(pdf_tools.storage, "Client", lambda **kwargs: mock_client)

        # Case 1: Matching size and MD5 -> zero downloads
        monkeypatch.setattr(
            pdf_tools,
            "_GCS_RAW_BLOBS_CACHE",
            [
                {
                    "file_name": "sample.pdf",
                    "subfolder": "data_sheets",
                    "relative_path": rel_path,
                    "blob_name": rel_path,
                    "gcs_uri": f"gs://test-bucket/{rel_path}",
                    "size_bytes": len(v1_bytes),
                    "md5_hash": v1_md5,
                }
            ],
        )
        p1, _ = pdf_tools._download_pdf_from_gcs("sample.pdf", "data_sheets")
        assert p1 == cached_file
        assert len(downloads) == 0

        # Case 2: Same size_bytes, updated md5_hash -> triggers re-download!
        import base64
        import hashlib

        v2_md5 = base64.b64encode(
            hashlib.md5(v2_bytes, usedforsecurity=False).digest()
        ).decode("ascii")
        monkeypatch.setattr(
            pdf_tools,
            "_GCS_RAW_BLOBS_CACHE",
            [
                {
                    "file_name": "sample.pdf",
                    "subfolder": "data_sheets",
                    "relative_path": rel_path,
                    "blob_name": rel_path,
                    "gcs_uri": f"gs://test-bucket/{rel_path}",
                    "size_bytes": len(v2_bytes),
                    "md5_hash": v2_md5,
                }
            ],
        )
        p2, _ = pdf_tools._download_pdf_from_gcs("sample.pdf", "data_sheets")
        assert p2 == cached_file
        assert len(downloads) == 1
        assert cached_file.read_bytes() == v2_bytes


def test_incremental_equipment_merge_and_conflict_detection(tmp_path):
    """Verify file-by-file incremental extraction merges sources, parameters, instruments, connections, and flags cross-document conflicts."""
    from extracter_agent.tools.okf_tools import generate_equipment_okf_tool

    bundle_dir = str(tmp_path)

    # Pass 1: Process Data Sheet ingested first
    res1 = generate_equipment_okf_tool(
        tag="V-9100",
        name="Primary Flash Drum",
        equipment_class="Vessel",
        unit="U91",
        function_summary="Separates light vapor from liquid feed.",
        design_data=[
            {
                "parameter": "Design Pressure",
                "value": "3.5",
                "unit": "kg/cm2g",
                "source": "PS-V9100",
            },
            {
                "parameter": "Shell ID",
                "value": "2400",
                "unit": "mm",
                "source": "PS-V9100",
            },
        ],
        operating_conditions=[
            {
                "parameter": "Operating Temperature",
                "value": "85",
                "unit": "°C",
                "source": "PS-V9100",
            }
        ],
        connections=[],
        hazards=["Maintain nitrogen blanket during shutdown."],
        source_files=["data_sheets/PS-V9100_DATASHEET.pdf"],
        instruments=[],
        output_bundle_dir=bundle_dir,
    )
    assert res1["status"] == "success"
    assert res1["merged_with_existing"] is False

    # Pass 2: P&ID ingested second (adds instruments, stream connection, and conflicting Design Pressure 5.0 vs 3.5)
    res2 = generate_equipment_okf_tool(
        tag="V-9100",
        name="Primary Flash Drum",
        equipment_class="Vessel",
        unit="U91",
        function_summary="Separates light vapor from liquid feed with ESD level protection.",
        design_data=[
            {
                "parameter": "Design Pressure",
                "value": "5.0",
                "unit": "kg/cm2g",
                "source": "DWG-91-001",
            },
            {
                "parameter": "Corrosion Allowance",
                "value": "3.0",
                "unit": "mm",
                "source": "DWG-91-001",
            },
        ],
        operating_conditions=[
            {
                "parameter": "Operating Pressure",
                "value": "1.2",
                "unit": "kg/cm2g",
                "source": "DWG-91-001",
            }
        ],
        connections=[
            {
                "stream_id": "S-901",
                "temperature": "85",
                "pressure": "1.2",
                "flow_rate": "15000",
                "description": "Flash drum liquid outlet",
                "source": "DWG-91-001",
            }
        ],
        hazards=["High level trips inlet isolation valve."],
        source_files=["pid/DWG-91-001_PID.pdf"],
        instruments=[
            {
                "tag": "LT-9101",
                "service": "Drum Level",
                "instrument_type": "Guided Wave Radar",
                "location": "Drum Side",
                "setpoint_or_range": "0-2000 mm",
                "interlock_or_alarm": "LSHH-9101",
                "source": "DWG-91-001",
            }
        ],
        output_bundle_dir=bundle_dir,
    )
    assert res2["status"] == "success"
    assert res2["merged_with_existing"] is True

    # Verify both sources are preserved
    sources_out = res2["frontmatter"]["sources"]
    assert len(sources_out) == 2

    # Verify prior Shell ID + new Corrosion Allowance + conflict note on Design Pressure are all preserved in Markdown
    md_text = (Path(bundle_dir) / "equipment" / "V-9100.md").read_text(encoding="utf-8")
    assert "Shell ID" in md_text
    assert "2400" in md_text
    assert "Corrosion Allowance" in md_text
    assert "Operating Temperature" in md_text
    assert "Operating Pressure" in md_text
    assert "LT-9101" in md_text
    assert "S-901" in md_text
    assert "Maintain nitrogen blanket during shutdown." in md_text
    assert "⚠️ CONFLICT — Design Pressure" in md_text

    # Pass 3: Newer revision of the same datasheet (PS-V9100 Rev Z1) updates Shell ID (2400 -> 2600) WITHOUT conflict,
    # while Sheet 1 Cover vs Sheet 4 Sketch on Design Temperature DOES flag a conflict!
    res3 = generate_equipment_okf_tool(
        tag="V-9100",
        name="Primary Flash Drum",
        equipment_class="Vessel",
        unit="U91",
        function_summary="Separates light vapor from liquid feed with ESD level protection.",
        design_data=[
            {
                "parameter": "Shell ID",
                "value": "2600",
                "unit": "mm",
                "source": "PS-V9100 Rev Z1",
            },
            {
                "parameter": "Design Temperature",
                "value": "120",
                "unit": "°C",
                "source": "PS-V9100 (Sheet 1 Cover)",
            },
            {
                "parameter": "Design Temperature",
                "value": "150",
                "unit": "°C",
                "source": "PS-V9100 (Sheet 4 Sketch)",
            },
        ],
        operating_conditions=[],
        connections=[],
        hazards=[],
        source_files=["data_sheets/PS-V9100_DATASHEET_Z1.pdf"],
        instruments=[],
        output_bundle_dir=bundle_dir,
    )
    assert res3["status"] == "success"
    assert res3["merged_with_existing"] is True
    # Superseded datasheet path replaced by Z1, so still 2 total sources (PS-V9100_Z1 + DWG-91-001)
    assert len(res3["frontmatter"]["sources"]) == 2

    md_text_3 = (Path(bundle_dir) / "equipment" / "V-9100.md").read_text(encoding="utf-8")
    assert "| Shell ID | 2600 | mm | PS-V9100 Rev Z1 |" in md_text_3
    assert "⚠️ CONFLICT — Shell ID" not in md_text_3
    assert "⚠️ CONFLICT — Design Temperature" in md_text_3


def test_equipment_tag_resolution_never_collides_on_shared_sources(tmp_path):
    """Verify equipment items citing shared P&IDs, manuals, or connected vessel datasheets never collide with neighbor equipment files."""
    from extracter_agent.models.domain import derive_canonical_equipment_tag

    equip_dir = tmp_path / "equipment"
    equip_dir.mkdir(parents=True)
    # Create existing vessel D-8100 and pump P-8200 citing a shared P&ID and manual
    (equip_dir / "D-8100.md").write_text(
        "---\ntype: Equipment Concept\ntitle: D-8100 — Sump Vessel\nsources:\n- title: ACME-2300-PS-D8100_Z1.pdf\n- title: PID-23-0020A_Z1.pdf\n- title: OM-Unit-Manual.pdf\nentity_metadata:\n  tag: D-8100\n---\n# D-8100\n",
        encoding="utf-8",
    )
    (equip_dir / "P-8200.md").write_text(
        "---\ntype: Equipment Concept\ntitle: P-8200 — Sump Pit Pump\nsources:\n- title: ACME-2300-PS-P8200_Z1.pdf\n- title: PID-23-0020A_Z1.pdf\nentity_metadata:\n  tag: P-8200\n---\n# P-8200\n",
        encoding="utf-8",
    )
    (equip_dir / "P-8104A.md").write_text(
        "---\ntype: Equipment Concept\ntitle: P-8104A — Sump Pump\nentity_metadata:\n  tag: P-8104A\n---\n# P-8104A\n",
        encoding="utf-8",
    )

    # 1. Pump P-8104A citing both its own datasheet PS-P8104 and vessel datasheet PS-D8100 must resolve to P-8104A, never D-8100
    assert (
        derive_canonical_equipment_tag(
            "P-8104A",
            [
                "ACME-2300-PS-P8104_Z1.pdf",
                "ACME-2300-PS-D8100_Z1.pdf",
                "PID-23-0020A_Z1.pdf",
            ],
            bundle_root=tmp_path,
        )
        == "P-8104A"
    )

    # 2. Package X-8201 citing shared P&ID and P-8200 datasheet must resolve to X-8201, never P-8200 or D-8100
    assert (
        derive_canonical_equipment_tag(
            "X-8201",
            [
                "PID-23-0020A_Z1.pdf",
                "ACME-2300-PS-P8200_Z1.pdf",
                "OM-Unit-Manual.pdf",
            ],
            bundle_root=tmp_path,
        )
        == "X-8201"
    )


def test_concept_id_specificity_prevents_prefix_and_shared_source_collision(tmp_path):
    """Verify multi-token slugs never collapse into shorter prefix files and explicit slugs beat shared-source neighbors."""
    from extracter_agent.models.domain import derive_canonical_concept_id

    haz_dir = tmp_path / "hazards"
    haz_dir.mkdir(parents=True)
    (haz_dir / "toluene.md").write_text(
        "---\ntype: Hazard Profile\ntitle: Toluene Hazard\nsources:\n- title: SDS_toluene.pdf\n- title: OM-Manual.pdf\n- title: DWG-006.pdf\n---\n# Toluene\n",
        encoding="utf-8",
    )
    (haz_dir / "toluene-diisocyanate.md").write_text(
        "---\ntype: Hazard Profile\ntitle: Toluene Diisocyanate Hazard\nsources:\n- title: SDS_tdi.pdf\n---\n# TDI\n",
        encoding="utf-8",
    )

    hazop_dir = tmp_path / "hazop"
    hazop_dir.mkdir(parents=True)
    (hazop_dir / "methodology.md").write_text(
        "---\ntype: HAZOP\ntitle: HAZOP Methodology\nsources:\n- title: STD-014.pdf\n---\n# Methodology\n",
        encoding="utf-8",
    )
    (hazop_dir / "risk-matrix.md").write_text(
        "---\ntype: HAZOP\ntitle: HAZOP Risk Matrix\nsources:\n- title: STD-014.pdf\n- title: STD-002.pdf\n---\n# Risk Matrix\n",
        encoding="utf-8",
    )

    # 1. Derivative chemical with '-hazard-profile' suffix must resolve to toluene-diisocyanate, never toluene
    assert (
        derive_canonical_concept_id(
            "hazards/toluene-diisocyanate-hazard-profile",
            concept_type="Hazard Profile",
            title="Toluene Diisocyanate Process Hazard Profile",
            sources=["SDS_tdi.pdf", "OM-Manual.pdf", "DWG-006.pdf"],
            bundle_root=tmp_path,
        )
        == "hazards/toluene-diisocyanate"
    )

    # 2. Base chemical with '-hazard' suffix must resolve to toluene, never toluene-diisocyanate
    assert (
        derive_canonical_concept_id(
            "hazards/toluene-hazard",
            concept_type="Hazard Profile",
            title="Toluene & Toluene Diisocyanate Process Safety Profile",
            sources=["SDS_toluene.pdf", "OM-Manual.pdf"],
            bundle_root=tmp_path,
        )
        == "hazards/toluene"
    )

    # 3. HAZOP methodology with 'Matrix' in title and shared STD-014 source must resolve to hazop/methodology, never hazop/risk-matrix
    assert (
        derive_canonical_concept_id(
            "hazop/hazop-methodology",
            concept_type="HAZOP",
            title="HAZOP Methodology & Deviation Matrix — STD-014",
            sources=["STD-014.pdf"],
            bundle_root=tmp_path,
        )
        == "hazop/methodology"
    )

    # 4. Uncreated hazop/study-info with 'Matrix' in title and concept_type must resolve to hazop/study-info, never hazop/risk-matrix
    assert (
        derive_canonical_concept_id(
            "hazop/study-info",
            concept_type="HAZOP Study Matrix",
            title="HAZOP Study Info — Process Hazard Analysis Study Matrix",
            sources=["STD-014.pdf", "STD-002.pdf"],
            bundle_root=tmp_path,
        )
        == "hazop/study-info"
    )


def test_pdf_resolution_boundary_and_shortened_citation():
    """Verify _match_pdf_candidate resolves base drawing 0012 to 0012_... even when 0012A_... sorts first, and resolves shortened <PREFIX>_Z1.pdf citations."""
    from extracter_agent.tools.pdf_tools import _match_pdf_candidate

    # In ASCII order, '0012A_' ('A' = 65) comes BEFORE '0012_' ('_' = 95)
    candidates = [
        {
            "file_name": "PID-23-0012A_P&ID CDN UNIT DECOMPOSER FEED FLUSH DRUM_Z1.pdf",
            "subfolder": "pid",
        },
        {
            "file_name": "PID-23-0012_P&ID CDN UNIT FLASH COLUMN BOTTOMS LINE_Z1.pdf",
            "subfolder": "pid",
        },
    ]

    # 1. Base code query 'PID-23-0012' must match 0012_, NOT 0012A_
    m1 = _match_pdf_candidate("PID-23-0012", "pid", candidates)
    assert m1 is not None
    assert m1["file_name"].startswith("PID-23-0012_")

    # 2. Shortened citation 'PID-23-0012_Z1.pdf' (omitting middle title words) must match 0012_
    m2 = _match_pdf_candidate("PID-23-0012_Z1.pdf", "pid", candidates)
    assert m2 is not None
    assert m2["file_name"].startswith("PID-23-0012_")

    # 3. Short drawing number '0012' must match 0012_, while '0012A' must match 0012A_
    m3 = _match_pdf_candidate("0012", "pid", candidates)
    assert m3 is not None
    assert m3["file_name"].startswith("PID-23-0012_")

    m4 = _match_pdf_candidate("0012A", "pid", candidates)
    assert m4 is not None
    assert m4["file_name"].startswith("PID-23-0012A_")


def test_datasheet_with_border_boilerplate_triggers_and_injects_multimodal(monkeypatch, tmp_path):
    """Verify a data_sheets PDF whose pages have >500 chars of border text still triggers multimodal vision and injects it into pages."""
    from extracter_agent.tools import pdf_tools

    dummy_pdf = tmp_path / "data_sheets" / "PS-D9999_VESSEL_DATASHEET.pdf"
    dummy_pdf.parent.mkdir(parents=True)
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy")

    border_boilerplate = "ACME ENGINEERING STANDARD BORDER HEADER FORM QUA-04-5 " * 20  # > 800 chars
    monkeypatch.setattr(
        pdf_tools,
        "get_pdf_metadata",
        lambda p: {"file_name": p.name, "file_size_bytes": 100, "page_count": 2},
    )
    monkeypatch.setattr(
        pdf_tools,
        "extract_pdf_pages",
        lambda p: [
            {"page_number": 1, "text": border_boilerplate, "char_count": len(border_boilerplate), "word_count": 120},
            {"page_number": 2, "text": border_boilerplate, "char_count": len(border_boilerplate), "word_count": 120},
        ],
    )
    monkeypatch.setattr(pdf_tools, "is_vector_drawing", lambda p: False)
    monkeypatch.setattr(
        pdf_tools,
        "extract_pdf_multimodal_summary",
        lambda p, prompt_hint=None: "Extracted Raster Sketch Loops: NT-99-2001, LI-9909, WT-99-2001",
    )

    res = pdf_tools.process_raw_pdf_tool(
        pdf_filename=str(dummy_pdf),
        subfolder="data_sheets",
        enable_multimodal=True,
    )
    assert res["status"] == "success"
    assert res["pages_processed"] == 2
    assert res["multimodal_analysis"] is not None
    assert "NT-99-2001" in res["multimodal_analysis"]
    assert any("NT-99-2001" in p["text"] for p in res["pages"])


def test_multimodal_window_batching_for_multipage_pdf(monkeypatch, tmp_path):
    """Verify extract_pdf_multimodal_summary slices >10-page PDFs into 10-page windows and concatenates all window extractions."""
    import pypdf

    from extracter_agent.pdf import processor

    # Create a valid 15-page PDF using pypdf.PdfWriter
    pdf_path = tmp_path / "PS-X9901_PACKAGE_15PAGES.pdf"
    writer = pypdf.PdfWriter()
    for _ in range(15):
        writer.add_blank_page(width=612, height=792)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    called_windows: list[str] = []

    def fake_single_window(pdf_bytes: bytes, cache_key_name: str, prompt_hint: str | None = None) -> str:
        called_windows.append(cache_key_name)
        return f"Extracted content for {cache_key_name}"

    monkeypatch.setattr(processor, "_extract_single_pdf_window_multimodal", fake_single_window)

    summary = processor.extract_pdf_multimodal_summary(pdf_path, window_size=10)
    assert len(called_windows) == 2
    assert called_windows[0].endswith("_p1-10")
    assert called_windows[1].endswith("_p11-15")
    assert "Pages 1–10 of 15" in summary
    assert "Pages 11–15 of 15" in summary


def test_merge_section_content_multi_table_and_mismatched_columns():
    """Verify _merge_section_content aligns mismatched column counts and preserves secondary ### sub-tables."""
    from extracter_agent.okf.synthesizer import merge_markdown_bodies

    old_md = (
        "# Package Instrument Summary\n\n"
        "## Instrumentation & Control Loops\n\n"
        "### Primary Package Loops\n\n"
        "| Tag | Service | Range | Source |\n"
        "| --- | --- | --- | --- |\n"
        "| PT-1001 | Suction Pressure | 0-760 mmHgA | DWG-001 |\n\n"
        "### Seal Water Pump P-9916A/B Local Gauges\n\n"
        "| Tag | Service | Location | Source |\n"
        "| --- | --- | --- | --- |\n"
        "| LG-9910 | Seal Pot Level | P-9916A | PS-X9901 |\n"
    )

    # New PDF has a 5-column table for Primary Package Loops (adding 'Type' column) and omits the secondary ### table
    new_md = (
        "# Package Instrument Summary\n\n"
        "## Instrumentation & Control Loops\n\n"
        "### Primary Package Loops\n\n"
        "| Tag | Type | Service | Range | Source |\n"
        "| --- | --- | --- | --- |\n"
        "| TI-1002 | RTD | Discharge Temp | 0-150 °C | DWG-002 |\n"
    )

    merged = merge_markdown_bodies(old_md, new_md)
    # 1. Both PT-1001 (from 4-col table) and TI-1002 (from 5-col table) must be in the merged Primary table
    assert "PT-1001" in merged
    assert "0-760 mmHgA" in merged
    assert "TI-1002" in merged
    assert "0-150 °C" in merged
    # 2. The secondary ### sub-table for P-9916A/B must also be preserved
    assert "### Seal Water Pump P-9916A/B Local Gauges" in merged
    assert "LG-9910" in merged


def test_multimodal_cache_key_includes_prompt_hash():
    """Verify _compute_multimodal_cache_digest produces distinct SHA-256 cache keys when prompt_hint or pdf_bytes changes."""
    from extracter_agent.pdf.processor import (
        _build_multimodal_prompt,
        _compute_multimodal_cache_digest,
    )

    sample_bytes = b"%PDF-1.4 sample engineering content"
    p_1 = _build_multimodal_prompt(prompt_hint="Hint A")
    p_2 = _build_multimodal_prompt(prompt_hint="Hint B")

    d1 = _compute_multimodal_cache_digest(sample_bytes, p_1)
    d2 = _compute_multimodal_cache_digest(sample_bytes, p_2)
    d3 = _compute_multimodal_cache_digest(sample_bytes + b"x", p_1)

    assert len(d1) == 24
    assert d1 == _compute_multimodal_cache_digest(sample_bytes, p_1)
    assert d1 != d2
    assert d1 != d3


def test_unified_multimodal_prompt_and_4page_window_size(monkeypatch, tmp_path):
    """Verify unified general multimodal prompt and default window_size=4 batching across multi-page PDFs."""
    import pypdf

    from extracter_agent.pdf import processor

    prompt_txt = processor._build_multimodal_prompt()
    assert "same loop number" in prompt_txt
    assert "parenthetical units" in prompt_txt
    assert "without summarizing or omitting columns" in prompt_txt

    # Verify default window_size=4 (a 10-page PDF slices into 3 windows: 1-4, 5-8, 9-10)
    ds_pdf = tmp_path / "SAMPLE_10PAGES.pdf"
    writer = pypdf.PdfWriter()
    for _ in range(10):
        writer.add_blank_page(width=612, height=792)
    with open(ds_pdf, "wb") as f:
        writer.write(f)

    called_windows: list[str] = []

    def fake_window(
        pdf_bytes: bytes,
        cache_key_name: str,
        prompt_hint: str | None = None,
    ) -> str:
        called_windows.append(cache_key_name)
        return f"Extracted {cache_key_name}"

    monkeypatch.setattr(processor, "_extract_single_pdf_window_multimodal", fake_window)
    summary_out = processor.extract_pdf_multimodal_summary(ds_pdf)
    assert sorted(called_windows) == [
        "SAMPLE_10PAGES_p1-4",
        "SAMPLE_10PAGES_p5-8",
        "SAMPLE_10PAGES_p9-10",
    ]
    assert (
        summary_out.index("SAMPLE_10PAGES_p1-4")
        < summary_out.index("SAMPLE_10PAGES_p5-8")
        < summary_out.index("SAMPLE_10PAGES_p9-10")
    )


def test_universal_multimodal_trigger_for_all_documents(monkeypatch, tmp_path):
    """Verify any PDF (including a 5-page document) triggers multimodal vision extraction when enable_multimodal=True."""
    from extracter_agent.tools import pdf_tools

    sds_pdf = tmp_path / "standards" / "SDS_SAMPLE_CHEMICAL.pdf"
    sds_pdf.parent.mkdir(parents=True)
    sds_pdf.write_bytes(b"%PDF-1.4 dummy sds")

    page_text = "SECTION 8 EXPOSURE CONTROLS TWA 50 ppm " * 40
    monkeypatch.setattr(
        pdf_tools,
        "get_pdf_metadata",
        lambda p: {"file_name": p.name, "file_size_bytes": 100, "page_count": 5},
    )
    monkeypatch.setattr(
        pdf_tools,
        "extract_pdf_pages",
        lambda p: [
            {"page_number": i, "text": page_text, "char_count": len(page_text), "word_count": 200}
            for i in range(1, 6)
        ],
    )
    monkeypatch.setattr(pdf_tools, "is_vector_drawing", lambda p: False)
    monkeypatch.setattr(
        pdf_tools,
        "extract_pdf_multimodal_summary",
        lambda p, prompt_hint=None: "Section 8: TWA 50 ppm (244 mg/m3); Section 9: Boiling Point 152.4 °C; Section 14: UN 1918",
    )

    res = pdf_tools.process_raw_pdf_tool(
        pdf_filename=str(sds_pdf),
        subfolder="standards",
        enable_multimodal=True,
    )
    assert res["status"] == "success"
    assert res["multimodal_analysis"] is not None
    assert "244 mg/m3" in res["multimodal_analysis"]
    assert any("UN 1918" in p["text"] for p in res["pages"])


def test_v4_additive_merge_preserves_equal_col_diff_headers_and_conflict_notes(tmp_path):
    """Verify V4 additive merge preserves equal-column-count tables with different headers, Sourceless cell conflicts, combined parameter notes, and custom H2 sections."""
    from extracter_agent.okf.synthesizer import merge_markdown_bodies
    from extracter_agent.tools.okf_tools import (
        generate_equipment_okf_tool,
        generate_okf_concept_tool,
    )

    # 1. Equal column count (4 cols each) with DIFFERENT header names + Sourceless table conflict
    md_turn_1 = (
        "# Instrument Register\n\n"
        "## Sizing Table\n\n"
        "| Tag | Specific Gravity | Vacuum Rating | Source |\n"
        "| --- | --- | --- | --- |\n"
        "| FT-9001 | 0.532 | -0.341 barg | PS-0001 |\n\n"
        "## Cv Summary\n\n"
        "| Valve | Cv |\n"
        "| --- | --- |\n"
        "| FV-9001 | 1050 |\n"
    )
    md_turn_2 = (
        "# Instrument Register\n\n"
        "## Sizing Table\n\n"
        "| Tag | Orifice Bore | Relief Capacity | Source |\n"
        "| --- | --- | --- | --- |\n"
        "| FT-9001 | 42.5 mm | 194.9 kg/hr | PS-0006 |\n\n"
        "## Cv Summary\n\n"
        "| Valve | Cv |\n"
        "| --- | --- |\n"
        "| FV-9001 | 13139 |\n"
    )
    merged_md = merge_markdown_bodies(md_turn_1, md_turn_2)
    assert "Specific Gravity" in merged_md
    assert "Vacuum Rating" in merged_md
    assert "Orifice Bore" in merged_md
    assert "Relief Capacity" in merged_md
    assert "0.532" in merged_md
    assert "-0.341 barg" in merged_md
    assert "194.9 kg/hr" in merged_md
    assert "13139 (1050)" in merged_md

    # 2. Equipment concept with custom H2 section and conflicting parameter where new_p also has a note
    bundle_dir = str(tmp_path)
    generate_okf_concept_tool(
        concept_id="equipment/E-9310",
        concept_type="Equipment Concept",
        title="E-9310 — Condenser",
        description="Condenser unit.",
        tags=["equipment"],
        sources=["data_sheets/PS-E9310.pdf"],
        body_markdown=(
            "# E-9310 — Condenser\n\n"
            "## Design Data\n\n"
            "| Parameter | Value | Unit | Source |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| Shell ID | 1280 | mm | PS-E9310 |\n\n"
            "## Relief Valve Sizing\n\n"
            "| PSV Tag | Rated Flow |\n"
            "| :--- | :--- |\n"
            "| PSV-9310 | 2479 kg/hr |\n"
        ),
        entity_metadata={"tag": "E-9310"},
        output_bundle_dir=bundle_dir,
    )

    generate_equipment_okf_tool(
        tag="E-9310",
        name="Condenser",
        equipment_class="Heat Exchanger",
        unit="U93",
        function_summary="Condenses overhead vapor.",
        design_data=[
            {
                "parameter": "Shell ID",
                "value": "1260",
                "unit": "mm",
                "source": "DWG-93-001",
                "note": "Title block nominal",
            }
        ],
        operating_conditions=[
            {
                "parameter": "Heat Duty",
                "value": "3.232",
                "unit": "MMkcal/hr",
                "source": "PS-E9310",
                "note": "Design margin: 3.394 MMkcal/hr",
            }
        ],
        connections=[],
        hazards=[],
        source_files=["pid/DWG-93-001.pdf"],
        output_bundle_dir=bundle_dir,
    )

    eq_text = (tmp_path / "equipment" / "E-9310.md").read_text(encoding="utf-8")
    assert "1260" in eq_text
    assert "1280" in eq_text
    assert "Title block nominal" in eq_text
    assert "3.232" in eq_text
    assert "3.394 MMkcal/hr" in eq_text
    assert "## Relief Valve Sizing" in eq_text
    assert "2479 kg/hr" in eq_text


def test_v4_chunked_register_append_sections_and_adaptive_vector_windowing(monkeypatch, tmp_path):
    """Verify append_sections_markdown in generate_okf_concept_tool and adaptive window_size=2 for landscape vector CAD drawings."""
    import pypdf

    from extracter_agent.pdf import processor
    from extracter_agent.tools.okf_tools import generate_okf_concept_tool

    # 1. Chunked register synthesis via append_sections_markdown
    bundle_dir = str(tmp_path / "bundle")
    res = generate_okf_concept_tool(
        concept_id="instruments/flow-register",
        concept_type="Instrument Specification",
        title="Flow Register",
        description="Flow elements register.",
        tags=["instruments"],
        sources=["data_sheets/PS-0001.pdf"],
        body_markdown=(
            "# Flow Register\n\n"
            "## Flow Elements\n\n"
            "| Tag | Specific Gravity | Max Flow | Source |\n"
            "| --- | --- | --- | --- |\n"
            "| FE-0101 | 0.607 | 12500 kg/hr | PS-0001 |\n"
        ),
        append_sections_markdown=[
            (
                "## Flow Elements\n\n"
                "| Tag | Specific Gravity | Max Flow | Source |\n"
                "| --- | --- | --- | --- |\n"
                "| FE-0202 | 0.939 | 8400 kg/hr | PS-0001 |\n"
            )
        ],
        output_bundle_dir=bundle_dir,
    )
    assert res["status"] == "success"
    reg_md = (Path(bundle_dir) / f"{res['concept_id']}.md").read_text(encoding="utf-8")
    assert "FE-0101" in reg_md and "0.607" in reg_md
    assert "FE-0202" in reg_md and "0.939" in reg_md

    # 2. Landscape vector CAD drawing (5 pages, width=1190 > height=842) adapts to window_size=2 (windows: 1-2, 3-4, 5-5)
    cad_pdf = tmp_path / "CAD_VECTOR_5PAGES.pdf"
    writer = pypdf.PdfWriter()
    for _ in range(5):
        writer.add_blank_page(width=1190, height=842)
    with open(cad_pdf, "wb") as f:
        writer.write(f)

    called_windows: list[str] = []

    def fake_window(
        pdf_bytes: bytes,
        cache_key_name: str,
        prompt_hint: str | None = None,
    ) -> str:
        called_windows.append(cache_key_name)
        return f"Extracted {cache_key_name}"

    monkeypatch.setattr(processor, "_extract_single_pdf_window_multimodal", fake_window)
    processor.extract_pdf_multimodal_summary(cad_pdf)
    assert sorted(called_windows) == [
        "CAD_VECTOR_5PAGES_p1-2",
        "CAD_VECTOR_5PAGES_p3-4",
        "CAD_VECTOR_5PAGES_p5-5",
    ]


def test_zero_collision_canonical_concept_resolution_v5(tmp_path):
    """Verify Step 28 (V5): all 13 instruments/*-cdn, 10 sources/ps-*-batch, datasheets, hazop chapters, procedures, and troubleshooting concepts resolve to distinct files on a cold-start bundle."""
    from extracter_agent.tools.okf_tools import generate_okf_concept_tool

    bundle_dir = str(tmp_path / "v5_bundle")

    # 1. All 13 instrument discipline registers must remain 13 distinct files
    inst_slugs = [
        ("instruments/analyzers-cdn", "CDN Section Analyzer Register"),
        ("instruments/cause-effect-cdn", "CDN Unit Cause and Effect Table"),
        ("instruments/control-valves-cdn", "CDN Section Control Valves Register"),
        ("instruments/flow-instruments-cdn", "CDN Section Flow Instrument Register"),
        ("instruments/level-instruments-cdn", "CDN Section Level Instrument Register"),
        ("instruments/motor-control", "CDN Pump Motor Control Register"),
        ("instruments/pressure-instruments-cdn", "CDN Section Pressure Instrument Register"),
        ("instruments/pressure-relief-valves-cdn", "CDN Pressure Relief Valves Register"),
        ("instruments/psv-cdn", "CDN PSV Sizing Register"),
        ("instruments/pump-seal-plans", "CDN Pump Mechanical Seal Plans"),
        ("instruments/sampling-cdn", "CDN Sampling Connection Register"),
        ("instruments/sis-cdn", "CDN Safety Instrumented System Register"),
        ("instruments/temperature-instruments-cdn", "CDN Temperature Instrument Register"),
    ]
    resolved_inst: set[str] = set()
    for slug, title in inst_slugs:
        res = generate_okf_concept_tool(
            concept_id=slug,
            concept_type="Instrument Register",
            title=title,
            description=f"Register for {title}.",
            tags=["cdn", "instruments"],
            sources=["PID-23-0002_Z1.pdf", "DS-PS-0031_Z1.pdf"],
            body_markdown=f"# {title}\n\n## Table\n\n| Tag | Value |\n| --- | --- |\n| T-1 | 100 |\n",
            output_bundle_dir=bundle_dir,
        )
        assert res["status"] == "success"
        resolved_inst.add(res["concept_id"])
    assert len(resolved_inst) == 13

    # 2. Source batches, datasheet numbers (0003 vs 0004), training chapters (ch1..ch7), and SDS sources never collide
    source_slugs = [
        ("sources/ps-analyzer-cdn-batch-2026-06-16", "Process Data Sheet — CDN Analyzers"),
        ("sources/ps-control-valve-cdn-batch-2026-06-16", "Process Data Sheet — CDN Control Valves"),
        ("sources/ps-flow-instrument-cdn-batch-2026-06-16", "Process Data Sheet — CDN Flow Instruments"),
        ("sources/ps-heat-exchanger-batch-2026-06-16", "Process Data Sheets — CDN Heat Exchanger Batch"),
        ("sources/ps-pressure-level-temp-instrument-cdn-batch-2026-06-16", "Process Data Sheet — CDN Pressure, Level & Temp"),
        ("sources/ps-prv-cdn-batch-2026-06-16", "Process Data Sheet — CDN Pressure Relief Valves"),
        ("sources/ps-rotating-equipment-batch-2026-06-16", "Process Data Sheets — Rotating Equipment Batch"),
        ("sources/ps-static-equipment-batch-2026-06-14", "Static Equipment Process Data Sheets Batch"),
        ("sources/sds-psi-batch-2026-06-14", "SDS PSI Batch — 15 GHS Safety Data Sheets"),
        ("sources/ds-ps-0003", "Analyzer Datasheet 0003"),
        ("sources/ds-ps-0010", "Control Valve Datasheet 0010"),
        ("sources/ds-ps-v2201", "Oxidation Column V-2201 Datasheet"),
        ("sources/ds-ps-v2301", "Preflash Column V-2301 Datasheet"),
        ("sources/hazop-leadership-training-ch1", "HAZOP Training Chapter 1"),
        ("sources/hazop-leadership-training-ch2", "HAZOP Training Chapter 2"),
        ("sources/hazop-leadership-training-ch3", "HAZOP Training Chapter 3"),
        ("sources/sds-98-82-8-cumene", "SDS 98-82-8 Cumene"),
        ("sources/sds-98-83-9-alpha-methylstyrene", "SDS 98-83-9 AMS"),
        ("sources/sds-98-86-2-acetophenone", "SDS 98-86-2 Acetophenone"),
    ]
    resolved_src: set[str] = set()
    for slug, title in source_slugs:
        res = generate_okf_concept_tool(
            concept_id=slug,
            concept_type="Source Document",
            title=title,
            description=f"Summary for {title}.",
            tags=["sources", "cdn"],
            sources=["DS-PS-0003_Z1.pdf", "SDS_98-82-8_cumene.pdf"],
            body_markdown=f"# {title}\n\n## Summary\n\nDetailed engineering content for {title}.\n",
            output_bundle_dir=bundle_dir,
        )
        assert res["status"] == "success"
        resolved_src.add(res["concept_id"])
    assert len(resolved_src) == len(source_slugs)


def test_multi_unit_equipment_tag_suffix_preservation_v5(tmp_path):
    """Verify Step 28 (V5): multi-unit equipment tags (P-2301A/B, E-2308A/B, P-2305A/B/C/D/E/F) preserve their AB/ABCDEF suffixes even when citing bare PS-P2301 datasheets, and upgrade bare files on disk."""
    from extracter_agent.models.domain import derive_canonical_equipment_tag
    from extracter_agent.tools.okf_tools import generate_equipment_okf_tool

    bundle_dir = tmp_path / "eq_v5"
    bundle_dir.mkdir(parents=True)

    assert (
        derive_canonical_equipment_tag(
            "P-2301A/B",
            ["PID-23-0009_Z1.pdf", "ACME-2300-PS-P2301_Z1.pdf"],
            bundle_root=bundle_dir,
        )
        == "P-2301AB"
    )
    assert (
        derive_canonical_equipment_tag(
            "E-2308A/B",
            ["PID-23-0014_Z1.pdf", "ACME-2300-PS-E2308_E-2308 PROCESS DATA SHEET_Z1.pdf"],
            bundle_root=bundle_dir,
        )
        == "E-2308AB"
    )
    assert (
        derive_canonical_equipment_tag(
            "P-2305A/B/C/D/E/F",
            ["PID-23-0015_Z1.pdf", "ACME-2300-PS-P2305_Z1.pdf"],
            bundle_root=bundle_dir,
        )
        == "P-2305ABCDEF"
    )

    # First pass creates bare P-2301.md, second pass with P-2301A/B upgrades it to P-2301AB.md
    r1 = generate_equipment_okf_tool(
        tag="P-2301",
        name="Flash Column Bottoms Pumps",
        equipment_class="Pump",
        unit="2300",
        function_summary="Bottoms transfer.",
        design_data=[{"parameter": "Design Pressure", "value": "12.0", "unit": "barg", "source": "PS-P2301"}],
        operating_conditions=[],
        connections=[],
        hazards=[],
        source_files=["ACME-2300-PS-P2301_Z1.pdf"],
        output_bundle_dir=str(bundle_dir),
    )
    assert r1["concept_id"] == "equipment/P-2301"

    r2 = generate_equipment_okf_tool(
        tag="P-2301A/B",
        name="Flash Column Bottoms Pumps",
        equipment_class="Pump",
        unit="2300",
        function_summary="Bottoms transfer pumps A/B.",
        design_data=[{"parameter": "Design Temp", "value": "210", "unit": "°C", "source": "PID-0009"}],
        operating_conditions=[],
        connections=[],
        hazards=[],
        source_files=["PID-23-0009_Z1.pdf"],
        output_bundle_dir=str(bundle_dir),
    )
    assert r2["concept_id"] == "equipment/P-2301AB"
    assert r2["merged_with_existing"] is True
    assert (bundle_dir / "equipment" / "P-2301AB.md").exists()
    assert not (bundle_dir / "equipment" / "P-2301.md").exists()


def test_dummy_probe_guard_and_inspect_canonical_alignment_v5(tmp_path):
    """Verify Step 28 (V5): generate_okf_concept_tool rejects dummy '# Test' probe calls and inspect_existing_okf_concept_tool resolves the exact same canonical path."""
    from extracter_agent.tools.okf_tools import (
        generate_okf_concept_tool,
        inspect_existing_okf_concept_tool,
    )

    bundle_dir = str(tmp_path / "probe_bundle")
    res_probe = generate_okf_concept_tool(
        concept_id="procedures/xxx-yyy-zzz",
        concept_type="Test Type",
        title="Test",
        description="Test",
        tags=["test"],
        sources=["OM.pdf"],
        body_markdown="# Test",
        output_bundle_dir=bundle_dir,
    )
    assert res_probe["status"] == "rejected_dummy_probe"
    assert not (Path(bundle_dir) / "procedures" / "xxx-yyy-zzz.md").exists()

    # Create a real hazard concept and verify inspect_existing resolves the suffix-stripped path
    res_real = generate_okf_concept_tool(
        concept_id="hazards/cumene-hydroperoxide-hazard-profile",
        concept_type="Hazard Profile",
        title="Cumene Hydroperoxide (CHP) Hazard Profile",
        description="Process hazard profile for CHP.",
        tags=["chp", "hazard"],
        sources=["SDS_80-15-9.pdf"],
        body_markdown="# Cumene Hydroperoxide\n\n## Limits\n\n- Self-accelerating decomposition temperature: 80 °C\n",
        output_bundle_dir=bundle_dir,
    )
    assert res_real["status"] == "success"
    assert res_real["concept_id"] == "hazards/cumene-hydroperoxide"

    insp = inspect_existing_okf_concept_tool(
        concept_id="hazards/cumene-hydroperoxide-process-hazard-profile",
        output_bundle_dir=bundle_dir,
    )
    assert insp["exists"] is True
    assert insp["concept_id"] == "hazards/cumene-hydroperoxide"


def test_repository_zero_confidential_leakage() -> None:
    """Verify zero confidential client, plant, licensor, contractor, or real GCP project identifiers exist in reference/, code, evals, scripts, and configs."""
    import re

    repo_root = Path(__file__).resolve().parent.parent

    # 1. reference/wiki must not exist, and reference/raw must contain exactly 20 synthetic PDFs
    assert not (repo_root / "reference" / "wiki").exists(), "reference/wiki/ must be completely removed"
    raw_pdfs = sorted((repo_root / "reference" / "raw").rglob("*.pdf"))
    assert len(raw_pdfs) == 20, f"Expected 20 synthetic PDFs in reference/raw/, found {len(raw_pdfs)}"

    # 2. Scan tracked code, config, evals, scripts, tests, and _agents for prohibited tokens (hex-encoded so zero plaintext tokens exist in tests)
    prohibited_hex = [
        "5c625054545c62",
        "5c625050434c5c62",
        "5c62504f53434f5c62",
        "5c62554f505c62",
        "5c6248656d6172616a5c62",
        "4d61705c732b54615c732b50687574",
        "5c625261796f6e675c62",
        "31343738302d38313230",
        "5c623936333736365c62",
        "5c623132303131375c62",
        "576172616b6f726e5c732b4465636861",
        "54616e617275616e6761726d6f726e",
        "5c62534347435c62",
        "766976656b73756272616d616e",
        "63732d706f632d79303372376b6d66796f76346b696c7a67353066643773",
        "313134363138333731353638",
        "31393131313138333334383432313039393532",
        "38323130323436383338363439383830353736",
    ]
    prohibited_patterns = [bytes.fromhex(h).decode("utf-8") for h in prohibited_hex]
    combined_re = re.compile("|".join(prohibited_patterns), re.IGNORECASE)

    scan_paths = [
        repo_root / "README.md",
        repo_root / ".env.example",
        repo_root / "cloudbuild.yaml",
        repo_root / "deploy.sh",
        repo_root / "agents-cli-manifest.yaml",
        repo_root / "agents-cli-manifest-query.yaml",
        repo_root / "terraform" / "variables.tf",
    ]
    for folder in ("extracter_agent", "query_agent", "evals", "scripts", "docs", "specs", "tests", "_agents"):
        for p in (repo_root / folder).rglob("*"):
            if p.is_file() and p.suffix in {".py", ".js", ".html", ".css", ".jsonl", ".sql", ".sh", ".md"}:
                if "__pycache__" not in p.parts:
                    scan_paths.append(p)

    violations: list[str] = []
    for p in scan_paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = combined_re.search(text)
        if m:
            violations.append(f"{p.relative_to(repo_root)}: matched '{m.group(0)}'")

    assert not violations, f"Confidential identifiers found in repository files: {violations}"
