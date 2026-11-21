"""Deterministic Unit Tests and Hypothesis Property-Based Tests (PBT) for Step 2:
Multi-Format Raw Document Ingestion (.xlsx, .xlsm, .csv, .docx, .png/.jpg/.webp),
XXE/Zip-Bomb Security Hardening, Web Server Streaming, and MOC Priority Ordering.
"""

from __future__ import annotations

import struct
import xml.sax.saxutils as saxutils
import zipfile
import zlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st

from evals.builders.build_file_by_file_eval_dataset import (
    SUBFOLDER_PRIORITY,
    generate_raw_file_by_file_eval_dataset,
)
from extracter_agent.pdf.ooxml_parser import (
    OOXMLProcessingError,
    _col_index_to_letters,
    _safe_parse_xml,
    extract_csv_pages,
    extract_docx_pages,
    extract_xlsx_pages,
)
from extracter_agent.pdf.processor import (
    PDFProcessingError,
    SUPPORTED_RAW_EXTENSIONS,
    get_image_dimensions,
    get_pdf_metadata,
    get_raw_mime_type,
    is_supported_raw_file,
    search_raw_documents,
)
from extracter_agent.tools.pdf_tools import process_raw_pdf_tool
from extracter_agent.web_server import create_web_app


def _make_minimal_png(width: int = 32, height: int = 24) -> bytes:
    """Create a valid uncompressed RGB PNG image in pure Python stdlib."""
    def _chunk(ctype: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)

    raw_rows = b"".join(b"\x00" + (b"\x10\x80\xf0" * width) for _ in range(height))
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _chunk(b"IDAT", zlib.compress(raw_rows)),
            _chunk(b"IEND", b""),
        ]
    )


def _write_synthetic_xlsx(
    dest: Path,
    sheets: list[dict[str, Any]],
    shared_strings: list[str] | None = None,
) -> None:
    """Write a valid ECMA-376 .xlsx ZIP archive for deterministic and PBT testing."""
    ss_list = list(shared_strings or [])
    wb_sheets_xml: list[str] = []
    rels_xml: list[str] = []

    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, sh in enumerate(sheets, start=1):
            sname = saxutils.escape(sh["name"])
            state = saxutils.escape(sh.get("state", "visible"))
            wb_sheets_xml.append(
                f'<sheet name="{sname}" sheetId="{idx}" state="{state}" r:id="rId{idx}"/>'
            )
            rels_xml.append(
                f'<Relationship Id="rId{idx}" '
                f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{idx}.xml"/>'
            )

            rows_by_r: dict[int, list[tuple[int, dict[str, Any]]]] = {}
            for (r_idx, c_idx), cell_spec in sorted(sh.get("cells", {}).items()):
                rows_by_r.setdefault(r_idx, []).append((c_idx, cell_spec))

            row_xml_parts: list[str] = []
            for r_idx, cols in sorted(rows_by_r.items()):
                c_xml_parts: list[str] = []
                for c_idx, cspec in cols:
                    coord = f"{_col_index_to_letters(c_idx)}{r_idx}"
                    kind = cspec.get("kind", "inline")
                    val = str(cspec.get("value", ""))
                    formula = cspec.get("formula")
                    f_tag = f"<f>{saxutils.escape(formula)}</f>" if formula else ""
                    if kind == "shared":
                        if val not in ss_list:
                            ss_list.append(val)
                        s_idx = ss_list.index(val)
                        c_xml_parts.append(f'<c r="{coord}" t="s">{f_tag}<v>{s_idx}</v></c>')
                    elif kind == "number":
                        c_xml_parts.append(f'<c r="{coord}">{f_tag}<v>{saxutils.escape(val)}</v></c>')
                    elif kind == "formula_only":
                        c_xml_parts.append(f'<c r="{coord}">{f_tag}</c>')
                    else:
                        c_xml_parts.append(
                            f'<c r="{coord}" t="inlineStr"><is><t>{saxutils.escape(val)}</t></is></c>'
                        )
                row_xml_parts.append(f'<row r="{r_idx}">{"".join(c_xml_parts)}</row>')

            merges = sh.get("merges", [])
            merge_xml = ""
            if merges:
                m_items = "".join(f'<mergeCell ref="{m}"/>' for m in merges)
                merge_xml = f'<mergeCells count="{len(merges)}">{m_items}</mergeCells>'

            ws_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{''.join(row_xml_parts)}</sheetData>"
                f"{merge_xml}"
                "</worksheet>"
            )
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", ws_xml.encode("utf-8"))

        if ss_list:
            si_items = "".join(f"<si><t>{saxutils.escape(s)}</t></si>" for s in ss_list)
            ss_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(ss_list)}" uniqueCount="{len(ss_list)}">'
                f"{si_items}</sst>"
            )
            zf.writestr("xl/sharedStrings.xml", ss_xml.encode("utf-8"))

        wb_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{''.join(wb_sheets_xml)}</sheets>"
            "</workbook>"
        )
        zf.writestr("xl/workbook.xml", wb_xml.encode("utf-8"))

        wb_rels = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{''.join(rels_xml)}"
            "</Relationships>"
        )
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels.encode("utf-8"))


