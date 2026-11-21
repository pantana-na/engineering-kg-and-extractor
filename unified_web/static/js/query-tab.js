/**
 * Tab 2: Knowledge Graph & Query Workbench (Lazy Two-Tier Spanner Tree, SSE Streaming Chat & Graph Inspector).
 */

import { fetchJson, streamSSE } from "./api.js";
import { renderInteractiveGraph } from "./graph-canvas.js";
import { escapeHtml, renderMarkdown } from "./markdown.js";
import { showToast, state } from "./state.js";
import { createTelemetryCard } from "./telemetry-card.js";

let searchTimer = null;

function buildDynamicPromptsForNode(tag, nodeType = null) {
  if (!tag) {
    return state.query.defaultPrompts || [];
  }
  const typeHint = nodeType ? ` (${nodeType.toLowerCase()})` : "";
  return [
    {
      id: `hazop_${tag}`,
      title: `HAZOP Study (${tag})`,
      focus_tag: tag,
      question:
        `Perform a 5-stage HAZOP study for ${tag}${typeHint} using Cloud Spanner: ` +
        `evaluate all relevant guideword deviations for ${tag} (such as High Pressure, High/Low Temperature, ` +
        `No/Low/Reverse Flow, High/Low Level, or Loss of Containment as applicable), and output a structured ` +
        `HAZOP table clearly showing both Pre-Mitigation Risk (unmitigated Severity x Likelihood = Risk Tier) ` +
        `and Post-Mitigation Risk (residual Severity x Likelihood = Risk Tier after safeguards/SIS/PSVs), ` +
        `along with upstream/downstream impact and Spanner source citations.`,
    },
    {
      id: `trace_${tag}`,
      title: `Upstream & Downstream Trace (${tag})`,
      focus_tag: tag,
      question:
        `Traverse the Cloud Spanner Property Graph (OkfKnowledgeGraph) around ${tag} up to 2 hops: ` +
        `list all upstream feeding nodes and downstream receiving nodes across CONNECTS_TO edges, ` +
        `stream/line IDs, fluid services, and operational blast radius if ${tag} trips or isolates.`,
    },
    {
      id: `lineage_${tag}`,
      title: `Document Lineage & Conflicts (${tag})`,
      focus_tag: tag,
      question:
        `Audit backward data lineage and cross-document conflicts for ${tag} in Cloud Spanner: ` +
        `list all governing source documents (PRIMARY, MOC_AUTHORITY, PENDING_REDRAFT, CONFLICTING), ` +
        `revisions, and any conflicting design or operating parameters side-by-side.`,
    },
    {
      id: `safety_${tag}`,
      title: `Safety Instruments (${tag})`,
      focus_tag: tag,
      question:
        `Identify all safety instruments, interlocks, alarm/trip setpoints, and pressure relief devices ` +
        `(MONITORS_OR_TRIPS) protecting or linked to ${tag} in Cloud Spanner, including governing relief cases, ` +
        `trip actions, and any unverified or conflicting setpoints.`,
    },
  ];
}

function renderRoleBadge(role) {
  const r = String(role || "PRIMARY").toUpperCase();
  const cls =
    r === "MOC_AUTHORITY"
      ? "role-moc"
      : r === "PENDING_REDRAFT"
        ? "role-redraft"
        : r === "CONFLICTING"
          ? "role-conflict"
          : "role-primary";
  return `<span class="wb-role-badge ${cls}">${escapeHtml(r)}</span>`;
}

function setFocusTag(tag, nodeType = null) {
  const cleanTag = tag ? String(tag).trim() : null;
  state.query.focusTag = cleanTag || null;
  state.query.focusNodeType = cleanTag ? (nodeType || null) : null;

  const pill = document.getElementById("qry-focus-pill");
  if (pill) {
    if (cleanTag) {
      pill.innerHTML = `Focus: ${escapeHtml(cleanTag)} <button type="button" id="btn-clear-focus" class="wb-icon-btn-xs" style="border:none;background:transparent;color:inherit;cursor:pointer;margin-left:4px" title="Clear focus">&times;</button>`;
      pill.querySelector("#btn-clear-focus")?.addEventListener("click", () => setFocusTag(null));
    } else {
      pill.textContent = "Focus: All";
    }
  }

  renderPreBuiltPrompts(buildDynamicPromptsForNode(cleanTag, nodeType), { isDynamic: true });

  if (cleanTag) {
    loadGraph(cleanTag);
    loadConceptDossier(cleanTag);
    loadDataplexCatalog(false, cleanTag);
  } else {
    const svgEl = document.getElementById("graph-svg");
    const gPill = document.getElementById("graph-status-pill");
    const dEl = document.getElementById("dossier-content");
    if (svgEl) svgEl.innerHTML = "";
    if (gPill) gPill.textContent = "Select a tag to visualize graph";
    if (dEl) dEl.innerHTML = `<div class="wb-empty">Select an equipment tag, instrument, or graph node to inspect Spanner parameters &amp; lineage.</div>`;
    loadDataplexCatalog(false, null);
  }
}

