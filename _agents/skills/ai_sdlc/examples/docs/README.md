# Operational & Skill Documentation (`docs/`)

This directory houses operational audit reports, security assessment logs, cloud infrastructure cost models, and standalone visual architecture assets produced by agent skills.

## Separation of Documentation Responsibilities

This repository maintains a strict boundary between specification documents and operational reports:
- **Spec-Driven Development Artifacts ([`specs/`](../specs/)):** Baseline models, formal feature specifications, test designs, and living plan execution reports.
- **Skill-Generated Operational Artifacts ([`docs/`](./)):** Generated security audits, real-time GCP cost estimations, and interactive architecture visual assets.

---

## Artifact Catalog & Standard Naming Conventions

### 1. Visual Architecture Diagrams ([`architecture-diagram`](../_agents/skills/architecture_diagram/SKILL.md))
- **Markdown Architecture Document:** `docs/<topic>-architecture.md`
- **Interactive Standalone HTML/SVG Asset:** `docs/<topic>-architecture.html`
- **Focus:** System topology, Cloud Run proxies, Gemini Enterprise Agent Platform runtime integration, data flows, and security zones.

### 2. Static Security & SAST Audit Reports ([`codemender`](../_agents/skills/codemender/SKILL.md))
- **Vulnerability Discovery Report:** `docs/codemender-01-vulnerability-scan-report.md` (`cm find`)
- **Exploit Verification & PoC Triage:** `docs/codemender-02-verification-report.md` (`cm verify`)
- **Remediation & Patch Diff Report:** `docs/codemender-03-remediation-report.md` (`cm fix`)
- **Master Security Audit Summary:** `docs/codemender-security-audit-summary.md`

### 3. Cloud Cost Estimations ([`gcp-cost-estimator`](../_agents/skills/gcp_cost_estimator/SKILL.md))
- **Workload Cost Analysis & Itemized BoM:** `docs/gcp_cost_estimate_<project_name>.md`
- **Pricing Source Mandate:** Real-time rates queried strictly from the live Google Cloud Billing API or official live pricing endpoints (zero local caching).
- **Structure:** Executive summary, category distribution, itemized BoM table with live SKU attributions, CUD savings (1-yr and 3-yr), FinOps unit economics (`cost per resolved session`), and elicited workload parameters.

### 4. Google Cloud Well-Architected Framework (WAF) & SAIF 2.0 Compliance Reviews ([`gcp-well-architected-saif`](../_agents/skills/gcp_well_architected_saif/SKILL.md))
- **WAF & SAIF Compliance Assessment Report:** `docs/waf-saif-review_<project_name>.md` (or embedded in `specs/features/SPEC-*.md` Sections 2.3, 3, & 7–8)
- **Focus:** All **6 WAF Pillars** (*Operational Excellence*, *Security/Privacy/Compliance*, *Reliability*, *Cost Optimization*, *Performance Optimization*, *Sustainability*) for all workloads, plus **Google SAIF (15 Risks) & SAIF 2.0 Agentic Controls** when `Workload Type` is `AI Agent` or `Hybrid`.

---

## Related Documentation
- **Agent Operating Manual:** [`AGENTS.md`](../AGENTS.md)
- **Master AI-SDLC Orchestrator Skill:** [`_agents/skills/ai_sdlc/SKILL.md`](../_agents/skills/ai_sdlc/SKILL.md)
- **Google Cloud WAF & SAIF Governance Skill:** [`_agents/skills/gcp_well_architected_saif/SKILL.md`](../_agents/skills/gcp_well_architected_saif/SKILL.md)
- **DevOps, Security & Quality Standards:** [`_agents/rules/devops_security_and_quality_standards.md`](../_agents/rules/devops_security_and_quality_standards.md)
- **System Specifications:** [`specs/README.md`](../specs/README.md)

