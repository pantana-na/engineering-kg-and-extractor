/**
 * Centralized UI state store with per-tab Gemini 4 model persistence.
 */

const STORAGE_KEYS = {
  extractorModel: "okf_v2_extractor_model",
  queryModel: "okf_v2_query_model",
  activeTab: "okf_v2_active_tab",
};

export const state = {
  activeTab: localStorage.getItem(STORAGE_KEYS.activeTab) || "extractor",
  allowedModels: [
    { id: "gemini-4-carbon", label: "Gemini 4 Carbon" },
    { id: "gemini-4-hydrogen", label: "Gemini 4 Hydrogen" },
    { id: "gemini-4-argon", label: "Gemini 4 Argon" },
    { id: "gemini-4-neon", label: "Gemini 4 Neon" },
  ],
  defaults: {
    extractor: "gemini-4-carbon",
    query: "gemini-4-hydrogen",
  },
  selectedModels: {
    extractor: localStorage.getItem(STORAGE_KEYS.extractorModel) || "gemini-4-carbon",
    query: localStorage.getItem(STORAGE_KEYS.queryModel) || "gemini-4-hydrogen",
  },
  status: null,
  extractor: {
    initialized: false,
    kind: "raw", // "raw" | "okf"
    q: "",
    subfolder: "",
    category: "",
    conflictsOnly: false,
    limit: 50,
    offset: 0,
    hasMore: false,
    syncVersion: "",
    items: [],
    selectedItem: null,
    rawSubfolders: {},
    okfCategories: {},
  },
  query: {
    initialized: false,
    sessionId: null,
    focusTag: null,
    conflictsOnly: false,
    searchQ: "",
    summary: null,
    inspectorTab: "graph",
    catalogLoaded: false,
  },
  jobs: {
    drawerOpen: false,
    items: [],
    pollTimer: null,
  },
};

export function setActiveTab(tab) {
  state.activeTab = tab === "query" ? "query" : "extractor";
  localStorage.setItem(STORAGE_KEYS.activeTab, state.activeTab);
}

export function getActiveModel() {
  return state.selectedModels[state.activeTab] || state.defaults[state.activeTab];
}

export function setActiveModel(modelId) {
  const validIds = new Set(state.allowedModels.map((m) => m.id));
  if (!validIds.has(modelId)) return;
  state.selectedModels[state.activeTab] = modelId;
  const key = state.activeTab === "query" ? STORAGE_KEYS.queryModel : STORAGE_KEYS.extractorModel;
  localStorage.setItem(key, modelId);
}

export function showToast(message, variant = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const el = document.createElement("div");
  el.className = `wb-toast ${variant}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}
