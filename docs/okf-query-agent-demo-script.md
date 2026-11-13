# Executive Demo Script & Talking Points: OKF Query Agent (5–7 Minutes)

- **Target Demo UI:** [`docs/okf-query-agent-mockup.html`](./okf-query-agent-mockup.html)
- **Baseline UI Spec:** [`docs/okf-query-agent-mockup-spec.md`](./okf-query-agent-mockup-spec.md)
- **Target Duration:** **5:30 – 6:30 minutes** (with optional +30s live Q&A pocket scenario)
- **Target Audience:** Engineering Leaders, Process Safety / PHA Teams, Chief Data & AI Architects, Operations Executives

---

## ⚡ Pre-Demo Setup Checklist (30 Seconds Before Screen Share)

1. Open [`docs/okf-query-agent-mockup.html`](./okf-query-agent-mockup.html) in a full-screen browser window (`100%` zoom on a 1080p/1440p display).
2. Click **`↺ Reset Demo`** in the top-right header to ensure a clean welcome state with **`Active Focus: RH-E-9A`** and the **Knowledge Graph** open on the right.
3. Keep the **Crisp Enterprise Light** theme active at start (you can click **`🌙 Dark Blueprint`** once during Act 1 or Act 6 to showcase the control-room theme).

---

## ⏱️ Pacing & Run-of-Show Overview (6 Minutes Total)

| Time | Segment | UI Action | Synchronized Studio Tab | Core Value Proved |
| :---: | :--- | :--- | :--- | :--- |
| **0:00 – 0:50** | **1. Hook & Workspace Orientation** | Tour Left Registry, Center Chat & Right Tabs | `🕸️ Knowledge Graph` | Why standard vector RAG fails on P&IDs & safety systems |
| **0:50 – 1:50** | **2. Equipment & Safety Parameters** | Click **`01 Equipment & Safety Specs`** | `🏛️ Knowledge Catalog` | Exact specs, safety relief/SIS setpoints & `⚠️ CONFLICT` detection |
| **1:50 – 2:50** | **3. Upstream / Downstream Trace** | Click **`02 Upstream / Downstream Trace`** | `🕸️ Knowledge Graph` *(Flow Trace)* | Deterministic multi-hop ISO GQL P&ID connectivity |
| **2:50 – 4:15** | **4. HAZOP & Risk Study (Hero)** | Click **`03 HAZOP & Risk Assessment`** | `🧬 Vector & RRF` | Governing `4×5 RAM` standard + **Before vs. After Safeguard** risk |
| **4:15 – 5:15** | **5. Failure Blast Radius** | Click **`04 Failure Blast Radius`** | `🕸️ Knowledge Graph` *(Blast Radius)* | Cascading failure impact across process + utility systems |
| **5:15 – 6:15** | **6. Data Lineage & Close** | Click **`05 Data Lineage & Source Docs`** | `📄 Lineage & Docs` | 100% auditability back to raw PDF revisions & Dataplex |

---

## 🎙️ Step-by-Step Script, Clicks & Talking Points

### Act 1: The Engineering Challenge & OKF Workbench Intro (`0:00 – 0:50`)

- **Screen Action:**
  - Start on the Welcome screen. Gesture briefly across the **Left Plant Registry** (`RH-E-9A`, `RH-P-8A`, `SI-P-6A`, `CC-E-17A`, plus OKF Standards), the **Center Agent Pane**, and the **4 Tabs** on the right.
  - *(Optional)* Click the **`☰` button** top-left off and back on to show how the layout declutters for deep engineering focus.
- **Talking Points:**
  > *"In complex industrial, power, and chemical facilities, critical safety knowledge is trapped across thousands of multi-sheet P&IDs, process data sheets, operating manuals, and risk standards. Standard 'chat-with-PDF' vector RAG fails here for three reasons: it cannot trace multi-hop piping connectivity across drawing sheets, it silently mixes outdated drawing revisions, and it cannot reason deterministically over safety interlocks."*
  >
  > *"What you’re looking at is the **OKF Query Agent** built on **Google ADK (`gemini-3.8-flash`)**, **Cloud Spanner Graph-RAG**, and **Dataplex Universal Catalog**. Raw engineering PDFs have been extracted into structured Open Knowledge Format (`OKF v0.2`) and synced deterministically into Cloud Spanner—combining an ISO GQL Property Graph, 768-dimension Vector + Keyword RRF search, and line-item PDF provenance in a single engine."*

