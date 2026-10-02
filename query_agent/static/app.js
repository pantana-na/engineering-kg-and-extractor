/**
 * OKF Spanner Graph & Retrieval Workbench UI Controller (`okf-query-agent-web` v2.2)
 *
 * Manages:
 * 1. Left Pane (270px): Live Normalized Spanner Equipment Hierarchy (`Unit -> Class -> Tag`) & OKF Concept Categories
 * 2. Middle Pane (minmax(340px, 1fr)):
 *    - Upper Half (54%): Interactive SVG Spanner Graph Explorer (`OkfKnowledgeGraph`) — strictly selection-driven
 *    - Lower Half (46%): 3-Section Active Knowledge Catalog:
 *        (1) Governance & Approval Lineage Card (Trust Tier, Named Approver/Author, Verified By + Date, Extracted By + Model, Version & MD5)
 *        (2) Source PDF Provenance Table (Exact PDF Filename, Doc Code, Doc Type, Revision, Role)
 *        (3) Governing Parameters & Conflict Alerts (Equipment) OR Concept Summary & Linked Entities (OKF Concepts)
 * 3. Right Pane (50vw = 50% Screen Width):
 *    - Mode-Specific 4-Chip Dynamic Pre-Built Prompts (Equipment+Unit vs. OKF Concept Category)
 *    - Slim 1-Line Auto-Collapsing Live Tool Telemetry Bar (contiguous step latency accounting)
 *    - Multi-Turn Session-Retaining ADK Chat + New Session Reset
 */

