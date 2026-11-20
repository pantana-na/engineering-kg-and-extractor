# Discovery Document: [PROJECT_NAME]

## 1. Document Control

| Field | Value |
| :--- | :--- |
| **Discovery ID** | `DISCOVERY-YYYYMMDD-001` |
| **Candidate Workload Type** | `Regular App` \| `AI Agent` \| `Hybrid` \| `Pending Phase 1` |
| **Status** | `Draft` \| `In Review` \| `Approved for AI-SDLC` |
| **Author** | |
| **Date** | `YYYY-MM-DD` |
| **Version** | `1.0` |
| **Input Package Path** | `[e.g., ./inputs/ or attached artifacts]` |
| **Prioritization framework used** | `[e.g., MoSCoW / WSJF / RICE]` |

> [!IMPORTANT]
> **Optional Pre-AI-SDLC Consolidation & Grounding Rule:**
> - Every Functional Requirement (§5), Non-Functional Requirement (§6), and Constraint (§7) **MUST** cite a concrete `Source Artifact`, `Locator` (line range, page/section, timestamp, or diagram region), and `Verbatim Quote` (or faithful visual transcription for drawings/diagrams).
> - Never invent requirements silently: any missing quality attribute or unstated decision **MUST** be logged in **§8 (Open Questions)** or **§9 (Assumptions Register)** so **[`ai-sdlc`](../../_agents/skills/ai_sdlc/SKILL.md)** can resolve blocking items via `ask_question` during Phase 1 (Inception) and pre-populate `specs/features/SPEC-*.md` without redundant questions.

### 1.1 Artifact Review Log

*One row per file in the package. Every artifact in the input package MUST be reviewed.*

| Artifact filename | Modality | Reviewed? | Requirements sourced | Notes / issues encountered |
| :--- | :--- | :---: | :--- | :--- |
| `[e.g., 01_stakeholder_interview.txt]` | `Transcript / Text` | `Yes` | `FR-001, NFR-001, CON-001` | |
| `[e.g., 02_whiteboard_flow.png]` | `Drawing / Diagram` | `Yes` | `FR-002, FR-003` | |

---

## 2. Executive Summary

### 2.1 The problem in the customer's own terms
Summarize the core operational pain point using the stakeholders' domain language and terminology, grounded in source citations.

### 2.2 Quantified business impact
Document measurable financial, operational, SLA, customer-churn, or compliance costs of the current state (citing exact numbers from the package, or flagging unquantified claims in §8).

### 2.3 Top 5 requirements by priority
1. **`[Req ID]`** — Brief summary & business rationale.
2. **`[Req ID]`** — Brief summary & business rationale.
3. **`[Req ID]`** — Brief summary & business rationale.
4. **`[Req ID]`** — Brief summary & business rationale.
5. **`[Req ID]`** — Brief summary & business rationale.

### 2.4 Recommended Phase 1 scope and the cut line
Define the cohesive Minimum Viable / Phase 1 delivery boundary, why the cut line is drawn there, and what value Phase 1 unlocks independently.

### 2.5 The three things that must be resolved before design can start
1. **Blocker 1 (`[Ref Q-# / Conflict-#]`):** Concise description, decision owner, and impact on `ai-sdlc` Phase 1 architecture.
2. **Blocker 2 (`[Ref Q-# / Conflict-#]`):** Concise description, decision owner, and impact on `ai-sdlc` Phase 1 architecture.
3. **Blocker 3 (`[Ref Q-# / Conflict-#]`):** Concise description, decision owner, and impact on `ai-sdlc` Phase 1 architecture.

---

## 3. Stakeholder Register

| Name | Role / Title | Key agenda / mandate | Sign-off / veto authority | Source citation |
| :--- | :--- | :--- | :--- | :--- |
| | | | | |

### 3.1 Stakeholder tensions to be reconciled

| Tension # | Position A (stakeholder + citation) | Position B (stakeholder + citation) | Recommended resolution / default | Decision owner |
| :--- | :--- | :--- | :--- | :--- |
| `TEN-01` | | | | |

---

## 4. Business Context & Value Drivers

### 4.1 Current state and why existing systems cannot solve it
Describe legacy workflows, manual bottlenecks, architectural limitations, or tool fragmentation documented in the input artifacts.

### 4.2 Regulatory and legal landscape
Document applicable regulations, data residency mandates, audit obligations, industry standards (e.g., GDPR, HIPAA, PCI-DSS, SOX, PDPA, FSI regulations), or contractual commitments.

### 4.3 Active enforcement and live incidents
Record any active audit findings, security incidents, SLA breaches, regulatory deadlines, or executive escalations driving urgency.

---

## 5. Functional Requirements Register

| Req ID | Functional Requirement Statement | Source Artifact | Locator | Verbatim Quote | Acceptance Criteria | Priority | Priority Justification |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `FR-001` | | | | | | | |

---

## 6. Non-Functional Requirements Register

| Req ID | Non-Functional Requirement Statement | Quality Attribute | Target Metric / SLA | Source Artifact | Locator | Verbatim Quote | Priority | Priority Justification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `NFR-001` | | | | | | | | |

### 6.1 Quality attribute coverage check

*List the quality attributes your NFRs cover (aligned with the **Google Cloud Well-Architected Framework 6 Pillars** + **`[AI-Agent Only]` Autonomy/Safety** when AI is in scope). Flag any attribute that has no requirement in the package, and raise it in §8.*

