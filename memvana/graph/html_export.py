"""Export the knowledge graph as a self-contained interactive HTML page.

No CDN or network access needed: the force layout is ~100 lines of vanilla
JS embedded alongside the graph JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from memvana.graph.model import KnowledgeGraph

_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Memvana Knowledge Graph</title>
<style>
  body { margin: 0; font-family: system-ui, sans-serif; background: #0f1117; color: #e6e6e6; }
  #bar { padding: 10px 16px; background: #171a23; display: flex; gap: 12px; align-items: center; }
  #bar input { background: #0f1117; color: #e6e6e6; border: 1px solid #333; border-radius: 6px; padding: 6px 10px; width: 240px; }
  #info { font-size: 13px; color: #9aa5ce; }
  canvas { display: block; }
  #detail { position: fixed; right: 12px; top: 60px; width: 300px; background: #171a23ee;
            border: 1px solid #333; border-radius: 10px; padding: 12px 14px; font-size: 13px;
            display: none; max-height: 70vh; overflow: auto; }
  #detail h3 { margin: 0 0 6px; font-size: 15px; }
  .rel { color: #7aa2f7; }
  .conf-inferred { color: #e0af68; }
</style>
</head>
<body>
<div id="bar">
  <strong>Memvana</strong>
  <input id="search" placeholder="Search nodes..." />
  <span id="info"></span>
</div>
<canvas id="canvas"></canvas>
<div id="detail"></div>
<script>
const GRAPH = __GRAPH_JSON__;
const COLORS = { document: "#7aa2f7", section: "#9ece6a", module: "#bb9af7",
  "class": "#f7768e", "function": "#e0af68", concept: "#73daca", url: "#565f89" };
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
let W, H;
function resize() { W = canvas.width = innerWidth; H = canvas.height = innerHeight - 52; }
resize(); addEventListener("resize", resize);

const nodes = GRAPH.nodes.map((n, i) => ({ ...n,
  x: W/2 + Math.cos(i*2.4)* (120 + i%7*40), y: H/2 + Math.sin(i*2.4)*(120 + i%5*40),
  vx: 0, vy: 0 }));
const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
const edges = GRAPH.edges.filter(e => byId[e.source] && byId[e.target]);
const degree = {};
edges.forEach(e => { degree[e.source] = (degree[e.source]||0)+1;
                     degree[e.target] = (degree[e.target]||0)+1; });
document.getElementById("info").textContent =
  nodes.length + " nodes / " + edges.length + " edges";

let selected = null, hover = null, dragging = null;
let panX = 0, panY = 0, zoom = 1;

function tick() {
  for (const n of nodes) { n.vx *= 0.85; n.vy *= 0.85; }
  for (let i = 0; i < nodes.length; i++) for (let j = i+1; j < nodes.length; j++) {
    const a = nodes[i], b = nodes[j];
    let dx = b.x - a.x, dy = b.y - a.y;
    const d2 = dx*dx + dy*dy + 0.01, f = Math.min(1200 / d2, 4);
    dx *= f; dy *= f; a.vx -= dx; a.vy -= dy; b.vx += dx; b.vy += dy;
  }
  for (const e of edges) {
    const a = byId[e.source], b = byId[e.target];
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx*dx+dy*dy) || 1;
    const f = (d - 90) * 0.002;
    a.vx += dx*f; a.vy += dy*f; b.vx -= dx*f; b.vy -= dy*f;
  }
  for (const n of nodes) {
    if (n === dragging) continue;
    n.vx += (W/2 - n.x) * 0.0005; n.vy += (H/2 - n.y) * 0.0005;
    n.x += n.vx; n.y += n.vy;
  }
}
function draw() {
  ctx.clearRect(0, 0, W, H);
  ctx.save(); ctx.translate(panX, panY); ctx.scale(zoom, zoom);
  for (const e of edges) {
    const a = byId[e.source], b = byId[e.target];
    ctx.strokeStyle = e.confidence === "inferred" ? "#e0af6833" : "#41486b66";
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  for (const n of nodes) {
    const r = 4 + Math.min(degree[n.id]||0, 12);
    ctx.fillStyle = COLORS[n.type] || "#888";
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7); ctx.fill();
    if (n === selected || n === hover) {
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke(); ctx.lineWidth = 1;
    }
    if (zoom > 0.7 || (degree[n.id]||0) > 3 || n === selected || n === hover) {
      ctx.fillStyle = "#c8c8d8"; ctx.font = "11px system-ui";
      ctx.fillText(n.label.slice(0, 28), n.x + r + 3, n.y + 3);
    }
  }
  ctx.restore();
}
function loop() { tick(); draw(); requestAnimationFrame(loop); }
loop();

function pick(mx, my) {
  const x = (mx - panX) / zoom, y = (my - panY) / zoom;
  return nodes.find(n => {
    const r = 6 + Math.min(degree[n.id]||0, 12);
    return (n.x-x)**2 + (n.y-y)**2 < r*r;
  });
}
canvas.onmousemove = e => {
  if (dragging) { dragging.x = (e.offsetX - panX)/zoom; dragging.y = (e.offsetY - panY)/zoom; return; }
  hover = pick(e.offsetX, e.offsetY);
  canvas.style.cursor = hover ? "pointer" : "default";
};
canvas.onmousedown = e => { dragging = pick(e.offsetX, e.offsetY); };
canvas.onmouseup = e => {
  if (dragging) { select(dragging); dragging = null; }
};
canvas.onwheel = e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  panX = e.offsetX - (e.offsetX - panX) * factor;
  panY = e.offsetY - (e.offsetY - panY) * factor;
  zoom *= factor;
};
function select(n) {
  selected = n;
  const box = document.getElementById("detail");
  if (!n) { box.style.display = "none"; return; }
  const related = edges.filter(e => e.source === n.id || e.target === n.id)
    .slice(0, 30).map(e => {
      const other = e.source === n.id ? byId[e.target] : byId[e.source];
      const conf = e.confidence === "inferred" ? " <span class='conf-inferred'>(inferred)</span>" : "";
      return "<div><span class='rel'>" + e.relation + "</span> " +
             other.label.slice(0, 40) + conf + "</div>";
    }).join("");
  box.innerHTML = "<h3>" + n.label + "</h3><div>" + n.type +
    (n.source ? " · " + n.source : "") + "</div>" +
    (n.detail ? "<p>" + n.detail.slice(0, 300) + "</p>" : "") +
    "<hr style='border-color:#333'>" + related;
  box.style.display = "block";
}
document.getElementById("search").oninput = e => {
  const q = e.target.value.toLowerCase();
  if (!q) return select(null);
  const found = nodes.find(n => n.label.toLowerCase().includes(q));
  if (found) select(found);
};
</script>
</body>
</html>
"""


def export_html(graph: KnowledgeGraph, output_path: Path) -> Path:
    payload = json.dumps(graph.to_dict(), ensure_ascii=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _TEMPLATE.replace("__GRAPH_JSON__", payload), encoding="utf-8"
    )
    return output_path