export async function loadSpannerSummary(refresh = false) {
  const treeEl = document.getElementById("qry-hierarchy-tree");
  const statsEl = document.getElementById("qry-summary-stats");
  if (!treeEl) return;

  try {
    const data = await fetchJson(`/api/spanner/hierarchy/summary?refresh=${refresh ? "true" : "false"}`);
    state.query.summary = data;
    if (statsEl) {
      statsEl.textContent = `${data.total_concepts} concepts · ${data.total_equipment} equip · ${data.total_conflicts} conflicts`;
    }
    renderSummaryTree(data);
  } catch (err) {
    treeEl.innerHTML = `<div class="wb-empty">Spanner unavailable: ${escapeHtml(err.message)}</div>`;
  }
}

function renderSummaryTree(summary) {
  const treeEl = document.getElementById("qry-hierarchy-tree");
  if (!treeEl) return;
  const blocks = [];

  for (const u of summary.units || []) {
    const classesHtml = (u.classes || [])
      .map(
        (cls) => `
          <div class="wb-tree-group" data-lazy-unit="${escapeHtml(u.unit)}" data-lazy-class="${escapeHtml(cls.class_name)}">
            <button class="wb-tree-header" data-expand-class="1">
              <span>${escapeHtml(cls.class_name)}</span>
              <span class="wb-pill">${cls.count}</span>
            </button>
            <div class="wb-tree-children hidden"></div>
          </div>
        `
      )
      .join("");
    blocks.push(`
      <div class="wb-tree-group">
        <button class="wb-tree-header" data-toggle-unit="1">
          <span>${escapeHtml(u.unit)}</span>
          <span class="wb-pill">${u.equipment_count}</span>
        </button>
        <div class="wb-tree-children">${classesHtml}</div>
      </div>
    `);
  }

  for (const cat of summary.knowledge_categories || []) {
    blocks.push(`
      <div class="wb-tree-group" data-lazy-cat="${escapeHtml(cat.category)}">
        <button class="wb-tree-header" data-expand-cat="1">
          <span>${escapeHtml(cat.category)}</span>
          <span class="wb-pill">${cat.count}</span>
        </button>
        <div class="wb-tree-children hidden"></div>
      </div>
    `);
  }

  treeEl.innerHTML = blocks.length
    ? blocks.join("")
    : `<div class="wb-empty">No concepts in Cloud Spanner yet. Trigger <strong>Sync OKF &rarr; Spanner</strong> from Extractor Studio.</div>`;

  treeEl.querySelectorAll("[data-toggle-unit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.nextElementSibling?.classList.toggle("hidden");
    });
  });

  treeEl.querySelectorAll("[data-expand-class]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const group = btn.closest("[data-lazy-unit]");
      const container = btn.nextElementSibling;
      if (!group || !container) return;
      container.classList.toggle("hidden");
      if (!container.dataset.loaded) {
        await loadLazyItemsInto(container, {
          unit: group.getAttribute("data-lazy-unit"),
          class_name: group.getAttribute("data-lazy-class"),
          category: "equipment",
        });
      }
    });
  });

  treeEl.querySelectorAll("[data-expand-cat]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const group = btn.closest("[data-lazy-cat]");
      const container = btn.nextElementSibling;
      if (!group || !container) return;
      container.classList.toggle("hidden");
      if (!container.dataset.loaded) {
        await loadLazyItemsInto(container, {
          category: group.getAttribute("data-lazy-cat"),
        });
      }
    });
  });
}

