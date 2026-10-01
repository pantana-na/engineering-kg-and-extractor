---
name: architecture-diagram
description: "Creates professional, dark-themed technical architecture/cloud/infra diagrams and documentation as markdown (.md) files in the 'docs' folder inside the project folder (with companion standalone HTML/SVG assets). Use when the user asks to create, generate, draw or visualize a technical system architecture, cloud infrastructure, microservice topology, or api/database deployment map. Don't use for physical objects, whiteboard sketches, scientific diagrams, or narrative journeys."
---

# Architecture Diagram Skill

Generate professional, dark-themed technical architecture diagrams and documentation as markdown (`.md`) files in the `docs/` folder inside the project folder, with accompanying standalone HTML/inline SVG graphics. No external tools, no API keys, no rendering libraries — just write the files and review in markdown viewers or browsers.

## Scope

**Best suited for:** - Software system architecture (frontend / backend /
database layers) - Cloud infrastructure (VPC, regions, subnets, managed
services) - Microservice / service-mesh topology - Database + API map,
deployment diagrams - Anything with a tech-infra subject that fits a dark,
grid-backed aesthetic

**Look elsewhere first for:** - Physics, chemistry, math, biology, or other
scientific subjects - Physical objects (vehicles, hardware, anatomy,
cross-sections) - Floor plans, narrative journeys, educational / textbook-style
visuals - Hand-drawn whiteboard sketches (consider `excalidraw`) - Animated
explainers (consider an animation skill)

If a more specialized skill is available for the subject, prefer that. If none
fits, this skill can also serve as a general SVG diagram fallback — the output
will just carry the dark tech aesthetic described below.