def _write_synthetic_docx(
    dest: Path,
    paragraphs: list[tuple[str | None, str]],
    tables: list[list[list[str]]],
    header_text: str | None = None,
) -> None:
    """Write a valid ECMA-376 .docx ZIP archive with styled paragraphs, tables, and optional header."""
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body_parts: list[str] = []

    for style, text in paragraphs:
        ppr = f'<w:pPr><w:pStyle w:val="{saxutils.escape(style)}"/></w:pPr>' if style else ""
        body_parts.append(f"<w:p>{ppr}<w:r><w:t>{saxutils.escape(text)}</w:t></w:r></w:p>")

    for tbl in tables:
        tr_parts: list[str] = []
        for row in tbl:
            tc_parts = [
                f"<w:tc><w:p><w:r><w:t>{saxutils.escape(cell)}</w:t></w:r></w:p></w:tc>"
                for cell in row
            ]
            tr_parts.append(f"<w:tr>{''.join(tc_parts)}</w:tr>")
        body_parts.append(f"<w:tbl>{''.join(tr_parts)}</w:tbl>")

    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{w_ns}"><w:body>{"".join(body_parts)}</w:body></w:document>'
    )
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", doc_xml.encode("utf-8"))
        if header_text:
            hdr_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<w:hdr xmlns:w="{w_ns}"><w:p><w:r><w:t>{saxutils.escape(header_text)}</w:t></w:r></w:p></w:hdr>'
            )
            zf.writestr("word/header1.xml", hdr_xml.encode("utf-8"))


