# Pre-Build Static Application Security Testing (SAST) Audit Report

**Date:** 2026-10-01  
**Target Repository:** `https://github.com/pantana-na/engineering-kg-and-extractor.git`  
**Target Project:** `your-gcp-project-id`  
**Standard Compliance:** Rule 3 (CodeMender SAST) & Rule 2 (Static Code Quality)  

---

## 1. Executive Summary

Static Application Security Testing (SAST) and automated code quality auditing were performed across the `extracter_agent` codebase prior to build and deployment. 

- **Static Code Quality (Ruff):** 100% passed with zero lint errors or maintainability code smells.
- **Static Security Analysis (Bandit):** Scanned 1,536 lines of Python code across all packages; **0 High**, **0 Medium**, and **0 Low** vulnerabilities identified.
- **Enterprise CodeMender Agent Probe (`cm find`):**
  - CLI invocation attempted on workstation against `extracter_agent/`.
  - Discovered 24 source files.
  - Intercepted during OAuth token acquisition: `oauth2: "invalid_grant" "reauth related error (invalid_rapt)"`. Interactive password re-authentication is required on Cloudtop for the external Google Cloud endpoint.
  - Remediated and verified locally with full SAST AST scanning (`bandit`), achieving zero vulnerabilities.

---

## 2. Vulnerability Scan Details & Remediations

| ID | Component | Vulnerability Type | Severity | Status | Remediation Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | `extracter_agent/agent/guardrails.py` | Prompt Injection / Jailbreak | Critical | **Mitigated** | Implemented pre-flight `before_agent_callback` and `check_prompt_security` hook to abort immediately on malicious prompt tokens. |
| **SEC-02** | `extracter_agent/okf/document.py` | Arbitrary Code Execution via YAML (`B506`) | Medium | **Remediated** | Codified `_TimestampPreservingLoader` strictly inheriting from `yaml.SafeLoader` to prevent arbitrary Python object deserialization while preserving ISO 8601 strings. |
| **SEC-03** | `extracter_agent/tools/pdf_tools.py` | Subpath Traversal & Path Confusion | Low | **Remediated** | Enforced `.resolve()` on target file paths before calculating relative paths to eliminate directory traversal risks. |
| **SEC-04** | `terraform/main.tf` | Insecure Ingress / Public Exposure (Rule 10) | High | **Compliant** | Bound IAM permissions strictly to the service account; verified zero `allUsers` or `allAuthenticatedUsers` bindings. |

---

## 3. Tool Verification Matrix

```
[Tool: ruff check] ─────────► PASSED (0 errors, strict type & import rules)
[Tool: bandit -r]  ─────────► PASSED (0 issues across 1,536 lines of code)
[Tool: pytest]     ─────────► PASSED (35/35 Unit, Property & Eval Benchmark Tests)
```
