/**
 * Cloud Run Pipeline Jobs Drawer (`okf-pipeline-job`),
 * Interactive Batch Extract + Sync Launcher Modal & Deterministic Purge HITL Modal.
 */

import { fetchJson, generateIdempotencyKey } from "./api.js";
import { escapeHtml } from "./markdown.js";
import { getActiveModel, showToast, state } from "./state.js";

let onSyncCompletedCb = null;

function setDrawerOpen(open) {
  state.jobs.drawerOpen = open;
  document.getElementById("jobs-drawer")?.classList.toggle("hidden", !open);
  document.getElementById("jobs-drawer-backdrop")?.classList.toggle("hidden", !open);
  if (open) {
    refreshJobs();
  }
}

function populateBatchScopeOptions() {
  const select = document.getElementById("batch-scope-select");
  if (!select) return;
  const subs = state.extractor.rawSubfolders || {};
  const totalRaw = Object.values(subs).reduce((acc, n) => acc + Number(n || 0), 0);
  const options = [
    `<option value="">All Documents (${totalRaw || "all"} files across all doc types)</option>`,
  ];
  for (const [sub, count] of Object.entries(subs)) {
    options.push(
      `<option value="${escapeHtml(sub)}">Doc Type: ${escapeHtml(sub)} (${count} file${Number(count) === 1 ? "" : "s"})</option>`
    );
  }
  select.innerHTML = options.join("");
  select.value = state.extractor.subfolder || "";
}

function setBatchModalOpen(open) {
  const modal = document.getElementById("batch-job-modal");
  const bg = document.getElementById("batch-modal-backdrop");
  if (open) populateBatchScopeOptions();
  modal?.classList.toggle("hidden", !open);
  bg?.classList.toggle("hidden", !open);
}

function setPurgeModalOpen(open) {
  const modal = document.getElementById("purge-modal");
  const bg = document.getElementById("purge-modal-backdrop");
  const input = document.getElementById("purge-confirm-input");
  const btn = document.getElementById("btn-confirm-purge");
  modal?.classList.toggle("hidden", !open);
  bg?.classList.toggle("hidden", !open);
  if (input) input.value = "";
  if (btn) btn.disabled = true;
  if (open) input?.focus();
}

function renderJobsList() {
  const listEl = document.getElementById("jobs-list");
  const badgeEl = document.getElementById("jobs-badge");
  const dotEl = document.getElementById("jobs-pulse-dot");
  if (!listEl) return;

  const jobs = state.jobs.items;
  const activeCount = jobs.filter((j) => j.status === "QUEUED" || j.status === "RUNNING").length;
  if (badgeEl) badgeEl.textContent = String(jobs.length);
  if (dotEl) {
    dotEl.className = "wb-status-dot " + (activeCount > 0 ? "running" : jobs[0]?.status === "FAILED" ? "err" : jobs.length ? "ok" : "idle");
  }

  if (!jobs.length) {
    listEl.innerHTML = `<div class="wb-empty">No pipeline jobs triggered in this session yet.</div>`;
    return;
  }

  listEl.innerHTML = jobs
    .map((j) => {
      const pct = Math.max(0, Math.min(100, Number(j.percent || 0)));
      const spCounts = j.spanner_counts && Object.keys(j.spanner_counts).length
        ? `<div class="wb-muted wb-xs">Spanner: ${j.spanner_counts.total_concepts ?? 0} concepts · ${j.spanner_counts.total_entities ?? 0} entities · ${j.spanner_counts.total_assertions ?? 0} facts</div>`
        : "";
      const errHtml = j.error ? `<div class="wb-xs" style="color:var(--rose)">Error: ${escapeHtml(j.error)}</div>` : "";
      return `
        <div class="wb-job-card">
          <div class="wb-item-top">
            <strong>${escapeHtml(j.job_mode.toUpperCase())} ${j.purge ? "· PURGE" : ""}</strong>
            <span class="wb-pill">${escapeHtml(j.status)}</span>
          </div>
          <div class="wb-muted wb-xs">
            <code>${escapeHtml(j.execution_id)}</code> · ${escapeHtml(j.model)} · ${escapeHtml(j.execution_backend)}
          </div>
          <div class="wb-progress-track"><div class="wb-progress-fill" style="width:${pct}%"></div></div>
          <div class="wb-xs">${escapeHtml(j.step || "")} (${pct.toFixed(0)}%)</div>
          ${spCounts}
          ${errHtml}
        </div>
      `;
    })
    .join("");
}

