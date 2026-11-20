/**
 * API client helpers for Unified OKF Engineering Workbench v2.
 */

function formatApiErrorDetail(rawDetail, fallback) {
  if (!rawDetail) return fallback;
  if (typeof rawDetail === "string") return rawDetail;
  if (Array.isArray(rawDetail)) {
    const parts = rawDetail.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const loc = Array.isArray(item.loc) ? item.loc.join(".") : "";
        const msg = item.msg || item.message || JSON.stringify(item);
        return loc ? `${loc}: ${msg}` : String(msg);
      }
      return String(item);
    });
    return parts.filter(Boolean).join("; ") || fallback;
  }
  if (typeof rawDetail === "object") {
    return rawDetail.message || rawDetail.detail || rawDetail.error || JSON.stringify(rawDetail);
  }
  return String(rawDetail);
}

export async function fetchJson(url, options = {}) {
  const { headers: customHeaders, ...restOptions } = options || {};
  const isFormData = typeof FormData !== "undefined" && restOptions.body instanceof FormData;
  const mergedHeaders = {
    "Accept": "application/json",
    ...(restOptions.body && !isFormData ? { "Content-Type": "application/json" } : {}),
    ...(customHeaders || {}),
  };
  const resp = await fetch(url, {
    ...restOptions,
    headers: mergedHeaders,
  });
  let payload = null;
  try {
    payload = await resp.json();
  } catch {
    payload = { detail: await resp.text() };
  }
  if (!resp.ok) {
    const msg = formatApiErrorDetail(
      payload?.detail ?? payload?.error,
      `HTTP ${resp.status}`
    );
    const err = new Error(msg);
    err.status = resp.status;
    err.payload = payload;
    throw err;
  }
  return payload;
}

export async function streamSSE(url, body, onEvent) {
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let errText = `HTTP ${resp.status}`;
    try {
      const p = await resp.json();
      errText = formatApiErrorDetail(p?.detail ?? p?.error, errText);
    } catch { /* ignore */ }
    throw new Error(errText);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";

    for (const frame of frames) {
      let evType = "message";
      const dataLines = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) {
          evType = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }
      if (!dataLines.length) continue;
      try {
        onEvent(evType, JSON.parse(dataLines.join("\n")));
      } catch {
        onEvent(evType, { raw: dataLines.join("\n") });
      }
    }
  }
}

export function generateIdempotencyKey(prefix = "okf") {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
