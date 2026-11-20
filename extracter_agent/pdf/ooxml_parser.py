"""Deterministic, XXE/zip-bomb-hardened OOXML (.xlsx, .xlsm, .docx) and CSV parser.

Extracts multi-sheet workbooks, formulas, cached values, merged cell spans,
Word paragraphs/headings/tables, and CSV files into GitHub-Flavored Markdown
pages using pure Python standard library modules.
"""

from __future__ import annotations

import csv
import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET  # nosec B405 - guarded by _safe_parse_xml DTD/ENTITY rejection
from pathlib import Path
from typing import Any

MAX_ZIP_MEMBERS: int = 2000
MAX_MEMBER_UNCOMPRESSED_BYTES: int = 64 * 1024 * 1024  # 64 MiB per XML member
MAX_TOTAL_UNCOMPRESSED_BYTES: int = 128 * 1024 * 1024  # 128 MiB across archive
MAX_MERGE_PROPAGATE_ROWS: int = 25
MAX_MERGE_PROPAGATE_COLS: int = 25
MAX_MERGE_RANGES_PER_SHEET: int = 5000
MAX_FORMULA_NOTES_PER_SHEET: int = 60
CSV_ROWS_PER_PAGE: int = 200
DOCX_CHARS_PER_PAGE: int = 6000