async function loadLazyItemsInto(container, filters, offset = 0) {
  const params = new URLSearchParams({
    limit: "50",
    offset: String(offset),
    conflicts_only: state.query.conflictsOnly ? "true" : "false",
  });
  if (filters.unit) params.set("unit", filters.unit);
  if (filters.class_name) params.set("class_name", filters.class_name);
  if (filters.category) params.set("category", filters.category);
  if (filters.q) params.set("q", filters.q);

  if (offset === 0) container.innerHTML = `<div class="wb-muted wb-xs">Loading...</div>`;
  try {
    const data = await fetchJson(`/api/spanner/hierarchy/items?${params.toString()}`);
    container.dataset.loaded = "1";
    const itemsHtml = (data.items || [])
      .map((item) => {
        const tag = item.canonical_tag || item.concept_id;
        const badge = item.has_conflict ? `<span class="wb-badge-conflict">CONFLICT</span>` : "";
        return `
          <button class="wb-list-item" data-spanner-tag="${escapeHtml(tag)}" data-spanner-cid="${escapeHtml(item.concept_id)}">
            <div class="wb-item-top">
              <span class="wb-item-title">${escapeHtml(tag)}</span>
              ${badge}
            </div>
            <span class="wb-item-sub">${escapeHtml(item.name || item.concept_id)}</span>
          </button>
        `;
      })
      .join("");

    if (offset === 0) {
      container.innerHTML = itemsHtml || `<div class="wb-muted wb-xs">No matching items.</div>`;
    } else {
      container.querySelector(".wb-more-wrap")?.remove();
      container.insertAdjacentHTML("beforeend", itemsHtml);
    }

    if (data.has_more) {
      const moreBtn = document.createElement("button");
      moreBtn.className = "wb-btn wb-btn-ghost wb-btn-sm wb-more-wrap";
      moreBtn.textContent = `Load more (${data.total - (offset + data.items.length)} left)`;
      moreBtn.addEventListener("click", () => loadLazyItemsInto(container, filters, offset + data.items.length));
      container.appendChild(moreBtn);
    }

    container.querySelectorAll("[data-spanner-tag]").forEach((btn) => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        setFocusTag(btn.getAttribute("data-spanner-tag"));
      });
    });
  } catch (err) {
    container.innerHTML = `<div class="wb-xs" style="color:var(--rose)">${escapeHtml(err.message)}</div>`;
  }
}

export async function loadGraph(centerTag) {
  const svgEl = document.getElementById("graph-svg");
  const pill = document.getElementById("graph-status-pill");
  const hops = document.getElementById("graph-hops-select")?.value || "2";
  const lineage = document.getElementById("graph-lineage-toggle")?.checked ? "true" : "false";
  if (pill) pill.textContent = `Loading graph for ${centerTag}...`;

  try {
    const data = await fetchJson(
      `/api/spanner/graph?center_tag=${encodeURIComponent(centerTag)}&max_hops=${hops}&include_lineage=${lineage}`
    );
    renderInteractiveGraph(svgEl, data, {
      onNodeClick: (label, nodeType) => setFocusTag(label, nodeType),
    });
    if (pill) {
      pill.textContent = `${centerTag} · ${data.nodes?.length || 0} nodes · ${data.edges?.length || 0} edges (${data.execution_time_ms} ms)`;
    }
  } catch (err) {
    if (pill) pill.textContent = `Graph error: ${err.message}`;
  }
}