| Quality Attribute (WAF Pillar / Domain) | Coverage Status (`Covered` \| `Missing`) | Linked NFR IDs | Gap Notes & §8 Open Question Reference |
| :--- | :---: | :--- | :--- |
| **Reliability (Availability SLO, RTO, RPO, Disaster Recovery)** | `Covered` \| `Missing` | | |
| **Performance (p95 Latency, Throughput / RPS, Concurrency)** | `Covered` \| `Missing` | | |
| **Security, Privacy & Compliance (Auth/IAM, Encryption/CMEK, Data Residency, DLP)** | `Covered` \| `Missing` | | |
| **Operability & Observability (Monitoring, Audit Logging, Supportability)** | `Covered` \| `Missing` | | |
| **Cost Optimization / FinOps (Budget Ceiling, Unit-Cost Target)** | `Covered` \| `Missing` | | |
| **Sustainability (Regional Carbon / `CFE %`, Data Retention TTLs)** | `Covered` \| `Missing` | | |
| **`[AI-Agent Only]` Agent Autonomy, HITL Gates, Streaming TTFT & Groundedness** *(Mark `N/A` if `Regular App`)* | `Covered` \| `Missing` \| `N/A` | | |

---

## 7. Customer-Imposed Constraints & Non-Negotiables

| Const ID | Constraint Description | Mandated By | Source Artifact | Locator | Verbatim Quote | Design Impact |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `CON-001` | | | | | | |

### 7.1 Explicit out-of-scope / negative scope
- List capabilities, user groups, legacy migrations, or integrations explicitly excluded by stakeholders (with source citations) or excluded from Phase 1.

---

## 8. Open Questions & Clarifications Required

*Blocking items (`Blocking Architecture / SDD? = Yes`) become the primary `ask_question` queue upon entering `ai-sdlc` Phase 1 (Inception).*

| Q # | Open Question | Why it matters for design | Owner | Blocking Architecture / SDD? | Default if unanswered |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `Q-01` | | | | `Yes` \| `No` | |

---

## 9. Assumptions Register

| Asm ID | Assumption Statement | Rationale | Risk if wrong | Owner | Validation action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ASM-01` | | | | | |

---

## 10. Conflicts, Contradictions & Discovery Risks

### 10.1 Contradictions between artifacts

| Conflict # | Source A (artifact + locator + quote) | Source B (artifact + locator + quote) | Recommended resolution / default | Decision owner |
| :--- | :--- | :--- | :--- | :--- |
| `CNF-01` | | | | |

### 10.2 Unsourced or undefined dependencies
Identify external APIs, legacy schemas, third-party vendors, datasets, or teams referenced in passing without interface specs, SLAs, or ownership details.

### 10.3 Discovery risks
Document blind spots in the discovery package (e.g., missing end-user interviews, outdated manuals, unverified traffic volumes, or absent security/legal stakeholders).

---

## 11. Prioritization Method & Ranked Backlog

### 11.1 Declared framework
Define the prioritization methodology (`MoSCoW`, `WSJF`, `RICE`, or `Value vs. Complexity + Risk`) and scoring/classification criteria used.

### 11.2 Prioritization matrix/table
Provide the scoring breakdown or classification rationale across candidate requirements.

### 11.3 Ranked backlog with the Phase 1 cut line

*All requirements in priority order, with a visible cut line after the last Phase 1 item.*

| Rank | Req ID | Priority | Phase | Justification |
| :---: | :--- | :---: | :---: | :--- |
| `1` | `FR-001` | `Must / P0` | `Phase 1` | |
| **—** | **====== PHASE 1 CUT LINE ======** | **—** | **—** | **Items above ship in Phase 1; items below defer to Phase 2+** |
| `2` | `FR-002` | `Should / P1` | `Phase 2` | |

### 11.4 Deliberate de-prioritisations
Explain which requested features were intentionally pushed below the Phase 1 cut line and why (e.g., unready upstream dependency, disproportionate compliance blast radius, or low ROI).

---

## 12. Data & Integration Inventory

### 12.1 Structured data sources
Inventory relational/NoSQL databases, data warehouses, ERP/CRM systems, and REST/gRPC/SOAP APIs (noting system of record, direction of flow, protocol, and volume/freshness).

### 12.2 Unstructured content sources
Inventory PDFs, SOP manuals, emails, images/drawings, SharePoint/Drive folders, audio/video recordings, or knowledge bases (noting format, size, update cadence, and OCR/chunking/RAG needs if applicable).

### 12.3 Sensitive data classification
Classify PII, PHI, PCI/PAN, credentials, financial records, or regulated intellectual property across data sources, mapping required **Cloud DLP / Sensitive Data Protection**, **CMEK**, and **Assured Workloads / residency** controls.

---

## 13. Dependencies & Delivery Sequencing

### 13.1 Dependency map
Document technical, data-readiness, organizational, security/compliance sign-off, and vendor dependencies across requirements.

### 13.2 Proposed phasing

| Phase | Req IDs | Outcome | Exit criteria |
| :--- | :--- | :--- | :--- |
| **Phase 1 (MVP / Foundation)** | | | |
| **Phase 2 (Scale / Expansion)** | | | |

---

## 14. Traceability Matrix (Artifact → Requirements)

| Artifact Filename | Requirements Sourced | Count | Unique Contribution |
| :--- | :--- | :---: | :--- |
| | | | |

---

## 15. Appendix

### 15.1 Glossary of domain terms
Define customer-specific acronyms, business terms, and legacy system names encountered across the input artifacts.

### 15.2 Additional notes or context
Capture supplementary observations, calculation notes, or diagram transcription details that support downstream `ai-sdlc` Solution Design.