_XML_FORBIDDEN_DECL_TEXT_RE = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_XML_ENCODING_ATTR_RE = re.compile(r'(<\?xml\b[^>]*?)\s+encoding\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
_CELL_COORD_RE = re.compile(r"^([A-Za-z]+)(\d+)$")
_FLOAT_NOISE_RE = re.compile(r"^-?\d+\.\d{10,}$")


class OOXMLProcessingError(Exception):
    """Raised when an OOXML or CSV document fails validation or parsing."""


def _local_tag(tag: str) -> str:
    """Strip XML namespace URI from an ElementTree tag string."""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _decode_xml_to_text(xml_bytes: bytes) -> str:
    """Decode XML bytes (UTF-8/UTF-16/UTF-32 with or without BOM) into Unicode text."""
    if xml_bytes.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        enc = "utf-32"
    elif xml_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        enc = "utf-16"
    elif xml_bytes.startswith(b"\xef\xbb\xbf"):
        enc = "utf-8-sig"
    elif b"\x00" in xml_bytes[:64]:
        # Detect BOM-less UTF-16/UTF-32 streams before regex inspection
        if xml_bytes[:4] in (b"<\x00\x00\x00", b"\x00\x00\x00<"):
            enc = "utf-32-le" if xml_bytes[0] != 0 else "utf-32-be"
        else:
            enc = "utf-16-le" if xml_bytes[0] != 0 else "utf-16-be"
    else:
        enc = "utf-8"
    try:
        return xml_bytes.decode(enc)
    except UnicodeDecodeError as exc:
        raise OOXMLProcessingError(f"Invalid XML character encoding ({enc}): {exc}") from exc


def _safe_parse_xml(xml_bytes: bytes) -> ET.Element:
    """Parse XML bytes after rejecting any DOCTYPE or ENTITY declarations across all encodings."""
    if len(xml_bytes) > MAX_MEMBER_UNCOMPRESSED_BYTES:
        raise OOXMLProcessingError(
            f"XML member exceeds maximum uncompressed size ({len(xml_bytes)} > {MAX_MEMBER_UNCOMPRESSED_BYTES} bytes)"
        )
    xml_text = _decode_xml_to_text(xml_bytes)
    if "\x00" in xml_text or _XML_FORBIDDEN_DECL_TEXT_RE.search(xml_text):
        raise OOXMLProcessingError(
            "XML contains forbidden DOCTYPE or ENTITY declaration (XXE/entity expansion blocked)"
        )
    normalized_xml = _XML_ENCODING_ATTR_RE.sub(r"\1", xml_text, count=1).encode("utf-8")
    try:
        return ET.fromstring(normalized_xml)  # nosec B314 - decoded & DOCTYPE/ENTITY explicitly rejected above
    except ET.ParseError as exc:
        raise OOXMLProcessingError(f"Malformed XML stream: {exc}") from exc


def _validate_and_open_ooxml_zip(path: Path) -> zipfile.ZipFile:
    """Open an OOXML ZIP archive after verifying member count, path confinement, and uncompressed sizes."""
    if not path.exists():
        raise OOXMLProcessingError(f"Document file does not exist: {path}")
    try:
        zf = zipfile.ZipFile(path, "r")
    except Exception as exc:
        raise OOXMLProcessingError(f"Invalid OOXML ZIP archive {path}: {exc}") from exc

    infos = zf.infolist()
    if len(infos) > MAX_ZIP_MEMBERS:
        zf.close()
        raise OOXMLProcessingError(
            f"OOXML archive {path.name} has {len(infos)} members (max {MAX_ZIP_MEMBERS})"
        )

    total_xml_uncompressed = 0
    for info in infos:
        fname = info.filename
        if "\x00" in fname or fname.startswith(("/", "\\")) or "\\" in fname:
            zf.close()
            raise OOXMLProcessingError(f"Unsafe archive member path in {path.name}: {fname!r}")
        norm_parts = posixpath.normpath(fname).split("/")
        if ".." in norm_parts:
            zf.close()
            raise OOXMLProcessingError(f"Path traversal member detected in {path.name}: {fname!r}")
        if fname.lower().endswith((".xml", ".rels")):
            if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                zf.close()
                raise OOXMLProcessingError(
                    f"Archive XML member {fname} exceeds {MAX_MEMBER_UNCOMPRESSED_BYTES} bytes"
                )
            total_xml_uncompressed += info.file_size
            if total_xml_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                zf.close()
                raise OOXMLProcessingError(
                    f"Archive total XML size exceeds {MAX_TOTAL_UNCOMPRESSED_BYTES} bytes"
                )

    return zf


def _read_zip_xml(zf: zipfile.ZipFile, member_name: str) -> ET.Element:
    """Safely read and parse an XML member from a validated ZipFile."""
    with zf.open(member_name, "r") as fp:
        data = fp.read(MAX_MEMBER_UNCOMPRESSED_BYTES + 1)
    return _safe_parse_xml(data)


def _extract_ooxml_core_props(zf: zipfile.ZipFile, fallback_title: str) -> dict[str, str | None]:
    """Read title and creator from docProps/core.xml when present."""
    props: dict[str, str | None] = {"title": None, "author": None, "creator": None}
    if "docProps/core.xml" in zf.namelist():
        try:
            root = _read_zip_xml(zf, "docProps/core.xml")
            for elem in root.iter():
                ltag = _local_tag(elem.tag)
                txt = (elem.text or "").strip()
                if not txt:
                    continue
                if ltag == "title":
                    props["title"] = txt
                elif ltag == "creator":
                    props["author"] = txt
                    props["creator"] = txt
                elif ltag == "lastModifiedBy" and not props["creator"]:
                    props["creator"] = txt
        except OOXMLProcessingError:
            raise
        except Exception:
            pass
    if not props["title"]:
        props["title"] = fallback_title
    return props


def _col_letters_to_index(letters: str) -> int:
    """Convert Excel 1-indexed column letters ('A' -> 1, 'Z' -> 26, 'AA' -> 27)."""
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx


def _col_index_to_letters(index: int) -> str:
    """Convert 1-indexed column integer to Excel column letters (1 -> 'A', 27 -> 'AA')."""
    out: list[str] = []
    n = max(1, index)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out.append(chr(ord("A") + rem))
    return "".join(reversed(out))


def _parse_cell_coord(coord: str) -> tuple[int, int] | None:
    """Parse 'B12' into 1-indexed (row=12, col=2)."""
    m = _CELL_COORD_RE.match(coord.strip())
    if not m:
        return None
    return int(m.group(2)), _col_letters_to_index(m.group(1))


def _escape_md_cell(value: str) -> str:
    """Escape pipe characters and normalize line breaks for GFM Markdown table cells."""
    cleaned = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    cleaned = cleaned.replace("|", "\\|").replace("\n", " <br> ")
    return cleaned


def _clean_numeric_text(raw_val: str) -> str:
    """Clean IEEE-754 binary float representation noise while preserving significant digits."""
    s = raw_val.strip()
    if _FLOAT_NOISE_RE.match(s):
        try:
            return format(float(s), ".12g")
        except ValueError:
            return s
    return s


def _extract_si_text(si_elem: ET.Element) -> str:
    """Extract concatenated text from a sharedString <si> or inline <is> element, skipping phonetic <rPh>."""
    parts: list[str] = []

    def _walk(node: ET.Element) -> None:
        ltag = _local_tag(node.tag)
        if ltag == "rPh":
            return
        if ltag == "t":
            if node.text:
                parts.append(node.text)
            return
        for child in node:
            _walk(child)

    _walk(si_elem)
    return "".join(parts)


def _load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """Load xl/sharedStrings.xml table if present in workbook."""
    for candidate in ("xl/sharedStrings.xml", "xl/SharedStrings.xml"):
        if candidate in zf.namelist():
            root = _read_zip_xml(zf, candidate)
            return [_extract_si_text(child) for child in root if _local_tag(child.tag) == "si"]
    return []


def _list_workbook_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str, str]]:
    """Return ordered list of (sheet_name, visibility_state, zip_member_path) with visible sheets first."""
    names_set = set(zf.namelist())
    if "xl/workbook.xml" not in names_set:
        sheet_files = sorted(
            n for n in names_set if n.startswith("xl/worksheets/") and n.endswith(".xml")
        )
        return [(Path(sf).stem, "visible", sf) for sf in sheet_files]

    wb_root = _read_zip_xml(zf, "xl/workbook.xml")
    rel_map: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in names_set:
        rels_root = _read_zip_xml(zf, "xl/_rels/workbook.xml.rels")
        for rel in rels_root:
            if _local_tag(rel.tag) == "Relationship":
                rid = rel.attrib.get("Id", "")
                target = rel.attrib.get("Target", "")
                if rid and target:
                    norm_target = posixpath.normpath(target.lstrip("/"))
                    if not norm_target.startswith("xl/"):
                        norm_target = posixpath.normpath(f"xl/{norm_target}")
                    rel_map[rid] = norm_target

    visible_sheets: list[tuple[str, str, str]] = []
    hidden_sheets: list[tuple[str, str, str]] = []
    fallback_idx = 1

    for elem in wb_root.iter():
        if _local_tag(elem.tag) != "sheet":
            continue
        sheet_name = elem.attrib.get("name") or f"Sheet{fallback_idx}"
        state = elem.attrib.get("state", "visible").strip() or "visible"
        rid = next((v for k, v in elem.attrib.items() if _local_tag(k) == "id"), "")
        target_member = rel_map.get(rid, "")
        if not target_member or target_member not in names_set:
            guess = f"xl/worksheets/sheet{fallback_idx}.xml"
            if guess in names_set:
                target_member = guess
        fallback_idx += 1
        if not target_member or target_member not in names_set:
            continue
        entry = (sheet_name, state, target_member)
        if state == "visible":
            visible_sheets.append(entry)
        else:
            hidden_sheets.append(entry)

    return visible_sheets + hidden_sheets


