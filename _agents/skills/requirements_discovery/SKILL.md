---
name: requirements-discovery
description: >-
  Consolidates raw, unstructured, multi-modal stakeholder inputs—such as interview transcripts,
  whiteboard/architecture drawings, user emails, SOP manuals, PDFs, spreadsheets, and RFP
  packages—into a single, citation-grounded 15-section Discovery Document
  (specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md). Extracts Functional and Non-Functional
  Requirements with verbatim quotes and locators, reconciles stakeholder tensions and cross-artifact
  contradictions, audits quality attribute coverage against the Google Cloud Well-Architected
  Framework (6 Pillars) and Google SAIF, ranks the Phase 1 cut line, and prepares a targeted open
  question queue for seamless handoff into the ai-sdlc skill. Activate as an optional pre-Inception
  step whenever a user provides raw discovery artifacts or asks to synthesize stakeholder inputs
  into a structured discovery/requirements document.
---

# Multi-Modal Requirements Consolidation & Discovery Skill (`requirements-discovery`)

You are a Principal Enterprise Discovery Architect & Business-Technical Analyst. Your mission is to ingest messy, heterogeneous, multi-modal customer discovery packages (interview scripts/transcripts, whiteboard sketches, architecture drawings, email threads, user manuals, policy PDFs, spreadsheets, incident tickets) and synthesize them into a **rigorous, citation-grounded 15-Section Discovery Document** (`specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md`) using [`../ai_sdlc/examples/specs/templates/discovery-template.md`](../ai_sdlc/examples/specs/templates/discovery-template.md).

### AI-SDLC Master Hub & Governance Wiring (Optional Pre-Phase-1 Spoke)
- **Optional Pre-Inception Entry Point for [`ai-sdlc`](../ai_sdlc/SKILL.md):**
  - **`ai-sdlc` Dual-Input Architecture:** `ai-sdlc` accepts requirements from **either** (A) a consolidated `specs/discovery/DISCOVERY-*.md` artifact produced by this skill + targeted `ask_question` resolution on remaining blockers, **or** (B) direct interactive `ask_question` elicitation + repository inspection when no raw discovery package exists.
  - This skill can also be invoked **standalone** whenever a user wants a standalone customer Discovery Document or RFP/workshop synthesis without immediately writing code.
- **Downstream Framework Alignment ([`gcp-well-architected-saif`](../gcp_well_architected_saif/SKILL.md)):**
  - Quality attribute gap analysis (**§6.1**) and sensitive data / constraint classification (**§7 & §12.3**) align directly with the **Google Cloud Well-Architected Framework (6 Pillars)** and, when AI/LLM capabilities appear in customer artifacts, the **Google Secure AI Framework (SAIF / SAIF 2.0)**—ensuring zero translation loss when handing off to `ai-sdlc` Phase 1 & `sdd-template.md`.

---

## Core Non-Negotiable Discovery Rules

1. **100% Package Coverage (Zero Unread Files):**
   - Every single file in the user's input folder or attachment list—including images/drawings (`.png`, `.jpg`, `.webp`, `.svg`), PDFs, manuals, transcripts, emails, and spreadsheets—**MUST** be inspected using `view_file` (which natively supports text, images, PDFs, audio, and video) and logged in **§1.1 Artifact Review Log** and **§14 Traceability Matrix**.
2. **Strict Verbatim Evidence Grounding (Zero Hallucinated Requirements):**
   - Every row in **§5 (Functional Requirements)**, **§6 (Non-Functional Requirements)**, and **§7 (Customer-Imposed Constraints)** **MUST** include:
     - `Source Artifact` (exact filename)
     - `Locator` (e.g., `L42-L49`, `p. 7 §3.2`, `[14:22-15:05]`, `Email 2026-10-12 para 3`, or `Diagram: Checkout Swimlane -> Box 4`)
     - `Verbatim Quote` (exact substring from text/PDF/email/transcript, or exact visual label/arrow transcription prefixed with `[Diagram Transcription]:` for drawings)
3. **Never Hide Gaps or Contradictions — Surface Them Explicitly:**
   - Do **NOT** invent silent SLAs, budgets, or tie-breakers when artifacts disagree or omit NFRs.
   - Stakeholder disagreements go into **§3.1 (Stakeholder Tensions)**; conflicting facts across files go into **§10.1 (Contradictions Between Artifacts)**; missing NFRs/decisions go into **§8 (Open Questions)** with `Blocking Architecture / SDD?` (`Yes` | `No`) and a sensible WAF/SAIF-aligned `Default if unanswered`; working inferences go into **§9 (Assumptions Register)**.
