#!/usr/bin/env python3
"""Automated Google Cloud Well-Architected Framework (WAF) & Secure AI Framework (SAIF) Validator.

Supports both:
  - `Regular App` (Non-AI web, API, microservice, or data workloads): Audits all 6 Google Cloud
    WAF Pillars, Cross-Pillar ADRs, and Zero-Trust IAM/Ingress anti-patterns (skips AI-only SAIF checks).
  - `AI Agent` / `Hybrid` Workloads: Audits all 6 WAF Pillars + Cross-Pillar ADRs + Google SAIF
    (15 Risks & 4-Point Model Armor/Cloud DLP Callbacks) + SAIF 2.0 Agentic Controls.
"""

import argparse
import os
from pathlib import Path
import re
import sys
from typing import List, Tuple

WAF_PILLARS: List[Tuple[str, str, List[str]]] = [
    (
        "Pillar 1: Operational Excellence",
        "SLIs/SLOs, error budgets, Cloud Logging/Monitoring/Trace, Terraform IaC, Cloud Build canary/rollback",
        [
            r"operational excellence",
            r"\bslo\b|\bsli\b|error budget",
            r"terraform|infrastructure manager",
            r"cloud logging|cloud monitoring|cloud trace|opentelemetry",
        ],
    ),
    (
        "Pillar 2: Security, Privacy, and Compliance",
        "Zero Trust (Pattern 1A ALB+Cloud Armor+IAP, Pattern 1B Direct Cloud Run IAP+JWT check, or Pattern 2 OAuth2), VPC-SC, CMEK/KMS, Shift-Left SAST (CodeMender), SLSA/Binary Auth",
        [
            r"security,?\s*privacy,?\s*(?:&|and)?\s*compliance|zero trust|zero-trust",
            r"cloud armor|identity-aware proxy|\biap\b|x-goog-iap-jwt-assertion|oauth",
            r"vpc service controls|\bvpc-sc\b|private service connect",
            r"\bcmek\b|cloud kms|cloud hsm|cloud ekm",
        ],
    ),
    (
        "Pillar 3: Reliability",
        "Multi-zone/multi-region HA, RTO/RPO, idempotency/failover (or Provisioned Throughput spillover), circuit breakers & graceful degradation",
        [
            r"reliability|resiliency",
            r"\brto\b|\brpo\b|high availability|multi-zone|multi-region|single-region",
            r"graceful degradation|circuit breaker|exponential backoff",
            r"idempotency|idempotent|failover|provisioned throughput|spillover",
        ],
    ),
    (
        "Pillar 4: Cost Optimization",
        "FinOps unit economics, cost labels/scale-to-zero (or Context Caching/model routing), BigQuery billing export/budgets/CUDs",
        [
            r"cost optimization|\bfinops\b|unit economics|unit-cost",
            r"scale-to-zero|min-instances|cost_center|context caching|model routing|model tiering",
            r"billing export|budget|committed use discount|\bcud\b|\bcuds\b",
        ],
    ),
    (
        "Pillar 5: Performance Optimization",
        "p50/p95/p99 (or TTFT) latency budgets, CDN/Memorystore/pooling (or SSE streaming/Context Caching), co-located region",
        [
            r"performance optimization|latency engineering",
            r"\bttft\b|time-to-first-token|\bp95\b|\bp99\b",
            r"cloud cdn|memorystore|connection pool|startup cpu boost|streaming|\bsse\b|websocket|context caching",
        ],
    ),
    (
        "Pillar 6: Sustainability",
        "Low-carbon region selection (CFE %), compute/AI efficiency, data/log TTL lifecycle rules, Carbon Footprint export",
        [
            r"sustainability|greenops",
            r"\bcfe\b|carbon-free energy|low co2|low-carbon|carbon footprint",
            r"lifecycle|\bttl\b|work-per-watt|scale-to-zero",
        ],
    ),
]

SAIF_CONTROLS: List[Tuple[str, str, List[str]]] = [
    (
        "SAIF Core Framework & 15-Risk Coverage",
        "Explicit alignment with Google Secure AI Framework (SAIF) and standardized risk mitigations",
        [
            r"secure ai framework|\bsaif\b",
            r"prompt injection|\bpij\b|data poisoning|rogue actions|\brac\b|sensitive data disclosure|\bsdd\b|denial of ml service|\bdms\b",
        ],
    ),
    (
        "SAIF 4-Point Inline Guardrails (Model Armor + Cloud DLP)",
        "Pre-model direct PIJ + DLP tokenization, post-tool (`after_tool_callback`) indirect PIJ scan, and post-model output/URL scrubbing",
        [
            r"model armor",
            r"sensitive data protection|cloud dlp|\bdlp\b|tokeniz|de-identif",
            r"after_tool_callback|indirect prompt injection",
        ],
    ),
    (
        "SAIF 2.0 Agentic Security (User Auth, Anti-Confused-Deputy & Externalized HITL)",
        "End-user identity propagation (`User Auth`), read-only vs. deterministic action boundary, externalized HITL approval gate, and execution budgets",
        [
            r"user auth|confused deputy|caller identity|oauth",
            r"human-in-the-loop|\bhitl\b",
            r"read-only|least privilege|idempotency",
        ],
    ),
]