def _parse_worksheet_to_markdown(
    sheet_name: str,
    visibility_state: str,
    ws_root: ET.Element,
    shared_strings: list[str],
) -> str | None:
    """Convert an OOXML worksheet XML tree into a structured GFM Markdown page."""
    cells: dict[tuple[int, int], str] = {}
    formulas: list[tuple[str, str, str]] = []
    merge_ranges: list[tuple[str, int, int, int, int]] = []

    current_row_num = 0
    for section in ws_root:
        sec_tag = _local_tag(section.tag)
        if sec_tag == "sheetData":
            for row_el in section:
                if _local_tag(row_el.tag) != "row":
                    continue
                r_attr = row_el.attrib.get("r")
                current_row_num = int(r_attr) if (r_attr and r_attr.isdigit()) else (current_row_num + 1)
                current_col_num = 0
                for c_el in row_el:
                    if _local_tag(c_el.tag) != "c":
                        continue
                    c_ref = c_el.attrib.get("r", "")
                    parsed_rc = _parse_cell_coord(c_ref) if c_ref else None
                    if parsed_rc is not None:
                        r_idx, c_idx = parsed_rc
                        current_col_num = c_idx
                    else:
                        r_idx = current_row_num
                        current_col_num += 1
                        c_idx = current_col_num
                        c_ref = f"{_col_index_to_letters(c_idx)}{r_idx}"

                    c_type = c_el.attrib.get("t", "")
                    v_text = ""
                    f_text = ""
                    inline_text = ""

                    for child in c_el:
                        ctag = _local_tag(child.tag)
                        if ctag == "v" and child.text is not None:
                            v_text = child.text
                        elif ctag == "f" and child.text is not None:
                            f_text = child.text.strip()
                        elif ctag == "is":
                            inline_text = _extract_si_text(child)

                    val = ""
                    if c_type == "s":
                        if v_text.strip().isdigit():
                            s_idx = int(v_text.strip())
                            if 0 <= s_idx < len(shared_strings):
                                val = shared_strings[s_idx]
                            else:
                                val = v_text
                        else:
                            val = v_text
                    elif c_type == "inlineStr":
                        val = inline_text
                    elif c_type == "b":
                        val = "TRUE" if v_text.strip() == "1" else "FALSE"
                    elif c_type in ("str", "e"):
                        val = v_text.strip()
                    else:
                        val = _clean_numeric_text(v_text)

                    if f_text:
                        if val:
                            formulas.append((c_ref, f_text, val))
                        else:
                            val = f"={f_text}"
                            formulas.append((c_ref, f_text, ""))

                    if val.strip():
                        cells[(r_idx, c_idx)] = val.strip()

        elif sec_tag == "mergeCells":
            for mc_el in section:
                if len(merge_ranges) >= MAX_MERGE_RANGES_PER_SHEET:
                    break
                if _local_tag(mc_el.tag) != "mergeCell":
                    continue
                ref = mc_el.attrib.get("ref", "").strip()
                if ":" not in ref:
                    continue
                start_s, end_s = ref.split(":", 1)
                p1 = _parse_cell_coord(start_s)
                p2 = _parse_cell_coord(end_s)
                if p1 and p2:
                    r1, c1 = min(p1[0], p2[0]), min(p1[1], p2[1])
                    r2, c2 = max(p1[0], p2[0]), max(p1[1], p2[1])
                    merge_ranges.append((ref, r1, c1, r2, c2))

    if not cells:
        return None

    active_merges: list[str] = []
    max_direct_scan = MAX_MERGE_PROPAGATE_ROWS * MAX_MERGE_PROPAGATE_COLS
    for ref, r1, c1, r2, c2 in merge_ranges:
        anchor_val = cells.get((r1, c1), "")
        if not anchor_val:
            span_area = (r2 - r1 + 1) * (c2 - c1 + 1)
            if span_area <= max_direct_scan:
                for rr in range(r1, r2 + 1):
                    for cc in range(c1, c2 + 1):
                        if cells.get((rr, cc)):
                            anchor_val = cells[(rr, cc)]
                            break
                    if anchor_val:
                        break
            else:
                for (rr, cc), candidate_val in sorted(cells.items()):
                    if r1 <= rr <= r2 and c1 <= cc <= c2 and candidate_val:
                        anchor_val = candidate_val
                        break
        if not anchor_val:
            continue
        active_merges.append(f"`{ref}` ({_escape_md_cell(anchor_val)})")
        if (r2 - r1 + 1) <= MAX_MERGE_PROPAGATE_ROWS and (c2 - c1 + 1) <= MAX_MERGE_PROPAGATE_COLS:
            for rr in range(r1, r2 + 1):
                for cc in range(c1, c2 + 1):
                    if (rr, cc) not in cells:
                        cells[(rr, cc)] = anchor_val

    non_empty_rows = sorted({r for r, _ in cells.keys()})
    non_empty_cols = sorted({c for _, c in cells.keys()})

    lines: list[str] = [
        f"## Worksheet: {sheet_name} [Visibility: {visibility_state}]",
        "",
    ]

    col_headers = ["Row"] + [_col_index_to_letters(c) for c in non_empty_cols]
    lines.append("| " + " | ".join(col_headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(col_headers)) + " |")

    for r in non_empty_rows:
        row_vals = [str(r)]
        for c in non_empty_cols:
            row_vals.append(_escape_md_cell(cells.get((r, c), "")))
        lines.append("| " + " | ".join(row_vals) + " |")

    if active_merges:
        lines.append("")
        lines.append("### Merged Cell Spans")
        for m_desc in active_merges[:80]:
            lines.append(f"- {m_desc}")

    if formulas:
        lines.append("")
        lines.append("### Worksheet Formulas")
        for coord, f_expr, cached_val in formulas[:MAX_FORMULA_NOTES_PER_SHEET]:
            if cached_val:
                lines.append(f"- `{coord}`: `={f_expr}` (cached value: `{_escape_md_cell(cached_val)}`)")
            else:
                lines.append(f"- `{coord}`: `={f_expr}`")

    return "\n".join(lines)