4. **Workload Mode Signal (`Regular App` vs. `AI Agent` / `Hybrid`):**
   - Classify **`Candidate Workload Type`** in **§1 Document Control** (`Regular App` | `AI Agent` | `Hybrid` | `Pending Phase 1`) based on whether the customer problem requires deterministic web/API/data workflows (`Regular App`) or conversational/autonomous reasoning (`AI Agent` / `Hybrid`). Omit `[AI-Agent Only]` checks in §6.1 when clearly a `Regular App`.
5. **First-Class Brownfield Compatibility (`specs/discovery/` Stakeholder Truth vs. `specs/baseline/` Code Truth):**
   - When run on a **brownfield repository**, `specs/discovery/DISCOVERY-*.md` captures **what stakeholders, legacy manuals, emails, and drawings claim/want**, while `specs/baseline/*.md` (authored in `ai-sdlc` Step 2.0) captures **what the deployed code, configs, and SQL Stored Procedures actually execute**.
   - If brownfield source code or `specs/baseline/*.md` is already present in the workspace during discovery, cross-check legacy manuals/drawings/interviews against actual code/SQL and log any **Manual-vs-Code Drift** (e.g., manual states a `$10k` limit while `usp_ApproveOrder.sql` enforces `$25k`, or a whiteboard omits an active nightly batch job) directly in **§10.1 Contradictions Between Artifacts** so the user can decide which behavior to carry forward via `ask_question`.

---

## End-to-End 6-Stage Discovery Workflow

```mermaid
flowchart LR
    S1["1. Inventory & Scaffold\n(specs/discovery/ + §1.1 Log)"] --> S2["2. Multi-Modal Ingestion\n(Transcripts, Drawings, Emails, Manuals)"]
    S2 --> S3["3. Verbatim Registers\n(§3 Stakeholders, §5 FR, §6 NFR, §7 CON, §12 Data)"]
    S3 --> S4["4. Conflict & WAF/SAIF Gap Audit\n(§3.1 Tensions, §6.1 Pillars, §8 Qs, §10 Conflicts)"]
    S4 --> S5["5. Prioritize & Cut Line\n(§11 Backlog, §13 Phasing, §14 Traceability)"]
    S5 --> S6["6. Validate & Handoff\n(validate_discovery.py + ask_question -> ai-sdlc)"]
```

### Stage 1: Workspace Check & Complete Artifact Inventory
1. Check if `specs/discovery/` and `specs/templates/discovery-template.md` exist in the project root. If missing (in an active project workspace), scaffold the `specs/` and `docs/` workspace structure:
   ```bash
   python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init
   ```