def test_real_standards_xlsm_xlsx_and_png_ingestion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify native ingestion of the 4 real non-PDF engineering files in reference/raw/standards/."""
    standards_dir = Path("reference/raw/standards")
    if not (standards_dir / "GC_ePHA_Template_v5.0(Risk Ranking).xlsm").exists():
        pytest.skip("Real standards workbooks not present on disk")

    monkeypatch.setenv("USE_GCS_STORAGE", "false")

    # 1. Macro-enabled Excel ePHA template (.xlsm)
    res_xlsm = process_raw_pdf_tool(
        pdf_filename="GC_ePHA_Template_v5.0(Risk Ranking).xlsm",
        subfolder="standards",
        enable_multimodal=True,
    )
    assert res_xlsm["status"] == "success"
    assert res_xlsm["pages_processed"] >= 5
    assert res_xlsm["multimodal_analysis"] is None  # Native OOXML parsing needs zero PDF vision
    assert "Worksheet: Risk Ranking [Visibility: visible]" in res_xlsm["pages"][0]["text"]
    assert "Level 5:" in res_xlsm["pages"][0]["text"]
    assert "Extreme" in res_xlsm["pages"][0]["text"]

    # 2. PSI & P&ID Readiness Checklists (.xlsx)
    for xlsx_name in (
        "Table A6.2-2 PSI readiness checklist (Final R1).xlsx",
        "Table A6.2-3 PID readiness checklist (Fianl R1).xlsx",
    ):
        res_xlsx = process_raw_pdf_tool(
            pdf_filename=xlsx_name,
            subfolder="standards",
            enable_multimodal=True,
        )
        assert res_xlsx["status"] == "success"
        assert res_xlsx["pages_processed"] == 2
        assert "readiness checklist for HAZOP Study" in res_xlsx["pages"][0]["text"]

    # 3. Standalone Risk Ranking Matrix (.png) metadata + mocked Gemini vision
    png_path = standards_dir / "Risk Ranking Matrix.png"
    meta_png = get_pdf_metadata(png_path)
    assert meta_png["mime_type"] == "image/png"
    assert meta_png["image_width"] > 100
    assert meta_png["image_height"] > 100

    with patch(
        "extracter_agent.tools.pdf_tools.extract_image_multimodal_summary",
        return_value="| Severity | Likelihood | Risk Level |\n| --- | --- | --- |\n| 5 | Frequent | Extreme |",
    ) as mock_vision:
        res_png = process_raw_pdf_tool(
            pdf_filename="Risk Ranking Matrix.png",
            subfolder="standards",
            enable_multimodal=True,
        )
        assert res_png["status"] == "success"
        assert mock_vision.call_count == 1
        assert "Extreme" in res_png["pages"][0]["text"]


def test_csv_docx_security_and_moc_dataset_ordering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify CSV/DOCX extraction, XXE & zip-slip rejection, web MIME streaming, and MOC-last ordering."""
    # 1. CSV extraction
    csv_file = tmp_path / "valve_schedule.csv"
    csv_file.write_text("Tag,Set Pressure,Unit\nPSV-901,14.5,barg\nPSV-902,22.0,barg\n", encoding="utf-8")
    csv_pages = extract_csv_pages(csv_file)
    assert len(csv_pages) == 1
    assert "PSV-901" in csv_pages[0]["text"]
    assert "14.5" in csv_pages[0]["text"]

    # 2. DOCX extraction with header metadata, headings, and table
    docx_file = tmp_path / "MOC-2026-009.docx"
    _write_synthetic_docx(
        docx_file,
        paragraphs=[("Heading1", "Management of Change Dossier"), (None, "Bypass line modification.")],
        tables=[[["Parameter", "Old", "New"], ["Design Temp", "150 C", "185 C"]]],
        header_text="Doc Code: MOC-2026-009 Rev A",
    )
    docx_pages = extract_docx_pages(docx_file)
    assert len(docx_pages) == 1
    assert "MOC-2026-009 Rev A" in docx_pages[0]["text"]
    assert "# Management of Change Dossier" in docx_pages[0]["text"]
    assert "| Design Temp | 150 C | 185 C |" in docx_pages[0]["text"]

    # 3. Security hardening: XXE / ENTITY rejection & ZIP path traversal rejection
    xxe_payload = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b"<root>&xxe;</root>"
    )
    with pytest.raises(OOXMLProcessingError, match="DOCTYPE or ENTITY"):
        _safe_parse_xml(xxe_payload)

    zip_slip = tmp_path / "slip.xlsx"
    with zipfile.ZipFile(zip_slip, "w") as zf:
        zf.writestr("../../evil.xml", b"<root/>")
    with pytest.raises(PDFProcessingError, match="Path traversal"):
        get_pdf_metadata(zip_slip)

    # 4. Dataset builder: excludes README.md/.DS_Store and orders moc LAST (priority 5)
    raw_root = tmp_path / "raw"
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    for sf in ("data_sheets", "moc", "standards"):
        (raw_root / sf).mkdir(parents=True)
        (raw_root / sf / "README.md").write_text("# Guide\n", encoding="utf-8")

    (raw_root / "standards" / ".DS_Store").write_bytes(b"\x00\x01")
    _write_synthetic_xlsx(
        raw_root / "data_sheets" / "DS-100.xlsx",
        sheets=[{"name": "Sheet1", "cells": {(1, 1): {"value": "Tag"}, (2, 1): {"value": "P-100"}}}],
    )
    _write_synthetic_docx(
        raw_root / "moc" / "MOC-001.docx",
        paragraphs=[(None, "MOC change")],
        tables=[],
    )
    (raw_root / "standards" / "Matrix.png").write_bytes(_make_minimal_png(40, 30))

    out_jsonl = tmp_path / "dataset.jsonl"
    summary = generate_raw_file_by_file_eval_dataset(raw_root, wiki_root, out_jsonl)
    assert summary["total_raw_files"] == 3
    assert SUBFOLDER_PRIORITY["moc"] == 5
    lines = [ln for ln in out_jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 3
    assert '"subfolder": "data_sheets"' in lines[0]
    assert '"subfolder": "standards"' in lines[1]
    assert '"subfolder": "moc"' in lines[2]  # MOC strictly ordered last!

    # 5. FastAPI /api/raw-pdf streaming MIME types & README/traversal rejection
    monkeypatch.setenv("USE_GCS_STORAGE", "false")
    monkeypatch.setenv("REFERENCE_RAW_DIR", str(raw_root))
    monkeypatch.setenv("OUTPUT_BUNDLE_DIR", str(tmp_path / "bundle"))
    client = TestClient(create_web_app())

    resp_xlsx = client.get("/api/raw-pdf/data_sheets/DS-100.xlsx")
    assert resp_xlsx.status_code == 200
    assert resp_xlsx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    resp_png = client.get("/api/raw-pdf/standards/Matrix.png")
    assert resp_png.status_code == 200
    assert resp_png.headers["content-type"].startswith("image/png")

    resp_readme = client.get("/api/raw-pdf/moc/README.md")
    assert resp_readme.status_code == 400

    assert len(search_raw_documents("", raw_root)) == 3
    for ext in SUPPORTED_RAW_EXTENSIONS:
        assert is_supported_raw_file(f"sample{ext}")
        assert get_raw_mime_type(f"sample{ext}") != "application/octet-stream"


_SAFE_CELL_TEXT = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
        whitelist_characters="-_./:|()%+",
    ),
    min_size=1,
    max_size=24,
).map(str.strip).filter(lambda s: len(s) >= 1)


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    sheet1_cells=st.dictionaries(
        keys=st.tuples(st.integers(1, 8), st.integers(1, 6)),
        values=_SAFE_CELL_TEXT,
        min_size=1,
        max_size=12,
    ),
    sheet2_nums=st.dictionaries(
        keys=st.tuples(st.integers(1, 6), st.integers(1, 5)),
        values=st.integers(-5000, 5000).map(str),
        min_size=1,
        max_size=8,
    ),
    formula_expr=st.sampled_from(["SUM(A1:A5)", "MAX(B1:B4)", "IF(A1>0,1,0)"]),
)
def test_pbt_ooxml_xlsx_roundtrip_preserves_all_nonempty_cells(
    tmp_path: Path,
    sheet1_cells: dict[tuple[int, int], str],
    sheet2_nums: dict[tuple[int, int], str],
    formula_expr: str,
) -> None:
    """PBT: Randomized multi-sheet .xlsx workbooks (shared strings, inline strings, numbers, formulas, merges) preserve 100% of non-empty cell values."""
    xlsx_path = tmp_path / "pbt_workbook.xlsx"
    s1_spec: dict[tuple[int, int], dict[str, Any]] = {}
    for idx, (rc, val) in enumerate(sheet1_cells.items()):
        s1_spec[rc] = {"kind": "shared" if idx % 2 == 0 else "inline", "value": val}

    s2_spec: dict[tuple[int, int], dict[str, Any]] = {
        rc: {"kind": "number", "value": val} for rc, val in sheet2_nums.items()
    }
    s2_spec[(9, 1)] = {"kind": "formula_only", "formula": formula_expr}

    _write_synthetic_xlsx(
        xlsx_path,
        sheets=[
            {"name": "VisibleSpec", "state": "visible", "cells": s1_spec, "merges": ["A1:B1"]},
            {"name": "HiddenCalc", "state": "hidden", "cells": s2_spec},
        ],
    )

    pages = extract_xlsx_pages(xlsx_path)
    assert len(pages) == 2
    assert pages[0]["visibility"] == "visible"
    assert pages[1]["visibility"] == "hidden"

    combined_md = "\n".join(p["text"] for p in pages)
    for val in sheet1_cells.values():
        escaped_expected = val.replace("|", "\\|")
        assert escaped_expected in combined_md

    for num_val in sheet2_nums.values():
        assert num_val in combined_md

    assert f"={formula_expr}" in combined_md


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    paragraphs=st.lists(
        st.tuples(
            st.sampled_from([None, "Heading1", "Heading2"]),
            _SAFE_CELL_TEXT,
        ),
        min_size=1,
        max_size=6,
    ),
    table_rows=st.lists(
        st.lists(_SAFE_CELL_TEXT, min_size=2, max_size=4),
        min_size=2,
        max_size=5,
    ),
)
def test_pbt_ooxml_docx_roundtrip_preserves_paragraphs_and_table_cells(
    tmp_path: Path,
    paragraphs: list[tuple[str | None, str]],
    table_rows: list[list[str]],
) -> None:
    """PBT: Randomized .docx documents preserve 100% of paragraph runs and table cell texts."""
    max_cols = max(len(r) for r in table_rows)
    norm_rows = [r + ["N/A"] * (max_cols - len(r)) for r in table_rows]

    docx_path = tmp_path / "pbt_procedure.docx"
    _write_synthetic_docx(docx_path, paragraphs=paragraphs, tables=[norm_rows])

    pages = extract_docx_pages(docx_path)
    combined_md = "\n".join(p["text"] for p in pages)

    for style, text in paragraphs:
        assert text in combined_md
        if style == "Heading1":
            assert f"# {text}" in combined_md
        elif style == "Heading2":
            assert f"## {text}" in combined_md

    for row in norm_rows:
        for cell in row:
            assert cell.replace("|", "\\|") in combined_md
