# Plan Progress Report: MOC Authority, Topological Lifecycle & Document Revision Hardening

**Report ID:** `PROGRESS_REPORT_20261005`  
**Linked Specification:** [`specs/features/SPEC-20261005-MOC-AND-DOCUMENT-UPDATE-LIFECYCLE.md`](../features/SPEC-20261005-MOC-AND-DOCUMENT-UPDATE-LIFECYCLE.md)  
**Baseline Reference:** [`specs/baseline/system-overview.md`](../baseline/system-overview.md)  
**Date:** `2026-10-05`  
**Current Lifecycle Phase:** Phase 2 (SDD Step 2.3 — Pre-Code Stakeholder Alignment Sub-Gate)  

---

## 1. Phase 1 (Inception) & Design Decisions Log

All four architectural design decisions were clarified and confirmed with the user via `ask_question`:

| Decision ID | Area | Confirmed Architectural Decision |
| :--- | :--- | :--- |
| **A1** | **MOC Authority & Pending Redraft Model** | **Authoritative MOC Override + `PENDING_REDRAFT` Lineage:** Approved MOCs update active parameter values, setpoints, and topology in-place; prior un-redrafted P&ID/Data Sheet values are preserved with `🔄 MOC PENDING REDRAFT` callouts and `source_role="PENDING_REDRAFT"` in Cloud Spanner (`FactLineageEdges`), while `⚠️ CONFLICT` (`has_conflict=TRUE`, `source_role="CONFLICTING"`) is strictly reserved for unauthorized cross-document discrepancies. |
| **A2** | **Topological Removals & Stream Reroutes** | **Active Edge Removal/Replacement + Historical Audit Trail:** Support `removed_instruments` and `removed_connections` to delete decommissioned `MONITORS_OR_TRIPS` and `CONNECTS_TO` edges from active OKF tables and Spanner `OkfKnowledgeGraph`; replace `source_tag`/`target_tag`/`setpoint` in-place on MOC or revision updates while logging prior states in `entity_metadata.moc_history`. |
| **A3** | **3-Part Document Update Hardening** | 1. **Cross-Filename Supersession:** `superseded_sources: list[str]` on synthesis tools so renamed replacement files cleanly supersede old PDFs.<br>2. **Deterministic Revision Rank Comparator (`compare_revision_tokens`):** Prevents out-of-order ingestion of older revisions (`Z0` after `Z1`) from overwriting newer revisions.<br>3. **Auto-Clearing Resolved `⚠️ CONFLICT` Bullets:** Automatically prunes `⚠️ CONFLICT — <Topic>:` bullets from `## Hazards & Safeguards` once the parameter discrepancy is resolved. |
| **A4** | **Canonical `reference/raw/moc/` & Synthetic Fixture** | Add `reference/raw/moc/` (`reference/raw/moc/README.md`) as a 6th canonical subfolder and generate `reference/raw/moc/MOC-2026-042_D2304_Quench_and_Setpoint_Upgrade_R1.pdf` via `scripts/generate_synthetic_reference.py`. |

---

## 2. Step-by-Step Implementation & Verification Matrix

| Step | Description | Deterministic Unit Tests | Property-Based Tests (PBT) | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Step 0** | **Brownfield Baseline & Feature SDD Authoring** (`specs/baseline/system-overview.md`, `specs/features/SPEC-20261005-MOC-AND-DOCUMENT-UPDATE-LIFECYCLE.md`) | Gate Validator (`validate_sdlc_gate.py`) | N/A | **Completed (Awaiting Sign-Off)** |
| **Step 1** | **Domain Models, Revision Rank Comparator & MOC Source Identification** (`extracter_agent/models/domain.py`, `extracter_agent/okf/synthesizer.py`, `query_agent/models/schemas.py`) | Pending (`tests/test_moc_and_revision_lifecycle.py`) | Pending (`hypothesis` antisymmetry, reflexivity, monotonicity & round-trip) | **Pending Gate Approval** |
| **Step 2** | **OKF Synthesizer — MOC Override (`PENDING_REDRAFT`), Topological Removals/Reroutes & Auto-Clearing Resolved Conflicts** (`extracter_agent/okf/synthesizer.py`) | Pending (`tests/test_moc_and_revision_lifecycle.py`) | Pending (`hypothesis` out-of-order commutativity, removal completeness, conflict pruning) | **Pending Gate Approval** |
| **Step 3** | **Spanner Lineage Extractor & Graph Edge Precision** (`query_agent/spanner/lineage_extractor.py`, `query_agent/tools/spanner_tools.py`, `query_agent/static/index.html`) | Pending (`tests/test_moc_and_revision_lifecycle.py`, `tests/test_query_agent_unit.py`) | Pending (`hypothesis` endpoint-scoped `CONNECTS_TO` & `MOC_AUTHORITY`/`PENDING_REDRAFT` lineage) | **Pending Gate Approval** |
| **Step 4** | **ADK Tool Registries, Orchestrator Prompts, `reference/raw/moc/` & Synthetic MOC Fixture** (`extracter_agent/tools/`, `extracter_agent/agent/`, `scripts/generate_synthetic_reference.py`) | Pending (`tests/test_pdf_unit.py`, `tests/test_agent_unit.py`, `evals/test_eval_benchmarks.py`) | Pending (`hypothesis` 21-PDF dataset & zero-confidentiality invariant) | **Pending Gate Approval** |

---

## 3. Root Cause Investigation (RCA) Log
- *No test or evaluation failures encountered yet.*

---

## 4. Resumption Guide & Next Actions

Development is paused at **Phase 2 SDD Step 2.3 (Pre-Code Stakeholder Alignment Sub-Gate)** with all specification artifacts committed and pushed to the `development` branch. When resuming:
1. Execute **Step 1** of [`SPEC-20261005-MOC-AND-DOCUMENT-UPDATE-LIFECYCLE.md`](../features/SPEC-20261005-MOC-AND-DOCUMENT-UPDATE-LIFECYCLE.md): implement `MOCChangeRecord`, `EquipmentEntity` lifecycle fields (`superseded_sources`, `removed_instruments`, `removed_connections`, `moc_history`), `extract_revision_token()`, `compare_revision_tokens()`, `is_moc_source()`, and `FactLineageEdge.source_role` (`MOC_AUTHORITY`, `PENDING_REDRAFT`) + unit & Hypothesis property-based tests in `tests/test_moc_and_revision_lifecycle.py`.
2. Execute **Step 2**: update `extracter_agent/okf/synthesizer.py` (`_merge_parameter_lists`, `merge_equipment_entity_with_existing`, `synthesize_equipment_markdown`) for MOC `PENDING_REDRAFT` overrides, topological removals/reroutes, cross-filename supersession, revision rank comparison, and auto-clearing resolved `⚠️ CONFLICT` bullets.
3. Execute **Step 3**: update `query_agent/spanner/lineage_extractor.py`, `query_agent/tools/spanner_tools.py`, and `query_agent/static/index.html` for `MOC_AUTHORITY` / `PENDING_REDRAFT` lineage roles and endpoint-scoped `CONNECTS_TO` extraction.
4. Execute **Step 4**: update ADK tools (`okf_tools.py`, `pdf_tools.py`), orchestrator prompts, `reference/raw/moc/README.md`, and `scripts/generate_synthetic_reference.py` (`MOC-2026-042_D2304_Quench_and_Setpoint_Upgrade_R1.pdf`), then run full `pytest tests/ evals/ -v` and `ruff check`.

