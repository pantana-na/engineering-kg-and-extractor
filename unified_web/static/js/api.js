/**
 * API client helpers for Unified OKF Engineering Workbench v2.
 */

export async function fetchJson(url, options = {}) {
  const resp = await fetch(url, {
    headers: {
      "Accept": "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  let payload = null;
  try {
    payload = await resp.json();
  } catch {
    payload = { detail: await resp.text() };
  }
  if (!resp.ok) {
    const msg = payload?.detail || payload?.error || `HTTP ${resp.status}`;
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
      errText = p.detail || p.error || errText;
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