def extract_xlsx_pages(file_path: Path | str) -> list[dict[str, Any]]:
    """Extract each non-empty worksheet in an .xlsx or .xlsm workbook as a structured Markdown page."""
    path = Path(file_path)
    with _validate_and_open_ooxml_zip(path) as zf:
        shared_strings = _load_shared_strings(zf)
        sheets = _list_workbook_sheets(zf)
        pages: list[dict[str, Any]] = []
        for sheet_name, visibility, member_path in sheets:
            ws_root = _read_zip_xml(zf, member_path)
            md_text = _parse_worksheet_to_markdown(
                sheet_name=sheet_name,
                visibility_state=visibility,
                ws_root=ws_root,
                shared_strings=shared_strings,
            )
            if md_text:
                pages.append(
                    {
                        "page_number": len(pages) + 1,
                        "sheet_name": sheet_name,
                        "visibility": visibility,
                        "text": md_text,
                        "char_count": len(md_text),
                        "word_count": len(md_text.split()),
                    }
                )
        if not pages:
            pages.append(
                {
                    "page_number": 1,
                    "text": f"## Workbook: {path.name}\n\n[No populated worksheet cells]",
                    "char_count": 0,
                    "word_count": 0,
                }
            )
        return pages


def get_xlsx_metadata(file_path: Path | str) -> dict[str, Any]:
    """Retrieve workbook-level metadata and non-empty worksheet count for .xlsx / .xlsm."""
    path = Path(file_path)
    with _validate_and_open_ooxml_zip(path) as zf:
        props = _extract_ooxml_core_props(zf, fallback_title=path.stem)
        pages = extract_xlsx_pages(path)
        sheet_names = [p.get("sheet_name") for p in pages if p.get("sheet_name")]
        return {
            "file_name": path.name,
            "file_size_bytes": path.stat().st_size,
            "page_count": len(pages),
            "sheet_names": sheet_names,
            "title": props["title"] or path.stem,
            "author": props["author"],
            "creator": props["creator"],
        }


