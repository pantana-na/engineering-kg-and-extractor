# Process Flow Diagrams (`reference/raw/pfd/`)

Place **Process Flow Diagrams (PFDs)**, **Heat & Material Balance (H&MB) Tables**, and **Material Selection Diagrams (MSDs)** (`.pdf`) in this folder.

## Typical Contents
- **Process Flow Diagrams (PFDs):** High-level unit topology, major equipment blocks, primary process streams, operating pressures/temperatures, and control philosophy.
- **Heat & Material Balance (H&MB) Sheets:** Stream-by-stream mass/molar flow rates, compositions, vapor fractions, densities, enthalpies, and molecular weights.

## Adding Files Locally & to GCS

```bash
# 1. Local: copy PFD PDFs into this directory
cp /path/to/PFD-23-0001_Cumene_Fractionation_Z1.pdf reference/raw/pfd/

# 2. GCS: upload directly or sync from local
source .env
gcloud storage cp reference/raw/pfd/*.pdf \
  "gs://${DESTINATION_GCS_BUCKET}/${SOURCE_GCS_RAW_PREFIX:-reference/raw}/pfd/"
```