ANTI_PATTERNS: List[Tuple[str, str, str]] = [
    (
        "IAM allUsers / allAuthenticatedUsers Exposure",
        r'members\s*=\s*\[[^\]]*("allUsers"|"allAuthenticatedUsers")',
        "Violates WAF Zero Trust & Organization Policy (`constraints/iam.allowedPolicyMemberDomains`).",
    ),
    (
        "Unauthenticated Pattern 3 Recommended for Internal Tools",
        r"Direct Unauthenticated Ingress[^\n]*Recommended for[^\n]*Internal",
        "Violates WAF Zero Trust & SAIF Principle 1: internal and AI tools MUST authenticate users via IAP or OAuth 2.0.",
    ),
]


def detect_workload_type(content: str) -> str:
    """Detect Workload Type ('regular', 'agent', or 'hybrid') from the Document Control field."""
    for line in content.splitlines():
        m = re.match(
            r"^\s*(?:\|\s*\*{0,2}workload\s+type\*{0,2}\s*\||[-*]?\s*\*{0,2}workload\s+type\*{0,2}\s*:)(.*)$",
            line,
            re.IGNORECASE,
        )
        if m:
            val = m.group(1)
            has_reg = bool(
                re.search(r"\bregular(?:\s+app)?\b|\bnon-ai\b|\bstandard\s+app\b", val, re.IGNORECASE)
            )
            has_ai = bool(re.search(r"\bai\s+agent\b|\bagentic\b", val, re.IGNORECASE))
            has_hyb = bool(re.search(r"\bhybrid\b", val, re.IGNORECASE))
            if has_reg and not has_ai and not has_hyb:
                return "regular"
            if has_ai and not has_reg and not has_hyb:
                return "agent"
            return "hybrid"
    return "hybrid"


def scan_text(content: str, workload_type: str = "auto") -> Tuple[List[str], List[str], List[str]]:
    resolved_type = detect_workload_type(content) if workload_type == "auto" else workload_type
    passed: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []

    lower_content = content.lower()

    for title, desc, patterns in WAF_PILLARS:
        matched = sum(1 for p in patterns if re.search(p, lower_content))
        if matched >= max(2, len(patterns) - 1):
            passed.append(f"[WAF PASS] {title} ({matched}/{len(patterns)} signal groups verified)")
        else:
            warnings.append(
                f"[WAF MISSING/INCOMPLETE] {title}: matched {matched}/{len(patterns)} signal groups. Expected: {desc}"
            )

    if re.search(r"trade-off|\badr\b|architectural decision", lower_content):
        passed.append("[WAF PASS] Cross-Pillar Architectural Trade-Offs / ADRs documented")
    else:
        warnings.append(
            "[WAF MISSING] Cross-Pillar Architectural Trade-Offs / ADR table not detected"
        )

    if resolved_type == "regular":
        passed.append(
            "[SAIF N/A] Workload Type is 'Regular App' — AI-Agent SAIF 2.0 controls skipped"
        )
    else:
        for title, desc, patterns in SAIF_CONTROLS:
            matched = sum(1 for p in patterns if re.search(p, lower_content))
            if matched == len(patterns):
                passed.append(f"[SAIF PASS] {title} ({matched}/{len(patterns)} signal groups verified)")
            else:
                warnings.append(
                    f"[SAIF MISSING/INCOMPLETE] {title}: matched {matched}/{len(patterns)} signal groups. Expected: {desc}"
                )

    for title, pattern, reason in ANTI_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            errors.append(f"[CONFLICT / ANTI-PATTERN] {title}: {reason}")

    return passed, warnings, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Solution Design or SDD markdown files against Google Cloud WAF & Google SAIF."
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Path to a Solution Design .md file, SDD .md file, or directory to audit.",
    )
    parser.add_argument(
        "--workload-type",
        choices=["auto", "regular", "agent", "hybrid"],
        default="auto",
        help="Workload mode: 'regular' skips AI-Agent-only SAIF checks; 'auto' reads Document Control.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status code if any WAF/SAIF warning is present.",
    )
    args = parser.parse_args()

    target_path = Path(args.target).resolve()
    if not target_path.exists():
        print(f"ERROR: Target path does not exist: {target_path}", file=sys.stderr)
        return 2

    files_to_scan: List[Path] = []
    if target_path.is_file():
        files_to_scan.append(target_path)
    else:
        for root, _, filenames in os.walk(target_path):
            for fname in sorted(filenames):
                if fname.endswith((".md", ".py", ".tf", ".yaml", ".yml")):
                    files_to_scan.append(Path(root) / fname)

    combined_content = "\n".join(
        f.read_text(encoding="utf-8", errors="ignore") for f in files_to_scan
    )
    resolved_type = (
        detect_workload_type(combined_content)
        if args.workload_type == "auto"
        else args.workload_type
    )
    passed, warnings, errors = scan_text(combined_content, workload_type=resolved_type)

    print("=" * 80)
    print(
        f"GOOGLE CLOUD WAF & SAIF COMPLIANCE AUDIT: {target_path.name} (workload={resolved_type})"
    )
    print("=" * 80)
    for item in passed:
        print(f"  ✅ {item}")
    for item in warnings:
        print(f"  ⚠️  {item}")
    for item in errors:
        print(f"  ❌ {item}")
    print("-" * 80)
    print(
        f"Summary: {len(passed)} Passed | {len(warnings)} Warnings | {len(errors)} Critical Conflicts"
    )
    print("=" * 80)

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