def extract_csv_pages(file_path: Path | str) -> list[dict[str, Any]]:
    """Extract a .csv file into one or more bounded GFM Markdown table pages."""
    path = Path(file_path)
    if not path.exists():
        raise OOXMLProcessingError(f"CSV file does not exist: {path}")

    raw_bytes = path.read_bytes()
    if len(raw_bytes) > MAX_MEMBER_UNCOMPRESSED_BYTES:
        raise OOXMLProcessingError(
            f"CSV file exceeds maximum size ({len(raw_bytes)} > {MAX_MEMBER_UNCOMPRESSED_BYTES} bytes)"
        )
    try:
        raw_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw_text = raw_bytes.decode("latin-1", errors="replace")

    reader = csv.reader(io.StringIO(raw_text))
    non_empty_rows: list[tuple[int, list[str]]] = []
    max_cols = 0
    for idx, row in enumerate(reader, start=1):
        if any(cell.strip() for cell in row):
            non_empty_rows.append((idx, row))
            max_cols = max(max_cols, len(row))

    if not non_empty_rows or max_cols == 0:
        return [
            {
                "page_number": 1,
                "text": f"## CSV Table: {path.name}\n\n[Empty CSV]",
                "char_count": 0,
                "word_count": 0,
            }
        ]

    pages: list[dict[str, Any]] = []
    col_headers = ["Row"] + [_col_index_to_letters(c) for c in range(1, max_cols + 1)]
    header_md = "| " + " | ".join(col_headers) + " |\n| " + " | ".join(["---"] * len(col_headers)) + " |"

    for start in range(0, len(non_empty_rows), CSV_ROWS_PER_PAGE):
        batch = non_empty_rows[start : start + CSV_ROWS_PER_PAGE]
        lines = [f"## CSV Table: {path.name} (Rows {batch[0][0]}–{batch[-1][0]})", "", header_md]
        for r_num, row in batch:
            padded = row + [""] * (max_cols - len(row))
            cells_md = [str(r_num)] + [_escape_md_cell(c) for c in padded]
            lines.append("| " + " | ".join(cells_md) + " |")
        md_text = "\n".join(lines)
        pages.append(
            {
                "page_number": len(pages) + 1,
                "text": md_text,
                "char_count": len(md_text),
                "word_count": len(md_text.split()),
            }
        )
    return pages


