/**
 * Tab 1: Extractor Studio (Paginated _manifest.json Explorer, Document Viewer,
 * GCS Sync & Live Streaming Extraction Assistant with Zero-Enter Extract + Sync).
 */

import { fetchJson, streamSSE } from "./api.js";
import { escapeHtml, renderMarkdown } from "./markdown.js";
import { showToast, state } from "./state.js";
import { createTelemetryCard } from "./telemetry-card.js";

let searchDebounce = null;
let onJumpToGraphCb = null;
let onSpannerMutatedCb = null;
let onQuickSyncSpannerCb = null;
let isExtracting = false;

function renderFilterChips() {
  const host = document.getElementById("ext-filter-chips");
  if (!host) return;
  const ext = state.extractor;
  const chips = [];

  if (ext.kind === "raw") {
    chips.push(
      `<button class="wb-chip ${!ext.subfolder ? "active" : ""}" data-filter-sub="">All</button>`
    );
    for (const [sub, count] of Object.entries(ext.rawSubfolders || {})) {
      chips.push(
        `<button class="wb-chip ${ext.subfolder === sub ? "active" : ""}" data-filter-sub="${escapeHtml(sub)}">${escapeHtml(sub)} (${count})</button>`
      );
    }
    host.innerHTML = chips.join("");
    host.querySelectorAll("[data-filter-sub]").forEach((btn) => {
      btn.addEventListener("click", () => {
        ext.subfolder = btn.getAttribute("data-filter-sub") || "";
        ext.offset = 0;
        loadExtractorFiles({ append: false });
      });
    });
  } else {
    chips.push(
      `<button class="wb-chip ${!ext.category && !ext.conflictsOnly ? "active" : ""}" data-filter-cat="">All</button>`,
      `<button class="wb-chip ${ext.conflictsOnly ? "active" : ""}" id="ext-conflicts-chip">Conflicts</button>`
    );
    for (const [cat, count] of Object.entries(ext.okfCategories || {})) {
      chips.push(
        `<button class="wb-chip ${ext.category === cat ? "active" : ""}" data-filter-cat="${escapeHtml(cat)}">${escapeHtml(cat)} (${count})</button>`
      );
    }
    host.innerHTML = chips.join("");
    host.querySelector("#ext-conflicts-chip")?.addEventListener("click", () => {
      ext.conflictsOnly = !ext.conflictsOnly;
      ext.offset = 0;
      loadExtractorFiles({ append: false });
    });
    host.querySelectorAll("[data-filter-cat]").forEach((btn) => {
      btn.addEventListener("click", () => {
        ext.category = btn.getAttribute("data-filter-cat") || "";
        ext.offset = 0;
        loadExtractorFiles({ append: false });
      });
    });
  }
}

function renderFileList() {
  const listEl = document.getElementById("ext-file-list");
  const metaEl = document.getElementById("ext-page-meta");
  const loadMoreBtn = document.getElementById("ext-load-more-btn");
  if (!listEl) return;

  const ext = state.extractor;
  if (!ext.items.length) {
    listEl.innerHTML = `<div class="wb-empty">No matching ${ext.kind === "raw" ? "raw documents" : "OKF concepts"} found.</div>`;
  } else if (ext.kind === "raw") {
    listEl.innerHTML = ext.items
      .map((p) => {
        const active = ext.selectedItem?.id === p.relative_path ? "active" : "";
        const kb = Math.max(1, Math.round((p.size_bytes || 0) / 1024));
        return `
          <button class="wb-list-item ${active}" data-raw-path="${escapeHtml(p.relative_path)}" data-raw-url="${escapeHtml(p.url)}" data-raw-sub="${escapeHtml(p.subfolder)}" data-raw-name="${escapeHtml(p.file_name)}">
            <div class="wb-item-top">
              <span class="wb-item-title">${escapeHtml(p.file_name)}</span>
              <span class="wb-muted wb-xs">${kb} KB</span>
            </div>
            <span class="wb-item-sub">${escapeHtml(p.subfolder)}</span>
          </button>
        `;
      })
      .join("");
    listEl.querySelectorAll("[data-raw-path]").forEach((el) => {
      el.addEventListener("click", () => {
        openRawDocument({
          relative_path: el.getAttribute("data-raw-path"),
          url: el.getAttribute("data-raw-url"),
          subfolder: el.getAttribute("data-raw-sub"),
          file_name: el.getAttribute("data-raw-name"),
        });
      });
    });
  } else {
    listEl.innerHTML = ext.items
      .map((f) => {
        const active = ext.selectedItem?.id === f.concept_id ? "active" : "";
        const badge = f.has_conflict ? `<span class="wb-badge-conflict">CONFLICT</span>` : "";
        return `
          <button class="wb-list-item ${active}" data-okf-id="${escapeHtml(f.concept_id)}">
            <div class="wb-item-top">
              <span class="wb-item-title">${escapeHtml(f.title || f.concept_id)}</span>
              ${badge}
            </div>
            <span class="wb-item-sub">${escapeHtml(f.concept_id)}</span>
          </button>
        `;
      })
      .join("");
    listEl.querySelectorAll("[data-okf-id]").forEach((el) => {
      el.addEventListener("click", () => openOkfConcept(el.getAttribute("data-okf-id")));
    });
  }

  if (metaEl) metaEl.textContent = `Showing ${ext.items.length} item(s)`;
  if (loadMoreBtn) loadMoreBtn.classList.toggle("hidden", !ext.hasMore);
}

