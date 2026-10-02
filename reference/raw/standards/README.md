# Engineering Standards, HAZOP, Risk Matrices & SDS (`reference/raw/standards/`)

Place **Engineering Design Standards**, **HAZOP Methodology Guides**, **Risk Assessment Matrices (RAM)**, **Safety Instrumented System (SIS) Cause & Effect Registers**, and **Chemical Safety Data Sheets (SDS)** (`.pdf`) in this folder.

## Typical Contents
- **HAZOP & Risk Assessment Standards:** HAZOP guide-word/deviation methodologies and corporate Risk Assessment Matrices (severity × likelihood scoring, escalation thresholds) used by `query_agent`'s 5-Stage HAZOP & Risk Assessment engine (`execute_multistage_risk_and_hazop_query`).
- **SIS Interlock & Cause-and-Effect Registers:** Voting logic (`1oo2`, `2oo3`), trip setpoints, SIL ratings, and final control element actions.
- **Safety Data Sheets (SDS):** Chemical hazard profiles, decomposition/runaway temperatures, flash points, and occupational exposure limits.
- **Included Reference Files:**
  - `HAZOP_Training_Guide.pdf`
  - `Risk_Assessment_Matrix.pdf`

## Adding Files Locally & to GCS

```bash
# 1. Local: copy Standard / HAZOP / SDS PDFs into this directory
cp /path/to/your_standard_or_sds.pdf reference/raw/standards/

# 2. GCS: upload directly or sync from local
source .env
gcloud storage cp reference/raw/standards/*.pdf \
  "gs://${DESTINATION_GCS_BUCKET}/${SOURCE_GCS_RAW_PREFIX:-reference/raw}/standards/"
```
