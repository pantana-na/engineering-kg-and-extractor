/**
 * Shared Live Execution Trace & Latency Timeline Card (`telemetry-card.js`).
 *
 * Used identically in both Extractor Assistant Chat (Tab 1) and Knowledge Graph & Query Chat (Tab 2).
 * Auto-expanded while running (showing live elapsed timer, active tool/step spinner, arguments
 * snippet, and exact per-step latency in ms updated in place without duplicates) and collapsible
 * once completed.
 */

import { escapeHtml } from "./markdown.js";

function formatLatency(ms) {
  if (ms === null || ms === undefined || Number.isNaN(Number(ms))) return "...";
  const num = Number(ms);
  if (num >= 10000) return `${(num / 1000).toFixed(1)} s`;
  if (num >= 1000) return `${(num / 1000).toFixed(2)} s`;
  return `${Math.round(num)} ms`;
}

function formatArgsSnippet(args) {
  if (!args || typeof args !== "object") return "";
  const pairs = Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .slice(0, 3)
    .map(([k, v]) => {
      const sv = typeof v === "string" ? v : JSON.stringify(v);
      return `${k}=${sv.length > 48 ? sv.slice(0, 45) + "..." : sv}`;
    });
  return pairs.join(", ");
}

function statusClass(status) {
  const s = String(status || "").toUpperCase();
  if (s === "RUNNING") return "running";
  if (s === "COMPLETED" || s === "OK" || s === "PASS") return "ok";
  if (s === "DEGRADED") return "warn";
  if (s === "BLOCKED" || s === "ERROR" || s === "FAILED") return "err";
  return "idle";
}

function statusGlyph(status) {
  const s = String(status || "").toUpperCase();
  if (s === "RUNNING") return "●";
  if (s === "COMPLETED" || s === "OK" || s === "PASS") return "✓";
  if (s === "DEGRADED") return "!";
  if (s === "BLOCKED" || s === "ERROR" || s === "FAILED") return "✕";
  return "•";
}

