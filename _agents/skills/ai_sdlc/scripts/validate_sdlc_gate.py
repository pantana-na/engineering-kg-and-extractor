#!/usr/bin/env python3
"""
AI-SDLC Workspace Scaffolder & Gate Readiness Validator (`validate_sdlc_gate.py`)

Scaffolds the `specs/` and `docs/` directory structures from `_agents/skills/ai_sdlc/examples/`
into the repository root upon skill activation (`--init`), and validates artifacts across the
3 phases of the AI-SDLC for both `Regular App` (Non-AI) and `AI Agent` / `Hybrid` workloads:
  - Phase 0 (Activation): Scaffold `specs/` (`baseline/`, `features/`, `plan/`, `templates/`) and `docs/`
  - Phase 1: Inception (Intent Framing & Architecture)
  - Phase 2: Execution (Spec-Driven Development Cycle)
  - Phase 3: Operation (SAST, Repository Integration & Deployment)

Usage:
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase inception
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase execution
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase operation
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase all [--json]
"""

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple


REQUIRED_SDD_SECTIONS = [
    "Document Control",
    "1. Executive Summary",
    "2. System Architecture",
    "3. Security, Privacy",
    "4. Resiliency, Reliability",
    "5. Observability",
    "6. Performance Optimization",
    "7. Architectural Decision Records",
    "8. Failure Mode",
    "9. Step-by-Step Implementation Plan",
    "10. Plan Progress Tracking",
]

SDD_PLACEHOLDER_PATTERNS: List[Tuple[str, str]] = [
    (r"\[SPEC-YYYYMMDD-TITLE\]", "Unfilled spec title [SPEC-YYYYMMDD-TITLE]"),
    (r"^\s*\|\s*\*{0,2}Workload Type\*{0,2}\s*\|[^\n]*`Regular App`\s*\\?\|\s*`AI Agent`", "Unselected Workload Type union in Document Control"),
    (r"^\s*\|\s*\*{0,2}Status\*{0,2}\s*\|[^\n]*`Draft`\s*\\?\|\s*`In Review`", "Unselected Status union in Document Control"),
    (r"`YYYY-MM-DD`", "Unfilled Date placeholder `YYYY-MM-DD`"),
    (r"\[e\.g\.,[^\]]*\]", "Unfilled SLA/KPI example placeholder [e.g., ...]"),
    (r"\[Decision Title\]", "Unfilled ADR title placeholder [Decision Title]"),
    (r"\bTBD\b", "Unresolved 'TBD' placeholder"),
]


def find_unfilled_sdd_placeholders(content: str) -> List[str]:
    """Detect leftover template placeholders in authored SDD body/table lines (ignoring '>' callouts)."""
    non_callout_content = "\n".join(
        line for line in content.splitlines()
        if not line.lstrip().startswith(">")
    )
    findings: List[str] = []
    for pattern, label in SDD_PLACEHOLDER_PATTERNS:
        if re.search(pattern, non_callout_content, flags=re.IGNORECASE | re.MULTILINE):
            findings.append(label)
    return findings