async function loadConceptDossier(tagOrId) {
  const el = document.getElementById("dossier-content");
  if (!el) return;
  el.innerHTML = `<div class="wb-empty">Loading Cloud Spanner dossier for ${escapeHtml(tagOrId)}...</div>`;
  try {
    const data = await fetchJson(`/api/spanner/concept/${encodeURI(tagOrId)}`);
    const params = (data.parameters || []).slice(0, 25);
    const paramRows = params
      .map(
        (p) =>
          `<tr><td>${escapeHtml(p.parameter_name)}</td><td>${escapeHtml(p.parameter_value)} ${escapeHtml(p.parameter_unit || "")}</td><td>${p.has_conflict ? "CONFLICT" : "OK"}</td></tr>`
      )
      .join("");
    const dossierDocs = Array.isArray(data.catalog_dossier?.source_documents)
      ? data.catalog_dossier.source_documents
      : [];
    const lineageSourceList = dossierDocs.length ? dossierDocs : (data.lineage_traces || []);
    const seenLineage = new Set();
    const dedupLineage = [];
    for (const l of lineageSourceList) {
      const fname = String(l.filename || l.document_name || l.source_id || "unknown");
      const rev = String(l.revision || "");
      const key = `${fname.toLowerCase()}|${rev.toLowerCase()}`;
      if (seenLineage.has(key)) continue;
      seenLineage.add(key);
      dedupLineage.push(l);
    }
    const lineageHtml = dedupLineage
      .slice(0, 12)
      .map((l) => {
        const fname = l.filename || l.document_name || l.source_id || "unknown";
        const rev = l.revision ? ` · Rev ${l.revision}` : "";
        const fc = Number(l.fact_count || 0) > 0 ? ` · ${l.fact_count} fact${l.fact_count === 1 ? "" : "s"}` : "";
        return `<li><code>${escapeHtml(fname)}</code>${escapeHtml(rev)}${escapeHtml(fc)} ${renderRoleBadge(l.source_role)}</li>`;
      })
      .join("");

    el.innerHTML = `
      <div>
        <h3 style="margin:0">${escapeHtml(data.concept?.title || data.concept?.name || tagOrId)}</h3>
        <span class="wb-muted wb-xs">${escapeHtml(data.concept?.concept_id || tagOrId)} · Spanner Only · ${data.execution_time_ms} ms ${data.cached ? "(cached)" : "(live)"}</span>
      </div>
      ${paramRows ? `<div class="wb-md"><table><thead><tr><th>Parameter</th><th>Value</th><th>Status</th></tr></thead><tbody>${paramRows}</tbody></table></div>` : ""}
      ${lineageHtml ? `<div><strong>Document Lineage (Cloud Spanner)</strong><ul>${lineageHtml}</ul></div>` : ""}
      ${renderMarkdown(data.concept?.body_markdown || "")}
    `;
  } catch (err) {
    el.innerHTML = `<div class="wb-empty">Dossier not found in Spanner: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadDataplexCatalog(forceSync = false, focusTag = undefined) {
  const el = document.getElementById("catalog-content");
  if (!el) return;
  const activeTag = focusTag !== undefined ? focusTag : state.query.focusTag;
  const qs = activeTag ? `?focus_tag=${encodeURIComponent(activeTag)}` : "";
  el.innerHTML = `<div class="wb-empty">Querying Cloud Spanner &amp; Dataplex Universal Catalog${activeTag ? ` for ${escapeHtml(activeTag)}` : ""}...</div>`;
  try {
    const data = forceSync
      ? await fetchJson(`/api/catalog/sync${qs}`, { method: "POST" })
      : await fetchJson(`/api/catalog${qs}`);
    state.query.catalogLoaded = true;
    state.query.lastCatalogFocus = activeTag || null;

    const focused = data.focused_node;
    let focusedHtml = "";
    if (focused && focused.found) {
      const g = focused.governance || {};
      const m = focused.metrics || {};
      const b = focused.dataplex_binding || {};
      const healthBadge = g.has_conflict
        ? `<span class="wb-health-warn">${g.conflict_count || 1} CONFLICT(S)</span>`
        : `<span class="wb-health-ok">VERIFIED · NO CONFLICTS</span>`;
      const srcDocs = Array.isArray(focused.source_documents) ? focused.source_documents : [];
      const traces = Array.isArray(focused.lineage_traces) ? focused.lineage_traces : [];
      const rawDocs = srcDocs.length ? srcDocs : traces;
      const seenDocs = new Set();
      const uniqueDocs = [];
      for (const d of rawDocs) {
        const fname = String(d.filename || d.document_name || d.source_id || "unknown");
        const rev = String(d.revision || "");
        const key = `${fname.toLowerCase()}|${rev.toLowerCase()}`;
        if (seenDocs.has(key)) continue;
        seenDocs.add(key);
        uniqueDocs.push(d);
      }
      const docRows = uniqueDocs
        .slice(0, 12)
        .map((d) => {
          const fname = d.filename || d.document_name || d.source_id || "unknown";
          const rev = d.revision ? ` · Rev ${d.revision}` : "";
          const fc = Number(d.fact_count || 0) > 0 ? ` · ${d.fact_count} fact${d.fact_count === 1 ? "" : "s"}` : "";
          const role = d.source_role || d.role || "PRIMARY";
          return `<li><code>${escapeHtml(fname)}</code>${escapeHtml(rev)}${escapeHtml(fc)} ${renderRoleBadge(role)}</li>`;
        })
        .join("");

      focusedHtml = `
        <div class="wb-dp-section">
          <div class="wb-item-top">
            <strong>1. Asset Governance &amp; Trust (${escapeHtml(focused.tag)})</strong>
            ${healthBadge}
          </div>
          <div class="wb-dp-kv">
            <span class="wb-dp-k">Concept ID</span><span class="wb-dp-v">${escapeHtml(g.concept_id || focused.tag)}</span>
            <span class="wb-dp-k">Class / Unit</span><span class="wb-dp-v">${escapeHtml(g.concept_type || "—")} · ${escapeHtml(g.unit || "—")}</span>
            <span class="wb-dp-k">Trust Tier</span><span class="wb-dp-v">${escapeHtml(g.trust_tier || "human-reviewed")} (${escapeHtml(g.status || "stable")})</span>
            <span class="wb-dp-k">Custodian</span><span class="wb-dp-v">${escapeHtml(g.governing_authority || (g.approved_by || []).join(", ") || "—")}</span>
            <span class="wb-dp-k">Provenance</span><span class="wb-dp-v">${escapeHtml(g.extracted_by || "—")} · ${escapeHtml(g.bundle_version || "—")}</span>
            <span class="wb-dp-k">Content MD5</span><span class="wb-dp-v">${escapeHtml((g.content_md5 || "—").slice(0, 16))}</span>
          </div>
        </div>

        <div class="wb-dp-section">
          <strong>2. Node Data Lineage &amp; Fact Coverage (Spanner)</strong>
          <div class="wb-lineage-chain">
            <span>RawSourceDocs (${m.source_doc_count ?? 0})</span>
            <span>&rarr;</span>
            <span>OKF Concept</span>
            <span>&rarr;</span>
            <span>${escapeHtml(focused.tag)} (${m.parameter_count ?? 0} facts)</span>
          </div>
          <div class="wb-dp-metrics">
            <span class="wb-pill">${m.parameter_count ?? 0} params</span>
            <span class="wb-pill">${m.connected_nodes ?? 0} linked nodes</span>
            <span class="wb-pill">${m.connected_edges ?? 0} edges</span>
            <span class="wb-pill">${m.conflict_count ?? 0} conflicts</span>
          </div>
          ${docRows ? `<ul style="margin:2px 0 0;padding-left:16px;font-size:11.5px">${docRows}</ul>` : `<div class="wb-muted wb-xs">No backward document lineage edges recorded for this node in Spanner.</div>`}
        </div>

        <div class="wb-dp-section">
          <div class="wb-item-top">
            <strong>3. Dataplex Universal Catalog Aspect Binding</strong>
            <span class="wb-pill">${escapeHtml(b.status || data.status || "SYNCED_LIVE")}</span>
          </div>
          <div class="wb-dp-kv">
            <span class="wb-dp-k">Entry Group</span><span class="wb-dp-v">${escapeHtml(b.entry_group || data.entry_group || "—")}</span>
            <span class="wb-dp-k">Aspect Type</span><span class="wb-dp-v">${escapeHtml(b.aspect_type || "okf-governance-template")}</span>
            <span class="wb-dp-k">Spanner Asset</span><span class="wb-dp-v">${escapeHtml(b.spanner_linked_resource || "—")}</span>
          </div>
        </div>
      `;
    } else if (focused && !focused.found) {
      focusedHtml = `<div class="wb-empty">${escapeHtml(focused.message || "Selected node not found in Spanner.")}</div>`;
    } else {
      const spannerEntries = (data.dataplex_entries || []).filter(
        (e) => e.entry_id === "okf_spanner_knowledge_graph"
      );
      const entriesHtml = (spannerEntries.length ? spannerEntries : data.dataplex_entries || [])
        .map(
          (e) => `
            <div class="wb-job-card">
              <div class="wb-item-top"><strong>${escapeHtml(e.display_name || e.entry_id)}</strong><span class="wb-pill">${escapeHtml(e.status)}</span></div>
              <div class="wb-muted wb-xs"><code>${escapeHtml(e.linked_resource || "")}</code></div>
            </div>
          `
        )
        .join("");
      focusedHtml = `
        <div class="wb-muted wb-xs">Select an equipment, instrument, or graph node on the left (or in the Graph tab) to inspect node-specific Spanner governance &amp; Dataplex lineage.</div>
        <div class="wb-muted wb-xs">Entry Group: <code>${escapeHtml(data.entry_group || "")}</code></div>
        ${entriesHtml}
      `;
    }

    el.innerHTML = `
      <div class="wb-item-top">
        <strong>Dataplex &amp; Governance ${activeTag ? `· ${escapeHtml(activeTag)}` : ""}</strong>
        <button id="btn-sync-dataplex" class="wb-btn wb-btn-secondary wb-btn-sm">Sync Catalog</button>
      </div>
      ${focusedHtml}
    `;
    el.querySelector("#btn-sync-dataplex")?.addEventListener("click", () => loadDataplexCatalog(true, activeTag));
  } catch (err) {
    el.innerHTML = `<div class="wb-empty">Catalog error: ${escapeHtml(err.message)}</div>`;
  }
}

async function sendQueryQuestion(question) {
  const msgContainer = document.getElementById("qry-chat-messages");
  const statusEl = document.getElementById("qry-stream-status");
  const sendBtn = document.getElementById("qry-send-btn");
  if (!msgContainer) return;

  const model = state.selectedModels.query;
  const userDiv = document.createElement("div");
  userDiv.className = "wb-msg user";
  userDiv.textContent = question;
  msgContainer.appendChild(userDiv);

  const botDiv = document.createElement("div");
  botDiv.className = "wb-msg assistant";
  const telemetry = createTelemetryCard({ model, modeLabel: "Spanner Query" });
  const answerEl = document.createElement("div");
  answerEl.className = "wb-answer-body";
  answerEl.innerHTML = `<span class="wb-muted">Querying Cloud Spanner &amp; reasoning...</span>`;
  botDiv.appendChild(telemetry.element);
  botDiv.appendChild(answerEl);
  msgContainer.appendChild(botDiv);
  msgContainer.scrollTop = msgContainer.scrollHeight;

  let streamedText = "";
  if (sendBtn) sendBtn.disabled = true;
  if (statusEl) statusEl.textContent = `Streaming from ${model}...`;

  try {
    await streamSSE(
      "/api/query/chat/stream",
      {
        question,
        session_id: state.query.sessionId,
        focus_tag: state.query.focusTag,
        model,
      },
      (evType, payload) => {
        if (evType === "start") {
          state.query.sessionId = payload.session_id;
        } else if (evType === "step") {
          telemetry.onStep(payload);
          msgContainer.scrollTop = msgContainer.scrollHeight;
        } else if (evType === "tool_call") {
          telemetry.onToolCall(payload);
          msgContainer.scrollTop = msgContainer.scrollHeight;
        } else if (evType === "token") {
          streamedText += payload.text || "";
          answerEl.innerHTML = renderMarkdown(streamedText);
          msgContainer.scrollTop = msgContainer.scrollHeight;
        } else if (evType === "done") {
          telemetry.onDone(payload);
          answerEl.innerHTML = renderMarkdown(payload.answer_markdown || streamedText || "Done.");
          const tags = payload.referenced_tags || [];
          if (tags.length) {
            const pills = document.createElement("div");
            pills.className = "wb-filter-row";
            pills.style.marginTop = "10px";
            pills.innerHTML = tags
              .map((t) => `<button class="wb-chip" data-jump-tag="${escapeHtml(t)}">Focus ${escapeHtml(t)}</button>`)
              .join("");
            pills.querySelectorAll("[data-jump-tag]").forEach((b) =>
              b.addEventListener("click", () => setFocusTag(b.getAttribute("data-jump-tag")))
            );
            botDiv.appendChild(pills);
          }
          msgContainer.scrollTop = msgContainer.scrollHeight;
        } else if (evType === "error") {
          telemetry.onError(payload.error || "Unknown error");
          answerEl.innerHTML = `<span style="color:var(--rose)">Error: ${escapeHtml(payload.error || "Unknown error")}</span>`;
        }
      }
    );
  } catch (err) {
    telemetry.onError(err.message);
    answerEl.innerHTML = `<span style="color:var(--rose)">Stream error: ${escapeHtml(err.message)}</span>`;
    showToast(`Query failed: ${err.message}`, "err");
  } finally {
    telemetry.destroy();
    if (sendBtn) sendBtn.disabled = false;
    if (statusEl) statusEl.textContent = "Ready · SSE Streaming enabled";
  }
}

export function renderPreBuiltPrompts(prompts, { isDynamic = false } = {}) {
  const strip = document.getElementById("qry-prompt-chips");
  if (!strip) return;
  if (!isDynamic) {
    state.query.defaultPrompts = Array.isArray(prompts) ? prompts : [];
  }
  const activeList =
    !isDynamic && state.query.focusTag
      ? buildDynamicPromptsForNode(state.query.focusTag, state.query.focusNodeType)
      : (prompts || []);
  strip.innerHTML = activeList
    .slice(0, 5)
    .map(
      (p) =>
        `<button class="wb-chip" data-prompt-q="${escapeHtml(p.question)}" data-prompt-tag="${escapeHtml(p.focus_tag || "")}">${escapeHtml(p.title)}</button>`
    )
    .join("");
  strip.querySelectorAll("[data-prompt-q]").forEach((btn) => {
    btn.addEventListener("click", () => {
      sendQueryQuestion(btn.getAttribute("data-prompt-q"));
    });
  });
}

export function focusEquipmentInQuery(tag) {
  setFocusTag(tag);
}

export function initQueryTab() {
  document.getElementById("qry-refresh-btn")?.addEventListener("click", () => {
    loadSpannerSummary(true);
    showToast("Refreshed Spanner hierarchy.", "ok");
  });

  document.getElementById("qry-conflicts-toggle")?.addEventListener("click", (e) => {
    state.query.conflictsOnly = !state.query.conflictsOnly;
    e.target.classList.toggle("active", state.query.conflictsOnly);
    const treeEl = document.getElementById("qry-hierarchy-tree");
    if (state.query.conflictsOnly || state.query.searchQ) {
      loadLazyItemsInto(treeEl, { q: state.query.searchQ });
    } else if (state.query.summary) {
      renderSummaryTree(state.query.summary);
    }
  });

  document.getElementById("qry-search-input")?.addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const q = e.target.value.trim();
      state.query.searchQ = q;
      const treeEl = document.getElementById("qry-hierarchy-tree");
      if (q || state.query.conflictsOnly) {
        loadLazyItemsInto(treeEl, { q });
      } else if (state.query.summary) {
        renderSummaryTree(state.query.summary);
      }
    }, 280);
  });

  document.getElementById("qry-new-session-btn")?.addEventListener("click", async () => {
    const res = await fetchJson("/api/query/session/new", { method: "POST" });
    state.query.sessionId = res.session_id;
    const log = document.getElementById("qry-chat-messages");
    if (log) {
      log.innerHTML = `<div class="wb-msg assistant">Started fresh multi-turn session <code>${escapeHtml(res.session_id)}</code>.</div>`;
    }
  });

  document.getElementById("qry-chat-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("qry-chat-input");
    const q = input?.value.trim();
    if (!q) return;
    input.value = "";
    sendQueryQuestion(q);
  });

  // Right Inspector Tabs
  document.querySelectorAll("[data-insp]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-insp");
      state.query.inspectorTab = target;
      document.querySelectorAll("[data-insp]").forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".wb-inspector-body").forEach((p) => p.classList.remove("active"));
      document.getElementById(`insp-pane-${target}`)?.classList.add("active");
      document.getElementById("graph-toolbar")?.classList.toggle("hidden", target !== "graph");
      if (target === "catalog" && (!state.query.catalogLoaded || state.query.lastCatalogFocus !== (state.query.focusTag || null))) {
        loadDataplexCatalog(false, state.query.focusTag);
      }
    });
  });

  document.getElementById("graph-hops-select")?.addEventListener("change", () => {
    if (state.query.focusTag) loadGraph(state.query.focusTag);
  });
  document.getElementById("graph-lineage-toggle")?.addEventListener("change", () => {
    if (state.query.focusTag) loadGraph(state.query.focusTag);
  });
}
