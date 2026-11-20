/**
 * Tab 1: Extractor Studio (Paginated _manifest.json Explorer, Document Viewer & Assistant Drawer).
 */

import { fetchJson } from "./api.js";
import { escapeHtml, renderMarkdown } from "./markdown.js";
import { showToast, state } from "./state.js";

let searchDebounce = null;
let onJumpToGraphCb = null;

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

function openRawDocument(doc) {
  state.extractor.selectedItem = { kind: "raw", id: doc.relative_path, ...doc };
  renderFileList();

  document.getElementById("ext-viewer-title").textContent = doc.file_name;
  document.getElementById("ext-viewer-subtitle").textContent = `reference/raw/${doc.relative_path}`;
  const actions = document.getElementById("ext-viewer-actions");
  actions.innerHTML = `
    <button class="wb-btn wb-btn-primary wb-btn-sm" id="btn-extract-this-doc">Extract This Document</button>
    <a class="wb-btn wb-btn-ghost wb-btn-sm" href="${escapeHtml(doc.url)}" target="_blank" rel="noopener">Open Raw</a>
  `;
  actions.querySelector("#btn-extract-this-doc")?.addEventListener("click", () => {
    document.getElementById("ext-chat-drawer")?.classList.remove("hidden");
    const input = document.getElementById("ext-chat-input");
    if (input) {
      input.value = `Extract all engineering parameters, equipment tags, and hazards from ${doc.relative_path}.`;
      input.focus();
    }
  });

  const body = document.getElementById("ext-viewer-body");
  if (doc.file_name.toLowerCase().endsWith(".pdf")) {
    body.innerHTML = `<iframe class="wb-pdf-frame" src="${escapeHtml(doc.url)}" title="${escapeHtml(doc.file_name)}"></iframe>`;
  } else {
    body.innerHTML = `<div class="wb-welcome-card"><h3>${escapeHtml(doc.file_name)}</h3><p class="wb-muted">Office/tabular document ready for native OOXML ingestion. Click <strong>Extract This Document</strong> or launch a <strong>Batch Extract</strong> job.</p></div>`;
  }
}

async function openOkfConcept(conceptId) {
  state.extractor.selectedItem = { kind: "okf", id: conceptId };
  renderFileList();

  const body = document.getElementById("ext-viewer-body");
  body.innerHTML = `<div class="wb-empty">Loading ${escapeHtml(conceptId)}...</div>`;
  try {
    const data = await fetchJson(`/api/okf/${encodeURI(conceptId)}`);
    document.getElementById("ext-viewer-title").textContent = data.frontmatter?.title || conceptId;
    document.getElementById("ext-viewer-subtitle").textContent = `${conceptId}.md · ${data.size_bytes} bytes · ${data.sources?.length || 0} source(s)`;

    const tagGuess = conceptId.includes("/") ? conceptId.split("/").pop() : conceptId;
    const actions = document.getElementById("ext-viewer-actions");
    actions.innerHTML = `
      <button class="wb-btn wb-btn-secondary wb-btn-sm" id="btn-toggle-raw-md">Raw YAML</button>
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
    actions.querySelector("#btn-jump-to-graph")?.addEventListener("click", () => {
      if (typeof onJumpToGraphCb === "function") onJumpToGraphCb(tagGuess);
    });
  } catch (err) {
    body.innerHTML = `<div class="wb-empty">Error loading concept: ${escapeHtml(err.message)}</div>`;
  }
}

function appendChatMessage(role, html) {
  const log = document.getElementById("ext-chat-log");
  if (!log) return;
  const div = document.createElement("div");
  div.className = `wb-msg ${role}`;
  div.innerHTML = html;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

export function initExtractorTab({ onJumpToGraph } = {}) {
  onJumpToGraphCb = onJumpToGraph || null;

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

  document.getElementById("ext-refresh-btn")?.addEventListener("click", () => {
    state.extractor.offset = 0;
    loadExtractorFiles({ append: false, forceGcs: true });
    showToast("Refreshed manifest from GCS.", "ok");
  });

  document.getElementById("ext-load-more-btn")?.addEventListener("click", () => {
    loadExtractorFiles({ append: true });
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
    const model = state.selectedModels.extractor;
    const invokeLlm = Boolean(document.getElementById("ext-live-llm-toggle")?.checked);
    input.value = "";
    appendChatMessage("user", escapeHtml(prompt));

    try {
      const sel = state.extractor.selectedItem;
      const res = await fetchJson("/api/chat/extract", {
        method: "POST",
        body: JSON.stringify({
          prompt,
          mode: sel?.kind === "raw" ? "by_pdf" : "chat",
          target_pdf: sel?.kind === "raw" ? sel.relative_path : null,
          model,
          invoke_vertex_llm: invokeLlm,
          async_job: false,
        }),
      });
      if (res.status === "blocked") {
        appendChatMessage("assistant", `<strong style="color:var(--rose)">Blocked by Model Armor:</strong> ${escapeHtml(res.error)}`);
        return;
      }
      appendChatMessage("assistant", renderMarkdown(res.reply_markdown || "Done."));
      loadExtractorFiles({ append: false });
    } catch (err) {
      appendChatMessage("assistant", `<span style="color:var(--rose)">Error: ${escapeHtml(err.message)}</span>`);
    }
  });
}