def _load_waf_saif_module():
    """Dynamically load sibling gcp_well_architected_saif validator module."""
    waf_script = (
        Path(__file__).resolve().parents[2]
        / "gcp_well_architected_saif"
        / "scripts"
        / "validate_waf_saif.py"
    )
    if not waf_script.exists():
        return None
    spec = importlib.util.spec_from_file_location("validate_waf_saif", waf_script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_discovery_module():
    """Dynamically load sibling requirements_discovery validator module."""
    disc_script = (
        Path(__file__).resolve().parents[2]
        / "requirements_discovery"
        / "scripts"
        / "validate_discovery.py"
    )
    if not disc_script.exists():
        return None
    spec = importlib.util.spec_from_file_location("validate_discovery", disc_script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scaffold_workspace(repo_root: Path, skill_dir: Path) -> Dict[str, Any]:
    """
    Copy `specs/` and `docs/` templates from `_agents/skills/ai_sdlc/examples/`
    into `repo_root` without overwriting existing files.
    """
    examples_dir = skill_dir / "examples"
    created_files: List[str] = []
    skipped_existing: List[str] = []

    for folder_name in ("specs", "docs"):
        src_root = examples_dir / folder_name
        dst_root = repo_root / folder_name
        if not src_root.exists():
            continue

        dst_root.mkdir(parents=True, exist_ok=True)
        for src_path in sorted(src_root.rglob("*")):
            rel_path = src_path.relative_to(src_root)
            dst_path = dst_root / rel_path
            if src_path.is_dir():
                dst_path.mkdir(parents=True, exist_ok=True)
            elif src_path.is_file():
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                if not dst_path.exists():
                    shutil.copy2(src_path, dst_path)
                    created_files.append(str(dst_path.relative_to(repo_root)))
                else:
                    skipped_existing.append(str(dst_path.relative_to(repo_root)))

    return {
        "action": "AI-SDLC Workspace Initialization (--init)",
        "status": "INITIALIZED",
        "repo_root": str(repo_root),
        "source_templates": str(examples_dir.relative_to(repo_root)) if examples_dir.is_relative_to(repo_root) else str(examples_dir),
        "created_files": created_files,
        "skipped_existing_files": skipped_existing,
    }


def validate_inception(repo_root: Path) -> Dict[str, Any]:
    """Check Phase 1 (Inception) artifacts, optional Discovery Docs, and readiness indicators."""
    specs_dir = repo_root / "specs"
    docs_dir = repo_root / "docs"
    disc_mod = _load_discovery_module()
    validate_disc_fn = getattr(disc_mod, "validate_discovery_text", None) if disc_mod else None

    discovery_paths = sorted(
        p for p in (specs_dir / "discovery").glob("*.md")
        if p.is_file() and p.name.lower() != "readme.md"
    ) if (specs_dir / "discovery").exists() else []

    discovery_validation: List[Dict[str, Any]] = []
    for dp in discovery_paths:
        if validate_disc_fn is not None:
            res = validate_disc_fn(dp.read_text(encoding="utf-8", errors="ignore"))
            discovery_validation.append({
                "file": str(dp.relative_to(repo_root)),
                "valid": res["valid"],
                "candidate_workload_type": res["candidate_workload_type"],
                "missing_sections": res["missing_sections"],
                "unfilled_placeholders": res["unfilled_placeholders"],
            })
        else:
            discovery_validation.append({"file": str(dp.relative_to(repo_root))})

    baseline_files = [
        p.name for p in (specs_dir / "baseline").glob("*.md")
        if p.is_file() and p.name.lower() != "readme.md"
    ] if (specs_dir / "baseline").exists() else []

    arch_docs = [
        p.name for p in docs_dir.glob("*architecture*.md")
        if p.is_file() and p.name.lower() != "readme.md"
    ] if docs_dir.exists() else []

    cost_docs = [
        p.name for p in docs_dir.glob("gcp_cost_estimate*.md")
        if p.is_file() and p.name.lower() != "readme.md"
    ] if docs_dir.exists() else []

    waf_saif_docs = [
        p.name for p in docs_dir.glob("*waf*saif*.md")
        if p.is_file() and p.name.lower() != "readme.md"
    ] if docs_dir.exists() else []

    checks = {
        "specs_directory_exists": specs_dir.exists(),
        "docs_directory_exists": docs_dir.exists(),
        "optional_discovery_docs_found": discovery_validation,
        "baseline_specs_found": baseline_files,
        "architecture_diagrams_found": arch_docs,
        "cost_estimates_found": cost_docs,
        "waf_saif_reviews_found": waf_saif_docs,
    }
    reminders = [
        "If specs/ or docs/ are missing, run: python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init",
        "Optional Pre-Step: If raw transcripts, drawings, emails, or manuals exist, consolidate them into specs/discovery/DISCOVERY-*.md via `requirements-discovery`.",
        "Ingest specs/discovery/DISCOVERY-*.md (if present) + repo context first; then use ask_question to resolve §2.5/§8 blockers, Workload Type, personas, goals, and non-goals.",
        "Confirm runtime topology: Single-Runtime Cloud Run (`cloud_run`) for Regular Apps vs Dual-Runtime (`cloud_run` + `agent_runtime`) for AI Agent / Hybrid Apps.",
        "Confirm Google Cloud WAF 6-Pillar posture (and SAIF 2.0 posture if AI Agent/Hybrid): Pattern 1A ALB+Cloud Armor+IAP, Pattern 1B Direct Cloud Run IAP, or Pattern 2 App OAuth.",
        "Offer companion skills (gcp-well-architected-saif, architecture-diagram, codemender [brownfield], and gcp-cost-estimator) and obtain Gate 1 sign-off via ask_question.",
    ]
    return {
        "phase": "Phase 1: Inception (Intent Framing & Architecture)",
        "status": "READY_FOR_GATE_1_REVIEW" if specs_dir.exists() and docs_dir.exists() else "NEEDS_INIT (--init)",
        "checks": checks,
        "gate_reminders": reminders,
    }


def validate_execution(repo_root: Path) -> Dict[str, Any]:
    """Check Phase 2 (Execution / SDD) specifications, workload-aware WAF/SAIF audit, and plan reports."""
    features_dir = repo_root / "specs" / "features"
    plan_dir = repo_root / "specs" / "plan"
    waf_mod = _load_waf_saif_module()
    scan_waf_saif = getattr(waf_mod, "scan_text", None) if waf_mod else None
    detect_wtype = getattr(waf_mod, "detect_workload_type", None) if waf_mod else None

    feature_specs = sorted(
        p for p in features_dir.glob("*.md")
        if p.is_file() and p.name.lower() != "readme.md"
    ) if features_dir.exists() else []

    progress_reports = sorted(
        p for p in plan_dir.glob("*.md")
        if p.is_file() and p.name.lower() != "readme.md"
    ) if plan_dir.exists() else []

    spec_validation: List[Dict[str, Any]] = []
    for spec_path in feature_specs:
        content = spec_path.read_text(encoding="utf-8", errors="ignore")
        workload_type = detect_wtype(content) if detect_wtype else "hybrid"
        requires_saif = workload_type != "regular"

        missing_sections = [
            sec for sec in REQUIRED_SDD_SECTIONS
            if sec.lower() not in content.lower()
        ]
        unfilled_placeholders = find_unfilled_sdd_placeholders(content)
        has_unit_tests = "unit test" in content.lower()
        has_pbt = "property-based test" in content.lower() or "pbt" in content.lower()
        has_waf = "well-architected" in content.lower() or "sustainability" in content.lower()
        has_saif = ("saif" in content.lower() or "model armor" in content.lower()) if requires_saif else True

        waf_saif_audit = None
        no_waf_conflicts = True
        if scan_waf_saif is not None:
            passed_ws, warnings_ws, errors_ws = scan_waf_saif(content, workload_type=workload_type)
            no_waf_conflicts = len(errors_ws) == 0
            waf_saif_audit = {
                "workload_type": workload_type,
                "passed_count": len(passed_ws),
                "warnings": warnings_ws,
                "conflicts": errors_ws,
            }

        spec_validation.append({
            "file": str(spec_path.relative_to(repo_root)),
            "workload_type": workload_type,
            "missing_sections": missing_sections,
            "unfilled_placeholders": unfilled_placeholders,
            "defines_unit_tests": has_unit_tests,
            "defines_property_based_tests": has_pbt,
            "defines_waf_6_pillars": has_waf,
            "defines_saif_controls": has_saif if requires_saif else "N/A (Regular App)",
            "chained_waf_saif_audit": waf_saif_audit,
            "valid": (
                len(missing_sections) == 0
                and len(unfilled_placeholders) == 0
                and has_unit_tests
                and has_pbt
                and has_waf
                and has_saif
                and no_waf_conflicts
            ),
        })

    all_specs_valid = len(spec_validation) > 0 and all(s["valid"] for s in spec_validation)
    has_progress_report = len(progress_reports) > 0

    return {
        "phase": "Phase 2: Execution (Spec-Driven Development Cycle)",
        "status": "PASSED" if (all_specs_valid and has_progress_report) else "INCOMPLETE_SDD_ARTIFACTS",
        "checks": {
            "feature_specs_count": len(feature_specs),
            "feature_specs_validation": spec_validation,
            "progress_reports_found": [str(p.relative_to(repo_root)) for p in progress_reports],
        },
        "gate_reminders": [
            "Analyze requirements/codebase first and use ask_question to complete all required sections of sdd-template.md (Document Control + Sections 1–10; zero TBD or [e.g., ...] placeholders).",
            "Ensure Document Control selects a single Workload Type (`Regular App`, `AI Agent`, or `Hybrid`) and omits `[AI-Agent Only]` items for Regular Apps.",
            "Ensure every implementation step (Section 9) has passing Deterministic Unit Tests and Generative Property-Based Tests (PBT).",
            "Ensure any test or agent eval failures were resolved via the Mandatory 4-Step RCA Protocol (Rule 13).",
            "Ensure SDD in specs/features/ is synchronized with code (Zero Spec Drift) and specs/plan/ (Section 10) is updated.",
            "Obtain explicit Gate 2 sign-off from user via ask_question before entering Phase 3 (Operation).",
        ],
    }


def validate_operation(repo_root: Path) -> Dict[str, Any]:
    """Check Phase 3 (Operation) SAST reports, workload-aware WAF/SAIF audit, unified .env, deployment manifests, and Git state."""
    docs_dir = repo_root / "docs"
    features_dir = repo_root / "specs" / "features"
    codemender_reports = sorted(
        str(p.relative_to(repo_root))
        for p in docs_dir.glob("codemender-*.md")
        if p.is_file()
    ) if docs_dir.exists() else []

    env_files_checked: Dict[str, Any] = {}
    for env_name in [".env.example", ".env"]:
        env_path = repo_root / env_name
        if env_path.exists():
            text = env_path.read_text(encoding="utf-8", errors="ignore")
            env_files_checked[env_name] = {
                "exists": True,
                "has_nonprod_block": "NONPROD_" in text,
                "has_prod_block": "PROD_" in text,
            }
        else:
            env_files_checked[env_name] = {"exists": False}

    waf_mod = _load_waf_saif_module()
    scan_waf_saif = getattr(waf_mod, "scan_text", None) if waf_mod else None
    detect_wtype = getattr(waf_mod, "detect_workload_type", None) if waf_mod else None

    # Determine workspace workload type from specs/features/*.md (default 'hybrid' if none exist)
    ws_workload_type = "hybrid"
    if features_dir.exists() and detect_wtype is not None:
        spec_files = [
            p for p in features_dir.glob("*.md")
            if p.is_file() and p.name.lower() != "readme.md"
        ]
        if spec_files:
            detected_types = {detect_wtype(p.read_text(encoding="utf-8", errors="ignore")) for p in spec_files}
            ws_workload_type = "regular" if detected_types == {"regular"} else "hybrid"

    deployment_artifacts = {
        "workload_type": ws_workload_type,
        "agents_cli_manifest": (repo_root / "agents-cli-manifest.yaml").exists() if ws_workload_type != "regular" else "N/A (Regular App)",
        "cloudbuild_yaml": (repo_root / "cloudbuild.yaml").exists(),
        "terraform_dir": (repo_root / "terraform").exists(),
    }

    waf_saif_workspace_audit: Dict[str, Any] = {"available": scan_waf_saif is not None}
    no_waf_conflicts = True
    if scan_waf_saif is not None:
        project_files = [
            p for p in repo_root.rglob("*")
            if p.is_file()
            and "_agents" not in p.parts
            and ".git" not in p.parts
            and p.suffix in (".md", ".py", ".tf", ".yaml", ".yml")
        ]
        combined = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in sorted(project_files))
        passed_ws, warnings_ws, errors_ws = scan_waf_saif(combined, workload_type=ws_workload_type)
        no_waf_conflicts = len(errors_ws) == 0
        waf_saif_workspace_audit = {
            "workload_type": ws_workload_type,
            "scanned_files_count": len(project_files),
            "passed_count": len(passed_ws),
            "warnings_count": len(warnings_ws),
            "conflicts": errors_ws,
        }

    git_info: Dict[str, Any] = {"is_git_repo": False}
    try:
        branch_proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if branch_proc.returncode == 0:
            git_info = {
                "is_git_repo": True,
                "active_branch": branch_proc.stdout.strip(),
                "working_tree_clean": len(status_proc.stdout.strip()) == 0,
                "uncommitted_entries_count": len(status_proc.stdout.strip().splitlines()) if status_proc.stdout.strip() else 0,
            }
    except Exception as exc:
        git_info["error"] = str(exc)

    return {
        "phase": "Phase 3: Operation (Repository Integration & Deployment)",
        "status": "READY" if (codemender_reports and git_info.get("working_tree_clean") and no_waf_conflicts) else "PENDING_OPERATIONAL_GATES",
        "checks": {
            "codemender_sast_reports": codemender_reports,
            "chained_waf_saif_workspace_audit": waf_saif_workspace_audit,
            "unified_env_validation": env_files_checked,
            "deployment_manifests": deployment_artifacts,
            "git_repository_state": git_info,
        },
        "gate_reminders": [
            "Verify CodeMender SAST (cm find, cm verify, cm fix) shows zero unaddressed High/Critical vulnerabilities.",
            "Verify chained Google Cloud WAF [& SAIF] audit (validate_waf_saif.py) shows zero conflicts.",
            "Verify unified .env / .env.example contains shared core, NONPROD_*, and PROD_* blocks with zero committed secrets.",
            "Verify clean Git working tree on target branch (main/develop for Non-Prod; reviewed PR for prod/release).",
            "Execute Cloud Build & Terraform Infra Manager deploy to Cloud Run (`cloud_run`) — plus `agents-cli deploy` (`agent_runtime`) if Workload Type is AI Agent / Hybrid.",
            "Verify live /healthz smoke tests (and DLP-safe live `agents-cli eval` if AI Agent / Hybrid) and record in specs/plan/.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold AI-SDLC Workspace & Validate Phase Gates")
    parser.add_argument(
        "--init",
        action="store_true",
        help="Scaffold specs/ and docs/ directories into the project root from _agents/skills/ai_sdlc/examples/",
    )
    parser.add_argument(
        "--phase",
        choices=["inception", "execution", "operation", "all"],
        default=None,
        help="Target AI-SDLC phase to validate (defaults to 'all' when --init is not passed)",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Path to repository root (defaults to auto-detected project root)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as formatted JSON",
    )
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parents[1]
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[4]

    init_res = None
    if args.init:
        init_res = scaffold_workspace(repo_root, skill_dir)
        if args.phase is None:
            if args.json:
                print(json.dumps(init_res, indent=2))
            else:
                print(f"=== {init_res['action']} ===")
                print(f"Repository Root:  {init_res['repo_root']}")
                print(f"Source Templates: {init_res['source_templates']}")
                print(f"Created Files ({len(init_res['created_files'])}):")
                for f in init_res["created_files"]:
                    print(f"  + {f}")
                if init_res["skipped_existing_files"]:
                    print(f"Skipped Existing Files ({len(init_res['skipped_existing_files'])}):")
                    for f in init_res["skipped_existing_files"]:
                        print(f"  = {f}")
            return
        elif not args.json:
            print(f"=== {init_res['action']} ===")
            print(f"Repository Root:  {init_res['repo_root']}")
            print(f"Created {len(init_res['created_files'])} files, skipped {len(init_res['skipped_existing_files'])} existing files.\n")

    target_phase = args.phase or "all"
    results: List[Dict[str, Any]] = []
    if target_phase in ("inception", "all"):
        results.append(validate_inception(repo_root))
    if target_phase in ("execution", "all"):
        results.append(validate_execution(repo_root))
    if target_phase in ("operation", "all"):
        results.append(validate_operation(repo_root))

    if args.json:
        payload: Dict[str, Any] = {"repo_root": str(repo_root), "validations": results}
        if init_res is not None:
            payload["initialization"] = init_res
        print(json.dumps(payload, indent=2))
        return

    print(f"=== AI-SDLC Gate Validation Report ({repo_root}) ===")
    for res in results:
        print(f"\n[{res['phase']}] -> Status: {res['status']}")
        print("  Checks:")
        for k, v in res["checks"].items():
            print(f"    - {k}: {v}")
        print("  Gate Requirements & Reminders:")
        for rem in res["gate_reminders"]:
            print(f"    * {rem}")


if __name__ == "__main__":
    main()
