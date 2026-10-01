# Living Plan Progress Tracking (`specs/plan/`)

This directory houses continuous execution reports, milestone tracking documents, test verification metrics, and architectural decision records generated during implementation.

## Progress Tracking Protocol

Under the **Spec-Driven Development (SDD)** standard ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../_agents/rules/ai_sdlc_and_sdd_standards.md)):

1. **Mandatory Progress Updates:** Whenever development pauses, a session concludes, or a major milestone is reached, developers and autonomous agents **MUST** author or update an execution progress report in this directory.
2. **Required Report Elements:**
   - **Specification Linkage:** Reference the parent feature SDD (e.g., `specs/features/SPEC-YYYYMMDD-TITLE.md`).
   - **Step-by-Step Progress Matrix:** Table detailing completed vs pending steps, implemented source files, unit test suites, property-based test suites, and live evaluation passes.
   - **Verification & Quality Metrics:** Test pass rates, evaluation benchmark scores ($\ge 95\%$ tool selection precision, 1.000 groundedness), and latency figures.
   - **Architectural & Design Decisions:** Non-obvious design choices, trade-offs, and user alignments made during development.
   - **Root Cause Analysis (RCA) Log:** If any defects, red tests, or eval regressions were investigated, summarize the 4-step RCA findings and user-selected fixes ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../_agents/rules/ai_sdlc_and_sdd_standards.md)).
   - **Resumption Guide & Next Actions:** Explicit next steps for resuming development seamlessly.

## Document Naming Convention
- `PROGRESS_REPORT_<YYYYMMDD>.md` (e.g. `PROGRESS_REPORT_20260920.md`)
