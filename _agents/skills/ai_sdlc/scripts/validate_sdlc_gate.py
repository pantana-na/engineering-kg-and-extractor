#!/usr/bin/env python3
"""
AI-SDLC Workspace Scaffolder & Gate Readiness Validator (`validate_sdlc_gate.py`)

Scaffolds the `specs/` and `docs/` directory structures from `_agents/skills/ai_sdlc/examples/`
into the repository root upon skill activation (`--init`), and validates artifacts across the
3 phases of the AI-SDLC:
  - Phase 0 (Activation): Scaffold `specs/` (`baseline/`, `features/`, `plan/`, `templates/`) and `docs/`
  - Phase 1: Inception (Intent Framing & Architecture)
  - Phase 2: Execution (Spec-Driven Development Cycle)
  - Phase 3: Operation (SAST, Repository Integration & Dual-Runtime Deployment)

Usage:
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase inception
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase execution
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase operation
  python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase all [--json]
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_SDD_SECTIONS = [
    "1. Problem Statement",
    "2. System Architecture",
    "3. Data Models",
    "4. API Contracts",
    "5. UI/UX",
    "6. DevOps, Security",
    "7. Step-by-Step Implementation Plan",
    "8. Plan Progress Tracking",
]


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
    """Check Phase 1 (Inception) artifacts and readiness indicators."""
    specs_dir = repo_root / "specs"
    docs_dir = repo_root / "docs"
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

    checks = {
        "specs_directory_exists": specs_dir.exists(),
        "docs_directory_exists": docs_dir.exists(),
        "baseline_specs_found": baseline_files,
        "architecture_diagrams_found": arch_docs,
        "cost_estimates_found": cost_docs,
    }
    reminders = [
        "If specs/ or docs/ are missing, run: python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init",
        "Confirm business intent, personas, goals, and explicit non-goals with user via ask_question.",
        "Confirm Dual-Runtime split: Gemini Enterprise Agent Platform (agent_runtime) vs Cloud Run (cloud_run).",
        "Confirm compliant IAM & Ingress pattern (Pattern 1: IAP, Pattern 2: App OAuth, Pattern 3: invoker-iam-disabled).",
        "Offer companion skills (architecture-diagram and gcp-cost-estimator) and obtain Gate 1 sign-off via ask_question.",
    ]
    return {
        "phase": "Phase 1: Inception (Intent Framing & Architecture)",
        "status": "READY_FOR_GATE_1_REVIEW" if specs_dir.exists() and docs_dir.exists() else "NEEDS_INIT (--init)",
        "checks": checks,
        "gate_reminders": reminders,
    }


def validate_execution(repo_root: Path) -> Dict[str, Any]:
    """Check Phase 2 (Execution / SDD) specifications, test design sections, and plan reports."""
    features_dir = repo_root / "specs" / "features"
    plan_dir = repo_root / "specs" / "plan"

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
        missing_sections = [
            sec for sec in REQUIRED_SDD_SECTIONS
            if sec.lower() not in content.lower()
        ]
        has_unit_tests = "unit test" in content.lower()
        has_pbt = "property-based test" in content.lower() or "pbt" in content.lower()
        spec_validation.append({
            "file": str(spec_path.relative_to(repo_root)),
            "missing_sections": missing_sections,
            "defines_unit_tests": has_unit_tests,
            "defines_property_based_tests": has_pbt,
            "valid": len(missing_sections) == 0 and has_unit_tests and has_pbt,
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
            "Ensure every implementation step has passing Deterministic Unit Tests and Generative Property-Based Tests (PBT).",
            "Ensure any test or agent eval failures were resolved via the Mandatory 4-Step RCA Protocol.",
            "Ensure SDD in specs/features/ is synchronized with code (Zero Spec Drift) and specs/plan/ is updated.",
            "Obtain explicit Gate 2 sign-off from user via ask_question before entering Phase 3 (Operation).",
        ],
    }


def validate_operation(repo_root: Path) -> Dict[str, Any]:
    """Check Phase 3 (Operation) SAST reports, unified .env structure, deployment manifests, and Git state."""
    docs_dir = repo_root / "docs"
    codemender_reports = sorted(
        str(p.relative_to(repo_root))
        for p in docs_dir.glob("codemender-*.md")
        if p.is_file()
    ) if docs_dir.exists() else []

    # Check .env / .env.example for unified NONPROD_* and PROD_* blocks
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

    # Check deployment artifacts
    deployment_artifacts = {
        "agents_cli_manifest": (repo_root / "agents-cli-manifest.yaml").exists(),
        "cloudbuild_yaml": (repo_root / "cloudbuild.yaml").exists(),
        "terraform_dir": (repo_root / "terraform").exists(),
    }

    # Check Git status & branch
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
        "status": "READY" if codemender_reports and git_info.get("working_tree_clean") else "PENDING_OPERATIONAL_GATES",
        "checks": {
            "codemender_sast_reports": codemender_reports,
            "unified_env_validation": env_files_checked,
            "deployment_manifests": deployment_artifacts,
            "git_repository_state": git_info,
        },
        "gate_reminders": [
            "Verify CodeMender SAST (cm find, cm verify, cm fix) shows zero unaddressed High/Critical vulnerabilities.",
            "Verify unified .env / .env.example contains shared core, NONPROD_*, and PROD_* blocks with zero committed secrets.",
            "Verify clean Git working tree on target branch (main/develop for Non-Prod; reviewed PR for prod/release).",
            "Execute dual-runtime deploy: agents-cli deploy (agent_runtime) + Cloud Build & Terraform Infra Manager (cloud_run).",
            "Verify live /healthz smoke tests and live agents-cli eval run (>=95% precision, 1.000 groundedness) and record in specs/plan/.",
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
        default="all",
        help="Target AI-SDLC phase to validate",
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

    if args.init:
        init_res = scaffold_workspace(repo_root, skill_dir)
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

    results: List[Dict[str, Any]] = []
    if args.phase in ("inception", "all"):
        results.append(validate_inception(repo_root))
    if args.phase in ("execution", "all"):
        results.append(validate_execution(repo_root))
    if args.phase in ("operation", "all"):
        results.append(validate_operation(repo_root))

    if args.json:
        print(json.dumps({"repo_root": str(repo_root), "validations": results}, indent=2))
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
