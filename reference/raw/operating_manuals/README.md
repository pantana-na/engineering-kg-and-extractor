# Operating & Inspection Manuals (`reference/raw/operating_manuals/`)

Place **Plant Operating Manuals**, **Equipment Inspection & Maintenance Manuals**, **Standard Operating Procedures (SOPs)**, and **Troubleshooting Guides** (`.pdf`) in this folder.

## Typical Contents
- **Unit Operating Manuals:** Normal operation envelopes, startup/shutdown sequences, emergency trip responses, and operator troubleshooting procedures.
- **Equipment Inspection & Maintenance Manuals:** Mechanical inspection criteria, degradation mechanisms, tube bundle/shell testing, and preventive maintenance intervals.
- **Included Reference Files:**
  - `Inspection_Manual_for_Heat_Exchangers_1.pdf`

## Adding Files Locally & to GCS

```bash
# 1. Local: copy Operating/Inspection Manual PDFs into this directory
cp /path/to/your_operating_manual.pdf reference/raw/operating_manuals/

# 2. GCS: upload directly or sync from local
source .env
gcloud storage cp reference/raw/operating_manuals/*.pdf \
  "gs://${DESTINATION_GCS_BUCKET}/${SOURCE_GCS_RAW_PREFIX:-reference/raw}/operating_manuals/"
```