export async function loadExtractorFiles({ append = false, forceGcs = false } = {}) {
  const ext = state.extractor;
  const params = new URLSearchParams({
    kind: ext.kind,
    limit: String(ext.limit),
    offset: String(append ? ext.offset : 0),
    q: ext.q,
    subfolder: ext.kind === "raw" ? ext.subfolder : "",
    category: ext.kind === "okf" ? ext.category : "",
    conflicts_only: ext.conflictsOnly ? "true" : "false",
    force_gcs: forceGcs ? "true" : "false",
  });

  try {
    const data = await fetchJson(`/api/files?${params.toString()}`);
    ext.syncVersion = data.sync_version || "";
    ext.rawSubfolders = data.raw_subfolders || {};
    ext.okfCategories = data.okf_categories || {};

    document.getElementById("ext-raw-count").textContent = String(data.raw_pdf_count ?? 0);
    document.getElementById("ext-okf-count").textContent = String(data.okf_file_count ?? 0);
    const kRaw = document.getElementById("kpi-raw");
    const kOkf = document.getElementById("kpi-okf");
    const kConf = document.getElementById("kpi-conflicts");
    const kVer = document.getElementById("kpi-sync-ver");
    if (kRaw) kRaw.textContent = String(data.raw_pdf_count ?? 0);
    if (kOkf) kOkf.textContent = String(data.okf_file_count ?? 0);
    if (kConf) kConf.textContent = String(data.conflict_count ?? 0);
    if (kVer) kVer.textContent = (ext.syncVersion || "—").slice(0, 8);

    const incoming = ext.kind === "raw" ? (data.raw_pdfs || []) : (data.okf_files || []);
    ext.items = append ? [...ext.items, ...incoming] : incoming;
    ext.offset = ext.items.length;
    ext.hasMore = ext.kind === "raw" ? Boolean(data.pagination?.raw_has_more) : Boolean(data.pagination?.okf_has_more);

    renderFilterChips();
    renderFileList();
  } catch (err) {
    showToast(`Failed to load files: ${err.message}`, "err");
  }
}

export async function syncFromGcs() {
  const btn = document.getElementById("btn-sync-gcs");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Syncing GCS...";
  }
  try {
    const res = await fetchJson("/api/gcs/sync", { method: "POST" });
    state.extractor.offset = 0;
    await loadExtractorFiles({ append: false, forceGcs: false });
    showToast(
      `GCS synced (${res.raw_pdf_count} raw docs · ${res.okf_file_count} OKF concepts · ${res.duration_ms} ms).`,
      "ok"
    );
  } catch (err) {
    showToast(`GCS sync failed: ${err.message}`, "err");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "&#x21bb; Sync GCS";
    }
  }
}

function resolveInteractiveTargetPdf() {
  const sel = state.extractor.selectedItem;
  if (sel?.kind === "raw" && sel.relative_path) {
    return sel.relative_path;
  }
  if (sel?.kind === "okf" && sel.primary_pdf_path) {
    return sel.primary_pdf_path;
  }
  return null;
}