2. List all files in the provided discovery input folder(s) using `list_dir` / `find_by_name` (plus any files referenced directly in the user's prompt).
3. Initialize `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md` from [`../ai_sdlc/examples/specs/templates/discovery-template.md`](../ai_sdlc/examples/specs/templates/discovery-template.md) and populate **§1.1 Artifact Review Log** with one row per input file (`Modality`: `Interview Transcript`, `Architecture / Whiteboard Drawing`, `User Email / Thread`, `Manual / SOP / PDF`, `Spreadsheet / Data Sample`, etc.).

### Stage 2: Multi-Modal Artifact Inspection & Evidence Extraction
Inspect **every** artifact using `view_file` (see [`references/discovery_to_sdd_mapping.md`](./references/discovery_to_sdd_mapping.md) for modality-specific extraction rules):
- **Interview Scripts / Transcripts & Emails:** Extract customer pain points in their own terminology (**§2.1**), quantified business/financial pain (**§2.2**), named stakeholders, agendas, and veto authorities (**§3**), explicit functional asks (**§5**), target metrics (**§6**), hard mandates & negative scope (**§7 & §7.1**), and domain acronyms (**§15.1**).
- **Drawings, Whiteboard Photos & Diagrams (`.png`, `.jpg`, `.pdf`, `.svg`):** Inspect visually via `view_file` to extract system boxes, actor flows, legacy integration arrows, trust boundaries, handwritten annotations, and implied dependencies (**§4.1**, **§5**, **§10.2**, **§12.1**). Flag any component drawn on a diagram that is never explained in text under **§10.2 (Unsourced or Undefined Dependencies)**.
- **User Manuals, Policy Docs & Incident Logs:** Extract current-state workarounds/limitations (**§4.1**), regulatory/compliance mandates (**§4.2**), active incidents/audit deadlines (**§4.3**), unstructured content volumes (**§12.2**), and PII/PCI/PHI sensitivity (**§12.3**).

### Stage 3: Conflict Detection & WAF/SAIF Quality Attribute Coverage Check
1. **Cross-Compare Every Source (§3.1 & §10.1):**
   - Whenever Stakeholder A wants X (e.g., *"launch self-service automation in 30 days"*) and Stakeholder B mandates Y (e.g., *"manual compliance sign-off on every transaction"*), record a numbered row in **§3.1 Stakeholder Tensions** with both citations, a recommended resolution, and the decision owner.
   - Whenever Artifact A states one fact/number (e.g., *"5,000 daily orders"* in an email) and Artifact B states another (e.g., *"50,000 peak daily orders"* in a spreadsheet or manual), record a numbered row in **§10.1 Contradictions Between Artifacts**.
2. **Execute §6.1 Quality Attribute Coverage Check (WAF 6 Pillars + Optional SAIF):**
   - Audit extracted NFRs (**§6**) against all 6 Google Cloud WAF quality domains (*Reliability/RTO/RPO*, *Performance/Latency/RPS*, *Security/Privacy/Residency*, *Operability/Observability*, *Cost/FinOps*, *Sustainability/CFE%*) plus *`[AI-Agent Only]` Autonomy/HITL & Groundedness* (if AI is in scope).
   - For **every** quality attribute marked `Missing`, create a corresponding open question in **§8 Open Questions & Clarifications Required** explaining why it matters for architecture design, whether `Blocking Architecture / SDD?` is `Yes` or `No`, and proposing a safe WAF/SAIF default if unanswered.

### Stage 4: Prioritization Framework, Phase 1 Cut Line & Phasing
1. Select an explicit prioritization framework (**MoSCoW**, **WSJF**, or **RICE** — ask via `ask_question` only if the customer mandated a specific rubric or if prioritization criteria are ambiguous) and declare it in **§1 Document Control** and **§11.1**.
2. Score/classify all `FR-*` and `NFR-*` items in **§11.2**, and produce the **Ranked Backlog with an explicit `====== PHASE 1 CUT LINE ======` row** in **§11.3** (summarized in **§2.3 Top 5** and **§2.4 Recommended Phase 1 Scope**).
3. Explain deliberate deferrals in **§11.4**, map technical/data/org dependencies in **§13.1**, and define phased exit criteria in **§13.2**.
4. Synthesize **§2.5 The three things that must be resolved before design can start** from the highest-impact blocking items in **§3.1**, **§8**, and **§10.1**.

### Stage 5: Traceability Matrix & Automated Completeness Validation
1. Complete **§14 Traceability Matrix (Artifact $\rightarrow$ Requirements)** confirming every artifact in **§1.1** is accounted for (noting `0 — Contextual/Glossary Only` if an artifact yielded background context rather than a discrete `FR`/`NFR`/`CON`).
2. Run the automated Discovery Document validator:
   ```bash
   python3 _agents/skills/requirements_discovery/scripts/validate_discovery.py \
     --target specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md \
     --package-dir <path-to-raw-input-folder-if-applicable>
   ```
3. Fix any missing sections, uncovered package files, missing cut lines, or leftover template placeholders (`[PROJECT_NAME]`, `[e.g., ...]`, `YYYY-MM-DD`, `TBD`, or unselected `|` unions) before presenting to the user.

### Stage 6: Interactive Review, Blocker Resolution & Handoff to `ai-sdlc` (`ask_question`)
Present the link to `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md` with a concise summary of:
- Total artifacts reviewed & total `FR` / `NFR` / `CON` items traced
- Recommended **Phase 1 Cut Line** (**§2.4 / §11.3**)
- **Top 3 Pre-Design Blockers (§2.5)**, key contradictions (**§10.1**), and blocking open questions (**§8**)

Then invoke `ask_question` to guide the next step:
- `(Recommended) Approve Discovery Document and proceed into ai-sdlc Phase 1 (Inception), resolving the §2.5 / §8 blocking questions now`
- `Resolve specific open questions or stakeholder conflicts first and update the Discovery Document`
- `Finalize as a standalone Discovery Document only (do not start ai-sdlc yet)`