def get_csv_metadata(file_path: Path | str) -> dict[str, Any]:
    """Retrieve document-level metadata for a .csv file."""
    path = Path(file_path)
    pages = extract_csv_pages(path)
    return {
        "file_name": path.name,
        "file_size_bytes": path.stat().st_size,
        "page_count": len(pages),
        "title": path.stem,
        "author": None,
        "creator": None,
    }


def _extract_docx_paragraph_text_and_breaks(p_elem: ET.Element) -> tuple[str, bool]:
    """Extract text runs, heading style prefix, and explicit page break status from a <w:p> element."""
    heading_level = 0
    is_list_item = False
    has_page_break = False
    runs: list[str] = []

    for child in p_elem:
        ctag = _local_tag(child.tag)
        if ctag == "pPr":
            for pr in child:
                pr_tag = _local_tag(pr.tag)
                if pr_tag == "pStyle":
                    val = next((v for k, v in pr.attrib.items() if _local_tag(k) == "val"), "")
                    m_h = re.match(r"^heading\s*([1-6])$", val.strip(), re.IGNORECASE)
                    if m_h:
                        heading_level = int(m_h.group(1))
                    elif val.strip().lower() == "title":
                        heading_level = 1
                elif pr_tag == "numPr":
                    is_list_item = True
        else:
            for node in child.iter():
                ntag = _local_tag(node.tag)
                if ntag == "t" and node.text:
                    runs.append(node.text)
                elif ntag == "tab":
                    runs.append("\t")
                elif ntag == "br":
                    br_type = next((v for k, v in node.attrib.items() if _local_tag(k) == "type"), "")
                    if br_type == "page":
                        has_page_break = True
                    else:
                        runs.append("\n")
                elif ntag == "lastRenderedPageBreak":
                    has_page_break = True

    text = "".join(runs).strip()
    if not text:
        return "", has_page_break
    if heading_level > 0:
        return f"{'#' * heading_level} {text}", has_page_break
    if is_list_item:
        return f"- {text}", has_page_break
    return text, has_page_break


