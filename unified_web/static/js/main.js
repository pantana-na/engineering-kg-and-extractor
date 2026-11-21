/**
 * Main Bootstrapper for Unified OKF Engineering Knowledge Workbench v2.
 * Handles top-level tab switching, lazy tab initialization, and context-aware Gemini 4 model selection.
 */

import { fetchJson } from "./api.js";
import { initExtractorTab, loadExtractorFiles } from "./extractor-tab.js";
import { initJobsDrawer, refreshJobs, triggerPipelineJob } from "./jobs-drawer.js";
import {
  focusEquipmentInQuery,
  initQueryTab,
  loadSpannerSummary,
  renderPreBuiltPrompts,
} from "./query-tab.js";
import {
  getActiveModel,
  setActiveModel,
  setActiveTab,
  showToast,
  state,
} from "./state.js";

function syncModelSelectorUI() {
  const selectEl = document.getElementById("model-select");
  const labelEl = document.getElementById("model-context-label");
  const extPill = document.getElementById("ext-chat-model-pill");
  if (!selectEl) return;

  selectEl.innerHTML = state.allowedModels
    .map((m) => `<option value="${m.id}">${m.label}</option>`)
    .join("");
  selectEl.value = getActiveModel();

  if (labelEl) {
    labelEl.textContent = state.activeTab === "query" ? "Query Model" : "Extractor Model";
  }
  if (extPill) {
    extPill.textContent = state.selectedModels.extractor;
  }
}

function activateTab(tabName) {
  setActiveTab(tabName);
  const isQuery = state.activeTab === "query";

  document.getElementById("tab-btn-extractor")?.classList.toggle("active", !isQuery);
  document.getElementById("tab-btn-extractor")?.setAttribute("aria-selected", String(!isQuery));
  document.getElementById("tab-btn-query")?.classList.toggle("active", isQuery);
  document.getElementById("tab-btn-query")?.setAttribute("aria-selected", String(isQuery));

  document.getElementById("panel-extractor")?.classList.toggle("active", !isQuery);
  document.getElementById("panel-query")?.classList.toggle("active", isQuery);

  syncModelSelectorUI();

  // Lazy-mount data only when tab becomes active
  if (!isQuery && !state.extractor.initialized) {
    state.extractor.initialized = true;
    loadExtractorFiles({ append: false });
  }
  if (isQuery && !state.query.initialized) {
    state.query.initialized = true;
    loadSpannerSummary(false);
  }
}

async function bootstrap() {
  // Wire primary tabs
  document.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.getAttribute("data-tab")));
  });

  // Wire model selector
  document.getElementById("model-select")?.addEventListener("change", (e) => {
    setActiveModel(e.target.value);
    syncModelSelectorUI();
    showToast(
      `Switched ${state.activeTab === "query" ? "Query" : "Extractor"} model to ${e.target.value}.`,
      "ok"
    );
  });

  initExtractorTab({
    onJumpToGraph: (tag) => {
      activateTab("query");
      focusEquipmentInQuery(tag);
    },
    onSpannerMutated: () => {
      if (state.query.initialized) loadSpannerSummary(true);
    },
    onQuickSyncSpanner: () => {
      triggerPipelineJob("sync", { targetSubfolder: null });
    },
  });
  initQueryTab();
  initJobsDrawer({
    onSyncCompleted: () => {
      loadExtractorFiles({ append: false });
      if (state.query.initialized) loadSpannerSummary(true);
    },
  });

  try {
    const [modelsRes, statusRes] = await Promise.all([
      fetchJson("/api/models"),
      fetchJson("/api/status"),
    ]);
    if (Array.isArray(modelsRes.allowed_models) && modelsRes.allowed_models.length) {
      state.allowedModels = modelsRes.allowed_models;
    }
    if (modelsRes.defaults) {
      state.defaults = modelsRes.defaults;
      if (!localStorage.getItem("okf_v2_extractor_model")) {
        state.selectedModels.extractor = modelsRes.defaults.extractor;
      }
      if (!localStorage.getItem("okf_v2_query_model")) {
        state.selectedModels.query = modelsRes.defaults.query;
      }
    }
    state.status = statusRes;

    const metaEl = document.getElementById("topbar-project-meta");
    if (metaEl) {
      metaEl.textContent = `${statusRes.project_id} · ${statusRes.region} · ${statusRes.spanner_database}`;
    }
    const jobSub = document.getElementById("jobs-drawer-subtitle");
    if (jobSub && statusRes.pipeline_job?.job_name) {
      jobSub.textContent = `${statusRes.pipeline_job.job_name} (${statusRes.pipeline_job.backend})`;
    }
    renderPreBuiltPrompts(statusRes.pre_built_prompts || []);
  } catch (err) {
    showToast(`Status init notice: ${err.message}`, "err");
  }

  activateTab(state.activeTab);
  refreshJobs();

  // Pause background polling when tab hidden, resume cleanly when visible
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.jobs.drawerOpen) {
      refreshJobs();
    }
  });
}

bootstrap();
