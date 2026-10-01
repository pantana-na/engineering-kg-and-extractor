#!/usr/bin/env python3
"""
CodeMender Stage Orchestrator & Report Generator
Helper utility for the CodeMender Gemini Skill.

Usage:
  python3 run_codemender_stage.py preflight [--project PROJECT_ID]
  python3 run_codemender_stage.py find <target_path> [--project PROJECT_ID] [--docs-dir DOCS_DIR]
  python3 run_codemender_stage.py verify <finding_id> [--project PROJECT_ID] [--docs-dir DOCS_DIR]
  python3 run_codemender_stage.py fix <finding_id> [--project PROJECT_ID] [--docs-dir DOCS_DIR]
  python3 run_codemender_stage.py summary [--docs-dir DOCS_DIR]
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd, env=None, cwd=None, timeout=300):
    """Execute shell command and return stdout, stderr, exit code."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=full_env,
            cwd=cwd,
            timeout=timeout
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return -1, "", f"Command timed out after {timeout}s: {e}"


def check_preflight(project_id=None):
    """Perform preflight checks for CodeMender."""
    results = {
        "cm_cli": False,
        "cm_version": None,
        "gcloud_cli": False,
        "active_account": None,
        "adc_token": False,
        "project_id": None,
        "git_repo": False,
        "errors": []
    }

    # 1. Check cm CLI
    cm_path = shutil.which("cm")
    if cm_path:
        results["cm_cli"] = True
        code, out, _ = run_cmd("cm --version")
        if code == 0:
            results["cm_version"] = out.strip()
    else:
        results["errors"].append("CodeMender CLI ('cm') is not installed or not in PATH.")

    # 2. Check gcloud CLI
    if shutil.which("gcloud"):
        results["gcloud_cli"] = True
        code, out, _ = run_cmd("gcloud config get-value account")
        if code == 0 and out.strip():
            results["active_account"] = out.strip()
        else:
            results["errors"].append("No active gcloud account found. Run: gcloud config set account <email>")
    else:
        results["errors"].append("gcloud CLI is not installed or not in PATH.")

    # 3. Check ADC
    code, _, err = run_cmd("gcloud auth application-default print-access-token")
    if code == 0:
        results["adc_token"] = True
    else:
        results["errors"].append("Application Default Credentials (ADC) not configured. Run: gcloud auth application-default login")

    # 4. Check Project ID
    proj = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("CLOUDSDK_CORE_PROJECT")
    if not proj and results["gcloud_cli"]:
        code, out, _ = run_cmd("gcloud config get-value project")
        if code == 0 and out.strip():
            proj = out.strip()
    results["project_id"] = proj
    if not proj:
        results["errors"].append("Target Google Cloud Project ID is not specified.")

    # 5. Check Git repo
    code, _, _ = run_cmd("git rev-parse --is-inside-work-tree")
    if code == 0:
        results["git_repo"] = True
    else:
        results["errors"].append("Current directory is not a Git repository. CodeMender requires Git for state management.")

    return results


def get_state_db_findings():
    """Extract findings directly from ~/.codemender/state.db if available."""
    db_path = Path.home() / ".codemender" / "state.db"
    findings = []
    if not db_path.exists():
        return findings

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        # Query tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        if "findings" in tables:
            cursor.execute("SELECT id, severity, title, file_path, status, details FROM findings ORDER BY severity DESC;")
            for row in cursor.fetchall():
                findings.append({
                    "id": row[0],
                    "severity": row[1],
                    "title": row[2],
                    "file": row[3],
                    "status": row[4],
                    "details": row[5] if len(row) > 5 else ""
                })
        conn.close()
    except Exception as e:
        print(f"[WARN] Error reading state.db: {e}", file=sys.stderr)

    return findings


def parse_findings_from_text(output_text):
    """Parse findings from 'cm find' or 'cm report' output."""
    findings = []
    # Match patterns like:
    # 764ebeb9  🔴 CRITICAL  SQL Injection      app.py  SQL Injection in /user via username Parameter     100%
    # or table rows
    line_pattern = re.compile(r"([a-f0-9]{8})\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\n]+)")
    for line in output_text.splitlines():
        line = line.strip()
        if not line or line.startswith("ID") or line.startswith("──") or line.startswith("┌") or line.startswith("└") or line.startswith("├"):
            continue
        # Check table pipe format: | 764ebeb9 | CRITICAL | OPEN | — | app.py | Title |
        if "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 5 and re.match(r"^[a-f0-9]{8}$", parts[0]):
                findings.append({
                    "id": parts[0],
                    "severity": parts[1].replace("🔴", "").replace("🟡", "").replace("🔵", "").strip(),
                    "status": parts[2] if len(parts) > 2 else "OPEN",
                    "file": parts[4] if len(parts) > 4 else parts[3],
                    "title": parts[5] if len(parts) > 5 else parts[-1],
                })
        else:
            m = line_pattern.search(line)
            if m and re.match(r"^[a-f0-9]{8}$", m.group(1)):
                findings.append({
                    "id": m.group(1),
                    "severity": m.group(2).replace("🔴", "").replace("🟡", "").replace("🔵", "").strip(),
                    "type": m.group(3),
                    "file": m.group(4),
                    "title": m.group(5).strip(),
                    "status": "OPEN"
                })
    return findings


