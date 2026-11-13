# Executive Briefing: Engineering Knowledge Graph & Safety Query Assistant

- **Interactive Demo:** [`docs/okf-query-agent-mockup.html`](./okf-query-agent-mockup.html)
- **Full Presenter Runbook:** [`docs/okf-query-agent-demo-script.md`](./okf-query-agent-demo-script.md)
- **Audience:** Plant Leadership, Process Safety Teams, Operations & Maintenance Leaders, Business & IT Decision-Makers

---

## 1. Executive Summary

In any industrial, chemical, or power facility, vital plant knowledge—how pipes connect, where safety valves sit, what limits equipment can handle, and how to respond during an upset—lives inside thousands of complex PDF drawings, datasheets, and manuals. Today, finding a complete, trustworthy answer to a safety or maintenance question can take an experienced engineer **hours or days** of manual cross-checking across multiple documents.

We built the **Engineering Knowledge Graph & Safety Query Assistant** to turn that multi-day search into a **5-second, fully verified answer**.

Instead of a generic AI chatbot that guesses from text snippets, our solution works in two clear steps:
1. **Smart Reading & Verification:** A multimodal AI reads engineering drawings (P&IDs), tables, and manuals visually—just like an engineer does—and organizes the facts into clean, human-readable knowledge files while automatically flagging any conflicting numbers between documents.
2. **Connected Answers with Full Proof:** Those verified facts are stored in a single connected database (**Google Cloud Spanner**) and tracked by a central governance catalog (**Google Cloud Dataplex**). When an engineer asks a question, the assistant traces how equipment is connected, checks safety rules, and shows the exact source PDF and page behind every single number.

In a live test of **120 real-world engineering and safety questions**, the assistant scored **100% accuracy (120/120)** with **zero made-up facts**.

---

## 2. Background & Challenge

### The Daily Reality in Plant Engineering
To answer a single question about a critical piece of equipment—such as Heat Exchanger `RH-E-9A`—an engineer often has to open:
- Equipment datasheets (for design pressure and temperature limits)
- Multiple piping drawings (to see what flows in, what flows out, and which valves protect it)
- Operating manuals (for inspection and maintenance rules)
- Corporate safety matrices (for risk ratings)

### Why Standard "Chat-with-PDF" AI Tools Fall Short
Most off-the-shelf AI document tools simply chop PDFs into paragraphs and search for similar words. That approach breaks down in engineering for four simple reasons:
1. **It Can't Follow Connections:** If a pipe starts on Drawing 1, crosses to Drawing 2, and feeds a backup pump on Drawing 3, a standard chatbot cannot reliably trace that path from start to finish.
2. **It Mixes Up Old and New Revisions:** If `Revision 0` and `Revision 11` of a drawing both exist, a standard AI may blend them together or pick the wrong number without warning anyone.
3. **It Can't Be Trusted for Safety Reviews:** Safety studies (like HAZOPs) require exact rules, exact valve setpoints, and clear before-and-after risk scores—not a probabilistic guess.
4. **No Paper Trail:** In regulated operations, an engineer cannot act on an AI answer unless they can see *exactly* which approved drawing and revision it came from.

---

## 3. Solution & Business Benefits

### How the Solution Works (In Plain English)
We separate **reading the PDFs** from **answering the questions** so that AI creativity never leaks into the live plant database:

- **Step 1 — Visual Extraction (`extracter_agent`):** Gemini's multimodal AI looks at high-resolution images of engineering drawings and tables, extracts equipment tags, pipe connections, and safety setpoints, and checks if different documents disagree. If two drawings show different values, it raises a clear **`⚠️ CONFLICT`** warning instead of hiding it.
- **Step 2 — Connected Knowledge & Lineage (`query_agent`):** Verified facts are loaded into **Google Cloud Spanner**, which lets the assistant search by **meaning** (concepts), by **exact tag** (like `RH-V13`), and by **connections** (following pipes and control loops step by step) all in one place. **Dataplex Universal Catalog** keeps a complete audit trail showing how every fact moved from the original PDF into the system.

### Key Business Benefits
- **Cut Safety & HAZOP Prep from Days to Seconds:** Automatically builds a structured safety worksheet showing unmitigated risk, active safeguards (alarms, relief valves, interlocks), and final residual risk.
- **Catch Document Conflicts Before Fieldwork:** Immediately alerts engineers when two drawings or revisions disagree, preventing costly rework or safety mistakes.
- **Faster Incident Response:** In seconds, operators can see the "blast radius" of an equipment failure—every downstream pump and system affected—alongside the approved backup recovery steps.
- **100% Audit-Ready:** Every answer links directly back to the exact source PDF, drawing sheet, and revision.

---

## 4. Key Executive Talking Points

- **On Safety & Trust:**
  > *"Standard AI guesses from text. Our assistant traces real plant connections, applies your exact corporate risk matrix, and cites the approved drawing and revision for every number."*
- **On Conflicting Drawings:**
  > *"When two drawings disagree, most AI tools quietly pick one and hope for the best. Ours puts a bright warning flag on the conflict so an engineer can verify it before anyone touches a valve."*
- **On Speed & Simplicity:**
  > *"We combined meaning-based search, exact tag lookup, and connection tracing inside a single database—Google Cloud Spanner—so engineers get complete, auditable answers in under five seconds."*

---

## 5. Demo Script: 6-Step Executive Walkthrough (5–6 Minutes)