export async function runInteractiveExtract({
  prompt = "",
  targetPdf = null,
  syncToSpanner = false,
  invokeVertexLlm = null,
} = {}) {
  if (isExtracting) {
    showToast("An interactive extraction is already running — please wait for it to finish.", "err");
    return;
  }

  const drawer = document.getElementById("ext-chat-drawer");
  const log = document.getElementById("ext-chat-log");
  if (drawer) drawer.classList.remove("hidden");
  if (!log) return;

  const model = state.selectedModels.extractor;
  const invokeLlm =
    invokeVertexLlm !== null
      ? Boolean(invokeVertexLlm)
      : Boolean(document.getElementById("ext-live-llm-toggle")?.checked ?? true);
  const syncMode = document.getElementById("sync-mode-select")?.value || "INCREMENTAL";

  const effectivePrompt =
    prompt.trim() ||
    (targetPdf
      ? `Extract all engineering parameters, equipment tags, instrumentation, connections, and hazards from ${targetPdf} and merge-update OKF concepts.`
      : "Audit current OKF bundle status and recent extraction log.");

  const userDiv = document.createElement("div");
  userDiv.className = "wb-msg user";
  userDiv.textContent = effectivePrompt;
  log.appendChild(userDiv);

  const botDiv = document.createElement("div");
  botDiv.className = "wb-msg assistant";
  const telemetry = createTelemetryCard({
    model,
    modeLabel: syncToSpanner ? "Extract + Sync" : "Extractor",
  });
  const answerEl = document.createElement("div");
  answerEl.className = "wb-answer-body";
  answerEl.innerHTML = `<span class="wb-muted">${syncToSpanner ? "Extracting & syncing to GCS + Spanner..." : "Running extraction..."}</span>`;
  botDiv.appendChild(telemetry.element);
  botDiv.appendChild(answerEl);
  log.appendChild(botDiv);
  log.scrollTop = log.scrollHeight;

  isExtracting = true;
  const topBtn = document.getElementById("btn-interactive-extract-sync");
  if (topBtn) topBtn.disabled = true;

  let streamedText = "";
  try {
    await streamSSE(
      "/api/extractor/chat/stream",
      {
        prompt: effectivePrompt,
        mode: targetPdf ? "by_pdf" : "chat",
        target_pdf: targetPdf,
        model,
        invoke_vertex_llm: invokeLlm,
        sync_to_spanner: Boolean(syncToSpanner),
        sync_mode: syncMode,
      },
      (evType, payload) => {
        if (evType === "step") {
          telemetry.onStep(payload);
          log.scrollTop = log.scrollHeight;
        } else if (evType === "tool_call") {
          telemetry.onToolCall(payload);
          log.scrollTop = log.scrollHeight;
        } else if (evType === "token") {
          streamedText += payload.text || "";
          answerEl.innerHTML = renderMarkdown(streamedText);
          log.scrollTop = log.scrollHeight;
        } else if (evType === "done") {
          telemetry.onDone(payload);
          if (payload.status === "blocked") {
            answerEl.innerHTML = `<strong style="color:var(--rose)">Blocked by Model Armor:</strong> ${escapeHtml(payload.error || "Policy violation")}`;
          } else {
            answerEl.innerHTML = renderMarkdown(payload.reply_markdown || streamedText || "Done.");
          }
          log.scrollTop = log.scrollHeight;
          loadExtractorFiles({ append: false });
          if (syncToSpanner && typeof onSpannerMutatedCb === "function") {
            onSpannerMutatedCb();
          }
        } else if (evType === "error") {
          telemetry.onError(payload.error || "Unknown error");
          answerEl.innerHTML = `<span style="color:var(--rose)">Error: ${escapeHtml(payload.error || "Unknown error")}</span>`;
        }
      }
    );
  } catch (err) {
    telemetry.onError(err.message);
    answerEl.innerHTML = `<span style="color:var(--rose)">Stream error: ${escapeHtml(err.message)}</span>`;
    showToast(`Interactive extract failed: ${err.message}`, "err");
  } finally {
    telemetry.destroy();
    isExtracting = false;
    if (topBtn) topBtn.disabled = false;
  }
}

function openRawDocument(doc) {
  state.extractor.selectedItem = { kind: "raw", id: doc.relative_path, ...doc };
  renderFileList();

  document.getElementById("ext-viewer-title").textContent = doc.file_name;
  document.getElementById("ext-viewer-subtitle").textContent = `reference/raw/${doc.relative_path}`;
  const actions = document.getElementById("ext-viewer-actions");
  actions.innerHTML = `
    <a class="wb-btn wb-btn-ghost wb-btn-sm" href="${escapeHtml(doc.url)}" target="_blank" rel="noopener">Open Raw</a>
  `;

  const body = document.getElementById("ext-viewer-body");
  if (doc.file_name.toLowerCase().endsWith(".pdf")) {
    body.innerHTML = `<iframe class="wb-pdf-frame" src="${escapeHtml(doc.url)}" title="${escapeHtml(doc.file_name)}"></iframe>`;
  } else {
    body.innerHTML = `<div class="wb-welcome-card"><h3>${escapeHtml(doc.file_name)}</h3><p class="wb-muted">Office/tabular document ready for native OOXML ingestion. Click <strong>Extract + Sync (Interactive)</strong> above to extract immediately, or launch <strong>Batch Extract + Sync (Job)</strong>.</p></div>`;
  }
}

