#!/usr/bin/env python3
"""
Discovery Document Completeness & Traceability Validator (`validate_discovery.py`)

Validates consolidated Discovery Documents (`specs/discovery/DISCOVERY-*.md`) against the
15-section Discovery Document schema before handoff into `ai-sdlc` Phase 1 (Inception):
  1. Verifies all 15 required top-level sections and critical subsections (§1.1, §2.4, §2.5, §3.1, §6.1, §7.1, §10.1, §11.3).
  2. Verifies Document Control declares a single `Candidate Workload Type` (`Regular App`, `AI Agent`, `Hybrid`, or `Pending Phase 1`).
  3. Verifies presence of Requirement/Constraint IDs (`FR-`, `NFR-`, `CON-`) and an explicit Phase 1 Cut Line in §11.3.
  4. Optionally cross-checks `--package-dir <dir>` to ensure 100% of raw input files appear in the Discovery Document (§1.1 / §14).
  5. Verifies zero leftover template placeholders (`[PROJECT_NAME]`, `[e.g., ...]`, `YYYY-MM-DD`, `TBD`, or unselected `|` unions).

Usage:
  python3 _agents/skills/requirements_discovery/scripts/validate_discovery.py \
    --target specs/discovery/DISCOVERY-20261104-PROJECT.md \
    [--package-dir ./raw_inputs] [--strict] [--json]
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REQUIRED_DISCOVERY_SECTIONS = [
    "1. Document Control",
    "1.1 Artifact Review Log",
    "2. Executive Summary",
    "2.4 Recommended Phase 1 scope",
    "2.5 The three things that must be resolved",
    "3. Stakeholder Register",
    "3.1 Stakeholder tensions",
    "4. Business Context",
    "5. Functional Requirements Register",
    "6. Non-Functional Requirements Register",
    "6.1 Quality attribute coverage check",
    "7. Customer-Imposed Constraints",
    "7.1 Explicit out-of-scope",
    "8. Open Questions",
    "9. Assumptions Register",
    "10. Conflicts, Contradictions",
    "10.1 Contradictions between artifacts",
    "11. Prioritization Method",
    "11.3 Ranked backlog",
    "12. Data & Integration Inventory",
    "13. Dependencies & Delivery Sequencing",
    "14. Traceability Matrix",
    "15. Appendix",
]

DISCOVERY_PLACEHOLDER_PATTERNS: List[Tuple[str, str]] = [
    (r"\[PROJECT_NAME\]", "Unfilled title placeholder [PROJECT_NAME]"),
    (
        r"^\s*\|\s*\*{0,2}Candidate Workload Type\*{0,2}\s*\|[^\n]*`Regular App`\s*\\?\|\s*`AI Agent`",
        "Unselected Candidate Workload Type union in Document Control",
    ),
    (
        r"^\s*\|\s*\*{0,2}Status\*{0,2}\s*\|[^\n]*`Draft`\s*\\?\|\s*`In Review`",
        "Unselected Status union in Document Control",
    ),
    (r"`YYYY-MM-DD`", "Unfilled Date placeholder `YYYY-MM-DD`"),
    (r"\[e\.g\.,[^\]]*\]", "Unfilled example placeholder [e.g., ...]"),
    (r"`Covered`\s*\\?\|\s*`Missing`", "Unselected `Covered` | `Missing` union in §6.1 Quality Attribute table"),
    (r"`Yes`\s*\\?\|\s*`No`", "Unselected `Yes` | `No` union in §8 Open Questions table"),
    (r"\bTBD\b", "Unresolved 'TBD' placeholder"),
]


def validate_discovery_text(content: str, package_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Validate a Discovery Document markdown string and optional raw input package directory."""
    lower = content.lower()
    missing_sections = [
        sec for sec in REQUIRED_DISCOVERY_SECTIONS
        if sec.lower() not in lower
    ]

    non_callout_content = "\n".join(
        line for line in content.splitlines()
        if not line.lstrip().startswith(">")
    )
    unfilled_placeholders: List[str] = []
    for pattern, label in DISCOVERY_PLACEHOLDER_PATTERNS:
        if re.search(pattern, non_callout_content, flags=re.IGNORECASE | re.MULTILINE):
            unfilled_placeholders.append(label)

    fr_ids = sorted(set(re.findall(r"\bFR-\d+\b", content)))
    nfr_ids = sorted(set(re.findall(r"\bNFR-\d+\b", content)))
    con_ids = sorted(set(re.findall(r"\bCON-\d+\b", content)))
    has_cut_line = bool(re.search(r"phase\s*1\s*cut\s*line|cut\s*line", content, flags=re.IGNORECASE))

    candidate_workload = "unspecified"
    for line in content.splitlines():
        if re.match(r"^\s*\|\s*\*{0,2}candidate\s+workload\s+type\*{0,2}\s*\|", line, flags=re.IGNORECASE):
            if "|" not in line.split("|", 2)[-1].replace("\\|", "|").strip(" |"):
                if "regular app" in line.lower():
                    candidate_workload = "regular"
                elif "hybrid" in line.lower():
                    candidate_workload = "hybrid"
                elif "ai agent" in line.lower():
                    candidate_workload = "agent"
                elif "pending" in line.lower():
                    candidate_workload = "pending_phase_1"
            break

    unreviewed_package_files: List[str] = []
    package_files_checked = 0
    if package_dir is not None and package_dir.exists() and package_dir.is_dir():
        pkg_files = sorted(
            p for p in package_dir.rglob("*")
            if p.is_file() and not p.name.startswith(".")
        )
        package_files_checked = len(pkg_files)
        for pf in pkg_files:
            if pf.name.lower() not in lower:
                unreviewed_package_files.append(str(pf.relative_to(package_dir)))

    valid = (
        len(missing_sections) == 0
        and len(unfilled_placeholders) == 0
        and len(fr_ids) > 0
        and has_cut_line
        and len(unreviewed_package_files) == 0
    )

    return {
        "valid": valid,
        "candidate_workload_type": candidate_workload,
        "missing_sections": missing_sections,
        "unfilled_placeholders": unfilled_placeholders,
        "counts": {
            "functional_requirements": len(fr_ids),
            "non_functional_requirements": len(nfr_ids),
            "constraints": len(con_ids),
            "package_files_checked": package_files_checked,
        },
        "has_phase_1_cut_line": has_cut_line,
        "unreviewed_package_files": unreviewed_package_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Consolidated Discovery Document (15 Sections)")
    parser.add_argument("--target", required=True, help="Path to DISCOVERY-*.md file")
    parser.add_argument(
        "--package-dir",
        default=None,
        help="Optional directory of raw discovery input files to verify 100%% coverage in §1.1 / §14",
    )
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if validation fails")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    target_path = Path(args.target).resolve()
    if not target_path.exists() or not target_path.is_file():
        print(f"ERROR: Discovery document not found: {target_path}", file=sys.stderr)
        sys.exit(2)

    pkg_dir = Path(args.package_dir).resolve() if args.package_dir else None
    report = validate_discovery_text(
        target_path.read_text(encoding="utf-8", errors="ignore"),
        package_dir=pkg_dir,
    )
    report["file"] = str(target_path)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASSED" if report["valid"] else "INCOMPLETE"
        print(f"=== Discovery Document Audit ({target_path.name}) -> {status} ===")
        print(f"Candidate Workload Type: {report['candidate_workload_type']}")
        print(
            f"Extracted IDs: {report['counts']['functional_requirements']} FR | "
            f"{report['counts']['non_functional_requirements']} NFR | "
            f"{report['counts']['constraints']} CON"
        )
        print(f"Phase 1 Cut Line Present: {report['has_phase_1_cut_line']}")
        if report["missing_sections"]:
            print(f"Missing Sections ({len(report['missing_sections'])}): {report['missing_sections']}")
        if report["unfilled_placeholders"]:
            print(f"Unfilled Placeholders ({len(report['unfilled_placeholders'])}): {report['unfilled_placeholders']}")
        if report["unreviewed_package_files"]:
            print(f"Unreviewed Package Files ({len(report['unreviewed_package_files'])}): {report['unreviewed_package_files']}")

    if args.strict and not report["valid"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
