# Live Evaluation Report: OKF Spanner Graph-RAG & Data Lineage Query Agent

- **Timestamp (UTC):** `2026-09-29T07:46:04.477448+00:00`
- **Vertex AI Agent Runtime (`agent_runtime`):** `projects/your-gcp-project-id/locations/asia-southeast1/reasoningEngines/<QUERY_AGENT_ENGINE_ID>`
- **Spanner Instance / Database:** `okf-demo-spanner` / `okf_demo_graph`
- **Total Questions Evaluated:** `120`
- **Passed Questions:** `120 / 120 (100.0%)`
- **Mean Tool Trajectory Precision:** `1.0000` (Target $\ge 0.9500$)
- **Mean Groundedness Score:** `1.0000` (Target $\ge 0.9500$)
- **Mean Query Latency:** `46.32s`

## Breakdown by Query Archetype

| Archetype | Total | Passed | Pass Rate | Trajectory Precision | Groundedness |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `A_ENTITY_PARAMETER_LOOKUP` | 25 | 25 | 100.0% | 1.0000 | 1.0000 |
| `B_INSTRUMENT_AND_INTERLOCK_LOOKUP` | 15 | 15 | 100.0% | 1.0000 | 1.0000 |
| `C_HYBRID_VECTOR_FTS_SEARCH` | 15 | 15 | 100.0% | 1.0000 | 1.0000 |
| `D_GRAPH_CONNECTIVITY_TRAVERSAL` | 15 | 15 | 100.0% | 1.0000 | 1.0000 |
| `E_BACKWARD_LINEAGE_AND_CONFLICT_AUDIT` | 15 | 15 | 100.0% | 1.0000 | 1.0000 |
| `F_FORWARD_PDF_BLAST_RADIUS` | 10 | 10 | 100.0% | 1.0000 | 1.0000 |
| `G_MULTISTAGE_HAZOP_AND_RISK_ASSESSMENT` | 20 | 20 | 100.0% | 1.0000 | 1.0000 |
| `H_CATALOG_AND_GOVERNANCE` | 5 | 5 | 100.0% | 1.0000 | 1.0000 |
