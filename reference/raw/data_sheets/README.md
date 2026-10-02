# Process & Mechanical Data Sheets (`reference/raw/data_sheets/`)

Place **Equipment Data Sheets**, **Instrument / Control Valve Sizing Packages**, and **Pressure Safety Valve (PSV) Calculation Sheets** (`.pdf`) in this folder.

## Typical Contents
- **Vessel, Column & Drum Data Sheets:** Design pressures/temperatures, dimensions (ID, T/T length), nozzle schedules, and metallurgy (e.g., `DS-V2301_Preflash_Column_Z1.pdf`, `DS-D2304_Reflux_Drum_Z0.pdf`).
- **Heat Exchanger (TEMA) & Fired Heater Data Sheets:** Shell/tube operating & design ratings, heat duty, heat transfer area, tube counts.
- **Rotating Equipment (Pump & Compressor) Data Sheets:** Rated flow, differential head, NPSHa/NPSHr, shaft power, seal flush plans, and driver ratings.
- **Instrument, Control Valve & Relief Valve Packages:** Multi-page ISA instrument data sheets, Cv sizing tables, and API 520/526 orifice sizing sheets.

## Adding Files Locally & to GCS

```bash
# 1. Local: copy PDFs into this directory
cp /path/to/DS-V2301_Preflash_Column_Z1.pdf reference/raw/data_sheets/

# 2. GCS: upload directly or sync from local
source .env
gcloud storage cp reference/raw/data_sheets/*.pdf \
  "gs://${DESTINATION_GCS_BUCKET}/${SOURCE_GCS_RAW_PREFIX:-reference/raw}/data_sheets/"
```
