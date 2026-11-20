# Management of Change (`reference/raw/moc/`)

Place approved **Management of Change (MOC)**, **Engineering Change Notice (ECN)**, and **Field Change Request (FCR)** packages (`.pdf`, `.docx`, `.xlsx`) in this folder.

## Supported Lifecycle Semantics (`SPEC-20261120-UNIFIED-WORKBENCH-V2`)
- **Authoritative Override (`MOC_AUTHORITY`):** Approved MOCs update active design parameters, trip setpoints, and piping topology in-place while tagging un-redrafted master P&IDs/Data Sheets as `PENDING_REDRAFT` (distinct from unauthorized `⚠️ CONFLICT` discrepancies).
- **Topological Removals & Reroutes:** Decommissioned instruments (`removed_instruments`) and lines (`removed_connections`) are cleanly removed from active OKF tables and Cloud Spanner `OkfKnowledgeGraph` edges while preserving audit history in `entity_metadata.moc_history`.
- **Upload to GCS:**
  ```bash
  source .env
  gcloud storage cp /path/to/MOC-2026-001.pdf \
    "gs://${DESTINATION_GCS_BUCKET}/${SOURCE_GCS_RAW_PREFIX:-reference/raw}/moc/" \
    --project="${GOOGLE_CLOUD_PROJECT}"
  ```
  Then click **`↻ Sync GCS`** in the Extractor Studio toolbar to refresh the file list immediately.