---

### Act 2: Equipment Detail, Safety Setpoints & Conflict Surfacing (`0:50 – 1:50`)

- **Screen Action:**
  1. Click Welcome Card **`01 • SPECS & SAFETY — Equipment Detail & Safety Parameters`** (or pill `01 Equipment & Safety Specs`).
  2. **During the ~4.5s Thinking Window:** Point to the live animated reasoning card.
  3. **When Answer Appears:** Point to the parameter table, the amber `⚠️ Cross-Document Revision Alert`, and the **Right Studio**, which automatically switches to **`🏛️ Knowledge Catalog`**.
- **What to Say During the 4.5s Thinking Window:**
  > *"Notice complete transparency while the agent works: first, Google Cloud **Model Armor** validates prompt safety in ~140 milliseconds, then `gemini-3.8-flash` plans its retrieval trajectory—calling Spanner SQL for design facts and ISO GQL to check cross-document lineage."*
- **Talking Points on the Result:**
  > *"In under five seconds, we get a 100% grounded engineering dossier for **RHR Heat Exchanger `RH-E-9A`**: Safety Class 2 tube side, 12-inch borated coolant nozzles, 20-inch Component Cooling Water shell, thermal relief valve **`RH-V13` set at `600 PSIG`**, and cooldown bypass **`Interlock G`**."*
  >
  > *"Even more importantly, look at the amber callout—and the synchronized **Dataplex Knowledge Catalog** on the right. Instead of guessing when two P&ID sheets disagree, the platform explicitly flags a **`⚠️ CONFLICT`** between `PID-1-SI-LR20448 (Rev 11)` and continuation sheet `PID-1-SI-LR20449 (Rev 0)` on valve `HCV-606` so an engineer verifies it before fieldwork."*

---

### Act 3: Multi-Hop Upstream & Downstream P&ID Connectivity (`1:50 – 2:50`)

- **Screen Action:**
  1. Click top pill **`02 Upstream / Downstream Trace`**.
  2. **During the ~4.6s Thinking Window:** Point out `traverse_equipment_connectivity_graph (Spanner ISO GQL)` executing `direction="BOTH", max_hops=3`.
  3. **When Answer Appears:** Highlight the **Right Studio**, which automatically switches to **`🕸️ Knowledge Graph` in animated `Flow Trace` mode**. Pan/zoom slightly or click a neighbor node (`SI-P-6A` or `PEN-X-11`) to show the bottom node inspector.
- **What to Say During the 4.6s Thinking Window:**
  > *"Now let's ask a question pure vector search can never answer reliably: tracing upstream suction feeds and downstream injection paths across multiple P&ID sheets. Here the agent executes native **ISO GQL** directly inside Cloud Spanner."*
- **Talking Points on the Result:**
  > *"Look at how the **Knowledge Graph** on the right synchronizes in **Flow Trace Mode**. Upstream, we trace post-LOCA suction from Containment Sump `CBS-TK-10A` through 16-inch guard pipe `CBS-V8` into pump `RH-P-8A`, plus 20-inch shell cooling from `CC-E-17A`."*
  >
  > *"Downstream of `RH-E-9A`, the agent traces both the 8-inch Low-Head Safety Injection path through `Penetration X-11` to `RCS Cold Legs 1 & 2` **and** the 8-inch piggyback cross-tie (`MOV RH-V22`) feeding Intermediate-Head Safety Injection Pump `SI-P-6A`—complete with every inline check valve, flow element, and MOV."*

---

### Act 4: 5-Stage HAZOP Study & Risk Assessment — Before vs. After Safeguards (`2:50 – 4:15`)

