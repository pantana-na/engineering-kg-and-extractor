# Piping & Instrumentation Diagrams (`reference/raw/pid/`)

Place **Piping & Instrumentation Diagrams (P&IDs)** and **Utility Flow Diagrams (UFDs)** (`.pdf`) in this folder.

## Typical Contents
- **Single-Sheet or Multi-Sheet P&ID Packages:** Vector CAD or high-resolution scanned P&IDs containing equipment symbols, piping line numbers/sizes/specs, inline valves, reducers, vents/drains, instrument bubbles, and safety interlock ties.
- **Included Reference Files:**
  - `ML101620329-part-1.pdf` through `ML101620329-part-8.pdf` (Multi-sheet Seabrook Station License Renewal P&ID drawings covering Spent Fuel Pool, Safety Injection, Residual Heat Removal, Containment Building Spray, and Nuclear Sample Systems).

## How `extracter_agent` Processes P&IDs
- Uses **300 DPI multimodal vision** with **7 multi-scale images per landscape drawing sheet** (1 full-sheet overview + 6 overlapping 3x2 regional zooms including Top-Center and Bottom-Center bridge crops) to trace continuous piping headers (`CONNECTS_TO`) and instrument impulse lines (`MONITORS_OR_TRIPS`) into Cloud Spanner Property Graph (`OkfKnowledgeGraph`).

## Adding Files Locally & to GCS

```bash
# 1. Local: copy P&ID PDFs into this directory
cp /path/to/your_pid_drawing.pdf reference/raw/pid/

# 2. GCS: upload directly or sync from local
source .env
gcloud storage cp reference/raw/pid/*.pdf \
  "gs://${DESTINATION_GCS_BUCKET}/${SOURCE_GCS_RAW_PREFIX:-reference/raw}/pid/"
```
