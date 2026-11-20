/**
 * Tab 1: Extractor Studio (Paginated _manifest.json Explorer, Document Viewer,
 * GCS Sync & Live Streaming Extraction Assistant with Zero-Enter Extract + Sync).
 */

import { fetchJson } from "./api.js";
import { escapeHtml, renderMarkdown } from "./markdown.js";
import { showToast, state } from "./state.js";
import { createTelemetryCard } from "./telemetry-card.js";

const ACTIVE_EXTRACT_JOB_KEY = "okf_v2_active_extract_job";

let searchDebounce = null;
let onJumpToGraphCb = null;
let onSpannerMutatedCb = null;
let onQuickSyncSpannerCb = null;
let isExtracting = false;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function saveActiveJob(meta) {
  try {
    sessionStorage.setItem(ACTIVE_EXTRACT_JOB_KEY, JSON.stringify(meta));
  } catch { /* ignore storage quota/privacy errors */ }
}

function loadSavedActiveJob() {
  try {
    const raw = sessionStorage.getItem(ACTIVE_EXTRACT_JOB_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function clearActiveJob() {
  try {
    sessionStorage.removeItem(ACTIVE_EXTRACT_JOB_KEY);
  } catch { /* ignore */ }
}

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
    btn.classList.add("is-busy");
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
      btn.classList.remove("is-busy");
      btn.innerHTML = "&#x21bb;";
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

function setInteractiveLockout(active, meta = null) {
  isExtracting = Boolean(active);
  state.extractor.isRunning = isExtracting;
  state.extractor.activeJobMeta = isExtracting ? meta : null;

  const lockIds = [
    "btn-open-batch-modal",
    "btn-interactive-extract-sync",
    "btn-open-upload-modal",
    "btn-sync-gcs",
    "ext-chat-input",
    "btn-ext-chat-send",
    "model-select",
    "btn-okf-sync-spanner",
    "btn-launch-batch-extract-sync",
    "btn-job-sync",
    "btn-job-purge-modal",
  ];
  for (const id of lockIds) {
    const el = document.getElementById(id);
    if (el) el.disabled = isExtracting;
  }

  const banner = document.getElementById("ext-running-banner");
  const bannerText = document.getElementById("ext-running-banner-text");
  if (banner) {
    banner.classList.toggle("hidden", !isExtracting);
  }
  if (isExtracting && bannerText) {
    const label = meta?.targetPdf || meta?.prompt || "interactive job";
    const shortLabel = label.length > 72 ? `${label.slice(0, 69)}...` : label;
    const modelStr = meta?.model || state.selectedModels.extractor || "gemini-4-carbon";
    const syncStr = meta?.syncToSpanner ? "Extract + Sync" : "Extraction";
    bannerText.textContent = `${syncStr} running (${modelStr}): ${shortLabel} — other actions are paused until complete.`;
  }
}

async function attachToInteractiveJob({
  jobId,
  prompt,
  targetPdf = null,
  model,
  syncToSpanner = false,
  reconnected = false,
}) {
  const drawer = document.getElementById("ext-chat-drawer");
  const log = document.getElementById("ext-chat-log");
  if (drawer) drawer.classList.remove("hidden");
  if (!log) return;

  const userDiv = document.createElement("div");
  userDiv.className = "wb-msg user";
  userDiv.textContent = reconnected
    ? `[Reconnected · ${jobId}] ${prompt}`
    : prompt;
  log.appendChild(userDiv);

  const botDiv = document.createElement("div");
  botDiv.className = "wb-msg assistant";
  const telemetry = createTelemetryCard({
    model,
    modeLabel: syncToSpanner ? "Extract + Sync" : "Extractor",
  });
  const answerEl = document.createElement("div");
  answerEl.className = "wb-answer-body";
  answerEl.innerHTML = `<span class="wb-muted">${
    reconnected
      ? "Reconnected to live extraction job — streaming updates..."
      : syncToSpanner
        ? "Extracting & syncing to GCS + Spanner (timeout-resilient background stream)..."
        : "Running extraction (timeout-resilient background stream)..."
  }</span>`;
  botDiv.appendChild(telemetry.element);
  botDiv.appendChild(answerEl);
  log.appendChild(botDiv);
  log.scrollTop = log.scrollHeight;

  setInteractiveLockout(true, { jobId, prompt, targetPdf, model, syncToSpanner });

  let afterSeq = -1;
  let streamedText = "";
  let consecutiveErrors = 0;
  let doneHandled = false;

  try {
    while (true) {
      let data;
      try {
        data = await fetchJson(
          `/api/extractor/interactive/${encodeURIComponent(jobId)}/events?after_seq=${afterSeq}`
        );
        consecutiveErrors = 0;
      } catch (err) {
        if (err.status === 404) {
          clearActiveJob();
          telemetry.onError("Previous server instance recycled");
          answerEl.innerHTML = `<span class="wb-muted">The Cloud Run instance recycled while reconnecting. Click <strong>&#x21bb; Sync GCS</strong> to view any OKF files already written to GCS.</span>`;
          loadExtractorFiles({ append: false });
          break;
        }
        consecutiveErrors += 1;
        if (consecutiveErrors > 10) {
          telemetry.onError(`Lost connection after ${consecutiveErrors} retries: ${err.message}`);
          answerEl.innerHTML = `<span style="color:var(--rose)">Polling paused after repeated network errors (${escapeHtml(err.message)}). Refresh the page to auto-reconnect.</span>`;
          showToast(`Polling interrupted: ${err.message}`, "err");
          break;
        }
        await sleep(Math.min(10000, 1500 * consecutiveErrors));
        continue;
      }

      const events = data.events || [];
      for (const ev of events) {
        if (typeof ev.seq === "number") {
          afterSeq = Math.max(afterSeq, ev.seq);
        }
        const evType = ev.event;
        const payload = ev.data || {};
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
          doneHandled = true;
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
          doneHandled = true;
          telemetry.onError(payload.error || "Unknown error");
          answerEl.innerHTML = `<span style="color:var(--rose)">Error: ${escapeHtml(payload.error || "Unknown error")}</span>`;
        }
      }

      if (data.status !== "RUNNING") {
        clearActiveJob();
        if (!doneHandled) {
          if (data.status === "ERROR") {
            telemetry.onError(data.error || "Extraction failed");
            answerEl.innerHTML = `<span style="color:var(--rose)">Error: ${escapeHtml(data.error || "Extraction failed")}</span>`;
          } else {
            telemetry.onDone({ total_duration_ms: data.total_duration_ms });
            answerEl.innerHTML = renderMarkdown(data.reply_markdown || streamedText || "Done.");
            loadExtractorFiles({ append: false });
            if (syncToSpanner && typeof onSpannerMutatedCb === "function") {
              onSpannerMutatedCb();
            }
          }
        }
        break;
      }

      await sleep(1200);
    }
  } finally {
    telemetry.destroy();
    setInteractiveLockout(false);
  }
}

async function checkAndResumeInteractiveJob() {
  if (isExtracting) return;
  const saved = loadSavedActiveJob();
  if (saved?.job_id) {
    try {
      const probe = await fetchJson(
        `/api/extractor/interactive/${encodeURIComponent(saved.job_id)}/events?after_seq=-1`
      );
      if (probe && (probe.status === "RUNNING" || probe.events?.length)) {
        await attachToInteractiveJob({
          jobId: probe.job_id,
          prompt: probe.prompt || saved.prompt || "Interactive extraction",
          targetPdf: probe.target_pdf || saved.target_pdf || null,
          model: probe.model || saved.model || state.selectedModels.extractor,
          syncToSpanner: Boolean(probe.sync_to_spanner ?? saved.sync_to_spanner),
          reconnected: true,
        });
        return;
      }
    } catch {
      clearActiveJob();
    }
  }

  try {
    const activeRes = await fetchJson("/api/extractor/interactive/active");
    const active = activeRes?.active;
    if (active?.job_id) {
      saveActiveJob({
        job_id: active.job_id,
        prompt: active.prompt,
        target_pdf: active.target_pdf || null,
        model: active.model,
        sync_to_spanner: Boolean(active.sync_to_spanner),
      });
      await attachToInteractiveJob({
        jobId: active.job_id,
        prompt: active.prompt || "Interactive extraction",
        targetPdf: active.target_pdf || null,
        model: active.model || state.selectedModels.extractor,
        syncToSpanner: Boolean(active.sync_to_spanner),
        reconnected: true,
      });
    }
  } catch { /* non-fatal on startup */ }
}

export async function runInteractiveExtract({
  prompt = "",
  targetPdf = null,
  syncToSpanner = false,
  syncMode = null,
} = {}) {
  if (isExtracting) {
    showToast("An interactive extraction is already running — please wait for it to finish.", "err");
    return;
  }

  const model = state.selectedModels.extractor;
  const resolvedSyncMode =
    syncMode ||
    document.getElementById("interactive-sync-mode-select")?.value ||
    "INCREMENTAL";

  const effectivePrompt =
    prompt.trim() ||
    (targetPdf
      ? `Extract all engineering parameters, equipment tags, instrumentation, connections, and hazards from ${targetPdf} and merge-update OKF concepts.`
      : "Audit current OKF bundle status and recent extraction log.");

  try {
    const started = await fetchJson("/api/extractor/interactive/start", {
      method: "POST",
      body: JSON.stringify({
        prompt: effectivePrompt,
        mode: targetPdf ? "by_pdf" : "chat",
        target_pdf: targetPdf,
        model,
        invoke_vertex_llm: true,
        sync_to_spanner: Boolean(syncToSpanner),
        sync_mode: resolvedSyncMode,
      }),
    });
    saveActiveJob({
      job_id: started.job_id,
      prompt: effectivePrompt,
      target_pdf: targetPdf,
      model: started.model || model,
      sync_to_spanner: Boolean(syncToSpanner),
    });
    await attachToInteractiveJob({
      jobId: started.job_id,
      prompt: effectivePrompt,
      targetPdf,
      model: started.model || model,
      syncToSpanner: Boolean(syncToSpanner),
      reconnected: false,
    });
  } catch (err) {
    showToast(`Interactive extract failed to start: ${err.message}`, "err");
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
      <button class="wb-btn wb-btn-secondary wb-btn-sm" id="btn-okf-sync-spanner" title="Sync existing OKF Markdown bundle to Cloud Spanner" ${isExtracting ? "disabled" : ""}>Sync to Spanner</button>
      <button class="wb-btn wb-btn-primary wb-btn-sm" id="btn-jump-to-graph">Inspect in Graph &rarr;</button>
    `;

    const buildSourcesPanelHtml = () => {
      const rawSources = Array.isArray(data.sources) ? data.sources : [];
      const resolvedList = Array.isArray(data.resolved_pdf_sources) ? data.resolved_pdf_sources : [];
      const resolvedByName = new Map();
      for (const r of resolvedList) {
        if (r.file_name) resolvedByName.set(String(r.file_name).toLowerCase(), r);
        if (r.relative_path) resolvedByName.set(String(r.relative_path).toLowerCase(), r);
      }

      const combined = [];
      const seen = new Set();
      for (const s of rawSources) {
        const resStr = typeof s === "string" ? s : String(s?.resource || s?.file_name || s?.document || "");
        if (!resStr) continue;
        const baseName = resStr.split("/").pop();
        const key = baseName.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        const match = resolvedByName.get(resStr.toLowerCase()) || resolvedByName.get(key) || null;
        combined.push({
          label: match?.relative_path || resStr,
          fileName: match?.file_name || baseName,
          subfolder: match?.subfolder || (resStr.includes("/") ? resStr.split("/")[0] : ""),
          url: match?.url || null,
          pages: typeof s === "object" && s?.pages ? String(s.pages) : "",
          revision: typeof s === "object" && s?.revision ? String(s.revision) : "",
          role: typeof s === "object" && (s?.role || s?.source_role) ? String(s.role || s.source_role) : "",
        });
      }
      for (const r of resolvedList) {
        const key = String(r.file_name || r.relative_path || "").toLowerCase();
        if (key && !seen.has(key)) {
          seen.add(key);
          combined.push({
            label: r.relative_path || r.file_name,
            fileName: r.file_name || r.relative_path,
            subfolder: r.subfolder || "",
            url: r.url || null,
            pages: "",
            revision: "",
            role: "",
          });
        }
      }

      const rowsHtml = combined.length
        ? combined
            .map((src) => {
              const metaParts = [
                src.subfolder ? `type: ${src.subfolder}` : "",
                src.revision ? `rev: ${src.revision}` : "",
                src.pages ? `pp. ${src.pages}` : "",
              ].filter(Boolean);
              const roleUpper = src.role.toUpperCase();
              const roleBadge = roleUpper
                ? `<span class="wb-role-badge ${
                    roleUpper === "MOC_AUTHORITY"
                      ? "role-moc"
                      : roleUpper === "PENDING_REDRAFT"
                        ? "role-redraft"
                        : roleUpper === "CONFLICTING"
                          ? "role-conflict"
                          : "role-primary"
                  }">${escapeHtml(roleUpper)}</span>`
                : "";
              const openLink = src.url
                ? `<a class="wb-btn wb-btn-ghost wb-btn-sm" href="${escapeHtml(src.url)}" target="_blank" rel="noopener">Open PDF</a>`
                : "";
              return `
                <div class="wb-source-row">
                  <div class="wb-source-main">
                    <code>${escapeHtml(src.label)}</code>
                    ${roleBadge}
                    ${metaParts.length ? `<span class="wb-muted wb-xs">${escapeHtml(metaParts.join(" · "))}</span>` : ""}
                  </div>
                  ${openLink}
                </div>
              `;
            })
            .join("")
        : `<div class="wb-muted wb-xs">No PDF source links recorded in YAML frontmatter for this concept.</div>`;

      const expanded = Boolean(state.extractor.showOkfSources);
      return `
        <div class="wb-sources-card" id="okf-sources-card">
          <div class="wb-sources-head">
            <strong class="wb-xs">Referenced PDF Sources (${combined.length})</strong>
            <button type="button" class="wb-btn wb-btn-ghost wb-btn-sm" id="btn-toggle-okf-sources">
              ${expanded ? "Hide Sources" : "Show Sources"}
            </button>
          </div>
          <div class="wb-sources-list ${expanded ? "" : "hidden"}" id="okf-sources-list">
            ${rowsHtml}
          </div>
        </div>
      `;
    };

    let showingRaw = false;
    const renderBody = () => {
      const contentHtml = showingRaw
        ? `<pre><code>${escapeHtml(data.raw_markdown || "")}</code></pre>`
        : renderMarkdown(data.body_markdown || data.raw_markdown || "");
      body.innerHTML = `${buildSourcesPanelHtml()}${contentHtml}`;
      body.querySelector("#btn-toggle-okf-sources")?.addEventListener("click", (e) => {
        state.extractor.showOkfSources = !state.extractor.showOkfSources;
        const listEl = body.querySelector("#okf-sources-list");
        listEl?.classList.toggle("hidden", !state.extractor.showOkfSources);
        e.target.textContent = state.extractor.showOkfSources ? "Hide Sources" : "Show Sources";
      });
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

  let pendingInteractiveTargetPdf = null;

  function setInteractiveSyncModalOpen(open, targetPdf = null) {
    const modal = document.getElementById("interactive-sync-modal");
    const bg = document.getElementById("interactive-sync-backdrop");
    if (open) {
      pendingInteractiveTargetPdf = targetPdf;
      const tgtEl = document.getElementById("interactive-sync-target");
      const mdlEl = document.getElementById("interactive-sync-model");
      const modeSel = document.getElementById("interactive-sync-mode-select");
      if (tgtEl) tgtEl.textContent = targetPdf || "—";
      if (mdlEl) mdlEl.textContent = state.selectedModels.extractor || "gemini-4-carbon";
      if (modeSel && !modeSel.value) modeSel.value = "INCREMENTAL";
    } else {
      pendingInteractiveTargetPdf = null;
    }
    modal?.classList.toggle("hidden", !open);
    bg?.classList.toggle("hidden", !open);
  }

  // Interactive Extract + Sync button -> opens Sync Mode selector popup
  document.getElementById("btn-interactive-extract-sync")?.addEventListener("click", () => {
    if (isExtracting) {
      showToast("An interactive extraction is already running — please wait for it to finish.", "err");
      return;
    }
    const targetPdf = resolveInteractiveTargetPdf();
    if (!targetPdf) {
      showToast(
        "Select a raw document on the left first for Interactive Extract + Sync, or use Batch Extract + Sync (Job) for multiple docs.",
        "err"
      );
      return;
    }
    setInteractiveSyncModalOpen(true, targetPdf);
  });

  document.getElementById("btn-close-interactive-sync")?.addEventListener("click", () => setInteractiveSyncModalOpen(false));
  document.getElementById("btn-cancel-interactive-sync")?.addEventListener("click", () => setInteractiveSyncModalOpen(false));
  document.getElementById("interactive-sync-backdrop")?.addEventListener("click", () => setInteractiveSyncModalOpen(false));
  document.getElementById("btn-confirm-interactive-sync")?.addEventListener("click", () => {
    const targetPdf = pendingInteractiveTargetPdf || resolveInteractiveTargetPdf();
    const chosenMode = document.getElementById("interactive-sync-mode-select")?.value || "INCREMENTAL";
    setInteractiveSyncModalOpen(false);
    if (!targetPdf) return;
    runInteractiveExtract({
      targetPdf,
      syncToSpanner: true,
      syncMode: chosenMode,
    });
  });
  // Raw Document Upload to GCS Modal
  function setUploadModalOpen(open) {
    const modal = document.getElementById("upload-raw-modal");
    const bg = document.getElementById("upload-raw-backdrop");
    if (open) {
      const typeSel = document.getElementById("upload-doc-type");
      const fileInput = document.getElementById("upload-file-input");
      const overwriteCheck = document.getElementById("upload-overwrite-check");
      if (typeSel && state.extractor.subfolder) {
        typeSel.value = state.extractor.subfolder;
      }
      if (fileInput) fileInput.value = "";
      if (overwriteCheck) overwriteCheck.checked = false;
    }
    modal?.classList.toggle("hidden", !open);
    bg?.classList.toggle("hidden", !open);
  }

  document.getElementById("btn-open-upload-modal")?.addEventListener("click", () => {
    if (isExtracting) {
      showToast("An interactive extraction is currently running — please wait for it to finish.", "err");
      return;
    }
    setUploadModalOpen(true);
  });
  document.getElementById("btn-close-upload-modal")?.addEventListener("click", () => setUploadModalOpen(false));
  document.getElementById("btn-cancel-upload-modal")?.addEventListener("click", () => setUploadModalOpen(false));
  document.getElementById("upload-raw-backdrop")?.addEventListener("click", () => setUploadModalOpen(false));

  document.getElementById("btn-confirm-upload-raw")?.addEventListener("click", async () => {
    const typeSel = document.getElementById("upload-doc-type");
    const fileInput = document.getElementById("upload-file-input");
    const overwriteCheck = document.getElementById("upload-overwrite-check");
    const confirmBtn = document.getElementById("btn-confirm-upload-raw");
    const file = fileInput?.files?.[0];
    if (!file) {
      showToast("Please choose a file to upload.", "err");
      return;
    }
    const subfolder = typeSel?.value || "data_sheets";
    const fd = new FormData();
    fd.append("file", file);
    fd.append("subfolder", subfolder);
    fd.append("overwrite", overwriteCheck?.checked ? "true" : "false");

    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = "Uploading...";
    }
    try {
      const res = await fetchJson("/api/raw-docs/upload", {
        method: "POST",
        body: fd,
      });
      setUploadModalOpen(false);
      // Switch to Raw Docs view and refresh manifest/list
      state.extractor.kind = "raw";
      state.extractor.offset = 0;
      document.querySelectorAll("[data-ext-kind]").forEach((b) => {
        b.classList.toggle("active", b.getAttribute("data-ext-kind") === "raw");
      });
      await loadExtractorFiles({ append: false, forceGcs: false });
      showToast(`Uploaded ${res.relative_path} (${Math.max(1, Math.round(res.size_bytes / 1024))} KB) & refreshed GCS.`, "ok");
    } catch (err) {
      showToast(`Upload failed: ${err.message}`, "err");
    } finally {
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = "Upload to GCS";
      }
    }
  });

  document.getElementById("btn-banner-open-assistant")?.addEventListener("click", () => {
    document.getElementById("ext-chat-drawer")?.classList.remove("hidden");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      setInteractiveSyncModalOpen(false);
      setUploadModalOpen(false);
    }
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

  // Auto-reconnect to any in-flight background interactive extraction after page reload
  checkAndResumeInteractiveJob();
}