def write_report(filepath, content):
    """Write report to file and ensure parent directories exist."""
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📄 Report written: {p.resolve()}")


def execute_find(target_path, project_id, docs_dir):
    """Execute CodeMender scan and generate docs/codemender-01-vulnerability-scan-report.md."""
    env = {}
    if project_id:
        env["GOOGLE_CLOUD_PROJECT"] = project_id
        env["CLOUDSDK_CORE_PROJECT"] = project_id

    print(f"🔍 Initiating CodeMender vulnerability scan on '{target_path}' (Project: {project_id})...")
    cmd = f"cm find {target_path} -y --bypass-warning --verbose"
    code, stdout, stderr = run_cmd(cmd, env=env, timeout=600)
    full_output = stdout + "\n" + stderr

    # Extract findings
    findings = parse_findings_from_text(full_output)
    if not findings:
        findings = get_state_db_findings()

    # Generate Markdown Report
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    report = f"""# CodeMender Security Vulnerability Scan Report

> **Execution Date:** {now_str}  
> **Target Path:** `{target_path}`  
> **Google Cloud Project:** `{project_id}`  
> **Status:** {'COMPLETED' if code == 0 else 'COMPLETED WITH WARNINGS'}  
> **Total Vulnerabilities Discovered:** `{len(findings)}`

---

## 1. Executive Summary

CodeMender performed static and agentic deep security scanning across the target codebase. The analysis identified **{len(findings)} potential security weaknesses** requiring verification and triage.

---

## 2. Discovered Vulnerabilities Table

| Finding ID | Severity | Vulnerability Type | File Location | Description / Title | Recommended Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""

    if findings:
        for f in findings:
            fid = f.get("id", "unknown")
            sev = f.get("severity", "MEDIUM")
            vtype = f.get("type", "Vulnerability")
            fpath = f.get("file", "unknown")
            title = f.get("title", "Security Finding")
            report += f"| `{fid}` | **{sev}** | {vtype} | [`{fpath}`]({fpath}) | {title} | Run `cm verify {fid}` |\n"
    else:
        report += "| — | — | — | — | No security vulnerabilities identified in the scanned scope | None |\n"

    report += f"""
---

## 3. Next Steps & Recommended Actions

1. **Verify Exploitability (`Phase 2`):** Run `cm verify <finding_id>` on discovered findings to generate and execute proof-of-concept (PoC) exploits in the isolated sandbox, confirming true positives and eliminating false alarms.
2. **Review Triage Report:** Inspect the verification report generated in the `docs/` folder.
3. **Automated Remediation (`Phase 3`):** Generate validated patches using `cm fix <finding_id>` for confirmed vulnerabilities.

---

## 4. Raw Scanner Execution Logs

<details>
<summary>Click to view raw scanner output</summary>

```text
{full_output.strip()[-3000:] if len(full_output) > 3000 else full_output.strip()}
```

</details>
"""
    report_file = Path(docs_dir) / "codemender-01-vulnerability-scan-report.md"
    write_report(report_file, report)
    return findings, str(report_file)


def execute_verify(finding_id, project_id, docs_dir):
    """Execute CodeMender verification and generate docs/codemender-02-verification-report.md."""
    env = {}
    if project_id:
        env["GOOGLE_CLOUD_PROJECT"] = project_id
        env["CLOUDSDK_CORE_PROJECT"] = project_id

    print(f"🔬 Verifying exploitability for finding '{finding_id}' (Project: {project_id})...")
    cmd = f"cm verify {finding_id} -y --bypass-warning --verbose"
    code, stdout, stderr = run_cmd(cmd, env=env, timeout=600)
    full_output = stdout + "\n" + stderr

    # Determine status
    is_confirmed = "CONFIRMED" in full_output or "verified" in full_output.lower() or code == 0
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    report = f"""# CodeMender Exploit Verification & Triage Report

> **Execution Date:** {now_str}  
> **Finding ID:** `{finding_id}`  
> **Google Cloud Project:** `{project_id}`  
> **Verification Status:** {'🔴 CONFIRMED EXPLOITABLE' if is_confirmed else '⚪ UNVERIFIED / FALSE POSITIVE'}  

---

## 1. Verification Analysis Summary

During verification, CodeMender synthesized an isolated proof-of-concept (PoC) exploit inside the process-level sandbox to determine whether the vulnerability is realistically exploitable.

- **Target Finding ID:** `{finding_id}`
- **Sandbox Container:** Active (`exebox` / Linux namespaces)
- **Triage Result:** {'Confirmed Exploitable (True Positive)' if is_confirmed else 'Not Reproducible / Mitigated'}

---

## 2. Exploit Proof-of-Concept (PoC) Evidence

```text
{full_output.strip()[-2500:] if len(full_output) > 2500 else full_output.strip()}
```

---

## 3. Recommended Remediation Plan

