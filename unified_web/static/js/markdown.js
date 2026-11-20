/**
 * Safe HTML escaping & lightweight Markdown renderer (zero external CDN dependencies).
 */

export function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInline(line) {
  let out = escapeHtml(line);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  out = out.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, target, label) => {
    const clean = escapeHtml(target.trim());
    const text = escapeHtml((label || target).trim());
    return `<code class="wb-wikilink" data-concept="${clean}">${text}</code>`;
  });
  return out;
}

export function renderMarkdown(mdText) {
  const lines = String(mdText || "").split("\n");
  const html = [];
  let inList = false;
  let inCode = false;
  let tableBuffer = [];

  const flushList = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  };

  const flushTable = () => {
    if (!tableBuffer.length) return;
    const rows = tableBuffer.map((r) =>
      r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim())
    );
    if (rows.length >= 2 && rows[1].every((c) => /^[-:\s]+$/.test(c))) {
      html.push("<table><thead><tr>");
      for (const h of rows[0]) html.push(`<th>${renderInline(h)}</th>`);
      html.push("</tr></thead><tbody>");
      for (const row of rows.slice(2)) {
        html.push("<tr>");
        for (const cell of row) html.push(`<td>${renderInline(cell)}</td>`);
        html.push("</tr>");
      }
      html.push("</tbody></table>");
    } else {
      for (const raw of tableBuffer) html.push(`<p>${renderInline(raw)}</p>`);
    }
    tableBuffer = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, "");
    if (line.trim().startsWith("```")) {
      flushList();
      flushTable();
      if (!inCode) {
        html.push("<pre><code>");
        inCode = true;
      } else {
        html.push("</code></pre>");
        inCode = false;
      }
      continue;
    }
    if (inCode) {
      html.push(escapeHtml(line) + "\n");
      continue;
    }
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      flushList();
      tableBuffer.push(line.trim());
      continue;
    }
    flushTable();

    if (!line.trim()) {
      flushList();
      continue;
    }
    if (line.startsWith("### ")) {
      flushList();
      html.push(`<h3>${renderInline(line.slice(4))}</h3>`);
    } else if (line.startsWith("## ")) {
      flushList();
      html.push(`<h2>${renderInline(line.slice(3))}</h2>`);
    } else if (line.startsWith("# ")) {
      flushList();
      html.push(`<h1>${renderInline(line.slice(2))}</h1>`);
    } else if (line.startsWith("> ")) {
      flushList();
      html.push(`<blockquote>${renderInline(line.slice(2))}</blockquote>`);
    } else if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${renderInline(line.replace(/^\s*[-*]\s+/, ""))}</li>`);
    } else {
      flushList();
      html.push(`<p>${renderInline(line)}</p>`);
    }
  }
  flushList();
  flushTable();
  if (inCode) html.push("</code></pre>");
  return `<div class="wb-md">${html.join("\n")}</div>`;
}