Based on
[Cocoon AI's architecture-diagram-generator](https://github.com/Cocoon-AI/architecture-diagram-generator)
(MIT).

## Workflow

1. **Architecture & Spec Discovery:**
   - Inspect existing `specs/baseline/*.md`, `specs/features/SPEC-*.md`, `terraform/*.tf`, `app/`, `src/`, and `server/` to extract confirmed components, runtime boundaries, and data flows.
2. **Mandatory Clarification of Unknowns (`ask_question`):**
   - If any architectural boundary or topology detail is unknown or ambiguous, **pause and ask the user via `ask_question`** before generating the diagram:
     - **Diagram Mode:** Are we generating a **Target Dual-Runtime Architecture** (Greenfield) or a **Brownfield "As-Is vs. Target Modernization" Comparison** (e.g., Legacy 3-Tier/.NET $\rightarrow$ Cloud Run + Agent Runtime)?
     - **IAM & Ingress Edge Pattern:** Pattern 1 (External HTTPS Load Balancer + Serverless NEG + IAP), Pattern 2 (Direct Ingress + App-Level Google OAuth 2.0), or Pattern 3 (Direct Public Frontend `invoker-iam-disabled: true` + Private Backend)?
     - **Data & Integration Tiers:** Which specific databases (Cloud SQL, Spanner, Firestore, Vector Search, or legacy SQL Server) and external APIs should be depicted?
3. **Generate Markdown & Companion Interactive HTML:**
   - Save the primary markdown architecture document with `write_to_file` to `docs/<project-name>-architecture.md` (ensuring `docs/` exists via `validate_sdlc_gate.py --init` if needed).
   - Save the standalone interactive HTML/SVG diagram to `docs/<project-name>-architecture.html` and link it from the markdown document.
4. **Preview & Review:**
   - Present the links to `docs/<project-name>-architecture.md` and `.html` to the user.

### Output Location

**CRITICAL**: Always output the architecture document as a markdown (`.md`) file in the `docs/` folder inside the project root:
- **Primary Markdown Document**: `docs/[project-name]-architecture.md` (or `docs/architecture.md`)
- **Companion HTML Diagram Asset**: `docs/[project-name]-architecture.html`

Ensure the `docs/` directory inside the project folder exists before writing.

### Preview

After saving, suggest the user review the markdown file in `docs/` or open the HTML file:
```bash
# macOS
open ./docs/my-architecture.html

# Linux
xdg-open ./docs/my-architecture.html
```

## Design System & Visual Language

### Color Palette (Semantic Mapping for Dual-Runtime & Cloud Architecture)

Use specific `rgba` fills and hex strokes to categorize components:

| Component Type | Fill (`rgba`) | Stroke (`Hex`) | Typical Repository Workloads |
| :--- | :--- | :--- | :--- |
| **Frontend / Client (`cloud_run`)** | `rgba(8, 51, 68, 0.4)` | `#22d3ee` (cyan-400) | React/Vite UI, Browser Client, OAuth Sign-In |
| **API Proxy / Gateway (`cloud_run`)** | `rgba(6, 78, 59, 0.4)` | `#34d399` (emerald-400) | FastAPI/Express Streaming Proxy, `/healthz` Liveness Probe |
| **AI Agents & ADK (`agent_runtime`)** | `rgba(120, 53, 15, 0.35)` | `#fbbf24` (amber-400) | Gemini Enterprise Agent Platform, ADK `OrchestratorAgent`, Domain Subagents, `FunctionTool` Registry |
| **Database & Vector Store** | `rgba(76, 29, 149, 0.4)` | `#a78bfa` (violet-400) | Cloud SQL, Spanner, Firestore, Vertex AI Vector Search, Legacy SQL Server |
| **Security & Guardrails** | `rgba(136, 19, 55, 0.4)` | `#fb7185` (rose-400) | Identity-Aware Proxy (IAP), Model Armor (`before_agent_callback`), Secret Manager, CodeMender SAST |
| **Event Bus & CI/CD** | `rgba(251, 146, 60, 0.3)` | `#fb923c` (orange-400) | Pub/Sub, Cloud Build, Artifact Registry, Infrastructure Manager (Terraform) |
| **Legacy / External Tier** | `rgba(30, 41, 59, 0.5)` | `#94a3b8` (slate-400) | Legacy .NET Framework / IIS / WCF Services, Third-Party APIs |

### Typography & Background

-   **Font:** JetBrains Mono (Monospace), loaded from Google Fonts
-   **Sizes:** 12px (Names), 9px (Sublabels), 8px (Annotations), 7px (Tiny
    labels)
-   **Background:** Slate-950 (`#020617`) with a subtle 40px grid pattern

```svg
<!-- Background Grid Pattern -->
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
  <path d="M 40 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>
</pattern>
```

## Technical Implementation Details

### Component Rendering

Components are rounded rectangles (`rx="6"`) with 1.5px strokes. To prevent
arrows from showing through semi-transparent fills, use a **double-rect masking
technique**: 1. Draw an opaque background rect (`#0f172a`) 2. Draw the
semi-transparent styled rect on top

### Dual-Runtime & Brownfield Boundary Rules

-   **Z-Order:** Draw arrows *early* in the SVG (after the grid) so they render
    behind component boxes
-   **Arrowheads:** Defined via SVG markers
-   **Security & Guardrail Flows:** Use dashed lines in rose color (`#fb7185`) for IAP auth verification and Model Armor `before_agent_callback` interception
-   **Mandatory Runtime Boundary Containers:**
    -   **Google Cloud Run Boundary (`cloud_run`):** Dashed (`6,4`) cyan/emerald border enclosing Frontend UI, Streaming API Proxy, and `/healthz` probe.
    -   **Gemini Enterprise Agent Platform Boundary (`agent_runtime`):** Dashed (`8,4`) amber border (`#fbbf24`, `rx="12"`) enclosing the ADK `OrchestratorAgent`, Domain Subagents, `before_agent_callback` Model Armor hook, `FunctionTool` registry, and `agentengine://` session store.
    -   **Brownfield "As-Is vs. Target" Split Mode:** When documenting a brownfield modernization (e.g., Legacy 3-Tier `.NET Framework` / WCF / SQL Stored Procedures $\rightarrow$ Dual-Runtime), render a top or left **"As-Is Legacy Tier"** boundary box (`#94a3b8` slate dashed border) alongside the **"Target Dual-Runtime Architecture"**, connected by Strangler Fig / API Facade or Data Migration arrows.

### Spacing & Layout Logic

-   **Standard Height:** 60px (Services); 80-120px (Large components)
-   **Vertical Gap:** Minimum 40px between components
-   **Message Buses:** Must be placed *in the gap* between services, not
    overlapping them
-   **Legend Placement:** **CRITICAL.** Must be placed outside all boundary
    boxes. Calculate the lowest Y-coordinate of all boundaries and place the
    legend at least 20px below it.

## Document Structure

The generated HTML file follows a four-part layout: 1. **Header:** Title with a
pulsing dot indicator and subtitle 2. **Main SVG:** The diagram contained within
a rounded border card 3. **Summary Cards:** A grid of three cards below the
diagram for high-level details 4. **Footer:** Minimal metadata

### Info Card Pattern

```html
<div class="card">
  <div class="card-header">
    <div class="card-dot cyan"></div>
    <h3>Title</h3>
  </div>
  <ul>
    <li>• Item one</li>
    <li>• Item two</li>
  </ul>
</div>
```

## Template Reference

Copy and customize the template at `resources/template.html`. Key customization
points:

*   Update the `<title>` and header text
*   Modify SVG `viewBox` dimensions if needed (default: 1000 x 820)
*   Add/remove/reposition component boxes
*   Draw connection arrows between components
*   Update the three summary cards
*   Update footer metadata

## Output Requirements

-   **Markdown Document in `docs/`:** Always output the primary architecture document as a `.md` file inside the `docs/` folder of the project directory.
-   **Standalone HTML in `docs/`:** One self-contained `.html` diagram file saved in `docs/` alongside the markdown report.
-   **No External Dependencies:** All CSS and SVG must be inline (except Google Fonts).
-   **No JavaScript:** Use pure CSS for any animations (like pulsing dots).
-   **Compatibility:** Must render correctly in any modern web browser and markdown previewer.