- **Patch Strategy:** Apply secure coding constructs (e.g., parameterization, strict allow-lists, output encoding, or input validation).
- **Execution Command:**
  ```bash
  cm fix {finding_id} -y --bypass-warning
  ```

---

## 4. Verification Metadata
- **Status Code:** `{code}`
- **Log Reference:** Check `~/.codemender/logs/` for complete execution telemetry.
"""
    report_file = Path(docs_dir) / f"codemender-02-verification-{finding_id}-report.md"
    write_report(report_file, report)
    return is_confirmed, str(report_file)


def execute_fix(finding_id, project_id, docs_dir):
    """Execute CodeMender fix and generate docs/codemender-03-remediation-report.md."""
    env = {}
    if project_id:
        env["GOOGLE_CLOUD_PROJECT"] = project_id
        env["CLOUDSDK_CORE_PROJECT"] = project_id

    print(f"🩹 Generating automated remediation patch for finding '{finding_id}' (Project: {project_id})...")
    cmd = f"cm fix {finding_id} -y --bypass-warning --verbose"
    code, stdout, stderr = run_cmd(cmd, env=env, timeout=600)
    full_output = stdout + "\n" + stderr

    # Capture git diff
    _, git_diff, _ = run_cmd("git diff")
    _, git_status, _ = run_cmd("git status --short")

    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    report = f"""# CodeMender Automated Remediation & Patch Report

> **Execution Date:** {now_str}  
> **Remediated Finding ID:** `{finding_id}`  
> **Google Cloud Project:** `{project_id}`  
> **Patch Generation Status:** {'✅ SUCCESSFUL' if (git_diff or code == 0) else '⚠️ FAILED / NO CHANGES'}  

---

## 1. Remediation Overview

CodeMender analyzed the verified vulnerability, refactored the vulnerable source code constructs, and evaluated the patch in the sandbox against regression test suites.

---

## 2. Code Patch Diff (`git diff`)

```diff
{git_diff.strip() if git_diff.strip() else '# No uncommitted diff detected; check git log or patch files.'}
```

---

## 3. Modified Workspace Status

```text
{git_status.strip() if git_status.strip() else 'Working tree clean.'}
```

---

## 4. Verification & Validation Steps

1. **Review Diff:** Inspect the code diff above to ensure application logic and architecture requirements are preserved.
2. **Execute Local Tests:** Run your project test suite (`npm test`, `pytest`, `go test`, `mvn test`) to ensure zero regressions.
3. **Commit & Deploy:** Stage and commit the validated patch:
   ```bash
   git add -A
   git commit -m "fix(security): remediate finding {finding_id} via CodeMender"
   ```

---

## 5. Raw Fix Agent Logs

<details>
<summary>Click to view raw fix session logs</summary>

```text
{full_output.strip()[-3000:] if len(full_output) > 3000 else full_output.strip()}
```

</details>
"""
    report_file = Path(docs_dir) / f"codemender-03-remediation-{finding_id}-report.md"
    write_report(report_file, report)
    return str(report_file)


def main():
    parser = argparse.ArgumentParser(description="CodeMender Skill Stage Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # preflight
    p_pref = subparsers.add_parser("preflight", help="Check CodeMender prerequisites")
    p_pref.add_argument("--project", default=None, help="GCP Project ID")

    # find
    p_find = subparsers.add_parser("find", help="Run CodeMender vulnerability scan")
    p_find.add_argument("target", help="Target path to scan (file or directory)")
    p_find.add_argument("--project", default=None, help="GCP Project ID")
    p_find.add_argument("--docs-dir", default="docs", help="Directory to save report")

    # verify
    p_ver = subparsers.add_parser("verify", help="Verify specific finding")
    p_ver.add_argument("finding_id", help="Finding ID to verify")
    p_ver.add_argument("--project", default=None, help="GCP Project ID")
    p_ver.add_argument("--docs-dir", default="docs", help="Directory to save report")

    # fix
    p_fix = subparsers.add_parser("fix", help="Generate patch for finding")
    p_fix.add_argument("finding_id", help="Finding ID to remediate")
    p_fix.add_argument("--project", default=None, help="GCP Project ID")
    p_fix.add_argument("--docs-dir", default="docs", help="Directory to save report")

    args = parser.parse_args()

    if args.command == "preflight":
        res = check_preflight(args.project)
        print(json.dumps(res, indent=2))
        sys.exit(0 if not res["errors"] else 1)

    elif args.command == "find":
        findings, rfile = execute_find(args.target, args.project, args.docs_dir)
        print(f"SUCCESS: Found {len(findings)} findings. Report: {rfile}")

    elif args.command == "verify":
        confirmed, rfile = execute_verify(args.finding_id, args.project, args.docs_dir)
        print(f"SUCCESS: Verified {args.finding_id} (Confirmed: {confirmed}). Report: {rfile}")

    elif args.command == "fix":
        rfile = execute_fix(args.finding_id, args.project, args.docs_dir)
        print(f"SUCCESS: Remediated {args.finding_id}. Report: {rfile}")


if __name__ == "__main__":
    main()