- **Screen Action:**
  1. Click top pill **`03 HAZOP & Risk Assessment`**.
  2. **During the ~4.8s Thinking Window:** Highlight the 3 tools working together: `execute_multistage_risk_and_hazop_query` + `hybrid_search_okf_spanner (Vector 768-d + RRF)` + `traverse_equipment_connectivity_graph`.
  3. **When Answer Appears:**
     - Scroll gently through **Section 1 (`4×5 Qualitative Risk Assessment Matrix`)** and **Section 2 (`Node RH-E-9A HAZOP Worksheet`)**.
     - Point to the **Right Studio**, which auto-switches to **`🧬 Vector & RRF`**, showing the exact `Risk_Assessment_Matrix.pdf` and `RH-E-9A` chunks with live Vector Cosine, FTS Token, and fused RRF score bars.
- **What to Say During the 4.8s Thinking Window:**
  > *"Next is a game-changer for Process Hazard Analysis. Instead of spending days manually cross-referencing P&IDs against corporate risk matrices, watch the agent run a 5-stage HAZOP study—combining graph topology with hybrid Vector + Keyword RRF search."*
- **Talking Points on the Result:**
  > *"First, the agent retrieves and renders our plant’s governing risk standard (`Risk_Assessment_Matrix.pdf`)—intersecting **Severity `I–IV`** with **Probability `A–E`** into **Risk Assessment Codes `RAC 1` (Red — Stop, Immediate Correction) through `RAC 4` (Green — Acceptable)**."*
  >
  > *"Second, look at the **Node `RH-E-9A` HAZOP Worksheet**, which contrasts **Unmitigated Risk Before Safeguards** against **Residual Risk After Safeguards**:"*
  > - *"On **Loss of CCW Shell Cooling**, unmitigated risk is **`S=I, P=B → RAC 1 (Extreme)`** due to pump cavitation and core heat-removal loss. Crediting outlet alarm `TI-608`, `PSL-6103` switchover, and Train B redundancy (`RH-E-9B`) reduces probability to `E`, bringing residual risk to **`RAC 3 (Moderate)`**."*
  > - *"On **Blocked-In Tube Overpressure**, unmitigated **`RAC 1`** drops to **`RAC 3`** via passive 600 PSIG thermal relief valve `RH-V13` and sensor `TE-604`."*
  > - *"On **Rapid Cooldown Overcooling**, **`RAC 2`** drops to **`RAC 4 (Low / Acceptable)`** via automatic bypass **Interlock G** (`FIS-610` / `RH-FCV-610`)."*
  >
  > *"And on the right under **Vector & RRF**, you can inspect the exact `768-d` semantic similarity and `TOKENLIST` keyword fusion scores that grounded every safeguard."*

---

### Act 5: Equipment Failure Blast Radius & Operational Recovery (`4:15 – 5:15`)

- **Screen Action:**
  1. Click top pill **`04 Failure Blast Radius`**.
  2. **During the ~4.5s Thinking Window:** Note the downstream multi-hop traversal starting from `CC-E-17A`.
  3. **When Answer Appears:** Point immediately to the **Right Studio**, which switches to **`🕸️ Knowledge Graph` in pulsing crimson `Blast Radius` mode**, and review the 3-tier cascade table + red recovery callout.
- **What to Say During the 4.5s Thinking Window:**
  > *"During an abnormal plant event, operators need to know the immediate blast radius if an auxiliary cooling exchanger or pump trips."*
- **Talking Points on the Result:**
  > *"Look at the **Blast Radius** overlay pulsing on the graph. Because Primary CCW Exchanger `CC-E-17A` cools both the 20-inch shell of `RH-E-9A` and the 3/4-inch mechanical seals on `RH-P-8A`, a single outage cascades across three tiers: **Hop 1** overheats `RH-P-8A` seals and halts `RH-E-9A` heat rejection; **Hop 2** starves `SI-P-6A` piggyback suction (`MOV RH-V22`); and **Hop 3** impacts Cold Leg injection at `Penetration X-11`."*
  >
  > *"Alongside the impact, the agent surfaces the verified recovery playbook: immediate failover to independent **Train B (`RH-P-8B` / `RH-E-9B` / `CC-E-17B`)**, opening 3-inch crossover MOVs `SI-V111/V112`, and TA Logic realignment to Ultimate Heat Sink Cooling Tower pump `P-110A`."*