export function createTelemetryCard({ model, modeLabel = "Agent" } = {}) {
  const details = document.createElement("details");
  details.className = "wb-telemetry wb-telemetry-live";
  details.open = true; // Auto-expanded while running

  details.innerHTML = `
    <summary class="wb-telemetry-summary">
      <span class="wb-telemetry-head-left">
        <span class="wb-status-dot running" data-tel-dot></span>
        <span class="wb-telemetry-model">${escapeHtml(model || "gemini-4")}</span>
        <span class="wb-telemetry-status" data-tel-status>Running ${escapeHtml(modeLabel)}...</span>
      </span>
      <span class="wb-telemetry-head-right">
        <span class="wb-pill wb-telemetry-timer" data-tel-timer>0.0 s</span>
      </span>
    </summary>
    <div class="wb-telemetry-steps" data-tel-steps></div>
  `;

  const dotEl = details.querySelector("[data-tel-dot]");
  const statusEl = details.querySelector("[data-tel-status]");
  const timerEl = details.querySelector("[data-tel-timer]");
  const stepsEl = details.querySelector("[data-tel-steps]");

  const rowsByKey = new Map();
  let completedTools = 0;
  let totalSteps = 0;
  let finished = false;
  const startedAt = performance.now();

  const timerHandle = setInterval(() => {
    if (finished || !timerEl) return;
    const elapsedSec = (performance.now() - startedAt) / 1000;
    timerEl.textContent = `${elapsedSec.toFixed(1)} s`;
  }, 100);

  function stopTimer() {
    finished = true;
    clearInterval(timerHandle);
  }

  function upsertRow(key, { badge, title, detail, status, durationMs }) {
    let row = rowsByKey.get(key);
    const cls = statusClass(status);
    const glyph = statusGlyph(status);
    const isRunning = String(status || "").toUpperCase() === "RUNNING";
    const latencyLabel = isRunning ? "running..." : formatLatency(durationMs);

    if (!row) {
      row = document.createElement("div");
      row.className = `wb-tel-row is-${cls}`;
      row.dataset.telKey = key;
      stepsEl.appendChild(row);
      rowsByKey.set(key, row);
      totalSteps += 1;
    } else {
      row.className = `wb-tel-row is-${cls}`;
    }

    row.innerHTML = `
      <span class="wb-tel-glyph is-${cls}">${glyph}</span>
      <div class="wb-tel-main">
        <div class="wb-tel-top">
          <span class="wb-tel-badge">${escapeHtml(badge)}</span>
          <strong class="wb-tel-title">${escapeHtml(title)}</strong>
        </div>
        ${detail ? `<div class="wb-tel-detail">${escapeHtml(detail)}</div>` : ""}
      </div>
      <span class="wb-tel-latency is-${cls}">${escapeHtml(latencyLabel)}</span>
    `;
  }

  return {
    element: details,

    onStep(payload) {
      if (!payload) return;
      // Avoid duplicate row if this step mirrors an already-tracked tool_call
      if (payload.call_index && rowsByKey.has(`tool:${payload.call_index}`)) {
        return;
      }
      const phaseStr = String(payload.phase || "STEP");
      if (phaseStr.includes("ADK TOOL") && rowsByKey.size > 0 && payload.title) {
        // Check if matching tool row already exists with same name
        for (const [k, el] of rowsByKey.entries()) {
          if (k.startsWith("tool:") && el.querySelector(".wb-tel-title")?.textContent === payload.title) {
            return;
          }
        }
      }
      const key = `step:${payload.step_id ?? payload.step_index ?? phaseStr}`;
      upsertRow(key, {
        badge: phaseStr,
        title: payload.title || phaseStr,
        detail: payload.detail || "",
        status: payload.status || "COMPLETED",
        durationMs: payload.duration_ms,
      });
      if (statusEl && !finished) {
        const active = String(payload.status || "").toUpperCase() === "RUNNING";
        statusEl.textContent = active
          ? `${payload.title || phaseStr}...`
          : `${completedTools} tool(s) · ${totalSteps} step(s)`;
      }
    },

    onToolCall(payload) {
      if (!payload) return;
      const idx = payload.call_index ?? rowsByKey.size + 1;
      const key = `tool:${idx}`;
      const prevStatus = rowsByKey.get(key)?.dataset.status;
      const curStatus = String(payload.status || "RUNNING").toUpperCase();
      if (curStatus === "COMPLETED" && prevStatus !== "COMPLETED") {
        completedTools += 1;
      }
      const argsTxt = formatArgsSnippet(payload.args);
      const summaryTxt = payload.summary || "";
      const combinedDetail =
        curStatus === "RUNNING"
          ? argsTxt ? `args: ${argsTxt}` : summaryTxt
          : [summaryTxt, argsTxt ? `(${argsTxt})` : ""].filter(Boolean).join(" ");

      upsertRow(key, {
        badge: `TOOL #${idx}`,
        title: payload.tool_name || "tool",
        detail: combinedDetail,
        status: curStatus,
        durationMs: payload.duration_ms,
      });
      const row = rowsByKey.get(key);
      if (row) row.dataset.status = curStatus;

      if (statusEl && !finished) {
        statusEl.textContent =
          curStatus === "RUNNING"
            ? `Calling ${payload.tool_name}...`
            : `${completedTools} tool call(s) completed...`;
      }
    },

    onDone(payload = {}) {
      stopTimer();
      const totalMs = payload.total_duration_ms ?? (performance.now() - startedAt);
      const toolCount = Array.isArray(payload.tool_calls) ? payload.tool_calls.length : completedTools;
      const isBlocked = Boolean(payload.blocked_by_guardrail || payload.status === "blocked");
      const hasDegraded = Array.isArray(payload.steps)
        && payload.steps.some((s) => String(s.status || "").toUpperCase() === "DEGRADED");

      if (dotEl) {
        dotEl.className = `wb-status-dot ${isBlocked ? "err" : hasDegraded ? "running" : "ok"}`;
      }
      if (statusEl) {
        statusEl.textContent = isBlocked
          ? "Blocked by Guardrail"
          : `${toolCount} tool call(s) · ${rowsByKey.size} step(s)${hasDegraded ? " (degraded sync)" : ""}`;
      }
      if (timerEl) {
        timerEl.textContent = formatLatency(totalMs);
      }
    },

    onError(message) {
      stopTimer();
      if (dotEl) dotEl.className = "wb-status-dot err";
      if (statusEl) statusEl.textContent = `Error: ${String(message || "Stream interrupted").slice(0, 80)}`;
      if (timerEl) timerEl.textContent = formatLatency(performance.now() - startedAt);
    },

    destroy: stopTimer,
  };
}