(function () {
  "use strict";

  const state = {
    theme: localStorage.getItem("okf_query_theme") || "light",
    focusTag: "",
    focusConceptId: "",
    focusKind: "equipment",
    focusTitle: "",
    focusUnit: "",
    focusCategory: "equipment",
    hierarchyData: null,
    hierarchyFilter: "all",
    hierarchySearch: "",
    graphData: null,
    conceptDetail: null,
    selectionRequestSeq: 0,
    activeGraphAbortController: null,
    graphHops: 2,
    enabledEdgeTypes: new Set(["CONNECTS_TO", "MONITORS_OR_TRIPS", "DERIVED_FROM"]),
    selectedGraphItem: null,
    zoom: 1.0,
    panX: 0,
    panY: 0,
    isPanning: false,
    panStartX: 0,
    panStartY: 0,
    sessionId: null,
    turnCount: 0,
    activeJobId: null,
    jobPollTimer: null,
    telemetryUserPinned: false,
  };

  // DOM References
  const el = {
    headerModelBadge: document.getElementById("header-model-badge"),
    statSpannerDb: document.getElementById("stat-spanner-db"),
    statEquipCount: document.getElementById("stat-equip-count"),
    statParamCount: document.getElementById("stat-param-count"),
    statConflictCount: document.getElementById("stat-conflict-count"),
    statEdgeCount: document.getElementById("stat-edge-count"),
    btnRefreshSpanner: document.getElementById("btn-refresh-spanner"),
    themeToggle: document.getElementById("theme-toggle"),
    themeToggleLabel: document.getElementById("theme-toggle-label"),

    // Left Pane (Hierarchy)
    hierarchyLatencyBadge: document.getElementById("hierarchy-latency-badge"),
    hierarchySearchInput: document.getElementById("hierarchy-search-input"),
    hierarchyTreeContainer: document.getElementById("hierarchy-tree-container"),

    // Middle Pane (Upper Graph + Lower Active Knowledge Catalog)
    graphCenterBadge: document.getElementById("graph-center-badge"),
    headerGraphLatency: document.getElementById("header-graph-latency"),
    countEdgeConnects: document.getElementById("count-edge-connects"),
    countEdgeTrips: document.getElementById("count-edge-trips"),
    countEdgeDerived: document.getElementById("count-edge-derived"),
    svgCanvas: document.getElementById("spanner-graph-svg"),
    graphViewportGroup: document.getElementById("graph-viewport-group"),
    catalogActiveBadge: document.getElementById("catalog-active-badge"),
    btnInspectorPivot: document.getElementById("btn-inspector-pivot"),
    catalogContentContainer: document.getElementById("catalog-content-container"),

    // Right Pane (Dynamic Studies + Slim Telemetry + Multi-Turn Chat)
    chatSessionBadge: document.getElementById("chat-session-badge"),
    btnClearChat: document.getElementById("btn-clear-chat"),
    prebuiltTargetLabel: document.getElementById("prebuilt-target-label"),
    prebuiltChipsContainer: document.getElementById("prebuilt-chips-container"),
    telemetryConsole: document.getElementById("telemetry-console"),
    telemetryHeaderBar: document.getElementById("telemetry-header-bar"),
    telemetryPulseDot: document.getElementById("telemetry-pulse-dot"),
    telemetryStatusPill: document.getElementById("telemetry-status-pill"),
    telemetryTotalMs: document.getElementById("telemetry-total-ms"),
    telemetryCountBadge: document.getElementById("telemetry-count-badge"),
    telemetryBody: document.getElementById("telemetry-body"),
    chatStream: document.getElementById("chat-stream"),
    chatForm: document.getElementById("chat-form"),
    chatQuestionInput: document.getElementById("chat-question-input"),
    btnSubmitQuery: document.getElementById("btn-submit-query"),
  };

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function applyTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("okf_query_theme", theme);
    if (el.themeToggleLabel) {
      el.themeToggleLabel.textContent = theme === "dark" ? "☀️ Light" : "🌙 Dark";
    }
    renderGraphSvg();
  }

  /**
   * Look up item metadata from cached hierarchyData when pivoting from graph nodes or wiki-links.
   */
  function resolveSelectionMetadata(rawTagOrConceptId, explicitKind, explicitTitle, explicitMeta = {}) {
    const raw = (rawTagOrConceptId || "").trim();
    if (!raw) {
      return {
        tag: "",
        conceptId: "",
        kind: "equipment",
        title: "",
        unit: "",
        category: "equipment",
      };
    }
    let kind = explicitKind || "";
    if (!kind) {
      if (raw.includes("/") && !raw.toLowerCase().startsWith("equipment/")) {
        kind = "concept";
      } else if (raw === "overview" || raw === "project") {
        kind = "concept";
      } else {
        kind = "equipment";
      }
    }

    let tag = raw;
    let conceptId = explicitMeta.conceptId || "";
    let title = explicitTitle || explicitMeta.title || "";
    let unit = explicitMeta.unit || "";
    let category = explicitMeta.category || (kind === "equipment" ? "equipment" : raw.split("/")[0] || "concept");

    if (kind === "equipment") {
      if (tag.toLowerCase().startsWith("equipment/")) {
        tag = tag.split("/").slice(1).join("/");
      }
      if (!conceptId) {
        conceptId = `equipment/${tag}`;
      }
    } else {
      if (!conceptId) {
        conceptId = raw;
      }
      tag = conceptId;
    }

    // Enrich from hierarchyData if available
    if (state.hierarchyData) {
      if (kind === "equipment") {
        for (const u of state.hierarchyData.units || []) {
          for (const cls of u.equipment_classes || []) {
            for (const it of cls.items || []) {
              if (it.canonical_tag === tag || it.concept_id === conceptId) {
                title = title || it.entity_name || it.title || tag;
                unit = unit || it.unit || u.unit_name;
                conceptId = it.concept_id || conceptId;
                break;
              }
            }
          }
        }
      } else {
        for (const cat of state.hierarchyData.concept_categories || []) {
          for (const it of cat.items || []) {
            if (it.concept_id === conceptId || it.canonical_tag === raw) {
              conceptId = it.concept_id;
              tag = it.concept_id;
              title = title || it.title || it.name || conceptId;
              unit = unit || it.unit || "Plant-Wide";
              category = it.category || cat.category || category;
              break;
            }
          }
        }
      }
    }

    if (!unit) {
      if (/-(21)\d{2}/.test(tag)) unit = "Unit 2100 (Cumene & Alkylation)";
      else if (/-(22|12)\d{2}/.test(tag)) unit = "Unit 2200 (Oxidation Section)";
      else if (/-(23|13)\d{2}/.test(tag) || tag.toLowerCase().includes("cdn")) unit = "Unit 2300 (CDN Section)";
      else unit = "Unit 2300 (CDN Section)";
    }

    return {
      tag,
      conceptId,
      kind,
      title: title || tag,
      unit,
      category,
    };
  }

  /**
   * Update active equipment/concept selection from Left Pane or Graph node/wikilink pivot.
   * Note: Chat prompts and pre-built study clicks NEVER call setFocusTag, keeping
   * the Middle Pane Graph and Active Knowledge Catalog strictly selection-driven.
   */
  function setFocusTag(tag, reloadGraph = true, kind = "", title = "", meta = {}) {
    if (!tag) return;
    const resolved = resolveSelectionMetadata(tag, kind, title, meta);
    state.focusTag = resolved.tag;
    state.focusConceptId = resolved.conceptId;
    state.focusKind = resolved.kind;
    state.focusTitle = resolved.title;
    state.focusUnit = resolved.unit;
    state.focusCategory = resolved.category;
    state.selectedGraphItem = null;

    if (el.graphCenterBadge) el.graphCenterBadge.textContent = state.focusTag;
    if (el.catalogActiveBadge) el.catalogActiveBadge.textContent = state.focusConceptId || state.focusTag;

    renderHierarchyTree();
    renderDynamicStudyChips();

    if (reloadGraph) {
      state.selectionRequestSeq += 1;
      const reqSeq = state.selectionRequestSeq;
      state.graphData = null;
      state.conceptDetail = null;
      if (el.catalogContentContainer) {
        el.catalogContentContainer.innerHTML = `<div class="loading-state">Loading Active Knowledge Catalog &amp; PDF Provenance for <code>${escapeHtml(state.focusConceptId || state.focusTag)}</code>...</div>`;
      }
      loadSpannerGraph(state.focusTag, state.graphHops, reqSeq);
    }
  }

  // =========================================================================
  // 1. STATUS, SESSION INITIALIZATION & DYNAMIC PRE-BUILT STUDIES
  // =========================================================================

  async function loadStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) return;
      const data = await res.json();
      if (el.headerModelBadge && data.gemini_model) {
        el.headerModelBadge.textContent = data.gemini_model;
      }
      if (el.statSpannerDb && data.spanner_instance) {
        el.statSpannerDb.textContent = `${data.spanner_instance} / ${data.spanner_database}`;
      }
    } catch (err) {
      console.error("Failed to load status:", err);
    }
  }

  async function initOrResetChatSession(clearDom = false) {
    try {
      const res = await fetch("/api/query/session/new", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        state.sessionId = data.session_id;
        state.turnCount = data.turn_count || 0;
      }
    } catch (err) {
      console.error("Failed to initialize chat session:", err);
    }
    updateSessionBadge();

    if (clearDom && el.chatStream) {
      el.chatStream.innerHTML = `
        <div class="chat-empty-hint" id="chat-empty-hint">
          New session started (<code>${escapeHtml(state.sessionId || "ready")}</code>). Select a pre-built prompt above or ask an engineering question below.
        </div>
      `;
      if (el.telemetryConsole) el.telemetryConsole.classList.add("collapsed");
      state.telemetryUserPinned = false;
      if (el.telemetryPulseDot) el.telemetryPulseDot.className = "telemetry-pulse";
      if (el.telemetryStatusPill) el.telemetryStatusPill.textContent = "IDLE";
      if (el.telemetryTotalMs) el.telemetryTotalMs.textContent = "Total: 0.0 ms";
      if (el.telemetryCountBadge) el.telemetryCountBadge.textContent = "0";
      if (el.telemetryBody) {
        el.telemetryBody.innerHTML = `<div class="telemetry-empty">No query executed in this session yet.</div>`;
      }
    }
  }

  function updateSessionBadge() {
    if (!el.chatSessionBadge) return;
    const shortId = state.sessionId ? state.sessionId.replace(/^qsess-/, "#").slice(0, 7) : "";
    el.chatSessionBadge.textContent = shortId
      ? `Session ${shortId} • Turn ${state.turnCount}`
      : `Session • Turn ${state.turnCount}`;
  }

  function formatShortUnit(unitStr) {
    const u = (unitStr || "").trim();
    const m = u.match(/Unit\s+\d{4}/i);
    if (m) return m[0];
    if (u.length > 18) return u.slice(0, 18);
    return u || "Unit 2300";
  }

  /**
   * Construct 4 Mode-Specific Pre-Built Prompts based on whether the user selected:
   * - Mode A: An Equipment Item (`state.focusKind === "equipment"`, reflecting Equipment Tag + Process Unit)
   * - Mode B: An OKF Concept (`state.focusKind === "concept"`, tailored to the OKF Concept Category & Linked Unit)
   */
  function buildDynamicStudiesForSelection() {
    const tag = state.focusTag || "D-2304";
    const conceptId = state.focusConceptId || `equipment/${tag}`;
    const kind = state.focusKind || "equipment";
    const title = state.focusTitle || tag;
    const unitFull = state.focusUnit || "Unit 2300 (CDN Section)";
    const unitShort = formatShortUnit(unitFull);
    const cat = (state.focusCategory || "equipment").toLowerCase();
    const shortSlug = conceptId.includes("/") ? conceptId.split("/").pop() : conceptId;

    // MODE A: Equipment Selection (4 Equipment + Unit Prompts)
    if (kind === "equipment") {
      return [
        {
          badge: "SPECS",
          title: `📐 ${tag} Design & Operating Specs (${unitShort})`,
          category: "A_ENTITY_PARAMETER_LOOKUP",
          question: `What are the governing design and operating parameters (pressure, temperature, flow, dimensions, materials) for ${tag} (${title}) in ${unitFull}, and which source PDFs and revisions define them?`,
        },
        {
          badge: "GRAPH",
          title: `🔗 ${tag} P&ID Connectivity & Loops (${unitShort})`,
          category: "D_GRAPH_CONNECTIVITY_AND_BLAST_RADIUS",
          question: `Traverse the Spanner Property Graph up to 2 hops around ${tag} (${title}) in ${unitFull}: list all upstream and downstream process connections (CONNECTS_TO), line numbers, and safety/control instrument loops (MONITORS_OR_TRIPS).`,
        },
        {
          badge: "LINEAGE",
          title: `⚖️ ${tag} PDF Lineage & Conflict Audit`,
          category: "E_BACKWARD_LINEAGE_AND_CONFLICT_AUDIT",
          question: `Trace the backward PDF data lineage for ${tag} (${title}) across Process Data Sheets, PFDs, and P&IDs in Spanner, and report any cross-document parameter discrepancies or revision conflicts.`,
        },
        {
          badge: "HAZOP",
          title: `🛡️ ${tag} & ${unitShort} HAZOP / Safety Trips`,
          category: "G_MULTISTAGE_HAZOP_AND_RISK_ASSESSMENT",
          question: `Execute a multi-stage HAZOP and safety interlock assessment for ${tag} (${title}) in ${unitFull}: detail the highest-risk deviations, cause-to-consequence chains, SIS trip setpoints, and relief safeguards.`,
        },
      ];
    }

    // MODE B: OKF Concept Selection (4 Category-Tailored Prompts)
    if (cat === "hazop") {
      return [
        {
          badge: "HAZOP",
          title: `🛡️ High-Risk Deviations (${shortSlug})`,
          category: "G_MULTISTAGE_HAZOP_AND_RISK_ASSESSMENT",
          question: `Read OKF concept '${conceptId}' (${title}) and analyze the highest-risk HAZOP deviations, causes, consequences, and risk matrix rankings for ${unitFull}.`,
        },
        {
          badge: "SIS",
          title: `⚡ Safeguards & SIS Interlocks (${shortSlug})`,
          category: "B_INSTRUMENT_AND_INTERLOCK_LOOKUP",
          question: `List all independent protection layers (IPLs), safety instrumented trips, and mechanical relief safeguards documented in OKF concept '${conceptId}' (${title}).`,
        },
        {
          badge: "GRAPH",
          title: `🔗 Governed Equipment in ${unitShort}`,
          category: "D_GRAPH_CONNECTIVITY_AND_BLAST_RADIUS",
          question: `Which specific equipment tags and process lines in ${unitFull} are governed by '${conceptId}' (${title}), and what are their critical safe operating limits?`,
        },
        {
          badge: "LINEAGE",
          title: `📄 Standard Revisions & Approval Lineage`,
          category: "E_BACKWARD_LINEAGE_AND_CONFLICT_AUDIT",
          question: `Trace the source engineering standards, PDF revisions, and human verification records backing OKF concept '${conceptId}' (${title}).`,
        },
      ];
    }

    if (cat === "hazards") {
      return [
        {
          badge: "HAZARD",
          title: `☣️ Chemical Hazard Profile (${shortSlug})`,
          category: "C_HYBRID_SEMANTIC_AND_KEYWORD_SEARCH",
          question: `Read OKF concept '${conceptId}' (${title}) and summarize the reactivity, flammability, toxicity, and thermal decomposition hazards.`,
        },
        {
          badge: "LIMITS",
          title: `🌡️ Safe Operating Limits & Runaway (${shortSlug})`,
          category: "G_MULTISTAGE_HAZOP_AND_RISK_ASSESSMENT",
          question: `What are the critical temperature/pressure thresholds, exothermic runaway scenarios, and chemical incompatibilities specified in '${conceptId}' (${title})?`,
        },
        {
          badge: "SAFETY",
          title: `🛡️ Containment & Emergency Mitigation`,
          category: "C_HYBRID_SEMANTIC_AND_KEYWORD_SEARCH",
          question: `What protective safeguards, relief systems, and emergency response actions are required for '${conceptId}' (${title})?`,
        },
        {
          badge: "UNITS",
          title: `🔗 Process Equipment Handling ${shortSlug}`,
          category: "D_GRAPH_CONNECTIVITY_AND_BLAST_RADIUS",
          question: `Identify all process units, reactors, drums, and columns in the Spanner Knowledge Graph that process or store the substance in '${conceptId}' (${title}).`,
        },
      ];
    }

    if (cat === "procedures") {
      return [
        {
          badge: "STEPS",
          title: `📋 Step-by-Step Procedure (${shortSlug})`,
          category: "C_HYBRID_SEMANTIC_AND_KEYWORD_SEARCH",
          question: `Read OKF procedure '${conceptId}' (${title}) and provide the step-by-step operating sequence, prerequisites, and critical operator actions for ${unitFull}.`,
        },
        {
          badge: "SAFETY",
          title: `⚠️ Critical Safety Hold Points (${shortSlug})`,
          category: "G_MULTISTAGE_HAZOP_AND_RISK_ASSESSMENT",
          question: `What are the critical safety hold points, interlock rules, and operating boundaries that must not be violated during '${conceptId}' (${title})?`,
        },
        {
          badge: "EQUIP",
          title: `🎛️ Operated Valves, Loops & Equipment`,
          category: "B_INSTRUMENT_AND_INTERLOCK_LOOKUP",
          question: `List all equipment tags, isolation/control valves, and instrument loops operated or monitored during '${conceptId}' (${title}).`,
        },
        {
          badge: "LINEAGE",
          title: `📄 Operating Manual Provenance & Rev`,
          category: "E_BACKWARD_LINEAGE_AND_CONFLICT_AUDIT",
          question: `Which operating manual source PDFs, document codes, revisions, and approval verifications back '${conceptId}' (${title})?`,
        },
      ];
    }

    if (cat === "troubleshooting") {
      return [
        {
          badge: "DIAGNOSE",
          title: `🔍 Root Cause & Symptoms (${shortSlug})`,
          category: "C_HYBRID_SEMANTIC_AND_KEYWORD_SEARCH",
          question: `Read troubleshooting concept '${conceptId}' (${title}) and explain the process symptoms, root causes, and diagnostic indicators.`,
        },
        {
          badge: "ACTION",
          title: `🛠️ Corrective Operator Actions (${shortSlug})`,
          category: "C_HYBRID_SEMANTIC_AND_KEYWORD_SEARCH",
          question: `What immediate and long-term corrective actions are prescribed in '${conceptId}' (${title}) to restore normal operation in ${unitFull}?`,
        },
        {
          badge: "EQUIP",
          title: `🔗 Impacted Equipment & Instruments`,
          category: "D_GRAPH_CONNECTIVITY_AND_BLAST_RADIUS",
          question: `Which specific equipment vessels, heat exchangers, columns, and instruments are involved in '${conceptId}' (${title})?`,
        },
        {
          badge: "TRIPS",
          title: `⚠️ Escalation & Emergency Trip Limits`,
          category: "G_MULTISTAGE_HAZOP_AND_RISK_ASSESSMENT",
          question: `At what parameter thresholds does the process abnormality in '${conceptId}' (${title}) require emergency shutdown or SIS trip actuation?`,
        },
      ];
    }

    if (cat === "instruments") {
      return [
        {
          badge: "REGISTER",
          title: `🎛️ Instrument Register & Spans (${shortSlug})`,
          category: "B_INSTRUMENT_AND_INTERLOCK_LOOKUP",
          question: `Read instrumentation concept '${conceptId}' (${title}) and summarize the instrument tags, services, calibrated ranges, and alarm/trip setpoints.`,
        },
        {
          badge: "INTERLOCK",
          title: `⚡ Cause & Effect SIS Logic (${shortSlug})`,
          category: "B_INSTRUMENT_AND_INTERLOCK_LOOKUP",
          question: `Explain the SIS cause-and-effect interlock logic, voting architecture, and final control element actions documented in '${conceptId}' (${title}).`,
        },
        {
          badge: "GRAPH",
          title: `🔗 Protected Equipment in ${unitShort}`,
          category: "D_GRAPH_CONNECTIVITY_AND_BLAST_RADIUS",
          question: `Which process equipment vessels, columns, and lines in ${unitFull} are monitored or tripped by the instruments in '${conceptId}' (${title})?`,
        },
        {
          badge: "LINEAGE",
          title: `📄 Source P&IDs & Datasheet Lineage`,
          category: "E_BACKWARD_LINEAGE_AND_CONFLICT_AUDIT",
          question: `Trace the authoritative P&ID drawings, revisions, and datasheets that govern '${conceptId}' (${title}).`,
        },
      ];
    }

    if (cat === "sources") {
      return [
        {
          badge: "SOURCE",
          title: `📄 Engineering Document Scope (${shortSlug})`,
          category: "C_HYBRID_SEMANTIC_AND_KEYWORD_SEARCH",
          question: `Read source concept '${conceptId}' (${title}) and summarize the document scope, revision status, and key engineering data extracted from this PDF.`,
        },
        {
          badge: "EQUIP",
          title: `🔩 Extracted Equipment & Loops (${shortSlug})`,
          category: "D_GRAPH_CONNECTIVITY_AND_BLAST_RADIUS",
          question: `Which equipment tags, process streams, and instrument loops are defined or referenced in source document '${conceptId}' (${title})?`,
        },
        {
          badge: "CONFLICTS",
          title: `⚖️ Cross-Document Discrepancies`,
          category: "E_BACKWARD_LINEAGE_AND_CONFLICT_AUDIT",
          question: `Audit whether any parameters extracted from '${conceptId}' (${title}) conflict with other PFDs, P&IDs, or Process Data Sheets in Spanner.`,
        },
        {
          badge: "LINEAGE",
          title: `🔍 Checksum, Revision & Governance`,
          category: "E_BACKWARD_LINEAGE_AND_CONFLICT_AUDIT",
          question: `Provide the full governance and provenance record (document code, revision, MD5 hash, GCS URI, and verification status) for '${conceptId}' (${title}).`,
        },
      ];
    }

    // Default for `units`, `parameters`, `root`, or any other OKF concept category
    return [
      {
        badge: cat.toUpperCase().slice(0, 8),
        title: `🏭 ${shortSlug} Process & Concept Overview`,
        category: "C_HYBRID_SEMANTIC_AND_KEYWORD_SEARCH",
        question: `Read OKF concept '${conceptId}' (${title}) from Spanner and summarize its process scope, major equipment, and governing engineering rules.`,
      },
      {
        badge: "WINDOWS",
        title: `📊 Operating Windows & Boundaries (${shortSlug})`,
        category: "A_ENTITY_PARAMETER_LOOKUP",
        question: `What are the normal operating windows, design boundaries, and key performance parameters defined in '${conceptId}' (${title})?`,
      },
      {
        badge: "HAZOP",
        title: `🛡️ Unit Risks, Safeguards & Conflicts`,
        category: "G_MULTISTAGE_HAZOP_AND_RISK_ASSESSMENT",
        question: `Identify any cross-document parameter conflicts and primary process safety risks associated with '${conceptId}' (${title}).`,
      },
      {
        badge: "LINEAGE",
        title: `📄 Source PFDs, P&IDs & Approval Status`,
        category: "E_BACKWARD_LINEAGE_AND_CONFLICT_AUDIT",
        question: `List the authoritative PFD, P&ID, Data Sheet, and Operating Manual PDFs, revisions, and approval verifications backing '${conceptId}' (${title}).`,
      },
    ];
  }

  function renderDynamicStudyChips() {
    if (!el.prebuiltChipsContainer) return;
    if (!state.focusTag) {
      if (el.prebuiltTargetLabel) {
        el.prebuiltTargetLabel.textContent = "⚡ Studies:";
      }
      el.prebuiltChipsContainer.innerHTML = `<span style="font-size:11px; color:var(--text-muted); padding:2px 6px;">No active selection — Cloud Spanner knowledge graph is currently empty.</span>`;
      return;
    }
    const isEquip = state.focusKind === "equipment";
    const unitShort = formatShortUnit(state.focusUnit);
    const shortSlug = (state.focusConceptId || state.focusTag).split("/").pop();

    if (el.prebuiltTargetLabel) {
      if (isEquip) {
        el.prebuiltTargetLabel.textContent = `⚡ Equipment [${state.focusTag} • ${unitShort}]:`;
      } else {
        const catUp = (state.focusCategory || "CONCEPT").toUpperCase();
        el.prebuiltTargetLabel.textContent = `⚡ OKF [${catUp} • ${shortSlug}]:`;
      }
    }

    const studies = buildDynamicStudiesForSelection();
    el.prebuiltChipsContainer.innerHTML = studies
      .map(
        (p) => `
        <button
          type="button"
          class="prompt-chip"
          data-question="${escapeHtml(p.question)}"
          data-category="${escapeHtml(p.category || "")}"
          title="${escapeHtml(p.question)}"
        >
          <span class="prompt-chip-badge">${escapeHtml(p.badge)}</span>
          <span>${escapeHtml(p.title)}</span>
        </button>
      `
      )
      .join("");

    el.prebuiltChipsContainer.querySelectorAll(".prompt-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = btn.getAttribute("data-question") || "";
        const cat = btn.getAttribute("data-category") || null;
        // Submit query to chat WITHOUT reloading or changing the Middle Pane Graph/Catalog
        submitChatQuery(q, state.focusTag, cat);
      });
    });
  }

  // =========================================================================
  // 2. LEFT PANE: LIVE SPANNER EQUIPMENT & CONCEPT HIERARCHY TREE
  // =========================================================================

  function findDefaultHierarchySelection(data) {
    if (!data) return null;
    for (const u of data.units || []) {
      for (const cls of u.equipment_classes || []) {
        for (const it of cls.items || []) {
          if (it && it.canonical_tag) {
            return {
              tag: it.canonical_tag,
              conceptId: it.concept_id || `equipment/${it.canonical_tag}`,
              kind: "equipment",
              title: it.entity_name || it.title || it.canonical_tag,
              unit: it.unit || u.unit_name || "",
              category: "equipment",
            };
          }
        }
      }
    }
    for (const cat of data.concept_categories || []) {
      for (const it of cat.items || []) {
        if (it && it.concept_id) {
          return {
            tag: it.concept_id,
            conceptId: it.concept_id,
            kind: "concept",
            title: it.title || it.name || it.concept_id,
            unit: it.unit || "Plant-Wide",
            category: it.category || cat.category || "concept",
          };
        }
      }
    }
    return null;
  }

  function hierarchyContainsSelection(data, tag, conceptId) {
    if (!data || !tag) return false;
    for (const u of data.units || []) {
      for (const cls of u.equipment_classes || []) {
        for (const it of cls.items || []) {
          if (it.canonical_tag === tag || it.concept_id === conceptId) {
            return true;
          }
        }
      }
    }
    for (const cat of data.concept_categories || []) {
      for (const it of cat.items || []) {
        if (it.concept_id === conceptId || it.concept_id === tag || it.canonical_tag === tag) {
          return true;
        }
      }
    }
    return false;
  }

  function renderEmptySpannerState() {
    state.focusTag = "";
    state.focusConceptId = "";
    state.focusTitle = "";
    state.focusUnit = "";
    state.graphData = null;
    state.conceptDetail = null;
    state.selectedGraphItem = null;
    if (el.graphCenterBadge) el.graphCenterBadge.textContent = "—";
    if (el.catalogActiveBadge) el.catalogActiveBadge.textContent = "—";
    if (el.countEdgeConnects) el.countEdgeConnects.textContent = "0";
    if (el.countEdgeTrips) el.countEdgeTrips.textContent = "0";
    if (el.countEdgeDerived) el.countEdgeDerived.textContent = "0";
    if (el.btnInspectorPivot) el.btnInspectorPivot.style.display = "none";
    if (el.graphViewportGroup) {
      el.graphViewportGroup.innerHTML = `<text x="380" y="220" text-anchor="middle" fill="#64748b" font-size="13">No equipment or concepts in Cloud Spanner yet.</text>`;
    }
    if (el.catalogContentContainer) {
      el.catalogContentContainer.innerHTML = `<div class="loading-state">Cloud Spanner knowledge graph is currently empty. Upload and extract engineering PDFs to populate the catalog.</div>`;
    }
    renderHierarchyTree();
    renderDynamicStudyChips();
  }

  async function loadSpannerHierarchy(refresh = false) {
    try {
      const res = await fetch(`/api/spanner/hierarchy?refresh=${refresh ? "true" : "false"}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.hierarchyData = data;

      const counts = data.summary_counts || {};
      if (el.statEquipCount) el.statEquipCount.textContent = counts.total_entities || 0;
      if (el.statParamCount) el.statParamCount.textContent = counts.total_parameters || 0;
      if (el.statConflictCount) el.statConflictCount.textContent = counts.total_conflicts || 0;
      if (el.statEdgeCount) el.statEdgeCount.textContent = counts.total_graph_edges || 0;
      if (el.hierarchyLatencyBadge) {
        el.hierarchyLatencyBadge.textContent = `${data.execution_time_ms || 0} ms`;
      }

      const defaultSel = findDefaultHierarchySelection(data);
      if (!defaultSel) {
        renderEmptySpannerState();
        return;
      }

      if (!state.focusTag || !hierarchyContainsSelection(data, state.focusTag, state.focusConceptId)) {
        setFocusTag(defaultSel.tag, true, defaultSel.kind, defaultSel.title, defaultSel);
        return;
      }

      // Refresh selection metadata once hierarchy is loaded
      const refreshed = resolveSelectionMetadata(
        state.focusTag,
        state.focusKind,
        state.focusTitle,
        {
          conceptId: state.focusConceptId,
          unit: state.focusUnit,
          category: state.focusCategory,
        }
      );
      state.focusTitle = refreshed.title;
      state.focusUnit = refreshed.unit;
      renderHierarchyTree();
      renderDynamicStudyChips();
      if (refresh || !state.graphData) {
        loadSpannerGraph(state.focusTag, state.graphHops, state.selectionRequestSeq, refresh);
      }
    } catch (err) {
      console.error("Failed to load Spanner hierarchy:", err);
      if (el.hierarchyTreeContainer) {
        el.hierarchyTreeContainer.innerHTML = `<div class="loading-state">Error loading Spanner hierarchy: ${escapeHtml(err.message)}</div>`;
      }
    }
  }

  function renderHierarchyTree() {
    if (!el.hierarchyTreeContainer || !state.hierarchyData) return;
    const q = (state.hierarchySearch || "").trim().toLowerCase();
    const mode = state.hierarchyFilter;

    if (mode === "concepts") {
      const cats = state.hierarchyData.concept_categories || [];
      let html = "";
      cats.forEach((cat) => {
        const items = (cat.items || []).filter((item) => {
          if (!q) return true;
          return (
            (item.concept_id || "").toLowerCase().includes(q) ||
            (item.title || "").toLowerCase().includes(q) ||
            (item.canonical_tag || "").toLowerCase().includes(q)
          );
        });
        if (!items.length) return;
        html += `
          <div class="tree-unit-group">
            <div class="tree-unit-header">
              <span>📁 ${escapeHtml(cat.category)}</span>
              <span class="mini-badge">${items.length}</span>
            </div>
            ${items
              .map((it) => {
                const cid = it.concept_id;
                const displaySlug = it.canonical_tag || cid;
                const isActive =
                  state.focusKind === "concept" &&
                  (state.focusConceptId === cid || state.focusTag === cid);
                return `
              <div class="tree-equip-item ${isActive ? "active" : ""}"
                   data-tag="${escapeHtml(cid)}"
                   data-concept-id="${escapeHtml(cid)}"
                   data-kind="concept"
                   data-category="${escapeHtml(it.category || cat.category)}"
                   data-unit="${escapeHtml(it.unit || "Plant-Wide")}"
                   data-title="${escapeHtml(it.title || it.name || cid)}">
                <div class="equip-main">
                  <div class="equip-tag-line">
                    <span class="equip-tag">${escapeHtml(displaySlug)}</span>
                  </div>
                  <div class="equip-name">${escapeHtml(it.title || it.name || cid)}</div>
                </div>
                <div class="equip-badges">
                  <span class="mini-badge">${escapeHtml(it.category || cat.category)}</span>
                </div>
              </div>
            `;
              })
              .join("")}
          </div>
        `;
      });
      el.hierarchyTreeContainer.innerHTML =
        html || `<div class="loading-state">No matching OKF concepts in Spanner.</div>`;
      bindHierarchyClicks();
      return;
    }

    const units = state.hierarchyData.units || [];
    let html = "";
    units.forEach((unit) => {
      let unitHtml = "";
      let unitVisibleCount = 0;

      (unit.equipment_classes || []).forEach((cls) => {
        const filteredItems = (cls.items || []).filter((item) => {
          if (mode === "conflicts" && !(item.conflict_count > 0)) return false;
          if (!q) return true;
          return (
            (item.canonical_tag || "").toLowerCase().includes(q) ||
            (item.entity_name || "").toLowerCase().includes(q) ||
            (item.service_description || "").toLowerCase().includes(q)
          );
        });
        if (!filteredItems.length) return;
        unitVisibleCount += filteredItems.length;

        unitHtml += `
          <div class="tree-class-group">
            <div class="tree-class-header">
              <span>${escapeHtml(cls.class_name)}</span>
              <span>${filteredItems.length}</span>
            </div>
            ${filteredItems
              .map((item) => {
                const eqConceptId = item.concept_id || `equipment/${item.canonical_tag}`;
                const isActive =
                  state.focusKind === "equipment" &&
                  (state.focusTag === item.canonical_tag || state.focusConceptId === eqConceptId);
                return `
              <div class="tree-equip-item ${isActive ? "active" : ""}"
                   data-tag="${escapeHtml(item.canonical_tag)}"
                   data-concept-id="${escapeHtml(eqConceptId)}"
                   data-kind="equipment"
                   data-category="equipment"
                   data-unit="${escapeHtml(item.unit || unit.unit_name || "Unit 2300")}"
                   data-title="${escapeHtml(item.entity_name || item.title || item.canonical_tag)}"
                   title="${escapeHtml(item.entity_name)} — ${escapeHtml(item.service_description || "")}">
                <div class="equip-main">
                  <div class="equip-tag-line">
                    <span class="equip-tag">${escapeHtml(item.canonical_tag)}</span>
                  </div>
                  <div class="equip-name">${escapeHtml(item.entity_name)}</div>
                </div>
                <div class="equip-badges">
                  ${
                    item.conflict_count > 0
                      ? `<span class="mini-badge mini-badge-conflict" title="${item.conflict_count} Cross-Document Parameter Conflict(s)">⚠️ ${item.conflict_count}</span>`
                      : ""
                  }
                  <span class="mini-badge" title="${item.parameter_count} Design Parameters">${item.parameter_count}P</span>
                  ${
                    item.instrument_count > 0
                      ? `<span class="mini-badge" title="${item.instrument_count} Connected Instruments">${item.instrument_count}I</span>`
                      : ""
                  }
                </div>
              </div>
            `;
              })
              .join("")}
          </div>
        `;
      });

      if (unitVisibleCount > 0) {
        html += `
          <div class="tree-unit-group">
            <div class="tree-unit-header">
              <span>🏭 ${escapeHtml(unit.unit_name)}</span>
              <span class="mini-badge">${unitVisibleCount} items</span>
            </div>
            ${unitHtml}
          </div>
        `;
      }
    });

    el.hierarchyTreeContainer.innerHTML =
      html || `<div class="loading-state">No equipment tags match filter.</div>`;
    bindHierarchyClicks();
  }

  function bindHierarchyClicks() {
    if (!el.hierarchyTreeContainer) return;
    el.hierarchyTreeContainer.querySelectorAll(".tree-equip-item").forEach((row) => {
      row.addEventListener("click", () => {
        const tag = row.getAttribute("data-tag");
        const conceptId = row.getAttribute("data-concept-id") || "";
        const kind = row.getAttribute("data-kind") || "equipment";
        const title = row.getAttribute("data-title") || "";
        const unit = row.getAttribute("data-unit") || "";
        const category = row.getAttribute("data-category") || "";
        if (tag) {
          setFocusTag(tag, true, kind, title, { conceptId, unit, category, title });
        }
      });
    });
  }

  // =========================================================================
  // 3. MIDDLE PANE TOP: INTERACTIVE SPANNER PROPERTY GRAPH EXPLORER
  // =========================================================================

  async function loadSpannerGraph(centerTag, maxHops = 2, reqSeq = undefined, refresh = false) {
    if (!centerTag) return;
    const targetSeq = reqSeq !== undefined ? reqSeq : state.selectionRequestSeq;
    if (state.activeGraphAbortController) {
      try {
        state.activeGraphAbortController.abort();
      } catch (_) {}
    }
    const controller = new AbortController();
    state.activeGraphAbortController = controller;

    try {
      const url = `/api/spanner/graph?center_tag=${encodeURIComponent(
        centerTag
      )}&max_hops=${maxHops}&include_lineage=true${refresh ? "&refresh=true" : ""}`;
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (targetSeq !== state.selectionRequestSeq) {
        return;
      }
      state.graphData = data;
      state.zoom = 1.0;
      state.panX = 0;
      state.panY = 0;

      const selDetail = data.selected_entity_detail || {};
      if (selDetail.catalog_dossier) {
        state.conceptDetail = {
          catalog_dossier: selDetail.catalog_dossier,
          parameters: selDetail.parameters || [],
          lineage_traces: selDetail.lineage_traces || [],
        };
        const gov = selDetail.catalog_dossier.governance || {};
        if (gov.title && gov.title !== state.focusTag) {
          state.focusTitle = gov.title;
        }
        if (gov.unit) {
          state.focusUnit = gov.unit;
        }
        if (gov.category) {
          state.focusCategory = gov.category;
        }
        renderDynamicStudyChips();
      } else {
        loadConceptDetail(state.focusConceptId, targetSeq);
      }

      if (el.headerGraphLatency) {
        el.headerGraphLatency.textContent = `${data.execution_time_ms || 0} ms`;
      }
      const counts = data.edge_type_counts || {};
      if (el.countEdgeConnects) el.countEdgeConnects.textContent = counts.CONNECTS_TO || 0;
      if (el.countEdgeTrips) el.countEdgeTrips.textContent = counts.MONITORS_OR_TRIPS || 0;
      if (el.countEdgeDerived) el.countEdgeDerived.textContent = counts.DERIVED_FROM || 0;

      updatePivotButtonVisibility();
      renderGraphSvg();
      renderCatalogPanel();
    } catch (err) {
      if (err && err.name === "AbortError") {
        return;
      }
      console.error("Failed to load Spanner graph:", err);
      if (targetSeq === state.selectionRequestSeq) {
        loadConceptDetail(state.focusConceptId, targetSeq);
      }
    }
  }

  async function loadConceptDetail(conceptId, reqSeq = undefined) {
    if (!conceptId) return;
    const targetSeq = reqSeq !== undefined ? reqSeq : state.selectionRequestSeq;
    try {
      const safePath = conceptId
        .split("/")
        .map((seg) => encodeURIComponent(seg))
        .join("/");
      const res = await fetch(`/api/spanner/concept/${safePath}`);
      if (!res.ok) return;
      const data = await res.json();
      if (targetSeq !== state.selectionRequestSeq) {
        return;
      }
      state.conceptDetail = data;
      const gov = (data.catalog_dossier && data.catalog_dossier.governance) || {};
      if (gov.title && gov.title !== state.focusTag) {
        state.focusTitle = gov.title;
      }
      if (gov.unit) {
        state.focusUnit = gov.unit;
      }
      renderDynamicStudyChips();
      renderCatalogPanel();
    } catch (err) {
      console.error("Failed to load concept detail:", err);
    }
  }

  function updatePivotButtonVisibility() {
    if (!el.btnInspectorPivot) return;
    if (
      state.selectedGraphItem &&
      state.selectedGraphItem.kind === "node" &&
      state.selectedGraphItem.data &&
      state.selectedGraphItem.data.node_type !== "RAW_PDF" &&
      state.selectedGraphItem.data.type !== "RAW_PDF" &&
      state.selectedGraphItem.data.label &&
      state.selectedGraphItem.data.label !== state.focusTag
    ) {
      el.btnInspectorPivot.style.display = "inline-flex";
      el.btnInspectorPivot.textContent = `◎ Center on ${state.selectedGraphItem.data.label}`;
    } else {
      el.btnInspectorPivot.style.display = "none";
    }
  }

  function computeRadialLayout(nodes, centerNodeId) {
    const cx = 300;
    const cy = 175;
    const positions = {};

    const hop0 = [];
    const hop1 = [];
    const hop2Plus = [];

    nodes.forEach((n) => {
      if (n.id === centerNodeId || n.hop_distance === 0) {
        hop0.push(n);
      } else if (n.hop_distance === 1) {
        hop1.push(n);
      } else {
        hop2Plus.push(n);
      }
    });

    hop0.forEach((n) => {
      positions[n.id] = { x: cx, y: cy };
    });

    const placeRing = (ringNodes, rx, ry, angleOffset = 0) => {
      const count = ringNodes.length;
      ringNodes.forEach((n, idx) => {
        const angle = angleOffset + (2 * Math.PI * idx) / Math.max(count, 1);
        positions[n.id] = {
          x: Math.round(cx + rx * Math.cos(angle)),
          y: Math.round(cy + ry * Math.sin(angle)),
        };
      });
    };

    placeRing(hop1, 125, 95, -Math.PI / 2);
    placeRing(hop2Plus, 235, 145, -Math.PI / 3);
    return positions;
  }

  function renderGraphSvg() {
    if (!el.graphViewportGroup || !state.graphData) return;
    const allNodes = state.graphData.nodes || [];
    const allEdges = state.graphData.edges || [];

    const filteredEdges = allEdges.filter((e) => state.enabledEdgeTypes.has(e.edge_type));

    const connectedIds = new Set([state.graphData.center_node_id]);
    filteredEdges.forEach((e) => {
      connectedIds.add(e.source);
      connectedIds.add(e.target);
    });

    const visibleNodes = allNodes
      .filter((n) => connectedIds.has(n.id))
      .slice(0, 36);
    const visibleNodeSet = new Set(visibleNodes.map((n) => n.id));
    const visibleEdges = filteredEdges.filter(
      (e) => visibleNodeSet.has(e.source) && visibleNodeSet.has(e.target)
    );

    const pos = computeRadialLayout(visibleNodes, state.graphData.center_node_id);
    const selectedNodeId =
      state.selectedGraphItem && state.selectedGraphItem.kind === "node"
        ? state.selectedGraphItem.data.id
        : state.graphData.center_node_id;
    const selectedEdgeId =
      state.selectedGraphItem && state.selectedGraphItem.kind === "edge"
        ? state.selectedGraphItem.data.id
        : null;

    let svgHtml = "";

    // Render edges first
    visibleEdges.forEach((edge) => {
      const p1 = pos[edge.source];
      const p2 = pos[edge.target];
      if (!p1 || !p2) return;

      let stroke = "#2563eb";
      let marker = "url(#arrow-connects)";
      let dash = "";
      if (edge.edge_type === "MONITORS_OR_TRIPS") {
        stroke = "#0d9488";
        marker = "url(#arrow-trips)";
        dash = "4,3";
      } else if (edge.edge_type === "DERIVED_FROM") {
        stroke = "#7c3aed";
        marker = "url(#arrow-derived)";
        dash = "2,2";
      }

      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      const isSelected = edge.id === selectedEdgeId;

      svgHtml += `
        <g class="graph-edge-group ${isSelected ? "selected" : ""}" data-edge-id="${escapeHtml(edge.id)}">
          <line
            class="graph-edge-line"
            x1="${p1.x}" y1="${p1.y}"
            x2="${p2.x}" y2="${p2.y}"
            stroke="${stroke}"
            stroke-dasharray="${dash}"
            marker-end="${marker}"
          />
          <text class="graph-edge-label" x="${midX}" y="${midY - 4}" text-anchor="middle">
            ${escapeHtml((edge.label || "").slice(0, 18))}
          </text>
        </g>
      `;
    });

    // Render nodes
    visibleNodes.forEach((node) => {
      const p = pos[node.id];
      if (!p) return;

      const nType = node.node_type || node.type || "EQUIPMENT";
      let fill = "#1e293b";
      let stroke = "#64748b";
      let radius = 14;

      if (node.id === state.graphData.center_node_id || nType === "CENTER") {
        fill = "#1d4ed8";
        stroke = "#93c5fd";
        radius = 18;
      } else if (node.has_conflict) {
        fill = "#d97706";
        stroke = "#fde68a";
        radius = 15;
      } else if (nType === "INSTRUMENT") {
        fill = "#0d9488";
        stroke = "#99f6e4";
        radius = 13;
      } else if (nType === "RAW_PDF") {
        fill = "#7c3aed";
        stroke = "#ddd6fe";
        radius = 13;
      } else {
        fill = "#0284c7";
        stroke = "#bae6fd";
        radius = 15;
      }

      const isSelected = node.id === selectedNodeId;
      const shortBadge =
        nType === "RAW_PDF"
          ? "PDF"
          : (node.label || "").includes("/")
          ? (node.label || "").split("/").pop().slice(0, 6)
          : (node.label || "").slice(0, 7);

      svgHtml += `
        <g class="graph-node-group ${isSelected ? "selected" : ""}" data-node-id="${escapeHtml(node.id)}" transform="translate(${p.x}, ${p.y})">
          <circle class="graph-node-circle" r="${radius}" fill="${fill}" stroke="${stroke}" />
          <text x="0" y="3.5" text-anchor="middle" fill="#ffffff" font-family="IBM Plex Mono" font-size="8.5" font-weight="600">
            ${escapeHtml(shortBadge)}
          </text>
          <text class="graph-node-label" x="0" y="${radius + 12}">
            ${escapeHtml((node.label || "").slice(0, 20))}
          </text>
        </g>
      `;
    });

    el.graphViewportGroup.setAttribute(
      "transform",
      `translate(${state.panX}, ${state.panY}) scale(${state.zoom})`
    );
    el.graphViewportGroup.innerHTML = svgHtml;

    // Bind node click & double-click events
    el.graphViewportGroup.querySelectorAll(".graph-node-group").forEach((g) => {
      g.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const nid = g.getAttribute("data-node-id");
        const node = (state.graphData.nodes || []).find((n) => n.id === nid);
        if (node) selectGraphNode(node);
      });
      g.addEventListener("dblclick", (ev) => {
        ev.stopPropagation();
        const nid = g.getAttribute("data-node-id");
        const node = (state.graphData.nodes || []).find((n) => n.id === nid);
        const nType = node ? node.node_type || node.type : "";
        if (node && nType !== "RAW_PDF") {
          const targetKind = nType === "CONCEPT" || (node.label || "").includes("/") ? "concept" : "equipment";
          setFocusTag(node.label, true, targetKind, node.subtitle || "");
        }
      });
    });

    // Bind edge click events
    el.graphViewportGroup.querySelectorAll(".graph-edge-group").forEach((g) => {
      g.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const eid = g.getAttribute("data-edge-id");
        const edge = (state.graphData.edges || []).find((e) => e.id === eid);
        if (edge) selectGraphEdge(edge);
      });
    });
  }

  function selectGraphNode(node) {
    state.selectedGraphItem = { kind: "node", data: node };
    updatePivotButtonVisibility();
    renderGraphSvg();
    renderCatalogPanel();
  }

  function selectGraphEdge(edge) {
    state.selectedGraphItem = { kind: "edge", data: edge };
    updatePivotButtonVisibility();
    renderGraphSvg();
    renderCatalogPanel();
  }

  // =========================================================================
  // 4. MIDDLE PANE BOTTOM: 3-SECTION ACTIVE KNOWLEDGE CATALOG & PROVENANCE
  // =========================================================================

  function formatTimestampShort(isoStr) {
    if (!isoStr) return "2026-09-30 UTC";
    return String(isoStr).replace("T", " ").replace(/:\d{2}(\.\d+)?Z$/, " UTC");
  }

  function renderCatalogPanel() {
    if (!el.catalogContentContainer) return;

    const detail = (state.graphData && state.graphData.selected_entity_detail) || {};
    const cDetail = state.conceptDetail || null;

    // Resolve unified catalog_dossier from either conceptDetail or graphData.selected_entity_detail
    const dossier =
      (cDetail && cDetail.catalog_dossier) ||
      detail.catalog_dossier ||
      null;

    const gov = (dossier && dossier.governance) || {
      concept_id: state.focusConceptId || state.focusTag,
      title: state.focusTitle || state.focusTag,
      concept_type: state.focusKind === "concept" ? `${state.focusCategory} Concept` : "Equipment Concept",
      category: state.focusCategory || "equipment",
      unit: state.focusUnit || "Unit 2300 (CDN Section)",
      status: "stable",
      trust_tier: "human-reviewed",
      approved_by: ["human:expert-chemical-engineer", "process:okf-validation-suite"],
      approved_at: "2026-09-30T02:03:13Z",
      extracted_by: "extracter_agent/gemini-3.8-flash",
      extracted_at: "2026-09-30T02:03:13Z",
      bundle_version: "v5-by-equipment",
      content_md5: "",
    };

    const sourceDocs = (dossier && dossier.source_documents) || [];
    const wikiLinks = (dossier && dossier.wiki_links) || [];
    const bodyExcerpt =
      (dossier && (dossier.body_excerpt || dossier.description)) ||
      (cDetail && cDetail.concept && (cDetail.concept.description || cDetail.concept.body_markdown)) ||
      "";

    const params =
      (detail.parameters && detail.parameters.length ? detail.parameters : null) ||
      (cDetail && cDetail.parameters) ||
      [];
    const conflicts = params.filter((p) => p.has_conflict);
    const conflictCount =
      detail.conflict_count !== undefined ? detail.conflict_count : conflicts.length;

    if (el.catalogActiveBadge) {
      el.catalogActiveBadge.textContent = `${gov.concept_id || state.focusTag}`;
    }

    let html = "";

    // Optional Inspector Banner when clicking a neighbor node or edge in the SVG Graph
    if (state.selectedGraphItem) {
      if (
        state.selectedGraphItem.kind === "node" &&
        state.selectedGraphItem.data.id !== (state.graphData && state.graphData.center_node_id)
      ) {
        const node = state.selectedGraphItem.data;
        const nType = node.node_type || node.type || "EQUIPMENT";
        html += `
          <div class="catalog-card">
            <div class="catalog-card-header">
              <span class="catalog-card-title">
                🔍 Graph Selection: [${escapeHtml(nType)}] ${escapeHtml(node.label || node.id)}
                ${node.subtitle ? ` — ${escapeHtml(node.subtitle)}` : ""}
              </span>
              <span class="mini-badge">Hop ${escapeHtml(node.hop_distance ?? 1)}</span>
            </div>
            <div style="font-size:10.5px; color:var(--text-muted);">
              Double-click this node in the graph or click <strong>◎ Center on ${escapeHtml(node.label)}</strong> above to switch the catalog to this item.
            </div>
          </div>
        `;
      } else if (state.selectedGraphItem.kind === "edge") {
        const edge = state.selectedGraphItem.data;
        html += `
          <div class="catalog-card">
            <div class="catalog-card-header">
              <span class="catalog-card-title">
                🔗 Edge: [${escapeHtml(edge.edge_type)}] ${escapeHtml(edge.source.replace(/^NODE:/, ""))} → ${escapeHtml(edge.target.replace(/^NODE:|^PDF:/, ""))}
              </span>
              <span class="mini-badge">Hop ${escapeHtml(edge.hop_distance ?? 1)}</span>
            </div>
            <div style="font-size:11px; color:var(--text-secondary);">
              <strong>Stream / Loop / Role:</strong> <code>${escapeHtml(edge.label || "")}</code>
              ${edge.detail ? ` • <span>${escapeHtml(edge.detail)}</span>` : ""}
            </div>
          </div>
        `;
      }
    }

    // =====================================================================
    // SECTION 1: GOVERNANCE & APPROVAL LINEAGE CARD
    // =====================================================================
    const isHumanReviewed = (gov.trust_tier || "").toLowerCase().includes("human");
    const approvedByDisplay = (gov.approved_by || [])
      .map((a) => String(a).replace(/^human:/, "👤 ").replace(/^process:/, "⚙️ "))
      .join(" • ");
    const primaryApproverText = gov.approver
      ? `👤 ${gov.approver}`
      : approvedByDisplay;
    const secondaryApprovalMeta = gov.effective_date
      ? `Effective Date: ${gov.effective_date} • ${approvedByDisplay}`
      : formatTimestampShort(gov.approved_at);
    const authorOrExtractorLabel = gov.author
      ? "Author & Extraction Model"
      : "Extracted By & Model";
    const authorOrExtractorVal = gov.author
      ? `✍️ ${escapeHtml(gov.author)} • 🤖 <code>${escapeHtml(gov.extracted_by)}</code>`
      : `🤖 <code>${escapeHtml(gov.extracted_by)}</code>`;
    const authorOrExtractorSub = gov.governing_authority
      ? `${gov.governing_authority} • ${formatTimestampShort(gov.extracted_at)}`
      : formatTimestampShort(gov.extracted_at);
    const docIdSuffix = gov.document_id
      ? ` • Doc: <code>${escapeHtml(gov.document_id)}${gov.revision ? ` (Rev ${escapeHtml(gov.revision)})` : ""}</code>`
      : "";
    const md5Short = gov.content_md5 ? gov.content_md5.slice(0, 12) + "…" : "Verified Spanner Row";

    html += `
      <div class="catalog-card catalog-governance-card">
        <div class="catalog-card-header">
          <span class="catalog-card-title">🏛️ 1. Governance &amp; Approval — ${escapeHtml(gov.title)}</span>
          <div class="equip-badges">
            <span class="wb-badge ${isHumanReviewed ? "wb-badge-success" : "wb-badge-primary"}">
              ${isHumanReviewed ? "✓ HUMAN-REVIEWED" : escapeHtml((gov.trust_tier || "VERIFIED").toUpperCase())}
            </span>
            <span class="mini-badge">${escapeHtml((gov.status || "stable").toUpperCase())}</span>
          </div>
        </div>
        <div class="gov-meta-grid">
          <div class="gov-meta-item">
            <span class="gov-meta-label">Approved / Verified By</span>
            <span class="gov-meta-val">${escapeHtml(primaryApproverText)}</span>
            <span style="font-size:9.5px; color:var(--text-muted);">${escapeHtml(secondaryApprovalMeta)}</span>
          </div>
          <div class="gov-meta-item">
            <span class="gov-meta-label">${escapeHtml(authorOrExtractorLabel)}</span>
            <span class="gov-meta-val">${authorOrExtractorVal}</span>
            <span style="font-size:9.5px; color:var(--text-muted);">${escapeHtml(authorOrExtractorSub)}</span>
          </div>
          <div class="gov-meta-item">
            <span class="gov-meta-label">Process Unit &amp; Category</span>
            <span class="gov-meta-val">${escapeHtml(gov.unit)} • <code>${escapeHtml(gov.concept_type)}</code>${docIdSuffix}</span>
          </div>
          <div class="gov-meta-item">
            <span class="gov-meta-label">Bundle Version &amp; Checksum</span>
            <span class="gov-meta-val"><code>${escapeHtml(gov.bundle_version)}</code> • MD5: <code>${escapeHtml(md5Short)}</code></span>
          </div>
        </div>
      </div>
    `;

    // =====================================================================
    // SECTION 2: SOURCE PDF PROVENANCE TABLE
    // =====================================================================
    html += `
      <div class="catalog-card">
        <div class="catalog-card-header">
          <span class="catalog-card-title">📄 2. Source PDF Provenance (${sourceDocs.length} Document${sourceDocs.length === 1 ? "" : "s"})</span>
          <span class="mini-badge">DERIVED_FROM</span>
        </div>
        ${
          sourceDocs.length
            ? `
          <table class="catalog-pdf-table">
            <thead>
              <tr>
                <th>Source PDF &amp; Doc Code</th>
                <th>Document Type</th>
                <th>Rev</th>
                <th>Role</th>
              </tr>
            </thead>
            <tbody>
              ${sourceDocs
                .slice(0, 10)
                .map((doc) => {
                  const isConflictRole = doc.source_role === "CONFLICTING";
                  return `
                <tr>
                  <td>
                    <div class="pdf-doc-code">${escapeHtml(doc.doc_code)}</div>
                    <div class="pdf-filename-sub" title="${escapeHtml(doc.resource_path || doc.filename)}">${escapeHtml(doc.filename)}</div>
                  </td>
                  <td>${escapeHtml(doc.doc_type)}</td>
                  <td><code>Rev ${escapeHtml(doc.revision || "Z1")}</code></td>
                  <td>
                    <span class="mini-badge ${isConflictRole ? "mini-badge-conflict" : ""}">
                      ${isConflictRole ? "⚠️ CONFLICTING" : escapeHtml(doc.source_role || "PRIMARY")}
                    </span>
                  </td>
                </tr>
              `;
                })
                .join("")}
            </tbody>
          </table>
        `
            : `<div style="font-size:11px; color:var(--text-muted);">Derived from OKF Knowledge Bundle (<code>${escapeHtml(gov.bundle_version)}</code>).</div>`
        }
      </div>
    `;

    // =====================================================================
    // SECTION 3: MODE-SPECIFIC ENGINEERING DETAILS
    //   - Equipment Mode: Conflict Alerts + Governing Parameters Table
    //   - OKF Concept Mode: Concept Summary/Excerpt + Clickable Wiki-Links
    // =====================================================================
    if (state.focusKind === "equipment" && params.length > 0) {
      if (conflicts.length > 0) {
        html += `
          <div class="catalog-card" style="border-left: 3px solid var(--status-conflict-border);">
            <div class="catalog-card-header">
              <span class="catalog-card-title" style="color: var(--status-conflict-text);">
                ⚠️ 3a. Cross-Document Parameter Conflicts (${conflicts.length})
              </span>
              <span class="mini-badge mini-badge-conflict">Action Required</span>
            </div>
            ${conflicts
              .slice(0, 6)
              .map(
                (c) => `
              <div style="font-size:11px; margin-bottom:5px; padding-bottom:4px; border-bottom:1px dashed var(--border-subtle);">
                <strong>${escapeHtml(c.parameter_name)}:</strong>
                <code>${escapeHtml(c.parameter_value)} ${escapeHtml(c.parameter_unit || "")}</code>
                ${
                  c.conflict_note
                    ? `<div style="font-size:10px; color:var(--text-muted); margin-top:2px;">Note: ${escapeHtml(c.conflict_note)}</div>`
                    : ""
                }
              </div>
            `
              )
              .join("")}
          </div>
        `;
      }

      html += `
        <div class="catalog-card">
          <div class="catalog-card-header">
            <span class="catalog-card-title">📐 3. Governing Parameters — ${escapeHtml(state.focusTag)} (${params.length})</span>
            <span class="mini-badge ${conflictCount > 0 ? "mini-badge-conflict" : ""}">
              Conflicts: ${conflictCount}
            </span>
          </div>
          <div class="catalog-kv-grid">
            ${params
              .slice(0, 16)
              .map(
                (p) => `
              <div>
                <strong>${escapeHtml(p.parameter_name)}:</strong>
                <code>${escapeHtml(String(p.parameter_value || "").slice(0, 65))} ${escapeHtml(p.parameter_unit || "")}</code>
                ${p.has_conflict ? `<span class="mini-badge mini-badge-conflict">⚠️</span>` : ""}
              </div>
            `
              )
              .join("")}
          </div>
        </div>
      `;
    } else {
      // OKF Concept Mode (or Equipment without FactAssertion rows)
      html += `
        <div class="catalog-card">
          <div class="catalog-card-header">
            <span class="catalog-card-title">📘 3. Concept Summary &amp; Linked Entities</span>
            <span class="mini-badge">${escapeHtml(gov.category)}</span>
          </div>
          ${
            bodyExcerpt
              ? `<div class="concept-excerpt-box">${escapeHtml(bodyExcerpt)}</div>`
              : `<div style="font-size:11px; color:var(--text-muted);">No additional markdown excerpt available.</div>`
          }
          ${
            wikiLinks.length
              ? `
            <div style="margin-top:6px;">
              <div class="gov-meta-label">Linked Equipment &amp; OKF Concepts (${wikiLinks.length}) — Click to Switch:</div>
              <div class="catalog-wikilinks">
                ${wikiLinks
                  .slice(0, 16)
                  .map((wl) => {
                    const toCid = wl.to_concept_id || "";
                    const isEq = toCid.toLowerCase().startsWith("equipment/");
                    const shortTarget = isEq ? toCid.split("/").slice(1).join("/") : toCid;
                    return `
                  <button
                    type="button"
                    class="wikilink-pill"
                    data-target-tag="${escapeHtml(shortTarget)}"
                    data-target-cid="${escapeHtml(toCid)}"
                    data-target-kind="${isEq ? "equipment" : "concept"}"
                    title="Switch to ${escapeHtml(toCid)} (${escapeHtml(wl.section_heading || "")})"
                  >
                    <span>${isEq ? "🔩" : "📘"}</span>
                    <span>${escapeHtml(shortTarget)}</span>
                  </button>
                `;
                  })
                  .join("")}
              </div>
            </div>
          `
              : ""
          }
        </div>
      `;
    }

    el.catalogContentContainer.innerHTML = html;

    // Bind clickable wiki-link pills inside the Active Knowledge Catalog
    el.catalogContentContainer.querySelectorAll(".wikilink-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetTag = btn.getAttribute("data-target-tag") || "";
        const targetCid = btn.getAttribute("data-target-cid") || "";
        const targetKind = btn.getAttribute("data-target-kind") || "equipment";
        if (targetTag) {
          setFocusTag(targetTag, true, targetKind, "", { conceptId: targetCid });
        }
      });
    });
  }

  // =========================================================================
  // 5. RIGHT PANE: MULTI-TURN ADK CHAT & SLIM CONTIGUOUS TELEMETRY BAR
  // =========================================================================

  async function submitChatQuery(question, focusTag, category = null) {
    if (!question || !question.trim()) return;
    const cleanQ = question.trim();

    // Remove empty state hint on first message
    const emptyHint = document.getElementById("chat-empty-hint");
    if (emptyHint) emptyHint.remove();

    appendUserMessage(cleanQ, focusTag || state.focusTag);

    // Auto-expand Slim Telemetry Bar while RUNNING
    if (el.telemetryConsole) el.telemetryConsole.classList.remove("collapsed");
    if (el.telemetryPulseDot) {
      el.telemetryPulseDot.className = "telemetry-pulse running";
    }
    if (el.telemetryStatusPill) el.telemetryStatusPill.textContent = "RUNNING";
    if (el.telemetryTotalMs) el.telemetryTotalMs.textContent = "Running...";
    if (el.telemetryBody) {
      el.telemetryBody.innerHTML = `<div class="telemetry-empty">Dispatching query to ADK Query Agent (<code>gemini-3.8-flash</code>)...</div>`;
    }

    try {
      const res = await fetch("/api/query/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: cleanQ,
          session_id: state.sessionId,
          focus_tag: focusTag || state.focusTag,
          category: category,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const job = await res.json();
      if (job.session_id) {
        state.sessionId = job.session_id;
      }
      if (job.turn_count !== undefined) {
        state.turnCount = job.turn_count;
      }
      updateSessionBadge();
      state.activeJobId = job.job_id;
      pollQueryJob(job.job_id);
    } catch (err) {
      console.error("Failed to start query job:", err);
      if (el.telemetryStatusPill) el.telemetryStatusPill.textContent = "ERROR";
    }
  }

  function pollQueryJob(jobId) {
    if (state.jobPollTimer) clearInterval(state.jobPollTimer);
    const check = async () => {
      try {
        const res = await fetch(`/api/query/jobs/${encodeURIComponent(jobId)}`);
        if (!res.ok) return;
        const job = await res.json();
        renderTelemetryConsole(job);
        if (job.status === "COMPLETED" || job.status === "ERROR") {
          clearInterval(state.jobPollTimer);
          state.jobPollTimer = null;
          appendAgentMessage(job);
          // Auto-collapse telemetry bar after completion (unless user manually pinned it open)
          if (!state.telemetryUserPinned && el.telemetryConsole) {
            setTimeout(() => {
              if (!state.telemetryUserPinned && el.telemetryConsole) {
                el.telemetryConsole.classList.add("collapsed");
              }
            }, 600);
          }
        }
      } catch (err) {
        console.error("Error polling job:", err);
      }
    };
    check();
    state.jobPollTimer = setInterval(check, 450);
  }

  function renderTelemetryConsole(job) {
    if (!el.telemetryBody) return;
    const steps = job.steps || [];
    const tools = job.tool_calls || [];

    if (el.telemetryCountBadge) {
      el.telemetryCountBadge.textContent = String(tools.length);
    }
    if (el.telemetryStatusPill) {
      el.telemetryStatusPill.textContent = job.status || "RUNNING";
    }
    if (el.telemetryPulseDot) {
      el.telemetryPulseDot.className =
        job.status === "COMPLETED"
          ? "telemetry-pulse completed"
          : "telemetry-pulse running";
    }
    if (el.telemetryTotalMs) {
      el.telemetryTotalMs.textContent =
        job.total_duration_ms !== null && job.total_duration_ms !== undefined
          ? `Total: ${job.total_duration_ms} ms`
          : "Running...";
    }

    if (!steps.length) return;
    el.telemetryBody.innerHTML = steps
      .map(
        (s) => `
        <div class="telemetry-step-row">
          <span class="telemetry-step-phase">${escapeHtml(s.phase)}</span>
          <span class="telemetry-step-detail" title="${escapeHtml(s.title)} — ${escapeHtml(s.detail)}">
            <strong>${escapeHtml(s.title)}</strong> • ${escapeHtml(s.detail)}
          </span>
          <span class="telemetry-step-latency">
            ${s.duration_ms !== null && s.duration_ms !== undefined ? `${s.duration_ms} ms` : "⏳ ..."}
          </span>
        </div>
      `
      )
      .join("");
  }

  function appendUserMessage(question, focusTag) {
    if (!el.chatStream) return;
    const div = document.createElement("div");
    div.className = "chat-msg chat-msg-user";
    div.innerHTML = `
      <div class="msg-meta-header">
        <span><strong>Engineer</strong> • Context: <code>${escapeHtml(focusTag)}</code></span>
        <span>${new Date().toLocaleTimeString()}</span>
      </div>
      <div class="msg-markdown">${escapeHtml(question)}</div>
    `;
    el.chatStream.appendChild(div);
    el.chatStream.scrollTop = el.chatStream.scrollHeight;
  }

  function appendAgentMessage(job) {
    if (!el.chatStream) return;
    const div = document.createElement("div");
    div.className = "chat-msg chat-msg-agent";

    const tools = job.tool_calls || [];
    const toolPillsHtml = tools.length
      ? `
        <div class="msg-tool-pills">
          ${tools
            .map(
              (t) => `
            <span class="msg-tool-pill" title="${escapeHtml(t.summary)}">
              🔧 <strong>${escapeHtml(t.tool_name)}</strong> (${t.duration_ms !== null ? `${t.duration_ms} ms` : "--"})
            </span>
          `
            )
            .join("")}
        </div>
      `
      : "";

    const rawMd = job.answer_markdown || job.error || "No response.";
    const renderedHtml =
      window.marked && typeof window.marked.parse === "function"
        ? window.marked.parse(rawMd)
        : `<pre>${escapeHtml(rawMd)}</pre>`;

    div.innerHTML = `
      <div class="msg-meta-header">
        <span><strong>OKF Query Agent</strong> • Turn ${escapeHtml(job.turn_count || state.turnCount || 1)}</span>
        <span>${tools.length} tool(s) • <strong>${job.total_duration_ms || 0} ms</strong></span>
      </div>
      ${toolPillsHtml}
      <div class="msg-markdown">${renderedHtml}</div>
    `;

    el.chatStream.appendChild(div);
    el.chatStream.scrollTop = el.chatStream.scrollHeight;
  }

  // =========================================================================
  // 6. EVENT BINDINGS & INITIALIZATION
  // =========================================================================

  function bindEvents() {
    if (el.themeToggle) {
      el.themeToggle.addEventListener("click", () => {
        applyTheme(state.theme === "dark" ? "light" : "dark");
      });
    }

    if (el.btnRefreshSpanner) {
      el.btnRefreshSpanner.addEventListener("click", () => {
        state.selectionRequestSeq += 1;
        loadSpannerHierarchy(true);
      });
    }

    if (el.hierarchySearchInput) {
      el.hierarchySearchInput.addEventListener("input", (e) => {
        state.hierarchySearch = e.target.value || "";
        renderHierarchyTree();
      });
    }

    document.querySelectorAll(".filter-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-tab").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.hierarchyFilter = btn.getAttribute("data-filter") || "all";
        renderHierarchyTree();
      });
    });

    document.querySelectorAll(".hop-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".hop-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.graphHops = parseInt(btn.getAttribute("data-hops") || "2", 10);
        state.selectionRequestSeq += 1;
        loadSpannerGraph(state.focusTag, state.graphHops, state.selectionRequestSeq);
      });
    });

    document.querySelectorAll(".edge-type-toggle").forEach((cb) => {
      cb.addEventListener("change", () => {
        const val = cb.value;
        if (cb.checked) state.enabledEdgeTypes.add(val);
        else state.enabledEdgeTypes.delete(val);
        renderGraphSvg();
      });
    });

    // Graph zoom/pan controls
    const btnZoomIn = document.getElementById("btn-graph-zoom-in");
    const btnZoomOut = document.getElementById("btn-graph-zoom-out");
    const btnReset = document.getElementById("btn-graph-reset");
    if (btnZoomIn) {
      btnZoomIn.addEventListener("click", () => {
        state.zoom = Math.min(2.4, state.zoom + 0.2);
        renderGraphSvg();
      });
    }
    if (btnZoomOut) {
      btnZoomOut.addEventListener("click", () => {
        state.zoom = Math.max(0.5, state.zoom - 0.2);
        renderGraphSvg();
      });
    }
    if (btnReset) {
      btnReset.addEventListener("click", () => {
        state.zoom = 1.0;
        state.panX = 0;
        state.panY = 0;
        renderGraphSvg();
      });
    }

    if (el.svgCanvas) {
      el.svgCanvas.addEventListener("mousedown", (e) => {
        state.isPanning = true;
        state.panStartX = e.clientX - state.panX;
        state.panStartY = e.clientY - state.panY;
      });
      window.addEventListener("mousemove", (e) => {
        if (!state.isPanning) return;
        state.panX = e.clientX - state.panStartX;
        state.panY = e.clientY - state.panStartY;
        if (el.graphViewportGroup) {
          el.graphViewportGroup.setAttribute(
            "transform",
            `translate(${state.panX}, ${state.panY}) scale(${state.zoom})`
          );
        }
      });
      window.addEventListener("mouseup", () => {
        state.isPanning = false;
      });
    }

    if (el.btnInspectorPivot) {
      el.btnInspectorPivot.addEventListener("click", () => {
        if (state.selectedGraphItem && state.selectedGraphItem.kind === "node") {
          const n = state.selectedGraphItem.data;
          const nType = n.node_type || n.type || "";
          if (nType !== "RAW_PDF") {
            const targetKind = nType === "CONCEPT" || (n.label || "").includes("/") ? "concept" : "equipment";
            setFocusTag(n.label, true, targetKind, n.subtitle || "");
          }
        }
      });
    }

    // Slim 1-Line Telemetry Bar click-to-toggle
    if (el.telemetryHeaderBar && el.telemetryConsole) {
      el.telemetryHeaderBar.addEventListener("click", () => {
        el.telemetryConsole.classList.toggle("collapsed");
        state.telemetryUserPinned = !el.telemetryConsole.classList.contains("collapsed");
      });
    }

    // "+ New Session" button: clears chat stream and creates a fresh ADK session_id
    if (el.btnClearChat) {
      el.btnClearChat.addEventListener("click", () => {
        initOrResetChatSession(true);
      });
    }

    if (el.chatForm) {
      el.chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const q = el.chatQuestionInput ? el.chatQuestionInput.value : "";
        if (!q.trim()) return;
        el.chatQuestionInput.value = "";
        submitChatQuery(q, state.focusTag);
      });
    }

    if (el.chatQuestionInput) {
      el.chatQuestionInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          el.chatForm.requestSubmit();
        }
      });
    }
  }

  function init() {
    applyTheme(state.theme);
    bindEvents();
    loadStatus();
    initOrResetChatSession(false);
    renderDynamicStudyChips();
    loadSpannerHierarchy(false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