async function openOkfConcept(conceptId) {
  state.extractor.selectedItem = { kind: "okf", id: conceptId, primary_pdf_path: null };
  renderFileList();

  const body = document.getElementById("ext-viewer-body");
  body.innerHTML = `<div class="wb-empty">Loading ${escapeHtml(conceptId)}...</div>`;
  try {
    const data = await fetchJson(`/api/okf/${encodeURI(conceptId)}`);
    const primaryPdf = data.resolved_pdf_sources?.[0]?.relative_path || null;
    state.extractor.selectedItem = {
      kind: "okf",
      id: conceptId,
      primary_pdf_path: primaryPdf,
    };

    document.getElementById("ext-viewer-title").textContent = data.frontmatter?.title || conceptId;
    document.getElementById("ext-viewer-subtitle").textContent = `${conceptId}.md · ${data.size_bytes} bytes · ${data.sources?.length || 0} source(s)`;

    const tagGuess = conceptId.includes("/") ? conceptId.split("/").pop() : conceptId;
    const actions = document.getElementById("ext-viewer-actions");
    actions.innerHTML = `
      <button class="wb-btn wb-btn-ghost wb-btn-sm" id="btn-toggle-raw-md">Raw YAML</button>
      <button class="wb-btn wb-btn-secondary wb-btn-sm" id="btn-okf-sync-spanner" title="Sync existing OKF Markdown bundle to Cloud Spanner">Sync to Spanner</button>
      <button class="wb-btn wb-btn-primary wb-btn-sm" id="btn-jump-to-graph">Inspect in Graph &rarr;</button>
    `;

    let showingRaw = false;
    const renderBody = () => {
      body.innerHTML = showingRaw
        ? `<pre><code>${escapeHtml(data.raw_markdown || "")}</code></pre>`
        : renderMarkdown(data.body_markdown || data.raw_markdown || "");
    };
    renderBody();

    actions.querySelector("#btn-toggle-raw-md")?.addEventListener("click", (e) => {
      showingRaw = !showingRaw;
      e.target.textContent = showingRaw ? "Rendered View" : "Raw YAML";
      renderBody();
    });
    actions.querySelector("#btn-okf-sync-spanner")?.addEventListener("click", () => {
      if (typeof onQuickSyncSpannerCb === "function") onQuickSyncSpannerCb();
    });
    actions.querySelector("#btn-jump-to-graph")?.addEventListener("click", () => {
      if (typeof onJumpToGraphCb === "function") onJumpToGraphCb(tagGuess);
    });
  } catch (err) {
    body.innerHTML = `<div class="wb-empty">Error loading concept: ${escapeHtml(err.message)}</div>`;
  }
}

export function initExtractorTab({ onJumpToGraph, onSpannerMutated, onQuickSyncSpanner } = {}) {
  onJumpToGraphCb = onJumpToGraph || null;
  onSpannerMutatedCb = onSpannerMutated || null;
  onQuickSyncSpannerCb = onQuickSyncSpanner || null;

  document.querySelectorAll("[data-ext-kind]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-ext-kind]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.extractor.kind = btn.getAttribute("data-ext-kind") || "raw";
      state.extractor.offset = 0;
      loadExtractorFiles({ append: false });
    });
  });

  document.getElementById("ext-search-input")?.addEventListener("input", (e) => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      state.extractor.q = e.target.value.trim();
      state.extractor.offset = 0;
      loadExtractorFiles({ append: false });
    }, 280);
  });

  document.getElementById("btn-sync-gcs")?.addEventListener("click", () => syncFromGcs());

  document.getElementById("ext-load-more-btn")?.addEventListener("click", () => {
    loadExtractorFiles({ append: true });
  });

  // Zero-Enter Interactive Extract + Sync button
  document.getElementById("btn-interactive-extract-sync")?.addEventListener("click", () => {
    const targetPdf = resolveInteractiveTargetPdf();
    if (!targetPdf) {
      showToast(
        "Select a raw document on the left first for Interactive Extract + Sync, or use Batch Extract + Sync (Job) for multiple docs.",
        "err"
      );
      return;
    }
    runInteractiveExtract({
      targetPdf,
      syncToSpanner: true,
    });
  });

  document.getElementById("btn-toggle-ext-chat")?.addEventListener("click", () => {
    document.getElementById("ext-chat-drawer")?.classList.toggle("hidden");
  });
  document.getElementById("btn-close-ext-chat")?.addEventListener("click", () => {
    document.getElementById("ext-chat-drawer")?.classList.add("hidden");
  });

  document.getElementById("ext-chat-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("ext-chat-input");
    const prompt = input?.value.trim();
    if (!prompt) return;
    input.value = "";
    const targetPdf = resolveInteractiveTargetPdf();
    await runInteractiveExtract({
      prompt,
      targetPdf,
      syncToSpanner: false,
    });
  });
}
