/**
 * Clean Interactive SVG Property Graph Renderer for Spanner OkfKnowledgeGraph.
 * Zero external libraries; supports radial hop layout, click-to-focus, and pan/zoom.
 */

import { escapeHtml } from "./markdown.js";

const NODE_COLORS = {
  EQUIPMENT: { fill: "rgba(14, 165, 233, 0.25)", stroke: "#38bdf8" },
  INSTRUMENT: { fill: "rgba(52, 211, 153, 0.22)", stroke: "#34d399" },
  SOURCE_DOCUMENT: { fill: "rgba(167, 139, 250, 0.22)", stroke: "#a78bfa" },
  CONCEPT: { fill: "rgba(251, 191, 36, 0.22)", stroke: "#fbbf24" },
};

const EDGE_COLORS = {
  CONNECTS_TO: "#38bdf8",
  MONITORS_OR_TRIPS: "#34d399",
  DERIVED_FROM: "#a78bfa",
  LINKS_TO_CONCEPT: "#94a3b8",
};

export function renderInteractiveGraph(svgEl, graphData, { onNodeClick } = {}) {
  if (!svgEl) return;
  const nodes = Array.isArray(graphData?.nodes) ? graphData.nodes : [];
  const edges = Array.isArray(graphData?.edges) ? graphData.edges : [];
  const width = svgEl.clientWidth || 420;
  const height = svgEl.clientHeight || 420;
  const cx = width / 2;
  const cy = height / 2;

  if (!nodes.length) {
    svgEl.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#94a3b8" font-size="12">No graph nodes found for this selection.</text>`;
    return;
  }

  // Group nodes by hop_distance for deterministic, clutter-free concentric radial layout
  const rings = new Map();
  for (const n of nodes) {
    const hop = Math.max(0, Math.min(3, Number(n.hop_distance ?? 1)));
    if (!rings.has(hop)) rings.set(hop, []);
    rings.get(hop).push(n);
  }

  const pos = new Map();
  const maxRadius = Math.min(width, height) * 0.41;
  for (const [hop, list] of rings.entries()) {
    if (hop === 0 && list.length === 1) {
      pos.set(list[0].id, { x: cx, y: cy });
      continue;
    }
    const r = hop === 0 ? 35 : (maxRadius * hop) / Math.max(1, Math.min(3, rings.size));
    list.forEach((node, idx) => {
      const angle = (2 * Math.PI * idx) / list.length - Math.PI / 2;
      pos.set(node.id, {
        x: cx + r * Math.cos(angle),
        y: cy + r * Math.sin(angle),
      });
    });
  }

  const edgeSvg = edges
    .map((e) => {
      const a = pos.get(e.source);
      const b = pos.get(e.target);
      if (!a || !b) return "";
      const color = EDGE_COLORS[e.type] || "#64748b";
      const dashed = e.type === "DERIVED_FROM" ? 'stroke-dasharray="4 3"' : "";
      return `<line x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}" stroke="${color}" stroke-opacity="0.55" stroke-width="1.4" ${dashed} />`;
    })
    .join("");

  const nodeSvg = nodes
    .map((n) => {
      const p = pos.get(n.id);
      if (!p) return "";
      const style = NODE_COLORS[n.type] || NODE_COLORS.CONCEPT;
      const stroke = n.has_conflict ? "#fbbf24" : style.stroke;
      const isCenter = Number(n.hop_distance ?? 1) === 0;
      const radius = isCenter ? 19 : 13;
      const label = escapeHtml((n.label || n.id).slice(0, 18));
      const fullTitle = escapeHtml(`${n.label || n.id} (${n.type})${n.subtitle ? " — " + n.subtitle : ""}`);
      return `
        <g class="wb-g-node" data-node-id="${escapeHtml(n.id)}" data-node-label="${escapeHtml(n.label || n.id)}" data-node-type="${escapeHtml(n.type || "")}" style="cursor:pointer">
          <title>${fullTitle}</title>
          <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${radius}" fill="#0f172a" />
          <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${radius}" fill="${style.fill}" stroke="${stroke}" stroke-width="${isCenter ? 2.4 : 1.5}" />
          <text x="${p.x.toFixed(1)}" y="${(p.y + radius + 12).toFixed(1)}" text-anchor="middle" fill="#e2e8f0" font-size="10" font-family="JetBrains Mono, monospace">${label}</text>
        </g>
      `;
    })
    .join("");

  svgEl.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svgEl.innerHTML = `<g class="wb-g-edges">${edgeSvg}</g><g class="wb-g-nodes">${nodeSvg}</g>`;

  if (typeof onNodeClick === "function") {
    svgEl.querySelectorAll(".wb-g-node").forEach((el) => {
      el.addEventListener("click", () => {
        const label = el.getAttribute("data-node-label") || "";
        const type = el.getAttribute("data-node-type") || "";
        if (type !== "SOURCE_DOCUMENT" && label) {
          onNodeClick(label, type);
        }
      });
    });
  }
}