---

### Act 6: End-to-End Data Lineage, Source PDFs & Executive Close (`5:15 – 6:15`)

- **Screen Action:**
  1. Click top pill **`05 Data Lineage & Source Docs`**.
  2. **During the ~4.3s Thinking Window:** Point out `trace_data_lineage_and_conflicts` and `sync_or_inspect_knowledge_catalog (Dataplex v1 API)`.
  3. **When Answer Appears:** On the right **`📄 Lineage & Docs`** tab, point to the **4-Stage Provenance Pipeline**, click between **`PID-1-SI-LR20448`** and **`PID-1-SI-LR20449`** in the Source PDF Registry to preview their drawing excerpts, and optionally toggle **`🌙 Dark Blueprint`** in the top-right header to show the control-room theme.
- **What to Say During the 4.3s Thinking Window:**
  > *"Finally, in regulated engineering environments, an AI answer is unusable unless every number is auditable back to an approved stamp and revision. Here the agent audits Spanner lineage edges alongside **Google Cloud Dataplex Universal Catalog**."*
- **Talking Points on the Result & Closing Summary:**
  > *"On the right, you see the complete **4-Stage Deterministic Lineage**: from read-only raw PDFs in Cloud Storage, to human-reviewed OKF v0.2 Markdown (`MD5: 9f4c2e81b70d4a1e`, approved by Dr. M. Vance), synced deterministically into Cloud Spanner with zero LLM ingestion drift, and governed in Dataplex."*
  >
  > *"Clicking any PDF in the registry—whether `ML101620329-part-1.pdf` (`Rev 11`), `part-2.pdf`, or the Heat Exchanger Inspection Manual—shows the exact drawing sheet, grid coordinate, and conflict role."*
  >
  > *"In summary: by uniting **OKF extraction**, **Cloud Spanner Graph + Hybrid Vector RRF**, and **Google ADK**, engineering teams cut HAZOP preparation, P&ID tracing, and incident impact analysis from days to seconds—with 100% source provenance."*

---

## 🎯 Pocket Bonus & Common Executive Q&A (If Time Permits)

- **Bonus Click (`+30s` if asked about maintenance manuals or exact tag search):**
  - Click **`06 Vector SOP & Fouling Search`** (or type `"How do we monitor fouling on F-33 and when do we plug heat exchanger tubes?"` in the input bar).
  - *Talking Point:* Shows Reciprocal Rank Fusion matching exact instrument tag `PDIS-2622` (`TOKENLIST`) alongside semantic concepts (`≥40% eddy-current wall loss plugging rule` from `OM-HX-101`).

- **Top 3 Anticipated Q&A Responses:**
  1. **"How do you prevent hallucinations during ingestion into the database?"**
     - *Answer:* LLM multimodal vision (`extracter_agent`) is used **only** in Stage 1 to compile human-readable, Git/GCS-versioned OKF `.md` files with explicit citations. Stage 2 (`sync_markdown_bundle_to_spanner`) is **100% deterministic Python**—zero LLM calls—projecting verified Markdown tables and YAML connections directly into Cloud Spanner and Dataplex.
  2. **"What happens when a new P&ID revision or Management of Change (MOC) arrives?"**
     - *Answer:* Same-document newer revisions (`Rev Z0 → Rev Z1`) update parameters in place automatically; if two *different* active documents disagree (e.g., Datasheet vs. P&ID), both values are preserved side-by-side with an explicit `⚠️ CONFLICT` flag until resolved by an engineer.
  3. **"Why use Cloud Spanner instead of separate Graph DB + Vector DB + Relational DB?"**
     - *Answer:* Running SQL parameter lookups, multi-hop ISO GQL graph traversals, `768-d` vector cosine search, and `TOKENLIST` full-text RRF inside **one ACID database (`Cloud Spanner`)** eliminates cross-database sync lag, cuts operational overhead, and guarantees that graph edges and vector chunks always reflect the exact same `MD5` bundle version.