> **Before You Start:** Open [`docs/okf-query-agent-mockup.html`](./okf-query-agent-mockup.html) in a full-screen browser and click **`↺ Reset Demo`** in the top-right corner.

### Quick Run-of-Show

| Step | Time | What to Click | What Shows on the Right | Key Takeaway |
| :---: | :---: | :--- | :--- | :--- |
| **1** | `0:00 – 0:50` | Tour the screen (`RH-E-9A` selected) | **Knowledge Graph** | Why normal AI fails on engineering drawings |
| **2** | `0:50 – 1:50` | **`01 Equipment & Safety Specs`** | **Knowledge Catalog** | Exact specs, safety setpoints & `⚠️ CONFLICT` alert |
| **3** | `1:50 – 2:50` | **`02 Upstream / Downstream Trace`** | **Knowledge Graph** *(Flow Trace)* | Tracing pipes & valves across multiple drawings |
| **4** | `2:50 – 4:15` | **`03 HAZOP & Risk Assessment`** | **Vector & RRF** | Automated safety study: Before vs. After safeguards |
| **5** | `4:15 – 5:15` | **`04 Failure Blast Radius`** | **Knowledge Graph** *(Blast Radius)* | Instant impact map if cooling fails + recovery plan |
| **6** | `5:15 – 6:15` | **`05 Data Lineage & Source Docs`** | **Lineage & Docs** | Full paper trail back to original PDFs & close |

---

### Step-by-Step Narration

#### Step 1: The Challenge & Workspace Tour (`0:00 – 0:50`)
- **Action:** Point to the **Left Panel** (plant equipment list), **Center Panel** (chat), and **Right Panel** (live visual tabs).
- **Say:**
  > *"In any plant, vital safety knowledge is buried across thousands of drawings, datasheets, and manuals. Standard AI chatbots fail here because they can't follow pipe connections across drawings, they mix up old and new revisions, and they don't show where their answers came from. What you're looking at is our **OKF Query Assistant**—built on Google Cloud to give engineers fast, connected, and 100% verifiable answers."*

#### Step 2: Equipment Specs & Catching Drawing Conflicts (`0:50 – 1:50`)
- **Action:** Click **`01 Equipment & Safety Specs`**. Point to the amber **`⚠️ CONFLICT`** box and the **Knowledge Catalog** tab that opens on the right.
- **Say:**
  > *"In under five seconds, we get the complete safety profile for Heat Exchanger `RH-E-9A`—including its `600 PSIG` relief valve (`RH-V13`) and automatic `Interlock G`."*
  > *"More importantly, look at the amber warning box. Two different drawings disagree on valve `HCV-606`. Instead of guessing, the system flags the conflict side-by-side so an engineer can verify it before fieldwork."*

#### Step 3: Tracing Pipes Upstream & Downstream (`1:50 – 2:50`)
- **Action:** Click **`02 Upstream / Downstream Trace`**. Point to the animated **Knowledge Graph** on the right and click a connected node (like `SI-P-6A` or `PEN-X-11`).
- **Say:**
  > *"Now let's ask something a normal PDF chatbot can't do: trace what feeds into this heat exchanger and where it flows next. On the right, the system maps the entire path—from the sump and pump upstream, to both the main injection line and the backup cross-tie downstream—including every valve along the way."*

#### Step 4: Automated HAZOP Safety & Risk Study (`2:50 – 4:15`)
- **Action:** Click **`03 HAZOP & Risk Assessment`**. Scroll through the risk matrix and the HAZOP table, then point to the **Vector & RRF** tab on the right.
- **Say:**
  > *"This is a huge time-saver for Process Safety teams. First, the assistant pulls your company's official `4×5` Risk Matrix. Then it builds a full HAZOP table showing **Risk Before Safeguards** versus **Risk After Safeguards**—for example, showing how alarms, relief valves, and backup Train B bring an Extreme `RAC 1` risk down to an acceptable `RAC 3` or `RAC 4`. On the right, you can see the exact document matches backing every safeguard."*

#### Step 5: Failure Blast Radius & Recovery Plan (`4:15 – 5:15`)
- **Action:** Click **`04 Failure Blast Radius`**. Point to the pulsing red **Blast Radius** map on the right and the red recovery box in the chat.
- **Say:**
  > *"If a critical cooling exchanger (`CC-E-17A`) fails, operators need to know what else is affected right now. The red map shows the 3-step ripple effect—first overheating the pump seals, then starving the backup pump, and finally impacting injection. Right below it, the assistant gives the verified recovery steps: switch to independent Train B and open the crossover valves."*

#### Step 6: Full Audit Trail & Wrap-Up (`5:15 – 6:15`)
- **Action:** Click **`05 Data Lineage & Source Docs`**. On the **Lineage & Docs** tab on the right, click between the source PDFs (`PID-1-SI-LR20448` and `PID-1-SI-LR20449`) to preview the drawings.
- **Say:**
  > *"Finally, in a regulated plant, you have to prove where every number came from. On the right is the complete paper trail—from the original approved PDF drawings, to the structured knowledge file, into our database and governance catalog. You can click any PDF to see the exact drawing and revision."*
  > *"To wrap up: this turns days of manual drawing checks and safety prep into seconds—while catching conflicts and keeping 100% proof."*

- **Optional Bonus (`+30s`):** Click **`06 Vector SOP & Fouling Search`** to show how the assistant also finds exact maintenance rules (like when to plug heat exchanger tubes) from operating manuals.
