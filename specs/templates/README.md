# Specification Templates (`specs/templates/`)

This directory contains standardized templates for authoring **Spec-Driven Development (SDD)** documents.

## Available Templates

- **[`sdd-template.md`](./sdd-template.md):** Standardized specification document template with embedded:
  - Runtime separation matrix (Gemini Enterprise Agent Platform vs Google Cloud Run)
  - Interactive Mermaid sequence diagrams
  - Type and API contract schemas
  - 13-rule DevOps, Security, ADK, and RCA governance checklist
  - Step-by-step implementation plan requiring **Unit Tests** and **Property-Based Tests (PBT)** for every step
  - Live agent evaluation (`agents-cli eval`) verification criteria
  - Plan progress tracking protocol

## Usage

To start a new feature or architectural proposal:
1. Copy `sdd-template.md` to `specs/features/SPEC-<YYYYMMDD>-<FEATURE_NAME>.md`.
2. Fill out all sections completely before writing production code.
3. Align with stakeholders on the implementation steps and test designs.
4. Execute implementation step-by-step with continuous progress updates in [`specs/plan/`](../plan/).
