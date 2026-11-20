# Consolidated Discovery Documents (`specs/discovery/`)

This directory stores optional **Pre-Inception Consolidated Discovery Documents** (`DISCOVERY-<YYYYMMDD>-<PROJECT>.md`) authored using [`../templates/discovery-template.md`](../templates/discovery-template.md) and the **[`requirements-discovery`](../../_agents/skills/requirements_discovery/SKILL.md)** skill.

## When to Use `specs/discovery/` (Optional Pre-AI-SDLC Step)

- **Use `specs/discovery/` when you have raw, multi-modal stakeholder inputs** — such as interview transcripts, architecture/whiteboard drawings (`.png`/`.jpg`/`.pdf`), email threads, SOP manuals, spreadsheets, or RFP packages — that need to be audited, reconciled for contradictions, and traced with verbatim citations before architecture and SDD authoring begin.
- **Skip `specs/discovery/` for lightweight or direct requests** — when requirements are concise or interactive, start **[`ai-sdlc`](../../_agents/skills/ai_sdlc/SKILL.md)** Phase 1 directly using codebase analysis + `ask_question`.

## How `ai-sdlc` Consumes Discovery Documents (Dual-Input Mode)

When a verified `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md` exists:
1. **`ai-sdlc` Phase 1 (Inception) & Phase 2 (SDD Authoring)** automatically ingest **Sections 2–7 and 11–14** to pre-populate business context, personas, SLAs, functional/non-functional contracts, regulatory/DLP constraints, and delivery phasing in `specs/features/SPEC-<YYYYMMDD>-<TITLE>.md` **without re-asking already answered questions**.
2. **`ask_question` focuses strictly on unresolved gaps:** Specifically **§2.5 (Top 3 Pre-Design Blockers)**, **§3.1 (Stakeholder Tensions)**, **§8 (`Blocking Architecture / SDD? = Yes` Open Questions)**, and **§10.1 (Cross-Artifact Contradictions)**.

## Naming Convention & Validation

- **File Naming:** `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT_SLUG>.md`
- **Automated Validator:**
  ```bash
  python3 _agents/skills/requirements_discovery/scripts/validate_discovery.py \
    --target specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT_SLUG>.md
  ```
