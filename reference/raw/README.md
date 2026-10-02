# Raw Engineering Source Documents (`reference/raw/`)

This directory holds the raw engineering PDF source documents ingested by **Agent 1 (`extracter_agent`)** and displayed side-by-side in the **Extraction Workbench (`extracter-agent-web`)**.

> **Immutability Rule:** Files under `reference/raw/` are treated as **strictly read-only source of truth** during agent execution. Neither `extracter_agent` nor `query_agent` modifies or deletes raw source PDFs.

---

## 📁 Canonical Subfolder Structure

All raw PDFs must be placed inside one of the **5 canonical category subfolders** (both locally under `reference/raw/` and in Google Cloud Storage under `gs://<DESTINATION_GCS_BUCKET>/reference/raw/`):

| Subfolder | Document Types | Examples |
| :--- | :--- | :--- |
| [`data_sheets/`](./data_sheets/README.md) | Process Data Sheets, Mechanical Equipment Data Sheets, Relief Valve (PSV) & Control Valve Sizing Packages | `DS-V2301_Preflash_Column_Z1.pdf`, `DS-D2304_Reflux_Drum_Z0.pdf` |
| [`pid/`](./pid/README.md) | Piping & Instrumentation Diagrams (P&IDs) — single-sheet or multi-sheet CAD/scanned drawing packages | `ML101620329-part-1.pdf` .. `ML101620329-part-8.pdf`, `PID-23-0012_Preflash_Tower_Z1.pdf` |
| [`pfd/`](./pfd/README.md) | Process Flow Diagrams (PFDs), Material Selection Diagrams (MSDs), and Heat & Material Balance (H&MB) sheets | `PFD-23-0001_Cumene_Fractionation_Z1.pdf` |
| [`operating_manuals/`](./operating_manuals/README.md) | Plant Operating Manuals, Equipment Inspection & Maintenance Manuals, Startup/Shutdown SOPs | `Inspection_Manual_for_Heat_Exchangers_1.pdf`, `OM-2300_Fractionation_Operating_Manual_R2.pdf` |
| [`standards/`](./standards/README.md) | Engineering Standards, HAZOP Guides, Risk Assessment Matrices (RAM), SIS Cause & Effect Matrices, Safety Data Sheets (SDS) | `HAZOP_Training_Guide.pdf`, `Risk_Assessment_Matrix.pdf`, `SDS-Cumene_Hydroperoxide_R1.pdf` |

---

## 📥 How to Add Source PDFs (Local & Google Cloud Storage)

### 1. Local Development (`reference/raw/<subfolder>/`)
Copy your `.pdf` files directly into the appropriate subfolder:

```bash
cp /path/to/your_datasheet.pdf reference/raw/data_sheets/
cp /path/to/your_pid_drawing.pdf reference/raw/pid/
cp /path/to/your_pfd.pdf reference/raw/pfd/
cp /path/to/your_manual.pdf reference/raw/operating_manuals/
cp /path/to/your_standard.pdf reference/raw/standards/
```

### 2. Google Cloud Storage (`gs://<DESTINATION_GCS_BUCKET>/reference/raw/<subfolder>/`)
When running on **Vertex AI Agent Runtime (`agent_runtime`)** and **Google Cloud Run (`cloud_run`)**, `extracter_agent` discovers and reads PDFs from `gs://${DESTINATION_GCS_BUCKET}/${SOURCE_GCS_RAW_PREFIX}/` (default prefix: `reference/raw`).

```bash
# Load bucket & prefix settings from .env
source .env

# Option A: Sync your entire local reference/raw/ directory tree to GCS
gcloud storage rsync reference/raw "gs://${DESTINATION_GCS_BUCKET}/${SOURCE_GCS_RAW_PREFIX:-reference/raw}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --recursive

# Option B: Upload a single PDF directly to a specific GCS subfolder
gcloud storage cp /path/to/your_pid.pdf \
  "gs://${DESTINATION_GCS_BUCKET}/${SOURCE_GCS_RAW_PREFIX:-reference/raw}/pid/"

# Option C: Provision infra + sync reference/raw/ via deploy.sh
./deploy.sh --target infra
```