export async function refreshJobs() {
  if (document.hidden) return;
  try {
    const prevStatuses = new Map(state.jobs.items.map((j) => [j.execution_id, j.status]));
    const data = await fetchJson("/api/jobs");
    state.jobs.items = data.jobs || [];
    renderJobsList();

    const newlyFinished = state.jobs.items.some(
      (j) => j.status === "SUCCEEDED" && prevStatuses.get(j.execution_id) !== "SUCCEEDED"
    );
    if (newlyFinished && typeof onSyncCompletedCb === "function") {
      onSyncCompletedCb();
      showToast("Pipeline job completed — caches & UI refreshed.", "ok");
    }

    const hasActive = state.jobs.items.some((j) => j.status === "QUEUED" || j.status === "RUNNING");
    if (hasActive && !state.jobs.pollTimer) {
      state.jobs.pollTimer = setInterval(refreshJobs, 3000);
    } else if (!hasActive && state.jobs.pollTimer) {
      clearInterval(state.jobs.pollTimer);
      state.jobs.pollTimer = null;
    }
  } catch (err) {
    console.warn("Jobs poll notice:", err);
  }
}

export async function triggerPipelineJob(
  jobMode,
  { purge = false, confirmPurge = false, targetSubfolder = undefined } = {}
) {
  if (state.extractor.isRunning) {
    showToast("An interactive extraction is currently running — please wait for it to finish first.", "err");
    return;
  }
  const syncMode = document.getElementById("sync-mode-select")?.value || "FULL_MIRROR";
  const model = state.selectedModels.extractor || getActiveModel();
  const resolvedSubfolder =
    targetSubfolder !== undefined ? (targetSubfolder || null) : (state.extractor.subfolder || null);

  const headers = {
    "X-Idempotency-Key": generateIdempotencyKey(`job-${jobMode}`),
  };
  if (purge && confirmPurge) {
    headers["X-Confirm-Purge"] = "CONFIRMED";
  }

  try {
    const res = await fetchJson("/api/jobs/run", {
      method: "POST",
      headers,
      body: JSON.stringify({
        job_mode: jobMode,
        model,
        sync_mode: syncMode,
        purge,
        target_subfolder: resolvedSubfolder,
        compute_embeddings: true,
        sync_dataplex_catalog: true,
      }),
    });
    const scopeLabel = resolvedSubfolder ? `doc type '${resolvedSubfolder}'` : "all documents";
    showToast(`Dispatched ${jobMode} (${scopeLabel}) -> ${res.execution_id} via ${res.execution_backend}.`, "ok");
    setDrawerOpen(true);
    await refreshJobs();
  } catch (err) {
    showToast(`Job trigger failed: ${err.message}`, "err");
  }
}

export function initJobsDrawer({ onSyncCompleted } = {}) {
  onSyncCompletedCb = onSyncCompleted || null;

  document.getElementById("btn-open-jobs")?.addEventListener("click", () => setDrawerOpen(true));
  document.getElementById("btn-close-jobs")?.addEventListener("click", () => setDrawerOpen(false));
  document.getElementById("jobs-drawer-backdrop")?.addEventListener("click", () => setDrawerOpen(false));
  document.getElementById("btn-refresh-jobs")?.addEventListener("click", () => refreshJobs());

  // Batch Extract + Sync Interactive Launcher Modal
  document.getElementById("btn-open-batch-modal")?.addEventListener("click", () => setBatchModalOpen(true));
  document.getElementById("btn-close-batch-modal")?.addEventListener("click", () => setBatchModalOpen(false));
  document.getElementById("btn-cancel-batch-modal")?.addEventListener("click", () => setBatchModalOpen(false));
  document.getElementById("batch-modal-backdrop")?.addEventListener("click", () => setBatchModalOpen(false));

  document.getElementById("btn-launch-batch-extract-sync")?.addEventListener("click", async () => {
    const scope = document.getElementById("batch-scope-select")?.value || "";
    setBatchModalOpen(false);
    await triggerPipelineJob("extract_and_sync", { targetSubfolder: scope });
  });

  // Advanced: Sync Existing OKF -> Spanner Only
  document.getElementById("btn-job-sync")?.addEventListener("click", async () => {
    setBatchModalOpen(false);
    await triggerPipelineJob("sync", { targetSubfolder: null });
  });

  // Destructive Purge HITL Modal
  document.getElementById("btn-job-purge-modal")?.addEventListener("click", () => {
    setBatchModalOpen(false);
    setPurgeModalOpen(true);
  });
  document.getElementById("btn-cancel-purge")?.addEventListener("click", () => setPurgeModalOpen(false));
  document.getElementById("purge-modal-backdrop")?.addEventListener("click", () => setPurgeModalOpen(false));

  const confirmInput = document.getElementById("purge-confirm-input");
  const confirmBtn = document.getElementById("btn-confirm-purge");
  confirmInput?.addEventListener("input", () => {
    if (confirmBtn) confirmBtn.disabled = confirmInput.value.trim() !== "PURGE SPANNER";
  });
  confirmBtn?.addEventListener("click", async () => {
    setPurgeModalOpen(false);
    await triggerPipelineJob("sync", { purge: true, confirmPurge: true, targetSubfolder: null });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      setBatchModalOpen(false);
      setPurgeModalOpen(false);
    }
  });
}