def _extract_docx_table_markdown(tbl_elem: ET.Element) -> str:
    """Convert a Word <w:tbl> element into a GFM Markdown table."""
    rows: list[list[str]] = []
    max_cols = 0

    for tr in tbl_elem:
        if _local_tag(tr.tag) != "tr":
            continue
        row_cells: list[str] = []
        for tc in tr:
            if _local_tag(tc.tag) != "tc":
                continue
            cell_paras: list[str] = []
            grid_span = 1
            for tc_child in tc:
                tc_tag = _local_tag(tc_child.tag)
                if tc_tag == "tcPr":
                    for pr in tc_child:
                        if _local_tag(pr.tag) == "gridSpan":
                            val = next((v for k, v in pr.attrib.items() if _local_tag(k) == "val"), "1")
                            if val.isdigit():
                                grid_span = max(1, min(20, int(val)))
                elif tc_tag == "p":
                    p_txt, _ = _extract_docx_paragraph_text_and_breaks(tc_child)
                    # Strip leading markdown heading hashes inside table cells
                    p_txt = re.sub(r"^#{1,6}\s+", "", p_txt)
                    if p_txt:
                        cell_paras.append(p_txt)
                elif tc_tag == "tbl":
                    nested_md = _extract_docx_table_markdown(tc_child)
                    if nested_md:
                        cell_paras.append(nested_md.replace("\n", " "))
            joined = _escape_md_cell("\n".join(cell_paras))
            row_cells.append(joined)
            for _ in range(grid_span - 1):
                row_cells.append(joined)
        if any(c.strip() for c in row_cells):
            rows.append(row_cells)
            max_cols = max(max_cols, len(row_cells))

    if not rows or max_cols == 0:
        return ""

    padded_rows = [r + [""] * (max_cols - len(r)) for r in rows]
    first_row = padded_rows[0]
    if all(bool(c.strip()) for c in first_row) and len(padded_rows) >= 2:
        lines = [
            "| " + " | ".join(first_row) + " |",
            "| " + " | ".join(["---"] * max_cols) + " |",
        ]
        for r in padded_rows[1:]:
            lines.append("| " + " | ".join(r) + " |")
        return "\n".join(lines)

    col_headers = [_col_index_to_letters(c) for c in range(1, max_cols + 1)]
    lines = [
        "| " + " | ".join(col_headers) + " |",
        "| " + " | ".join(["---"] * max_cols) + " |",
    ]
    for r in padded_rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def extract_docx_pages(file_path: Path | str) -> list[dict[str, Any]]:
    """Extract paragraphs, headings, tables, and header/footer metadata from a .docx file."""
    path = Path(file_path)
    with _validate_and_open_ooxml_zip(path) as zf:
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise OOXMLProcessingError(f"Missing word/document.xml in {path.name}")

        header_footer_blocks: list[str] = []
        for hf_name in sorted(
            n for n in names if n.startswith(("word/header", "word/footer")) and n.endswith(".xml")
        ):
            hf_root = _read_zip_xml(zf, hf_name)
            hf_items: list[str] = []
            for child in hf_root:
                ctag = _local_tag(child.tag)
                if ctag == "p":
                    txt, _ = _extract_docx_paragraph_text_and_breaks(child)
                    if txt:
                        hf_items.append(txt)
                elif ctag == "tbl":
                    t_md = _extract_docx_table_markdown(child)
                    if t_md:
                        hf_items.append(t_md)
            if hf_items:
                joined_hf = "\n".join(hf_items)
                if joined_hf not in header_footer_blocks:
                    header_footer_blocks.append(joined_hf)

        doc_root = _read_zip_xml(zf, "word/document.xml")
        body_el = next((el for el in doc_root if _local_tag(el.tag) == "body"), doc_root)

        pages_blocks: list[list[str]] = [[]]
        current_chars = 0

        if header_footer_blocks:
            hf_section = "### Document Header / Footer Metadata\n" + "\n\n".join(header_footer_blocks)
            pages_blocks[0].append(hf_section)
            current_chars += len(hf_section)

        for block in body_el:
            btag = _local_tag(block.tag)
            if btag == "p":
                p_txt, has_break = _extract_docx_paragraph_text_and_breaks(block)
                if has_break and pages_blocks[-1]:
                    pages_blocks.append([])
                    current_chars = 0
                if p_txt:
                    if current_chars + len(p_txt) > DOCX_CHARS_PER_PAGE and pages_blocks[-1]:
                        pages_blocks.append([])
                        current_chars = 0
                    pages_blocks[-1].append(p_txt)
                    current_chars += len(p_txt)
            elif btag == "tbl":
                tbl_md = _extract_docx_table_markdown(block)
                if tbl_md:
                    if current_chars + len(tbl_md) > DOCX_CHARS_PER_PAGE and pages_blocks[-1]:
                        pages_blocks.append([])
                        current_chars = 0
                    pages_blocks[-1].append(tbl_md)
                    current_chars += len(tbl_md)

        pages: list[dict[str, Any]] = []
        for blk_list in pages_blocks:
            if not blk_list:
                continue
            md_text = "\n\n".join(blk_list)
            pages.append(
                {
                    "page_number": len(pages) + 1,
                    "text": md_text,
                    "char_count": len(md_text),
                    "word_count": len(md_text.split()),
                }
            )

        if not pages:
            pages.append(
                {
                    "page_number": 1,
                    "text": f"## Word Document: {path.name}\n\n[Empty document]",
                    "char_count": 0,
                    "word_count": 0,
                }
            )
        return pages


def get_docx_metadata(file_path: Path | str) -> dict[str, Any]:
    """Retrieve document-level metadata for a .docx file."""
    path = Path(file_path)
    with _validate_and_open_ooxml_zip(path) as zf:
        props = _extract_ooxml_core_props(zf, fallback_title=path.stem)
        pages = extract_docx_pages(path)
        return {
            "file_name": path.name,
            "file_size_bytes": path.stat().st_size,
            "page_count": len(pages),
            "title": props["title"] or path.stem,
            "author": props["author"],
            "creator": props["creator"],
        }
