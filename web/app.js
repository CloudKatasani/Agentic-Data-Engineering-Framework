/* ADEF console - dependency-free single-page app. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const main = () => $("#main");
let CATALOG = null;
let SETTINGS = null;
let pollTimer = null;
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

// ------------------------------------------------------------------ api + ui helpers
async function api(method, path, body, raw = false) {
  const headers = {};
  const token = store.get("adef_token", "");
  if (token) headers.Authorization = `Bearer ${token}`;
  const opts = { method, headers };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(`/api${path}`, opts);
  if (r.status === 401) {
    const t = prompt("This console requires an API token (ADEF_API_TOKEN):");
    if (t) { store.set("adef_token", t); return api(method, path, body, raw); }
  }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || msg; if (j.guardrail) msg = `Guardrail: ${msg}`; } catch { /* not json */ }
    throw new Error(msg);
  }
  if (raw) return r;
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}

function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = `t ${kind}`;
  t.textContent = msg;
  $("#toast").appendChild(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3500);
}
async function guard(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(okMsg, "ok"); return r; } catch (e) { toast(e.message, "err"); throw e; }
}
function modal(html) { $("#modalBody").innerHTML = html; $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

const STATUS_BADGE = {
  pending: "", running: "b-info", "awaiting-approval": "b-warn", approved: "b-ok", done: "b-ok", completed: "b-ok",
  active: "b-info", failed: "b-bad", blocked: "b-bad", rejected: "b-bad", stale: "b-violet", "stale-upstream": "b-violet",
  pass: "b-ok", fail: "b-bad", high: "b-ok", medium: "b-warn", low: "b-bad",
};
const badge = (s, label) => `<span class="badge ${STATUS_BADGE[s] || ""}">${esc(label || s)}</span>`;
const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString() : "");
const short = (h, n = 10) => (h ? String(h).slice(0, n) : "");

async function download(path, filename) {
  const r = await guard(() => api("GET", path, undefined, true));
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename || (r.headers.get("content-disposition") || "").split("filename=")[1]?.replaceAll('"', "") || "download";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// ------------------------------------------------------------------ markdown (subset) + csv
function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])_([^_]+)_(?=[\s).,]|$)/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function md(src) {
  const lines = String(src).replace(/\r/g, "").split("\n");
  let out = "", i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (l.startsWith("```")) {
      const lang = l.slice(3).trim(); const buf = []; i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++;
      out += lang === "mermaid" ? `<pre class="code">${esc(buf.join("\n"))}</pre>` : `<pre class="code"><code>${esc(buf.join("\n"))}</code></pre>`;
      continue;
    }
    if (/^\|.*\|\s*$/.test(l) && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
      const cells = (r) => r.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
      const head = cells(l); i += 2; const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) rows.push(cells(lines[i++]));
      out += `<div class="table-wrap"><table><thead><tr>${head.map((h) => `<th>${inline(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
      continue;
    }
    const h = l.match(/^(#{1,4})\s+(.*)$/);
    if (h) { out += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; i++; continue; }
    if (/^\s*[-*]\s+/.test(l)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      out += `<ul>${items.map((x) => `<li>${inline(x)}</li>`).join("")}</ul>`; continue;
    }
    if (/^\s*\d+[.)]\s+/.test(l)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ""));
      out += `<ol>${items.map((x) => `<li>${inline(x)}</li>`).join("")}</ol>`; continue;
    }
    if (l.startsWith(">")) {
      const buf = [];
      while (i < lines.length && lines[i].startsWith(">")) buf.push(lines[i++].replace(/^>\s?/, ""));
      out += `<blockquote>${inline(buf.join(" "))}</blockquote>`; continue;
    }
    if (!l.trim()) { i++; continue; }
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(#|```|\||\s*[-*]\s|>|\s*\d+[.)]\s)/.test(lines[i])) buf.push(lines[i++]);
    if (!buf.length) { buf.push(lines[i++]); }
    out += `<p>${buf.map(inline).join("<br>")}</p>`;
  }
  return `<div class="md">${out}</div>`;
}
function parseCsv(text) {
  const rows = []; let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') q = false; else cell += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else if (c !== "\r") cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}
function renderFile(path, text) {
  if (path.endsWith(".md")) return md(text);
  if (path.endsWith(".csv")) {
    const rows = parseCsv(text);
    if (!rows.length) return '<div class="empty">empty</div>';
    return `<div class="table-wrap"><table><thead><tr>${rows[0].map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.slice(1).map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }
  if (path.endsWith(".json")) { try { text = JSON.stringify(JSON.parse(text), null, 2); } catch { /* keep raw */ } }
  return `<pre class="code">${esc(text)}</pre>`;
}

// ------------------------------------------------------------------ ER diagram (SVG)
function erSvg(model) {
  const ents = model.entities || [];
  if (!ents.length) return '<div class="empty">No entities</div>';
  const byName = Object.fromEntries(ents.map((e) => [e.name, e]));
  const level = {};
  const depth = (n, seen = new Set()) => {
    if (level[n] !== undefined) return level[n];
    if (seen.has(n)) return 0; seen.add(n);
    const parents = (byName[n]?.attributes || []).filter((a) => a.fk && a.fk.entity !== n && byName[a.fk.entity]).map((a) => a.fk.entity);
    level[n] = parents.length ? 1 + Math.max(...parents.map((p) => depth(p, seen))) : 0;
    return level[n];
  };
  ents.forEach((e) => depth(e.name));
  const W = 230, rowH = 18, headH = 30, gapX = 70, gapY = 60;
  const levels = {};
  ents.forEach((e) => (levels[level[e.name]] = levels[level[e.name]] || []).push(e));
  const pos = {}; let maxX = 0, y = 20;
  Object.keys(levels).sort((a, b) => a - b).forEach((lv) => {
    let x = 20, rowMax = 0;
    levels[lv].forEach((e) => {
      const h = headH + Math.min(e.attributes.length, 14) * rowH + 10;
      pos[e.name] = { x, y, h };
      x += W + gapX; rowMax = Math.max(rowMax, h); maxX = Math.max(maxX, x);
    });
    y += rowMax + gapY;
  });
  const color = (k) => ({ fact: "var(--accent)", dimension: "var(--ok)", reference: "var(--violet)", bridge: "var(--warn)" }[k] || "var(--muted)");
  let lines = "", boxes = "";
  ents.forEach((e) => e.attributes.forEach((a) => {
    if (!a.fk || !pos[a.fk.entity] || a.fk.entity === e.name) return;
    const f = pos[e.name], t = pos[a.fk.entity];
    const x1 = f.x + W / 2, y1 = f.y, x2 = t.x + W / 2, y2 = t.y + t.h;
    const my = (y1 + y2) / 2;
    lines += `<path d="M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}" fill="none" stroke="var(--muted)" stroke-width="1.4" marker-end="url(#one)"/>`;
    lines += `<text x="${(x1 + x2) / 2 + 4}" y="${my - 4}" font-size="10" fill="var(--muted)">${esc(a.name)}</text>`;
  }));
  ents.forEach((e) => {
    const p = pos[e.name];
    boxes += `<g><rect x="${p.x}" y="${p.y}" width="${W}" height="${p.h}" rx="8" fill="var(--panel)" stroke="${color(e.kind)}" stroke-width="1.6"/>`;
    boxes += `<rect x="${p.x}" y="${p.y}" width="${W}" height="${headH}" rx="8" fill="${color(e.kind)}" opacity=".14"/>`;
    boxes += `<text x="${p.x + 10}" y="${p.y + 19}" font-size="13" font-weight="700" fill="var(--text)">${esc(e.name)}</text>`;
    boxes += `<text x="${p.x + W - 10}" y="${p.y + 19}" font-size="10" text-anchor="end" fill="${color(e.kind)}">${esc(e.kind)}${e.history === "type2" ? " · SCD2" : ""}</text>`;
    e.attributes.slice(0, 14).forEach((a, i) => {
      const yy = p.y + headH + 14 + i * rowH;
      const key = a.pk ? "PK" : a.fk ? "FK" : "";
      const cls = a.classification === "restricted" ? "var(--bad)" : a.classification === "confidential" ? "var(--warn)" : "var(--text)";
      boxes += `<text x="${p.x + 10}" y="${yy}" font-size="10" font-weight="700" fill="var(--accent)">${key}</text>`;
      boxes += `<text x="${p.x + 32}" y="${yy}" font-size="11.5" fill="${cls}">${esc(a.name)}</text>`;
      boxes += `<text x="${p.x + W - 10}" y="${yy}" font-size="10" text-anchor="end" fill="var(--muted)">${esc(a.type)}</text>`;
    });
    if (e.attributes.length > 14) boxes += `<text x="${p.x + 32}" y="${p.y + p.h - 4}" font-size="10" fill="var(--muted)">+${e.attributes.length - 14} more</text>`;
    boxes += "</g>";
  });
  return `<svg width="${maxX}" height="${y}" viewBox="0 0 ${maxX} ${y}" role="img" aria-label="Entity relationship diagram">
    <defs><marker id="one" viewBox="0 0 10 10" refX="5" refY="10" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,10 L10,10 M5,0 L5,10" stroke="var(--muted)" stroke-width="1.5"/></marker></defs>
    ${lines}${boxes}</svg>`;
}
const erLegend = '<div class="row small muted" style="margin-top:8px"><span><b style="color:var(--accent)">■</b> fact</span><span><b style="color:var(--ok)">■</b> dimension</span><span style="color:var(--bad)">restricted attribute</span><span style="color:var(--warn)">confidential attribute</span></div>';

// ------------------------------------------------------------------ medallion flow (source -> bronze -> silver -> gold -> analytics)
function pipelineFlow(profile, counts) {
  const t = (slot) => profile?.slots?.[slot]?.tool || "-";
  const c = counts || {};
  const node = (title, sub, k, cls = "") => `<div class="fnode ${cls}"><div class="ft">${esc(title)}</div><div class="fs">${esc(sub)}</div>${c[k] ? `<div class="fc">${esc(c[k])}</div>` : ""}</div>`;
  const arrow = (label, sub) => `<div class="farrow"><div class="fl">${esc(label)}</div><div class="fs">${esc(sub)}</div><div class="fa">→</div></div>`;
  return `<div class="flow">
    ${node("Source database", t("source_database"), "source", "src")}
    ${arrow("Pipeline 1 · Ingest", t("ingestion"))}
    ${node("Bronze", `${t("table_format")} · ${t("object_storage")}`, "bronze", "bronze")}
    ${arrow("Pipeline 2 · Curate", `${t("transformation")} on ${t("lakehouse_compute")}`)}
    ${node("Silver → Gold", `${t("table_format")} · ${t("lake_catalog")}`, "gold", "gold")}
    ${arrow("Pipeline 3 · Publish", t("compute_engine"))}
    ${node("Analytics", t("compute_engine"), "serving", "serve")}
  </div>`;
}

// ------------------------------------------------------------------ router
const routes = {};
function route(name, fn) { routes[name] = fn; }
async function navigate() {
  clearInterval(pollTimer);
  main().onclick = null;
  const [, name = "dashboard", arg] = location.hash.split("/");
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === (name === "run" ? "dashboard" : name)));
  main().innerHTML = '<div class="loading">Loading…</div>';
  try { await (routes[name] || routes.dashboard)(arg ? decodeURIComponent(arg) : undefined); }
  catch (e) { main().innerHTML = `<div class="card"><div class="notice bad">${esc(e.message)}</div></div>`; }
}
window.addEventListener("hashchange", navigate);

async function loadBase() {
  [CATALOG, SETTINGS] = await Promise.all([api("GET", "/catalog"), api("GET", "/settings")]);
}
const refreshSettings = async () => (SETTINGS = await api("GET", "/settings"));
const providerById = (id) => SETTINGS.providers.find((p) => p.id === id);
const allStacks = () => [...CATALOG.presets, ...(SETTINGS.stack_profiles || [])];

// ------------------------------------------------------------------ AI team + human team
const STAGE_OUTPUT = {
  intake: "Scope brief, backlog, stack validation", requirements: "Requirements, acceptance criteria, NFRs",
  mapping: "Source-to-target mapping, gaps, quality rules", design: "Logical and physical model, cost estimate, ADRs",
  build: "Pipeline code on a feature branch, pull request", test: "Executed tests, quality evidence, reconciliation",
  release: "Release plan, rollback rehearsal, deployment", operations: "Runbooks, monitors, SLOs",
  consumption: "Semantic layer, access, data product docs", assembly: "Audit-ready delivery pack",
};
const agentShort = (a) => String(a || "").replace(/^adef-/, "");
const dur = (s) => (s < 1 ? "under 1s" : s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`);
const since = (iso) => (iso ? dur(Math.max(0, (Date.now() - new Date(iso)) / 1000)) : "");
const people = (list) => {
  const by = {};
  (list || []).forEach((w) => (by[w.name] = by[w.name] || []).push(w.role));
  return Object.entries(by).map(([n, rs]) => `<b>${esc(n)}</b> (${rs.map(esc).join(", ")})`).join(" and ");
};
// The operating model: which agent does the work at each stage, and which named human role decides.
function operatingModel() {
  const rows = CATALOG.stages.map((s, i) => {
    const roles = [...new Set(s.gates.flatMap((g) => CATALOG.gate_roles[g] || []))];
    const b = SETTINGS.agents[s.agent] || {};
    return `<tr><td><b>${i}. ${esc(s.label)}</b></td>
      <td><span class="who ai">AI</span> ${esc(agentShort(s.agent))}<div class="small muted mono">${esc(b.model || "")}</div></td>
      <td class="small">${esc(STAGE_OUTPUT[s.key] || "")}</td>
      <td>${s.gates.map((g) => `<span class="chip">${esc(g)}</span>`).join(" ") || '<span class="muted small">-</span>'}</td>
      <td>${roles.length ? `<span class="who hu">Human</span> ${roles.map((r) => esc(CATALOG.role_labels[r])).join(", ")}` : '<span class="muted small">Handed to the team</span>'}</td></tr>`;
  }).join("");
  return `<h2>How the AI team works with your team</h2>
    <div class="om-points">
      <div><b>Agents do the work.</b> One specialist agent per lifecycle stage drafts, builds, tests and documents.</div>
      <div><b>People make the decisions.</b> ${Object.keys(CATALOG.gate_labels).length} approval gates, each owned by a named role. Agents can never approve.</div>
      <div><b>Every decision is evidence.</b> Each approval is tied to the exact artifact version and kept in a tamper-evident log.</div>
    </div>
    <div class="table-wrap"><table><thead><tr><th>Stage</th><th>Who does the work</th><th>What it produces</th><th>Gate</th><th>Who decides</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
// Two swimlanes across the lifecycle: the AI team on top, the human team underneath, so the hand-offs are visible.
function teamLanes(st) {
  const rows = st.team.stages;
  const stageCells = st.stage_defs.map((s, i) => `<div class="lane-stage"><span class="muted">${i}</span> ${esc(s.label)}</div>`).join("");
  const AI_STATE = { pending: ["queued", ""], running: ["working", "live"], failed: ["stopped", "bad"], blocked: ["blocked", "bad"], rejected: ["rework needed", "bad"],
    "awaiting-approval": ["handed over", "done"], approved: ["done", "done"], done: ["done", "done"] };
  const aiCells = st.stage_defs.map((s) => {
    const ss = st.stages[s.key]; const [label, cls] = AI_STATE[ss.status] || [ss.status, ""];
    return `<div class="lane-cell ai ${cls}" title="${esc(ss.error || ss.summary || s.agent)}"><div class="nm">${esc(agentShort(s.agent))}</div>
      <div class="stt">${cls === "live" ? '<span class="pulse"></span>' : ""}${esc(label)}</div>
      ${st.context_counts?.[s.key] ? `<div class="stt ctxn" data-now="context:${esc(s.key)}" role="button" tabindex="0" title="Context attached by the team">+${st.context_counts[s.key]} context</div>` : ""}</div>`;
  }).join("");
  const huCells = st.stage_defs.map((s, i) => {
    const r = rows[i]; const states = s.gates.map((g) => st.gates_detail[g]?.state || "not-requested");
    if (!s.gates.length) return `<div class="lane-cell hu none"><div class="nm">Receives the pack</div><div class="stt">${st.status === "completed" ? "delivered" : "at the end"}</div></div>`;
    const [label, cls] = states.includes("pending") ? ["your turn", "live"] : states.includes("rejected") ? ["rejected", "bad"] : states.includes("stale") ? ["re-approve", "bad"]
      : states.every((x) => x === "approved") ? ["approved", "done"] : states.includes("approved") ? ["next gate soon", ""] : ["waits for the agent", ""];
    const roles = [...new Set(r.humans.map((h) => h.role))];
    return `<div class="lane-cell hu ${cls}" ${cls === "live" ? 'data-now="approvals" role="button" tabindex="0"' : ""} title="${esc(r.humans.map((h) => `${h.name} (${h.role})`).join(", "))}">
      <div class="nm">${roles.map(esc).join(", ")}</div>
      <div class="stt">${s.gates.map((g) => `<span class="chip ${esc(st.gates_detail[g]?.state || "")}">${esc(g)}</span>`).join("")} ${esc(label)}</div></div>`;
  }).join("");
  return `<div class="lanes-wrap"><div class="lanes">
    <div class="lane-label"></div>${stageCells}
    <div class="lane-label"><span class="who ai">AI</span>team<div class="small muted">does the work</div></div>${aiCells}
    <div class="lane-label"><span class="who hu">Human</span>team<div class="small muted">decides</div></div>${huCells}
  </div></div>`;
}
// One line that says what the run is doing right now and who it is waiting on. Shown on every tab.
function nowBar(st) {
  const n = st.now || {};
  const btn = (act, label, primary = true) => `<button class="btn ${primary ? "primary" : ""} small" data-now="${act}">${label}</button>`;
  switch (n.kind) {
    case "running": return `<div class="now ai"><span class="pulse"></span><div><b>AI team working · ${esc(n.label)}</b><div class="small">${esc(agentShort(n.agent))} on ${esc(n.model || "its model")} · ${since(n.since)} so far. No action needed; the gate opens when the agent hands over.</div></div></div>`;
    case "review": return `<div class="now hu"><div><b>Your turn · ${esc(n.gate)} ${esc(n.gate_label)}</b><div class="small">Waiting on ${people(n.waiting_on)} to review ${n.artifacts} artifacts${n.since ? ` · waiting ${since(n.since)}` : ""}. The agents are paused until then.</div></div>${btn("approvals", `Review ${esc(n.gate)}`)}</div>`;
    case "rejected": return `<div class="now bad"><div><b>${esc(n.label)} was rejected</b><div class="small">Send it back to ${esc(agentShort(n.agent))} with rework instructions, and attach any context it was missing.</div></div>${btn(`context:${esc(n.stage)}`, "Add context", false)}${btn("approvals", "Open rework")}</div>`;
    case "failed": return `<div class="now bad"><div><b>${esc(n.label)} stopped</b><div class="small">${esc(String(n.error || "").slice(0, 220))}</div></div>${btn("retry", "Retry stage")}${btn("approvals", "Details", false)}</div>`;
    case "blocked": return `<div class="now bad"><div><b>${esc(n.label)} is blocked and escalated to the human owner</b><div class="small">${esc(String(n.error || "").slice(0, 220))}</div></div>${btn("approvals", "Open")}</div>`;
    case "stale": return `<div class="now warn"><div><b>${esc(n.gate)} approval is out of date</b><div class="small">An approved artifact changed, so the approval no longer covers it. Re-request the gate.</div></div>${btn("approvals", "Open")}</div>`;
    case "finishing": return `<div class="now ai"><span class="pulse"></span><div><b>Carrying out the approved ${esc(n.gate)} action</b><div class="small">${esc(n.gate_label)}. The next stage starts when this finishes.</div></div></div>`;
    case "resume": return `<div class="now warn"><div><b>${esc(n.gate)} is approved but its follow-up work was interrupted</b><div class="small">Nothing is running. Resume to continue from ${esc(n.label)}.</div></div>${btn("resume", "Resume run")}</div>`;
    case "next": return `<div class="now warn"><div><b>Ready for ${esc(n.label)}</b><div class="small">Autopilot is off for this run, so ${esc(agentShort(n.agent))} waits for you to start it.</div></div>${btn(`context:${esc(n.stage)}`, "Add context first", false)}${btn("resume", `Start ${esc(n.label)}`)}</div>`;
    case "complete": return `<div class="now ok"><div><b>Run complete</b><div class="small">${st.team.totals.artifacts} artifacts delivered by the agents in ${dur(st.team.totals.agent_seconds)} of working time, with ${st.team.totals.decisions} human decisions.</div></div>${btn("pack", "Open delivery pack")}</div>`;
    default: return "";
  }
}
function bindNowBar(st) {
  $$("#nowBar [data-now], #stepper [data-now]").forEach((b) => (b.onclick = async () => {
    const act = b.dataset.now;
    if (act.startsWith("context:")) {
      RUN.tab = "context"; CTX.open = act.slice(8); store.set("adef_run_tab", RUN.tab); renderRunHead(st); await renderRunBody();
      $("#runBody").scrollIntoView({ behavior: "smooth", block: "start" }); return;
    }
    if (act === "approvals" || act === "pack") {
      RUN.tab = act === "pack" ? "artifacts" : "approvals";
      if (act === "pack") RUN.file = "final/delivery-pack.md";
      store.set("adef_run_tab", RUN.tab); renderRunHead(st); await renderRunBody();
      $("#runBody").scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (act === "retry") { await guard(() => api("POST", `/runs/${RUN.id}/stages/${st.now.stage}/start`), "Retrying"); refreshRun(true); }
    else if (act === "resume") { await guard(() => api("POST", `/runs/${RUN.id}/resume`), "Resumed"); refreshRun(true); }
  }));
}
function teamCard(st) {
  const t = st.team; const tot = t.totals;
  const share = tot.agent_seconds + tot.human_wait_seconds > 0 ? Math.round((100 * tot.human_wait_seconds) / (tot.agent_seconds + tot.human_wait_seconds)) : 0;
  return `<div class="grid g4">
      <div class="card kpi"><div class="l">Agent working time</div><div class="v">${dur(tot.agent_seconds)}</div><div class="small muted">${tot.artifacts} artifacts produced</div></div>
      <div class="card kpi"><div class="l">Waiting on people</div><div class="v">${dur(tot.human_wait_seconds)}</div><div class="small muted">${share}% of elapsed time so far</div></div>
      <div class="card kpi"><div class="l">Human decisions</div><div class="v">${tot.decisions}</div><div class="small muted">${tot.reviews} artifact verdicts recorded</div></div>
      <div class="card kpi"><div class="l">Agents that can approve</div><div class="v">0</div><div class="small muted">only named people decide</div></div>
    </div>
    <div class="card"><h2>AI team and human team on this run</h2><div class="table-wrap"><table><thead><tr><th>Stage</th><th>AI agent</th><th>Agent time</th><th>Human approvers</th><th>Review wait</th><th>Status</th></tr></thead><tbody>
    ${t.stages.map((r) => `<tr><td><b>${esc(r.label)}</b> ${r.gates.map((g) => `<span class="chip ${esc(st.gates_detail[g]?.state || "")}">${esc(g)}</span>`).join(" ")}</td>
      <td><span class="who ai">AI</span> ${esc(agentShort(r.agent))}<div class="small muted mono">${esc(r.model || "")}</div></td>
      <td>${r.status === "pending" || r.status === "running" ? "-" : dur(r.agent_seconds)}</td>
      <td>${r.humans.length ? `<span class="who hu">Human</span> ${people(r.humans)}` : '<span class="muted small">-</span>'}</td>
      <td>${r.human_wait_seconds ? dur(r.human_wait_seconds) : "-"}</td><td>${badge(r.status)}</td></tr>`).join("")}
    </tbody></table></div><p class="small muted">Times are measured on this run: agent time is from stage start to handover; review wait is from the approval request to the last decision.</p></div>`;
}

// ------------------------------------------------------------------ context for agents
const CTX = { data: null, open: null };
const srcLabel = (d, id) => d.sources[id]?.label || d.manual[id] || id;
const stageLabel = (k) => (k === "all" ? "Every stage" : CATALOG.stages.find((s) => s.key === k)?.label || k);
function ctxItemUse(i, stageStatus) {
  if (i.pending_rework) return badge("awaiting-approval", "not used yet · rework the stage to apply");
  if (!i.last_used) return badge("", stageStatus === "running" ? "in use" : "ready for the agent");
  return i.cited ? badge("pass", "used and cited") : badge("", "given to the agent");
}
async function renderContext(st, el) {
  const d = (CTX.data = await api("GET", `/runs/${RUN.id}/context`));
  const cur = st.now?.stage || st.stage_defs.find((s) => ["pending", "running", "rejected", "failed"].includes(st.stages[s.key].status))?.key;
  if (CTX.open === null) CTX.open = cur || "intake";
  const total = d.stages.reduce((n, s) => n + s.items.length, 0);
  el.innerHTML = `<div class="card"><div class="spread"><div><h2>Context for the agents</h2>
      <div class="small muted">Each agent works from the approved upstream artifacts plus whatever the team attaches here. Attach from an integration, upload a file or write a note, at any stage. Everything is optional, treated as reference data (never as instructions), and listed for the approver at the gate.</div></div>
      <button class="btn primary" data-ctx-add="${esc(CTX.open)}">Add context</button></div>
      <div class="small muted" style="margin-top:8px">${total} item${total === 1 ? "" : "s"} attached to this run.</div></div>
    ${d.stages.map((s) => {
      const def = st.stage_defs.find((x) => x.key === s.stage); const status = def ? st.stages[s.stage].status : "";
      const met = s.needs.filter((n) => n.met_by).length;
      return `<details class="card ctx-stage" data-stage="${esc(s.stage)}" ${CTX.open === s.stage ? "open" : ""}>
        <summary><span><b>${esc(stageLabel(s.stage))}</b>${def ? ` <span class="who ai">AI</span><span class="small">${esc(agentShort(def.agent))}</span>` : ""}
          <span class="small muted"> · ${esc(s.job)}</span></span>
          <span class="row">${s.needs.length ? `<span class="chip ${met === s.needs.length ? "approved" : ""}">${met}/${s.needs.length} covered</span>` : ""}
          <span class="chip">${s.items.length} attached</span>${status ? badge(status) : ""}</span></summary>
        ${s.needs.length ? `<div class="table-wrap" style="margin-top:10px"><table class="small"><thead><tr><th>What this agent needs</th><th>Why it matters</th><th>Status</th><th></th></tr></thead><tbody>
          ${s.needs.map((n) => `<tr><td><b>${esc(n.need)}</b><div class="muted">Usually in: ${n.sources.map((x) => esc(srcLabel(d, x))).join(", ")}</div></td><td>${esc(n.why)}</td>
            <td>${n.met_by ? badge("pass", "covered") : badge("", "not provided")}<div class="muted">${esc(n.met_by || "The agent will flag gaps as open questions.")}</div></td>
            <td><button class="btn small" data-ctx-add="${esc(s.stage)}" data-need="${esc(n.id)}" data-src="${esc(n.sources[0])}">Add</button></td></tr>`).join("")}
          </tbody></table></div>` : ""}
        ${s.items.length ? `<div class="table-wrap" style="margin-top:10px"><table class="small"><thead><tr><th>ID</th><th>Attached item</th><th>Source</th><th>By</th><th>Use</th><th></th></tr></thead><tbody>
          ${s.items.map((i) => `<tr><td class="mono">${esc(i.id)}</td><td><a href="#" data-ctx-view="${esc(i.id)}">${esc(i.title)}</a><div class="muted">${i.chars.toLocaleString()} chars${i.truncated ? " · truncated" : ""}${i.secrets_redacted ? ` · ${i.secrets_redacted} secret(s) redacted` : ""}${i.injection_findings.length ? ' · <span style="color:var(--bad)">instruction-like text flagged; passed as data only</span>' : ""}</div></td>
            <td>${esc(srcLabel(d, i.source))}</td><td>${esc(i.added_by)}<div class="muted">${fmtTime(i.added_at)}</div></td><td>${ctxItemUse(i, status)}</td>
            <td><button class="btn small" data-ctx-del="${esc(i.id)}">Remove</button></td></tr>`).join("")}</tbody></table></div>` : `<div class="small muted" style="margin-top:10px">Nothing attached${s.stage === "all" ? " for every stage" : " for this stage"} yet.</div>`}
        <div class="row" style="margin-top:10px"><button class="btn small" data-ctx-add="${esc(s.stage)}">Add context for ${esc(stageLabel(s.stage))}</button>
          ${s.items.some((i) => i.pending_rework) && ["awaiting-approval", "rejected", "failed"].includes(status) ? `<button class="btn small primary" data-ctx-rework="${esc(s.stage)}">Re-run ${esc(stageLabel(s.stage))} with the new context</button>` : ""}</div>
      </details>`;
    }).join("")}`;
  $$(".ctx-stage", el).forEach((x) => x.addEventListener("toggle", () => { if (x.open) CTX.open = x.dataset.stage; }));
  $$("[data-ctx-add]", el).forEach((b) => (b.onclick = (e) => { e.preventDefault(); addContextDialog(st, b.dataset.ctxAdd, b.dataset.need || "", b.dataset.src || ""); }));
  $$("[data-ctx-del]", el).forEach((b) => (b.onclick = async () => { await guard(() => api("DELETE", `/runs/${RUN.id}/context/${b.dataset.ctxDel}?by=${encodeURIComponent(ctxPerson(st))}`), "Removed"); renderContext(st, el); }));
  $$("[data-ctx-view]", el).forEach((a) => (a.onclick = async (e) => {
    e.preventDefault();
    const i = await api("GET", `/runs/${RUN.id}/context/${a.dataset.ctxView}`);
    modal(`<h2>${esc(i.id)} · ${esc(i.title)}</h2><div class="small muted">${esc(srcLabel(d, i.source))}${i.ref ? ` · ${esc(i.ref)}` : ""} · attached by ${esc(i.added_by)} · sha256 ${esc(short(i.sha256, 16))}</div>
      <pre class="code" style="margin-top:10px;max-height:55vh;overflow:auto;white-space:pre-wrap">${esc(i.content)}</pre><div style="margin-top:12px"><button class="btn" onclick="closeModal()">Close</button></div>`);
  }));
  $$("[data-ctx-rework]", el).forEach((b) => (b.onclick = async () => {
    const ids = d.stages.find((s) => s.stage === b.dataset.ctxRework).items.filter((i) => i.pending_rework).map((i) => i.id).join(", ");
    await guard(() => api("POST", `/runs/${RUN.id}/stages/${b.dataset.ctxRework}/rework`, { feedback: `Redo this stage using the context attached since the last run (${ids}). Cite the items you rely on.` }), "Re-running with the new context");
    refreshRun(true);
  }));
}
const ctxPerson = (st) => store.get("adef_ctx_person", "") || st.run.approvers.product_owner || "";
function addContextDialog(st, stage, need, src) {
  const d = CTX.data; const kinds = [...Object.keys(d.sources), "upload", "note"];
  let kind = kinds.includes(src) ? src : "confluence";
  const stageOpts = [...st.stage_defs.filter((s) => s.key !== "assembly").map((s) => [s.key, s.label]), ["all", "Every stage"]];
  modal(`<h2>Add context for an agent</h2>
    <div class="field-row"><div><label>For which stage</label><select id="cxStage">${stageOpts.map(([k, l]) => `<option value="${k}" ${k === stage ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
      <div><label>Attached by (named person)</label><input id="cxBy" value="${esc(ctxPerson(st))}"></div></div>
    <div class="tabs" id="cxTabs" style="margin-top:12px">${kinds.map((k) => `<div class="tab" data-k="${k}">${esc(srcLabel(d, k).replace("Uploaded file", "Upload a file").replace("Note from a person", "Write a note"))}</div>`).join("")}</div>
    <div id="cxBody"></div><div style="margin-top:14px"><button class="btn" onclick="closeModal()">Close</button></div>`);
  const body = $("#cxBody");
  const base = () => { store.set("adef_ctx_person", $("#cxBy").value.trim()); return { stage: $("#cxStage").value, added_by: $("#cxBy").value.trim(), need: $("#cxStage").value === stage ? need : "" }; };
  const done = async (item) => { need = ""; toast(`${item.id} attached for ${stageLabel(item.stage)}`, "ok"); CTX.open = item.stage; if (RUN.tab === "context") await renderContext(st, $("#runBody")); };
  const draw = () => {
    $$("#cxTabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.k === kind));
    if (kind === "upload") {
      body.innerHTML = `<p class="small muted">Text, Markdown, CSV, JSON, YAML, SQL, HTML or Word (.docx), up to 5 MB. The first 20,000 characters are given to the agent. Secrets are redacted.</p><input type="file" id="cxFile" accept=".txt,.md,.csv,.tsv,.json,.yaml,.yml,.sql,.xml,.html,.htm,.docx,.dbml,.rst,.log">`;
      $("#cxFile").onchange = async (e) => {
        const f = e.target.files[0]; if (!f) return;
        const fd = new FormData(); const b = base(); fd.append("file", f); fd.append("stage", b.stage); fd.append("added_by", b.added_by); fd.append("need", b.need);
        const item = await guard(() => api("POST", `/runs/${RUN.id}/context/upload`, fd)); await done(item); e.target.value = "";
      };
    } else if (kind === "note") {
      body.innerHTML = `<p class="small muted">Tell the agent something it could not know: a decision, a constraint, a correction.</p><label>Title</label><input id="cxTitle" placeholder="Decision from the steering meeting">
        <label>Note</label><textarea id="cxText" style="min-height:120px"></textarea><div class="row" style="margin-top:10px"><button class="btn primary" id="cxSave">Attach note</button></div>`;
      $("#cxSave").onclick = async () => { const item = await guard(() => api("POST", `/runs/${RUN.id}/context`, { ...base(), source: "note", title: $("#cxTitle").value || "Note", content: $("#cxText").value })); $("#cxText").value = ""; await done(item); };
    } else {
      const s = d.sources[kind];
      body.innerHTML = `<p class="small muted">${esc(s.label)} holds: ${esc(s.holds)}. ${s.mode === "demo" ? `<b>Demo mode</b>: sample content for this run's industry. Connect your own under <a href="#/integrations" onclick="closeModal()">Integrations</a>.` : "<b>Live</b>, read-only."}</p>
        <div class="row"><input id="cxQ" placeholder="${esc(s.query_hint)}" style="flex:1"><button class="btn" id="cxGo">Search</button></div><div id="cxRes" style="margin-top:10px"></div>`;
      const search = async () => {
        $("#cxRes").innerHTML = '<div class="muted small">Searching…</div>';
        let r;
        try { r = await api("POST", `/integrations/${kind}/search`, { query: $("#cxQ").value, domain: st.run.domain_pack, stage: $("#cxStage").value }); }
        catch (e) { $("#cxRes").innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
        const sug = new Set((r.suggested || []).map((x) => x.ref));
        const rows = [...r.results].sort((a, b) => sug.has(b.ref) - sug.has(a.ref));
        $("#cxRes").innerHTML = rows.length ? `<div class="table-wrap"><table class="small"><tbody>${rows.map((x) => `<tr><td><b>${esc(x.title)}</b> ${sug.has(x.ref) ? badge("pass", "fits this stage") : ""}<div class="muted">${esc(x.excerpt)}</div></td>
          <td style="white-space:nowrap"><button class="btn small primary" data-ref="${esc(x.ref)}">Attach</button></td></tr>`).join("")}</tbody></table></div>` : '<div class="muted small">Nothing found.</div>';
        $$("#cxRes [data-ref]").forEach((b) => (b.onclick = async () => { const item = await guard(() => api("POST", `/runs/${RUN.id}/context`, { ...base(), source: kind, ref: b.dataset.ref })); b.disabled = true; b.textContent = "Attached"; await done(item); }));
      };
      $("#cxGo").onclick = search; $("#cxQ").onkeydown = (e) => { if (e.key === "Enter") search(); };
      $("#cxStage").onchange = search; search();
    }
  };
  $$("#cxTabs .tab").forEach((t) => (t.onclick = () => { kind = t.dataset.k; draw(); }));
  draw();
}
// Settings cards for the optional context integrations (Confluence, GitHub, ServiceNow).
const INTEG_FIELDS = {
  base_url: ["Base URL", { confluence: "https://your-company.atlassian.net", github: "https://api.github.com", servicenow: "https://your-instance.service-now.com" }],
  email: ["Account email (Cloud)", {}], space: ["Space key (optional)", { confluence: "DATA" }], repo: ["Repository (owner/name)", { github: "acme/data-platform" }],
  branch: ["Branch", { github: "main" }], user: ["User name (leave empty for a bearer token)", {}],
};
async function renderIntegrationCards(el) {
  const [d, secrets] = await Promise.all([api("GET", "/context/sources"), api("GET", "/secrets")]);
  const ids = Object.keys(d.sources).filter((k) => d.sources[k].fields.length);
  el.innerHTML = `<div class="spread"><div><h2>Context integrations for the agents</h2><div class="small muted">Optional and read-only. Connect the systems where your project knowledge lives, so people can attach the right page, file or record to any stage of a run. Each one works in demo mode until you connect it.</div></div></div>
    <div class="grid g3" style="margin-top:12px">${ids.map((id) => {
      const s = d.sources[id]; const c = s.config;
      return `<div class="integ" data-integ="${id}"><div class="spread"><b>${esc(s.label)}</b>${badge(s.mode === "live" ? "pass" : "", s.mode)}</div><div class="small muted">${esc(s.holds)}</div>
        <label>Mode</label><select data-k="mode"><option value="demo" ${c.mode !== "live" ? "selected" : ""}>Demo content</option><option value="live" ${c.mode === "live" ? "selected" : ""}>Live (read-only)</option></select>
        ${s.fields.includes("deployment") ? `<label>Deployment</label><select data-k="deployment"><option value="cloud" ${c.deployment !== "server" ? "selected" : ""}>Cloud (email + API token)</option><option value="server" ${c.deployment === "server" ? "selected" : ""}>Data Center (personal access token)</option></select>` : ""}
        ${s.fields.filter((f) => INTEG_FIELDS[f]).map((f) => `<label>${INTEG_FIELDS[f][0]}</label><input data-k="${f}" value="${esc(c[f] || "")}" placeholder="${esc(INTEG_FIELDS[f][1][id] || "")}">`).join("")}
        <label>Token</label><select data-k="token_ref"><option value="${esc(c.token_ref || "")}">${c.token_ref ? `Keep ${esc(c.token_ref)}` : "Not set"}</option>${secrets.filter((x) => `secret:${x.name}` !== c.token_ref).map((x) => `<option value="secret:${esc(x.name)}">secret:${esc(x.name)}</option>`).join("")}</select>
        <input data-new-token type="password" placeholder="…or paste a new token (stored encrypted)" autocomplete="off" style="margin-top:6px">
        <div class="row" style="margin-top:10px"><button class="btn primary small" data-save>Save</button><button class="btn small" data-test>Test</button></div><div class="small" data-out style="margin-top:8px"></div></div>`;
    }).join("")}</div>
    <details style="margin-top:14px"><summary class="small"><b>What each agent needs, and where it usually lives</b></summary><div class="table-wrap" style="margin-top:8px"><table class="small"><thead><tr><th>Stage</th><th>Context the agent needs</th><th>Usual sources</th></tr></thead><tbody>
      ${Object.entries(d.stages).filter(([, v]) => v.needs.length).map(([k, v]) => v.needs.map((n, i) => `<tr>${i === 0 ? `<td rowspan="${v.needs.length}"><b>${esc(stageLabel(k))}</b><div class="muted">${esc(v.job)}</div></td>` : ""}<td>${esc(n.need)}<div class="muted">${esc(n.why)}</div></td><td>${n.sources.map((x) => esc(d.sources[x]?.label || d.manual[x] || x)).join(", ")}</td></tr>`).join("")).join("")}
    </tbody></table></div></details>`;
  $$(".integ", el).forEach((card) => {
    const id = card.dataset.integ; const out = $("[data-out]", card);
    const save = async () => {
      const cfg = Object.fromEntries($$("[data-k]", card).map((x) => [x.dataset.k, x.value]));
      const tok = $("[data-new-token]", card).value;
      if (tok) { await api("POST", "/secrets", { name: `${id}-token`, value: tok, description: `${d.sources[id].label} token` }); cfg.token_ref = `secret:${id}-token`; }
      await api("PUT", `/settings/integrations/${id}`, cfg);
    };
    $("[data-save]", card).onclick = async () => { await guard(save, `${d.sources[id].label} saved`); renderIntegrationCards(el); };
    $("[data-test]", card).onclick = async () => {
      out.textContent = "Testing…";
      try { await save(); const r = await api("POST", `/integrations/${id}/test`); out.innerHTML = r.ok ? `${badge("pass", "connected")} ${esc(r.detail || "")}` : `${badge("fail", "failed")} ${esc(r.error)}`; }
      catch (e) { out.innerHTML = `${badge("fail", "failed")} ${esc(e.message)}`; }
    };
  });
}

// ------------------------------------------------------------------ dashboard
route("dashboard", async () => {
  const runs = await api("GET", "/runs");
  const pending = runs.reduce((n, r) => n + r.pending_gates.length, 0);
  const llm = new Set(Object.values(SETTINGS.agents).map((a) => providerById(a.provider_id)?.type || "?"));
  main().innerHTML = `
    <div class="spread"><div><h1>Delivery dashboard</h1><div class="sub">An AI delivery team working alongside your people: agents build, test and deploy; named humans approve every gate.</div></div>
      <div class="row"><a class="btn primary" href="#/new">New run</a></div></div>
    <div class="grid g4">
      <div class="card kpi"><div class="l">Runs</div><div class="v">${runs.length}</div></div>
      <div class="card kpi"><div class="l">Completed</div><div class="v">${runs.filter((r) => r.status === "completed").length}</div></div>
      <div class="card kpi"><div class="l">Gates awaiting you</div><div class="v">${pending}</div></div>
      <div class="card kpi"><div class="l">Agent team</div><div class="v">${llm.size} <span class="small muted" style="font-size:13px">providers · ${new Set(Object.values(SETTINGS.agents).map((a) => a.model)).size} models</span></div><div class="small muted">${[...llm].map((t) => esc(CATALOG.provider_types[t]?.label || t)).join(" · ")}</div></div>
    </div>
    <div class="card" style="margin-top:16px">
      <h2>Runs</h2>
      ${runs.length ? `<div class="table-wrap"><table><thead><tr><th>Run</th><th>Client</th><th>Use case</th><th>Domain</th><th>Stack</th><th>Status</th><th>Current</th><th>Needs you</th><th>Updated</th></tr></thead><tbody>
      ${runs.map((r) => `<tr class="click" data-run="${esc(r.run_id)}"><td class="mono">${esc(r.run_id)}</td><td>${esc(r.client_code)}</td><td>${esc(r.use_case)}</td><td>${esc(r.domain_pack)}</td><td>${esc(r.stack)}</td><td>${badge(r.status)}</td><td>${esc(r.current || "-")}</td><td>${r.pending_gates.map((g) => `<span class="chip pending">${esc(g)}</span>`).join(" ")}</td><td class="small muted">${fmtTime(r.updated)}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">No runs yet. <a href="#/new">Start one</a> - the offline Demo Simulator needs no API key.</div>`}
    </div>
    <div class="card" style="margin-top:16px">${operatingModel()}</div>
    <div class="card" style="margin-top:16px" id="gettingStarted"></div>`;
  const stt = await api("GET", "/status");
  const live = stt.agents_with_live_model;
  const check = (ok, title, text, link, linkText) => `<div class="gs ${ok ? "ok" : ""}"><div class="gi">${ok ? "✓" : "•"}</div><div><b>${title}</b><div class="small muted">${text}</div><a href="${link}" class="small">${linkText} →</a></div></div>`;
  $("#gettingStarted").innerHTML = `<h2>Getting started</h2><div class="gs-grid">
    ${check(live > 0, "Model keys", live ? `${live}/${stt.agents_total} agents on live models${stt.keys_from_environment.length ? ` · keys from environment: ${esc(stt.keys_from_environment.join(", "))}` : ""}` : "No keys yet: agents run on the Demo Simulator. Start with ANTHROPIC_API_KEY=… ./run.sh or add a key in the console.", "#/providers", "Providers & API keys")}
    ${check(true, "Agent team", `Preset: ${esc(CATALOG.team_presets[stt.team_preset]?.label || stt.team_preset || "custom")}${stt.bound_providers_without_key.length ? ` · ${stt.bound_providers_without_key.length} providers without a key${stt.demo_fallback ? " (simulated)" : ""}` : ""}`, "#/agents", "Agents & models")}
    ${check(stt.sources > 0, "Source database", `${stt.sources} available, including synthetic SQLite sources for every industry. Oracle and Db2 can be connected.`, "#/integrations", "Source databases")}
    ${check(true, "Technology stack", "Six reference stacks: Oracle/Db2 → S3, ADLS, GCS or OneLake (Iceberg/Delta) → Snowflake, Databricks, BigQuery, Redshift or Fabric, plus a Local lakehouse that really runs.", "#/stacks", "Technology stacks")}
  </div>`;
  $$("tr[data-run]").forEach((tr) => tr.addEventListener("click", () => (location.hash = `#/run/${tr.dataset.run}`)));
});

// ------------------------------------------------------------------ new run wizard
const WZ = { step: 0, data: null };
function wizardDefaults() {
  const meta = store.get("adef_pending_metadata", null);
  return {
    client_code: "ACME-ENERGY", domain_pack: "utilities", use_case: "", request: "", req_source: "jira",
    jql: SETTINGS.jira.default_jql && SETTINGS.jira.mode !== "demo" ? SETTINGS.jira.default_jql : "project = UTIL",
    jira_issues: [], selected_keys: [], documents: "", stack_id: "example-a", source_metadata: meta,
    approvers: { ...SETTINGS.approver_defaults }, compute_cost_cap: 500, autopilot: true, source_id: "synthetic-utilities",
  };
}
const DOMAIN_PROJECT = { utilities: "UTIL", telco: "TEL", "financial-services": "FIN", retail: "RET" };
const SAMPLE = {
  jira: (dom) => `${dom}/jira/${DOMAIN_PROJECT[dom]}-jira-export.csv`,
  catalog: (dom) => `${dom}/source-metadata/${dom}-source-catalog.csv`,
};
// Upload a bundled demo file to an import endpoint exactly as if the user had picked it.
async function importDemoFile(path, endpoint) {
  const r = await api("GET", `/demo-files/file?path=${encodeURIComponent(path)}`, undefined, true);
  const fd = new FormData();
  fd.append("file", new Blob([await r.text()], { type: "text/plain" }), path.split("/").pop());
  return api("POST", endpoint, fd);
}
async function uploadFile(file, endpoint) { const fd = new FormData(); fd.append("file", file); return api("POST", endpoint, fd); }
route("new", async () => {
  WZ.sources = await api("GET", "/sources");
  WZ.ready = await api("GET", "/providers/readiness");
  WZ.data = WZ.data || wizardDefaults();
  WZ.step = 0;
  renderWizard();
});
function renderWizard() {
  const d = WZ.data;
  const steps = ["Client & domain", "Requirements source", "Technology stack", "Source metadata", "Approvers & budget", "Review & launch"];
  const body = [wzClient, wzReqs, wzStack, wzMeta, wzApprovers, wzReview][WZ.step](d);
  main().innerHTML = `<h1>New delivery run</h1><div class="sub">One run delivers one thin use-case slice for one client. Nothing risky happens without a named human approver.</div>
    <div class="wizard-steps">${steps.map((s, i) => `<span class="ws ${i === WZ.step ? "active" : i < WZ.step ? "done" : ""}" data-i="${i}">${i + 1}. ${s}</span>`).join("")}</div>
    <div class="card">${body}</div>
    <div class="spread" style="margin-top:14px"><button class="btn" id="wzBack" ${WZ.step === 0 ? "disabled" : ""}>Back</button>
      ${WZ.step < steps.length - 1 ? '<button class="btn primary" id="wzNext">Next</button>' : '<button class="btn primary" id="wzLaunch">Launch run</button>'}</div>`;
  $$(".ws").forEach((el) => el.addEventListener("click", () => { collect(); WZ.step = +el.dataset.i; renderWizard(); }));
  $("#wzBack").onclick = () => { collect(); WZ.step--; renderWizard(); };
  if ($("#wzNext")) $("#wzNext").onclick = () => { collect(); WZ.step++; renderWizard(); };
  if ($("#wzLaunch")) $("#wzLaunch").onclick = launch;
  bindWizard();
}
function collect() {
  const d = WZ.data;
  $$("[data-f]").forEach((el) => {
    const k = el.dataset.f;
    if (k.startsWith("appr.")) d.approvers[k.slice(5)] = el.value;
    else if (el.type === "checkbox") d[k] = el.checked;
    else d[k] = el.value;
  });
  const sel = $$("[data-issue]:checked").map((x) => x.dataset.issue);
  if ($$("[data-issue]").length) d.selected_keys = sel;
}
function wzClient(d) {
  return `<div class="field-row"><div><label>Client code (isolation boundary)</label><input data-f="client_code" value="${esc(d.client_code)}"></div>
    <div><label>Use case (one sentence, optional)</label><input data-f="use_case" value="${esc(d.use_case)}" placeholder="Defaults to the domain's reference use case"></div></div>
    <label>Domain Pack (industry vocabulary, classification and controls)</label>
    <div class="option-cards">${CATALOG.domain_packs.map((p) => `<div class="option ${p.pack_id === d.domain_pack ? "sel" : ""}" data-domain="${esc(p.pack_id)}"><div class="t">${esc(p.pack_id)}</div><div class="small muted">${esc(p.typical_use_cases.slice(0, 2).join(" · "))}</div><div style="margin-top:6px">${badge("pending", p.status)}</div></div>`).join("")}</div>`;
}
function wzReqs(d) {
  return `<div class="row">${["jira", "text", "both"].map((m) => `<label style="display:flex;gap:6px;align-items:center;margin:0;font-size:13px;color:var(--text)"><input type="radio" name="rs" value="${m}" ${d.req_source === m ? "checked" : ""} style="width:auto"> ${{ jira: "Read from Jira", text: "Describe the request", both: "Both" }[m]}</label>`).join("")}</div>
    <div ${d.req_source === "text" ? 'style="display:none"' : ""}>
      <label>JQL ${SETTINGS.jira.mode === "demo" ? '<span class="badge b-info">demo Jira</span>' : `<span class="badge b-ok">${esc(SETTINGS.jira.base_url)}</span>`}</label>
      <div class="row"><input data-f="jql" value="${esc(d.jql)}" style="flex:1"><button class="btn" id="jqlRun">Fetch issues</button></div>
      <label>…or upload a Jira export (CSV "all fields" or JSON search response)</label>
      <div class="row"><input type="file" id="jiraFile" accept=".csv,.json" style="max-width:360px"><button class="btn" id="jiraSample">Use sample export (${esc(DOMAIN_PROJECT[d.domain_pack])})</button></div>
      <div id="issues" style="margin-top:10px">${issuesTable(d)}</div>
    </div>
    <div ${d.req_source === "jira" ? 'style="display:none"' : ""}>
      <label>Business request</label><textarea data-f="request" placeholder="Who needs what, why, and how you will know it worked">${esc(d.request)}</textarea>
      <label>Supporting documents (paste text, optional)</label><textarea data-f="documents">${esc(d.documents)}</textarea>
    </div>
    <p class="small muted">Ticket and document text is treated as untrusted data: it is scanned for embedded instructions and credentials and never executed. Never paste passwords or keys - they are rejected.</p>`;
}
function issuesTable(d) {
  if (!d.jira_issues.length) return '<div class="muted small">No issues fetched yet.</div>';
  return `<div class="table-wrap"><table><thead><tr><th></th><th>Key</th><th>Type</th><th>Summary</th><th>Acceptance criteria</th><th>Findings</th></tr></thead><tbody>
    ${d.jira_issues.map((i) => `<tr><td><input type="checkbox" data-issue="${esc(i.key)}" ${d.selected_keys.includes(i.key) ? "checked" : ""} style="width:auto"></td><td class="mono">${esc(i.key)}</td><td>${esc(i.type)}</td><td>${esc(i.summary)}</td><td class="small">${esc((i.acceptance_criteria || []).join(" | "))}</td><td>${i.untrusted_findings?.injection?.length ? badge("fail", "instruction-like text") : ""}</td></tr>`).join("")}
  </tbody></table></div>`;
}
function wzStack(d) {
  const stacksList = allStacks();
  const cur = stacksList.find((s) => s.profile_id === d.stack_id) || stacksList[0];
  const srcs = (WZ.sources || []).filter((x) => !x.built_in || x.pack === d.domain_pack);
  if (!srcs.find((x) => x.id === d.source_id)) d.source_id = `synthetic-${d.domain_pack}`;
  return `<div class="option-cards">${stacksList.map((s) => `<div class="option ${s.profile_id === d.stack_id ? "sel" : ""}" data-stack="${esc(s.profile_id)}"><div class="t">${esc(s.label || s.profile_id)}</div><div class="small muted">${esc(s.description || "")}</div>${CATALOG.preset_pipelines[s.profile_id]?.local ? '<div style="margin-top:6px"><span class="badge b-ok">runs locally</span></div>' : ""}</div>`).join("")}</div>
    <h3>The three pipelines</h3>${pipelineFlow(cur)}
    <label>Source database for Pipeline 1</label><select data-f="source_id">${srcs.map((x) => `<option value="${esc(x.id)}" ${x.id === d.source_id ? "selected" : ""}>${esc(x.label || x.id)}</option>`).join("")}</select>
    <p class="small muted">The Test stage rehearses all three pipelines against this database for real. With the Local lakehouse stack, the G6a/G6b releases also run them. Add Oracle or Db2 connections on <a href="#/integrations">Integrations</a>.</p>
    <h3>Bound tools - ${esc(cur.label || cur.profile_id)}</h3><div class="slot-grid">${CATALOG.slots.map((sl) => `<div class="slot"><div class="name">${esc(sl.slot)}</div><div>${esc(cur.slots[sl.slot]?.tool || "-")}</div></div>`).join("")}</div>
    <p class="small muted">Build your own on <a href="#/stacks">Technology stacks</a>. The logical design never names a product; technology is bound in Design step B, so switching stack means switching profile.</p>`;
}
function wzMeta(d) {
  const m = d.source_metadata;
  return `<p class="muted">Optional: import a data catalog or data-modelling export (CSV dictionary, ADEF/JSON model, DBML, or CREATE TABLE DDL from erwin, ER/Studio, SqlDBM, PowerDesigner, Collibra, Purview, Alation…). The Mapping agent reconciles every source against it.</p>
    <div class="row"><input type="file" id="metaFile" accept=".csv,.json,.dbml,.sql,.ddl,.txt" style="max-width:420px"><button class="btn" id="metaSample">Use sample source catalog (${esc(d.domain_pack)})</button></div>
    <div id="metaPreview" style="margin-top:12px">${m ? metaSummary(m) : '<div class="muted small">No metadata attached.</div>'}</div>`;
}
function metaSummary(m) {
  const inj = m.untrusted_content_findings?.injection?.length || 0;
  return `<div class="notice">${esc(m.source_file)}: ${m.stats.tables} tables, ${m.stats.columns} columns${inj ? ` · <b>${inj} instruction-like findings</b>` : ""} <button class="btn small" id="metaClear">Remove</button></div>
    <div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>Table</th><th>Columns</th></tr></thead><tbody>${m.tables.slice(0, 12).map((t) => `<tr><td class="mono">${esc((t.schema ? t.schema + "." : "") + t.name)}</td><td class="small">${esc(t.columns.map((c) => c.name).join(", "))}</td></tr>`).join("")}</tbody></table></div>`;
}
function wzApprovers(d) {
  return `<p class="muted">Named humans per role (approval matrix). One person may hold several roles in a demo; an agent never holds one.</p>
    <div class="field-row">${Object.entries(CATALOG.role_labels).map(([k, v]) => `<div><label>${esc(v)}</label><input data-f="appr.${k}" value="${esc(d.approvers[k] || "")}"></div>`).join("")}</div>
    <div class="field-row"><div><label>Compute cost cap (currency, 0 = every paid action needs approval)</label><input type="number" data-f="compute_cost_cap" value="${esc(d.compute_cost_cap)}"></div>
    <div><label>Autopilot</label><label style="display:flex;gap:8px;align-items:center;color:var(--text);font-weight:400"><input type="checkbox" data-f="autopilot" ${d.autopilot ? "checked" : ""} style="width:auto"> Start the next stage automatically after each approved gate</label></div></div>`;
}
function wzReview(d) {
  const stack = allStacks().find((s) => s.profile_id === d.stack_id);
  d.agent_bindings = d.agent_bindings || {};
  const fallback = SETTINGS.runtime?.simulate_unavailable_providers !== false;
  const rows = CATALOG.agents.map((a) => {
    const team = SETTINGS.agents[a.name]; const b = { ...team, ...(d.agent_bindings[a.name] || {}) };
    const changed = !!d.agent_bindings[a.name]; const ok = b.provider_id === "demo" || (WZ.ready || {})[b.provider_id];
    const models = (CATALOG.provider_types[providerById(b.provider_id)?.type]?.models || []).map((m) => m.id).concat(store.get(`adef_models_${b.provider_id}`, []));
    const stage = CATALOG.stages.filter((s) => s.agent === a.name).map((s) => s.label).join(", ");
    return `<tr data-agent="${esc(a.name)}"><td><b>${esc(agentShort(a.name))}</b>${changed ? ' <span class="chip pending">this run only</span>' : ""}<div class="small muted">${esc(stage)}</div></td>
      <td><select data-b="provider_id">${SETTINGS.providers.map((p) => `<option value="${esc(p.id)}" ${p.id === b.provider_id ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select></td>
      <td><input data-b="model" value="${esc(b.model)}" list="wz-dl-${esc(a.name)}"><datalist id="wz-dl-${esc(a.name)}">${models.map((m) => `<option value="${esc(m)}">`).join("")}</datalist></td>
      <td><select data-b="effort">${CATALOG.effort_levels.map((e) => `<option ${e === b.effort ? "selected" : ""}>${e}</option>`).join("")}</select></td>
      <td>${b.provider_id === "demo" ? badge("", "offline") : ok ? badge("pass", providerById(b.provider_id)?.api_key_ref ? "key configured" : "local endpoint, no key needed") : badge(fallback ? "awaiting-approval" : "fail", fallback ? "no key - simulated" : "no key - stage will fail")}</td></tr>`;
  }).join("");
  const n = Object.keys(d.agent_bindings).length;
  return `<div class="kv"><div class="k">Client</div><div>${esc(d.client_code)}</div><div class="k">Domain</div><div>${esc(d.domain_pack)}</div>
    <div class="k">Stack</div><div>${esc(stack?.label || d.stack_id)}</div><div class="k">Requirements</div><div>${d.req_source !== "text" ? `${d.selected_keys.length} Jira issues` : ""} ${d.request ? "· request text" : ""}</div>
    <div class="k">Metadata</div><div>${d.source_metadata ? esc(d.source_metadata.source_file) : "none"}</div><div class="k">Cost cap</div><div>${esc(d.compute_cost_cap)}</div></div>
    <div class="spread" style="margin-top:14px"><h3 style="margin:0">Agent team and models for this run</h3>${n ? `<button class="btn small" id="wzResetTeam">Reset to team defaults (${n} changed)</button>` : ""}</div>
    <p class="small muted">Change the provider, model or effort of any agent for this run only. The saved team on <a href="#/agents">Agents &amp; models</a> is not changed.</p>
    <div class="table-wrap"><table id="wzTeam"><thead><tr><th style="width:24%">Agent</th><th>Provider</th><th>Model</th><th>Effort</th><th>Key</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function bindWizard() {
  const d = WZ.data;
  $$("#wzTeam [data-b]").forEach((el) => (el.onchange = () => {
    const agent = el.closest("tr").dataset.agent; const team = SETTINGS.agents[agent];
    const b = { provider_id: team.provider_id, model: team.model, effort: team.effort, ...(d.agent_bindings[agent] || {}) };
    b[el.dataset.b] = el.value.trim();
    if (el.dataset.b === "provider_id") {   // a model from another provider would not exist there: pick that provider's first model
      const p = providerById(b.provider_id);
      b.model = b.provider_id === team.provider_id ? team.model : (CATALOG.provider_types[p?.type]?.models || [])[0]?.id || "";
    }
    if (b.provider_id === team.provider_id && b.model === team.model && b.effort === team.effort) delete d.agent_bindings[agent];
    else d.agent_bindings[agent] = b;
    collect(); renderWizard();
  }));
  if ($("#wzResetTeam")) $("#wzResetTeam").onclick = () => { d.agent_bindings = {}; collect(); renderWizard(); };
  $$("[data-domain]").forEach((el) => el.addEventListener("click", () => {
    d.domain_pack = el.dataset.domain;
    if (SETTINGS.jira.mode === "demo") { d.jql = `project = ${DOMAIN_PROJECT[d.domain_pack]}`; d.jira_issues = []; d.selected_keys = []; }
    collect(); renderWizard();
  }));
  $$("[data-stack]").forEach((el) => el.addEventListener("click", () => { collect(); d.stack_id = el.dataset.stack; renderWizard(); }));
  $$("input[name=rs]").forEach((el) => el.addEventListener("change", () => { collect(); d.req_source = el.value; renderWizard(); }));
  if ($("#jqlRun")) $("#jqlRun").onclick = async () => {
    collect();
    d.jira_issues = await guard(() => api("POST", "/jira/search", { jql: d.jql, max_results: 50 }));
    d.selected_keys = d.jira_issues.map((i) => i.key);
    $("#issues").innerHTML = issuesTable(d);
  };
  const setIssues = (issues) => { d.jira_issues = issues; d.selected_keys = issues.map((i) => i.key); $("#issues").innerHTML = issuesTable(d); toast(`${issues.length} issues loaded`, "ok"); };
  if ($("#jiraFile")) $("#jiraFile").onchange = async (e) => setIssues(await guard(() => uploadFile(e.target.files[0], "/jira/import")));
  if ($("#jiraSample")) $("#jiraSample").onclick = async () => setIssues(await guard(() => importDemoFile(SAMPLE.jira(d.domain_pack), "/jira/import")));
  const setMeta = (m) => { d.source_metadata = m; delete d.source_metadata.logical_model; $("#metaPreview").innerHTML = metaSummary(m); bindWizard(); };
  if ($("#metaFile")) $("#metaFile").onchange = async (e) => setMeta(await guard(() => uploadFile(e.target.files[0], "/metadata/import")));
  if ($("#metaSample")) $("#metaSample").onclick = async () => setMeta(await guard(() => importDemoFile(SAMPLE.catalog(d.domain_pack), "/metadata/import")));
  if ($("#metaClear")) $("#metaClear").onclick = () => { d.source_metadata = null; store.set("adef_pending_metadata", null); renderWizard(); };
}
async function launch() {
  collect();
  const d = WZ.data;
  const issues = d.req_source === "text" ? [] : d.jira_issues.filter((i) => d.selected_keys.includes(i.key));
  if (d.req_source !== "text" && !issues.length && !d.request) { toast("Fetch and select Jira issues, or describe the request.", "err"); return; }
  const noModel = Object.entries(d.agent_bindings || {}).filter(([, b]) => !b.model).map(([a]) => agentShort(a));
  if (noModel.length) { toast(`Choose a model for: ${noModel.join(", ")}`, "err"); return; }
  const src = (WZ.sources || []).find((x) => x.id === d.source_id) || { type: "sqlite-local", pack: d.domain_pack };
  const source_connection = Object.fromEntries(Object.entries(src).filter(([k]) => !["label", "built_in"].includes(k)));
  const body = { source_connection, client_code: d.client_code, domain_pack: d.domain_pack, use_case: d.use_case || undefined,
    request: d.req_source === "jira" ? "" : d.request, documents: d.req_source === "jira" ? "" : d.documents,
    jira_issues: issues, stack_profile: allStacks().find((s) => s.profile_id === d.stack_id),
    source_metadata: d.source_metadata, approvers: d.approvers, compute_cost_cap: +d.compute_cost_cap, autopilot: d.autopilot, agent_bindings: d.agent_bindings || {} };
  const r = await guard(() => api("POST", "/runs", body), "Run started");
  store.set("adef_pending_metadata", null);
  WZ.data = null;
  location.hash = `#/run/${r.run_id}`;
}

// ------------------------------------------------------------------ run detail
const RUN = { id: null, tab: "approvals", eventsNext: 0, file: null, status: null };
route("run", async (rid) => {
  RUN.id = rid; RUN.eventsNext = 0; RUN.file = null;
  RUN.tab = store.get("adef_run_tab", "approvals");
  main().innerHTML = `<div id="runHead"></div><div id="stepper"></div><div id="nowBar"></div>
    <div class="run-layout"><div><div class="tabs" id="runTabs"></div><div id="runBody"></div></div>
    <div class="card"><div class="spread"><h2>Agent activity</h2><span class="badge b-info" id="liveBadge">live</span></div><div class="feed" id="feed"></div></div></div>`;
  await refreshRun(true);
  pollTimer = setInterval(() => refreshRun(false), 1500);
});
async function refreshRun(first) {
  const st = await api("GET", `/runs/${RUN.id}`);
  const changed = JSON.stringify(st.stages) + JSON.stringify(st.gates_detail) !== JSON.stringify(RUN.status?.stages) + JSON.stringify(RUN.status?.gates_detail);
  RUN.status = st;
  renderRunHead(st);
  const ev = await api("GET", `/runs/${RUN.id}/events?after=${RUN.eventsNext}`);
  if (ev.events.length) {
    RUN.eventsNext = ev.next;
    const feed = $("#feed");
    feed.insertAdjacentHTML("afterbegin", ev.events.reverse().map((e) => `<div class="e k-${esc(e.kind)}"><div class="ts">${new Date(e.ts).toLocaleTimeString()} · ${esc(e.kind)}</div>${esc(e.text)}</div>`).join(""));
  }
  if (first || changed) renderRunBody();
  $("#liveBadge").textContent = st.status === "completed" ? "complete" : "live";
}
function renderRunHead(st) {
  const r = st.run;
  $("#runHead").innerHTML = `<div class="spread"><div><h1>${esc(r.run_id)} · ${esc(r.use_case)}</h1>
    <div class="sub">${esc(r.client_code)} · domain <b>${esc(r.domain_pack)}</b> · stack <b>${esc(st.stack.label || st.stack.profile_id)}</b> · ${badge(st.status)}</div></div>
    <div class="row"><button class="btn" id="bundleBtn">Download run bundle</button><button class="btn" id="integrityBtn">Verify audit logs</button></div></div>`;
  $("#bundleBtn").onclick = () => download(`/runs/${RUN.id}/bundle.zip`, `${RUN.id}.zip`);
  $("#integrityBtn").onclick = async () => {
    const r2 = await guard(() => api("GET", `/runs/${RUN.id}/integrity`));
    modal(`<h2>Append-only log integrity</h2><p class="muted">Each entry carries the hash of the previous one; editing any past entry breaks the chain.</p><table>${r2.logs.map((l) => `<tr><td class="mono">${esc(l.log)}.jsonl</td><td>${l.ok ? badge("pass", `intact · ${l.entries} entries`) : badge("fail", `broken at entry ${l.broken_at}`)}</td></tr>`).join("")}</table><div style="margin-top:14px"><button class="btn" onclick="closeModal()">Close</button></div>`);
  };
  $("#stepper").innerHTML = teamLanes(st);
  $("#nowBar").innerHTML = nowBar(st); bindNowBar(st);
  const tabs = [["approvals", "Approvals"], ["context", "Context"], ["lakehouse", "Lakehouse"], ["artifacts", "Artifacts"], ["model", "Data model & exports"], ["code", "Code"], ["handoffs", "Handoffs"], ["audit", "Audit logs"], ["metrics", "Team & cost"]];
  $("#runTabs").innerHTML = tabs.map(([k, l]) => `<div class="tab ${RUN.tab === k ? "active" : ""}" data-tab="${k}">${l}</div>`).join("");
  $$("#runTabs .tab").forEach((t) => (t.onclick = () => { RUN.tab = t.dataset.tab; store.set("adef_run_tab", RUN.tab); renderRunHead(st); renderRunBody(); }));
}
async function renderRunBody() {
  const st = RUN.status; const el = $("#runBody");
  if (RUN.tab === "approvals") return renderApprovals(st, el);
  if (RUN.tab === "context") return renderContext(st, el);
  if (RUN.tab === "artifacts") return renderArtifacts(el);
  if (RUN.tab === "model") return renderRunModel(el);
  if (RUN.tab === "code") return renderCode(el);
  if (RUN.tab === "handoffs") return renderHandoffs(el);
  if (RUN.tab === "audit") return renderAudit(el);
  if (RUN.tab === "metrics") return renderMetrics(st, el);
  if (RUN.tab === "lakehouse") return renderLakehouse(st, el);
}
function renderApprovals(st, el) {
  const blocks = [];
  st.stage_defs.forEach((s) => {
    const ss = st.stages[s.key];
    if (["failed", "blocked", "rejected"].includes(ss.status)) {
      blocks.push(`<div class="card gate-card rejected"><div class="spread"><h2>${esc(s.label)} · ${badge(ss.status)}</h2></div>
        <div class="notice bad" style="white-space:pre-line">${esc(ss.error || "")}</div>
        <label>Rework instructions for ${esc(s.agent)}</label><textarea id="fb-${s.key}" placeholder="What exactly must change (artifact, section, defect)">${esc(reworkPrefill(ss.error))}</textarea>
        <div class="row" style="margin-top:8px"><button class="btn primary" data-rework="${s.key}">Send back for rework</button><button class="btn" data-retry="${s.key}">Retry as-is</button></div></div>`);
    }
  });
  const gates = Object.entries(st.gates_detail).filter(([, g]) => g.state !== "not-requested");
  const order = { pending: 0, stale: 1, rejected: 2, approved: 3, expired: 4 };
  gates.sort((a, b) => (order[a[1].state] ?? 9) - (order[b[1].state] ?? 9) || b[0].localeCompare(a[0]));
  gates.forEach(([g, gd]) => blocks.push(gateCard(st, g, gd)));
  const running = st.stage_defs.filter((s) => st.stages[s.key].status === "running");
  if (running.length && !blocks.length) blocks.push(`<div class="empty">${running.map((s) => `${esc(s.label)} is in progress. Its approval gate appears here when ${esc(agentShort(s.agent))} hands over.`).join("<br>")}</div>`);
  el.innerHTML = blocks.join("") || '<div class="empty">No gates requested yet.</div>';
  $$("[data-rework]").forEach((b) => (b.onclick = () => guard(() => api("POST", `/runs/${RUN.id}/stages/${b.dataset.rework}/rework`, { feedback: $(`#fb-${b.dataset.rework}`).value }), "Sent back for rework")));
  $$("[data-retry]").forEach((b) => (b.onclick = () => guard(() => api("POST", `/runs/${RUN.id}/stages/${b.dataset.retry}/start`), "Retrying")));
  $$("[data-decide]").forEach((b) => (b.onclick = async () => {
    const [gate, role, decision] = b.dataset.decide.split("|");
    const comment = $(`#c-${gate}`).value;
    if (decision === "rejected" && !comment) { toast("A rejection needs the exact artifact, section and defect.", "err"); return; }
    const cond = ($(`#k-${gate}`)?.value || "").split("\n").map((x) => x.trim()).filter(Boolean);
    await guard(() => api("POST", `/runs/${RUN.id}/gates/${gate}/decision`, { approver: $(`#a-${gate}-${role}`).value, role, decision: cond.length && decision === "approved" ? "approved-with-conditions" : decision, comment, conditions: cond }), `${gate} ${decision}`);
    refreshRun(true);
  }));
  $$("[data-av]").forEach((b) => (b.onclick = () => setVerdict(b.closest("tr"), b.dataset.av)));
  $$("[data-allok]").forEach((b) => (b.onclick = () => $$(`#rv-${b.dataset.allok} tr[data-path]`).forEach((tr) => setVerdict(tr, "approved"))));
  $$("[data-review]").forEach((b) => (b.onclick = async () => {
    const gate = b.dataset.review; const roles = b.dataset.roles.split(",");
    const rows = $$(`#rv-${gate} tr[data-path]`);
    const reviews = rows.map((tr) => ({ path: tr.dataset.path, decision: tr.dataset.verdict || "", comment: tr.querySelector("input").value.trim() }));
    const todo = reviews.filter((r) => !r.decision);
    if (todo.length) { toast(`Approve or reject every artifact first (${todo.length} not reviewed).`, "err"); return; }
    const noReason = reviews.filter((r) => r.decision === "rejected" && r.comment.length < 5);
    if (noReason.length) { toast(`Give a reason for each rejected artifact: ${noReason.map((r) => r.path).join(", ")}`, "err"); return; }
    const cond = ($(`#k-${gate}`)?.value || "").split("\n").map((x) => x.trim()).filter(Boolean);
    const nRej = reviews.filter((r) => r.decision === "rejected").length;
    await guard(() => api("POST", `/runs/${RUN.id}/gates/${gate}/review`, { approver: b.dataset.approver, roles, reviews, conditions: cond }),
      nRej ? `${gate} rejected (${nRej} artifact${nRej > 1 ? "s" : ""})` : `${gate} artifacts approved`);
    refreshRun(true);
  }));
  $$("[data-gate-ctx]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); RUN.tab = "context"; CTX.open = a.dataset.gateCtx; store.set("adef_run_tab", RUN.tab); renderRunHead(st); renderRunBody(); }));
  $$("[data-rereq]").forEach((b) => (b.onclick = () => guard(() => api("POST", `/runs/${RUN.id}/gates/${b.dataset.rereq}/rerequest`), "Gate re-opened").then(() => refreshRun(true))));
  $$("[data-open]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); RUN.tab = "artifacts"; RUN.file = a.dataset.open; renderRunHead(st); renderRunBody(); }));
  if ($("#openPack")) $("#openPack").onclick = (e) => { e.preventDefault(); RUN.tab = "artifacts"; RUN.file = "final/delivery-pack.md"; renderRunHead(st); renderRunBody(); };
}
function reworkPrefill(err) {
  const lines = String(err || "").split("\n").filter((l) => l.startsWith("- "));
  return lines.length ? `Fix these rejected artifacts:\n${lines.join("\n")}` : "";
}
function setVerdict(tr, v) {
  tr.dataset.verdict = v;
  tr.querySelectorAll("[data-av]").forEach((x) => x.classList.toggle("on", x.dataset.av === v));
  const inp = tr.querySelector("input");
  inp.placeholder = v === "rejected" ? "Required: section and defect" : "Optional note";
  inp.classList.toggle("need", v === "rejected");
  if (v === "rejected") inp.focus();
}
function gateContext(st, g, arts) {
  const stage = st.stage_defs.find((s) => s.gates.includes(g));
  const pack = arts.map(([p]) => p).find((p) => p.endsWith("/context-pack.md"));
  const n = st.context_counts?.[stage.key] || 0;
  return `${pack ? `The agent was given ${n} item${n === 1 ? "" : "s"} attached by the team: <a href="#" data-open="${esc(pack)}">see what it knew</a>.` : "Upstream artifacts only; nothing extra was attached."}
    <a href="#" data-gate-ctx="${esc(stage.key)}">Missing something? Add context and re-run</a>`;
}
function gateCard(st, g, gd) {
  const req = gd.request || {};
  const roles = req.required_roles || [];
  const pending = gd.state === "pending";
  const decided = Object.fromEntries((gd.decisions || []).map((d) => [d.role_key, d]));
  const reviews = gd.artifact_reviews || {};
  const roleRows = roles.map((r) => {
    const d = decided[r];
    return `<div class="role-row"><div><b>${esc(st.role_labels[r])}</b><div class="small muted">named approver</div></div>
      <div>${esc(st.run.approvers[r] || "-")}</div>
      <div class="row">${d ? badge(d.decision.startsWith("approved") ? "approved" : "rejected", `${d.decision} · ${short(d.approval_id, 8)}`) : pending ? badge("awaiting-approval", "awaiting review") : ""}</div></div>`;
  }).join("");
  // One submit per named person, covering every pending role that person holds.
  const byPerson = {};
  roles.filter((r) => !decided[r]).forEach((r) => { const who = st.run.approvers[r] || ""; (byPerson[who] = byPerson[who] || []).push(r); });
  const submit = pending ? Object.entries(byPerson).map(([who, rs]) =>
    `<button class="btn primary small" data-review="${g}" data-approver="${esc(who)}" data-roles="${rs.join(",")}">Submit review as ${esc(who || "?")} (${rs.map((r) => esc(st.role_labels[r])).join(", ")})</button>`).join("") : "";
  const arts = Object.entries(req.artifacts || {});
  const prior = (p) => (reviews[p] || []).map((v) => `<span class="badge ${v.decision === "approved" ? "b-ok" : "b-bad"}" title="${esc(v.approver)} · ${esc(v.timestamp)}${v.comment ? ` · ${esc(v.comment)}` : ""}">${v.decision === "approved" ? "✓" : "✗"} ${esc(v.role)}</span>`).join(" ");
  const artRows = arts.map(([p, h]) => {
    const rej = (reviews[p] || []).filter((v) => v.decision === "rejected" && v.comment);
    return `<tr data-path="${esc(p)}"><td><a href="#" data-open="${esc(p)}">${esc(p)}</a><div class="hash">${short(h, 16)}</div>
      ${rej.map((v) => `<div class="small" style="color:var(--bad)">${esc(v.role)}: ${esc(v.comment)}</div>`).join("")}</td>
      <td style="white-space:nowrap">${prior(p) || (pending ? "" : '<span class="muted small">gate-level decision</span>')}</td>
      ${pending ? `<td style="white-space:nowrap"><span class="seg"><button class="btn small" data-av="approved">Approve</button><button class="btn small" data-av="rejected">Reject</button></span></td>
      <td style="min-width:200px"><input placeholder="Optional note"></td>` : ""}</tr>`;
  }).join("");
  return `<div class="card gate-card ${esc(gd.state)}">
    <div class="spread"><div><h2>${esc(g)} · ${esc(st.gate_labels[g])}</h2><div class="small muted">${esc(req.request_id)} · ${esc(req.action_class)} · expires ${esc(req.expires)}</div></div>${badge(gd.state === "pending" ? "awaiting-approval" : gd.state, gd.state)}</div>
    ${gd.state === "stale" ? `<div class="notice warn" style="margin:10px 0">Approval drift: ${esc(gd.changed_artifacts.join(", "))} changed after the request. The approval no longer covers these hashes. <button class="btn small" data-rereq="${g}">Re-request ${g}</button></div>` : ""}
    <p>${esc(req.summary)}</p>
    <div class="kv"><div class="k">Risk</div><div>${esc(req.risk)}</div><div class="k">Cost</div><div>${esc(req.cost)}</div><div class="k">Rollback</div><div>${esc(req.rollback)}</div>
    <div class="k">Options</div><div>${(req.options || []).map(esc).join(" · ")}</div>
    <div class="k">Evidence</div><div>${(req.evidence || []).map((p) => `<a href="#" data-open="${esc(p)}">${esc(p)}</a>`).join("<br>") || "-"}</div>
    <div class="k">Bundle hash</div><div class="hash">${esc(req.artifact_sha256)}</div>
    <div class="k">Agent context</div><div>${gateContext(st, g, arts)}</div></div>
    <div class="spread" style="margin-top:12px"><h3 style="margin:0">Artifacts for review (${arts.length})</h3>${pending ? `<button class="btn small" data-allok="${g}">Approve all</button>` : ""}</div>
    ${pending ? '<div class="small muted">Approve or reject each artifact. Any rejected artifact rejects the gate, and its reason goes back to the agent as rework instructions. Each verdict is bound to the artifact\'s hash.</div>' : ""}
    <div class="table-wrap"><table class="small review-table" id="rv-${g}"><thead><tr><th>Artifact</th><th>Reviews</th>${pending ? "<th>Your verdict</th><th>Reason / note</th>" : ""}</tr></thead><tbody>${artRows}</tbody></table></div>
    ${gd.conditions?.length ? `<div class="notice" style="margin-top:8px">Binding conditions: ${gd.conditions.map(esc).join("; ")}</div>` : ""}
    ${pending ? `<label>Conditions (optional, one per line - become binding constraints downstream if approved)</label><textarea id="k-${g}" style="min-height:44px"></textarea>
      <div class="row" style="margin-top:8px;flex-wrap:wrap">${submit}</div>` : ""}
    <div style="margin-top:8px">${roleRows}</div></div>`;
}
async function renderArtifacts(el) {
  const files = await api("GET", `/runs/${RUN.id}/files`);
  const groups = {};
  files.forEach((f) => { const top = f.path.split("/")[0]; (groups[top] = groups[top] || []).push(f); });
  el.innerHTML = `<div class="files"><div class="tree">${Object.entries(groups).map(([g, fs]) => `<div class="d">${esc(g)}</div>${fs.map((f) => `<div class="f ${f.path === RUN.file ? "active" : ""}" data-f="${esc(f.path)}" title="${esc(f.path)}">${esc(f.path.split("/").slice(1).join("/") || f.path)}</div>`).join("")}`).join("")}</div>
    <div class="viewer card" id="viewer"><div class="empty">Select an artifact</div></div></div>`;
  $$(".tree .f").forEach((f) => (f.onclick = () => { RUN.file = f.dataset.f; $$(".tree .f").forEach((x) => x.classList.toggle("active", x === f)); showFile(); }));
  if (RUN.file) showFile();
}
async function showFile() {
  const path = RUN.file;
  const text = await api("GET", `/runs/${RUN.id}/file?path=${encodeURIComponent(path)}`);
  const f = (await api("GET", `/runs/${RUN.id}/files`)).find((x) => x.path === path);
  const editable = /^(0\d-|final\/)/.test(path) && !/\.(jsonl)$/.test(path);
  $("#viewer").innerHTML = `<div class="spread"><div><b class="mono">${esc(path)}</b><div class="hash">sha256 ${esc(f?.sha256 || "")}</div></div>
    <div class="row">${editable ? '<button class="btn small" id="editBtn">Edit as human</button>' : ""}<button class="btn small" id="rawBtn">Raw</button></div></div><hr><div id="fileBody">${renderFile(path, text)}</div>`;
  $("#rawBtn").onclick = () => ($("#fileBody").innerHTML = `<pre class="code">${esc(text)}</pre>`);
  if ($("#editBtn")) $("#editBtn").onclick = () => {
    $("#fileBody").innerHTML = `<div class="notice warn">Editing an approved artifact invalidates its approval (hash-bound). The gate must then be re-requested.</div>
      <textarea id="editArea" style="min-height:360px;font-family:var(--mono);font-size:12.5px;margin-top:8px">${esc(text)}</textarea>
      <div class="row" style="margin-top:8px"><button class="btn primary" id="saveEdit">Save</button><button class="btn" id="cancelEdit">Cancel</button></div>`;
    $("#cancelEdit").onclick = showFile;
    $("#saveEdit").onclick = async () => {
      const r = await guard(() => api("PUT", `/runs/${RUN.id}/file`, { path, content: $("#editArea").value, editor: RUN.status.run.approvers.product_owner }));
      toast(r.stale_gates.length ? `Saved. Approval now stale: ${r.stale_gates.join(", ")}` : "Saved", r.stale_gates.length ? "err" : "ok");
      refreshRun(true);
    };
  };
}
async function renderRunModel(el) {
  let model;
  try { model = await api("GET", `/runs/${RUN.id}/model`); } catch { el.innerHTML = '<div class="empty">The logical model appears after the Design stage.</div>'; return; }
  const dialects = CATALOG.dialects;
  el.innerHTML = `<div class="card"><div class="spread"><h2>Logical data model · ${esc(model.name)}</h2><span class="muted small">${model.entities.length} entities · ${model.metrics.length} metrics</span></div>
    <div class="er">${erSvg(model)}</div>${erLegend}</div>
    <div class="card"><h2>Data modelling &amp; data catalog exports</h2><p class="muted small">Rendered from the approved logical model, the source-to-target mapping and this run's Stack Profile. Downloads are logged as A0 actions; loading into a shared catalog is an A2 action for the catalog owner.</p>
    <div class="table-wrap"><table><thead><tr><th>Export</th><th>Category</th><th>Description</th><th></th></tr></thead><tbody>
    ${CATALOG.exporters.map((x) => `<tr><td><b>${esc(x.label)}</b></td><td>${badge("", x.category)}</td><td class="small">${esc(x.desc)}</td><td style="white-space:nowrap">${x.id === "ddl" ? `<select id="dl-dialect" style="width:auto;padding:4px">${dialects.map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select> ` : ""}<button class="btn small" data-ex="${x.id}">Download</button></td></tr>`).join("")}
    </tbody></table></div></div>`;
  const cur = (RUN.status.stack && CATALOG.dialects.find(([k]) => k === dialectFor(RUN.status.stack)));
  if (cur && $("#dl-dialect")) $("#dl-dialect").value = cur[0];
  $$("[data-ex]").forEach((b) => (b.onclick = () => download(`/runs/${RUN.id}/exports/${b.dataset.ex}${b.dataset.ex === "ddl" ? `?dialect=${$("#dl-dialect").value}` : ""}`)));
}
const dialectFor = (p) => ({ snowflake: "snowflake", databricks: "databricks", bigquery: "bigquery", redshift: "redshift", synapse: "tsql", fabric: "tsql", postgres: "postgres" }[p.slots?.compute_engine?.tool] || "ansi");
async function renderCode(el) {
  const r = await api("GET", `/runs/${RUN.id}/repo`);
  if (!r.files.length) { el.innerHTML = '<div class="empty">Code appears after the Build stage (feature branch → pull request → G4 merge).</div>'; return; }
  el.innerHTML = `<div class="card tight"><b>Git history</b><pre class="code" style="max-height:160px;margin-top:8px">${esc(r.log)}</pre></div>
    <div class="files" style="margin-top:14px"><div class="tree">${r.files.map((f) => `<div class="f" data-rf="${esc(f)}">${esc(f)}</div>`).join("")}</div><div class="viewer card" id="codeView"><div class="empty">Select a file</div></div></div>`;
  $$("[data-rf]").forEach((f) => (f.onclick = async () => {
    $$("[data-rf]").forEach((x) => x.classList.toggle("active", x === f));
    const t = await api("GET", `/runs/${RUN.id}/repo/file?path=${encodeURIComponent(f.dataset.rf)}`);
    $("#codeView").innerHTML = `<b class="mono">${esc(f.dataset.rf)}</b><hr><pre class="code">${esc(t)}</pre>`;
  }));
}
async function renderHandoffs(el) {
  const hs = await api("GET", `/runs/${RUN.id}/handoffs`);
  el.innerHTML = hs.length ? `<div class="table-wrap"><table><thead><tr><th>#</th><th>From → To</th><th>Status</th><th>Gate</th><th>Summary</th><th>Artifacts</th><th>Confidence</th></tr></thead><tbody>
    ${hs.map((h) => `<tr class="click" data-h="${esc(h.file)}"><td>${h.seq}</td><td class="mono small">${esc(h.from_agent)}<br>→ ${esc(h.to_agent)}</td><td>${badge(h.status === "returned" ? "fail" : h.status === "needs-approval" ? "awaiting-approval" : "approved", h.status)}</td><td>${esc(h.gate || "")}</td><td class="small">${esc(h.summary)}${h.return_reason ? `<div class="notice bad small">${esc(h.return_reason)}</div>` : ""}</td><td>${h.artifacts.length}</td><td>${badge(h.confidence.level)}</td></tr>`).join("")}
    </tbody></table></div><p class="small muted">Envelopes are validated against <code>handoff-envelope.schema.json</code>; receivers re-check every hash and the upstream approval before starting.</p>` : '<div class="empty">No handoffs yet.</div>';
  $$("[data-h]").forEach((tr) => (tr.onclick = async () => modal(`<h2>${esc(tr.dataset.h)}</h2><pre class="code">${esc(await api("GET", `/runs/${RUN.id}/file?path=${encodeURIComponent(tr.dataset.h)}`))}</pre><div style="margin-top:12px"><button class="btn" onclick="closeModal()">Close</button></div>`)));
}
async function renderAudit(el) {
  const [apr, act] = await Promise.all([api("GET", `/runs/${RUN.id}/logs/approvals`), api("GET", `/runs/${RUN.id}/logs/action-log`)]);
  const decisions = apr.filter((a) => a.type === "decision");
  const blocked = act.filter((a) => a.phase === "blocked");
  el.innerHTML = `<div class="card"><h2>Approval decisions</h2>${decisions.length ? `<div class="table-wrap"><table><thead><tr><th>ID</th><th>Gate</th><th>Decision</th><th>Role</th><th>Approver</th><th>Artifact hash</th><th>When</th></tr></thead><tbody>${decisions.map((d) => `<tr><td class="mono">${esc(d.approval_id)}</td><td>${esc(d.gate)}</td><td>${badge(d.decision.startsWith("approved") ? "approved" : "rejected", d.decision)}</td><td>${esc(d.role)}</td><td>${esc(d.approver)}</td><td class="hash">${short(d.artifact_sha256, 14)}</td><td class="small">${fmtTime(d.timestamp)}</td></tr>`).join("")}</tbody></table></div>` : '<div class="muted">None yet.</div>'}</div>
    <div class="card"><h2>Guardrail blocks</h2>${blocked.length ? `<table>${blocked.map((b) => `<tr><td class="small">${fmtTime(b.ts)}</td><td class="mono">${esc(b.agent)}</td><td>${esc(b.action)}</td><td>${badge("fail", b.rule)}</td><td class="small">${esc(b.target)}</td></tr>`).join("")}</table>` : '<div class="muted">No blocked actions in this run.</div>'}</div>
    <div class="card"><h2>Action log (${act.length})</h2><div class="table-wrap" style="max-height:420px;overflow:auto"><table><thead><tr><th>When</th><th>Agent</th><th>Action</th><th>Class</th><th>Phase</th><th>Target</th></tr></thead><tbody>${act.slice().reverse().map((a) => `<tr><td class="small">${new Date(a.ts).toLocaleTimeString()}</td><td class="mono small">${esc(a.agent)}</td><td>${esc(a.action)}</td><td>${badge(a.class === "A4" ? "fail" : a.class === "A3" ? "awaiting-approval" : a.class === "A2" ? "running" : "", a.class)}</td><td>${esc(a.phase)}</td><td class="small mono">${esc(a.target)}</td></tr>`).join("")}</tbody></table></div></div>`;
}
function renderMetrics(st, el) {
  const rows = CATALOG.agents.map((a) => { const u = st.usage[a.name]; const b = st.run.agent_bindings?.[a.name] || {}; return [a.name, `${b.provider_id || "?"} / ${b.model || "?"}`, (u?.models || ["-"]).join(", ") + (u?.fallback ? ` - ${u.fallback}` : ""), u?.calls ?? 0, u?.tokens ?? 0, u ? `$${u.llm_cost_usd.toFixed(4)}` : "-"]; });
  const tot = Object.values(st.usage).reduce((a, u) => ({ t: a.t + u.tokens, c: a.c + u.llm_cost_usd }), { t: 0, c: 0 });
  el.innerHTML = `${teamCard(st)}<div class="grid g3" style="margin-top:16px"><div class="card kpi"><div class="l">LLM tokens</div><div class="v">${tot.t.toLocaleString()}</div></div><div class="card kpi"><div class="l">LLM cost (list price)</div><div class="v">$${tot.c.toFixed(3)}</div></div><div class="card kpi"><div class="l">Guardrail blocks</div><div class="v">${st.metrics.guardrail_blocks || 0}</div></div></div>
    <div class="card"><h2>Models and cost for this run</h2><div class="table-wrap"><table><thead><tr><th>Agent</th><th>Bound to</th><th>Served by</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td class="${i < 3 ? "mono small" : ""}">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    <p class="small muted">"Served by" shows what actually ran. A simulated stage means the bound provider had no key or could not be reached and the demo fallback was on. Bindings are captured when the run is created.</p></div>`;
}

async function renderLakehouse(st, el) {
  const lk = await api("GET", `/runs/${RUN.id}/lakehouse`);
  const envs = ["prod", "test", "rehearsal"].filter((e) => lk.reports[e]);
  RUN.lakeEnv = envs.includes(RUN.lakeEnv) ? RUN.lakeEnv : envs[0];
  const rep = lk.reports[RUN.lakeEnv];
  const sum = (layer) => (rep?.layers[layer] || []).reduce((n, x) => n + (x.rows ?? x.rows_extracted ?? 0), 0);
  const counts = rep ? { source: `${rep.layers.source.length} tables · ${sum("source").toLocaleString()} rows`, bronze: `${rep.layers.bronze.length} tables · ${sum("bronze").toLocaleString()} rows`,
    gold: `${rep.layers.silver.length} silver · ${rep.layers.gold.length} gold`, serving: `${rep.layers.serving.length} tables · masked views` } : null;
  const canRun = ["test", "release", "operations", "consumption", "assembly"].some((k) => st.stages[k].status !== "pending") || st.stages.design.status === "approved";
  el.innerHTML = `<div class="card"><div class="spread"><div><h2>Three pipelines ${lk.executable_locally ? badge("pass", "executes locally") : badge("", "cloud code generated · rehearsed locally")}</h2>
    <div class="small muted">Source: ${esc(lk.source?.type || "synthetic")} ${lk.source?.pack ? `(${esc(lk.source.pack)})` : ""}${lk.source?.dsn ? ` · ${esc(lk.source.dsn)}` : ""}</div></div>
    <div class="row">${envs.length ? `<select id="lkEnv" style="width:auto">${envs.map((e) => `<option value="${e}" ${e === RUN.lakeEnv ? "selected" : ""}>${e}</option>`).join("")}</select>` : ""}
    ${canRun ? '<button class="btn" id="lkRun">Re-run rehearsal (incremental)</button>' : ""}</div></div>
    ${pipelineFlow({ ...st.stack, slots: { ...st.stack.slots, source_database: { tool: lk.source?.type || st.stack.slots.source_database?.tool } } }, counts)}
    ${rep ? `<div class="row small" style="margin-top:8px">${badge(rep.status === "passed" ? "pass" : rep.status === "failed" ? "fail" : "awaiting-approval", rep.status)} <span class="muted">${esc(rep.format)} · batch ${esc(rep.pipelines.ingest.batch_id)} · ingest ${rep.pipelines.ingest.seconds}s · curate ${rep.pipelines.curate.seconds}s${rep.pipelines.publish ? ` · publish ${rep.pipelines.publish.seconds}s` : ""} · finished ${fmtTime(rep.finished)}</span></div>` : `<div class="notice" style="margin-top:10px">No pipeline run yet. The Test stage rehearses the three pipelines against the source database${lk.executable_locally ? "; G6a and G6b deploy them for real to test and prod" : ""}.</div>`}</div>
    ${rep ? `<div class="grid g2" style="margin-top:16px">
      <div class="card"><h2>Layers</h2><div class="table-wrap"><table><thead><tr><th>Layer</th><th>Table</th><th>Rows</th><th>Version</th></tr></thead><tbody>
        ${["bronze", "silver", "gold", "serving"].map((L) => rep.layers[L].map((x, i) => `<tr><td>${i === 0 ? `<b>${L}</b>` : ""}</td><td class="mono small">${esc(x.table)}</td><td>${esc(x.rows ?? x.rows_extracted)}</td><td class="hash">${esc(String(x.version ?? (x.masked_columns?.length ? "masked: " + x.masked_columns.join(", ") : "")).slice(0, 22))}</td></tr>`).join("")).join("")}
      </tbody></table></div></div>
      <div class="card"><h2>Quality on real data</h2><table>${(rep.dq || []).map((d) => `<tr><td class="mono">${esc(d.id)}</td><td>${badge(d.status === "pass" ? "pass" : "fail", d.status)}</td><td class="small muted">${d.failures ? `${d.failures} of ${d.rows} rows` : ""}</td></tr>`).join("")}</table>
        <h3>Metrics: gold vs analytics layer</h3><table>${(rep.metrics || []).map((m) => `<tr><td>${esc(m.label)}</td><td class="mono">${m.gold != null ? Number(m.gold).toLocaleString(undefined, { maximumFractionDigits: 3 }) : "-"}</td><td>${badge(m.status)}</td></tr>`).join("")}</table></div></div>
    <div class="card"><div class="spread"><h2>Analytics layer preview (consumer view, masked)</h2><select id="lkTable" style="width:auto">${rep.layers.serving.map((x) => `<option value="${esc(x.table.replace("serving.", ""))}">${esc(x.table)}</option>`).join("")}</select></div><div id="lkRows" class="small muted">Select a table</div></div>` : ""}`;
  if ($("#lkEnv")) $("#lkEnv").onchange = () => { RUN.lakeEnv = $("#lkEnv").value; renderLakehouse(st, el); };
  if ($("#lkRun")) $("#lkRun").onclick = async (e) => { e.target.disabled = true; e.target.textContent = "Running…"; await guard(() => api("POST", `/runs/${RUN.id}/lakehouse/rehearse`), "Pipelines executed"); RUN.lakeEnv = "rehearsal"; renderLakehouse(st, el); };
  const preview = async () => {
    const q = await guard(() => api("GET", `/runs/${RUN.id}/lakehouse/query?env=${RUN.lakeEnv}&table=${$("#lkTable").value}&limit=15`));
    $("#lkRows").innerHTML = `<div class="small muted" style="margin-bottom:6px">${q.total_rows.toLocaleString()} rows · showing ${q.rows.length}</div><div class="table-wrap"><table><thead><tr>${q.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${q.rows.map((r) => `<tr>${r.map((v) => `<td class="small">${v === "***" ? '<span class="badge b-violet">masked</span>' : esc(v ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  };
  if ($("#lkTable")) { $("#lkTable").onchange = preview; preview(); }
}

// ------------------------------------------------------------------ agents & models
route("agents", async () => {
  await refreshSettings();
  const ready = await api("GET", "/providers/readiness");
  const rt = SETTINGS.runtime || {};
  const keyBadge = (pid) => pid === "demo" ? badge("", "offline") : ready[pid] ? badge("pass", "key configured") : badge(rt.simulate_unavailable_providers === false ? "fail" : "awaiting-approval", rt.simulate_unavailable_providers === false ? "no key - stage will fail" : "no key - simulated");
  const provOpts = (sel) => SETTINGS.providers.map((p) => `<option value="${esc(p.id)}" ${p.id === sel ? "selected" : ""}>${esc(p.label)}</option>`).join("");
  const suggestions = (pid) => { const p = providerById(pid); return (CATALOG.provider_types[p?.type]?.models || []).map((m) => m.id).concat(store.get(`adef_models_${pid}`, [])); };
  main().innerHTML = `<div class="spread"><div><h1>Agents &amp; models</h1><div class="sub">Bind each of the nine agents to a provider and model. Mix providers freely - for example a top-tier model for Design and a fast model for Operations.</div></div>
    <div class="row"><button class="btn primary" id="saveAgents">Save bindings</button></div></div>
    <div class="card tight"><div class="row"><b>Team preset:</b><select id="presetSel" style="width:auto">${Object.entries(CATALOG.team_presets).map(([k, p]) => `<option value="${esc(k)}" ${k === rt.team_preset ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select>
      <span class="small muted" id="presetDesc"></span><button class="btn" id="applyPreset">Apply preset</button></div>
      <label style="display:flex;gap:8px;align-items:center;color:var(--text);font-weight:400;margin-top:10px"><input type="checkbox" id="simToggle" style="width:auto" ${rt.simulate_unavailable_providers !== false ? "checked" : ""}>
      Demo fallback: if an agent's provider has no key, can't be reached or rejects the key, run that stage on the Demo Simulator and label it as simulated. Turn this off for real client work.</label></div>
    <div class="card tight"><div class="row"><b>Apply to all agents:</b><select id="allProv" style="width:auto">${provOpts(SETTINGS.agents["adef-orchestrator"].provider_id)}</select><input id="allModel" list="dl-all" style="width:240px" placeholder="model"><datalist id="dl-all"></datalist><select id="allEffort" style="width:auto">${CATALOG.effort_levels.map((e) => `<option ${e === "medium" ? "selected" : ""}>${e}</option>`).join("")}</select><button class="btn" id="applyAll">Apply</button></div></div>
    <div class="card"><div class="table-wrap"><table><thead><tr><th style="width:30%">Agent</th><th>Provider</th><th>Model</th><th>Effort</th><th>Max tokens</th><th>Key</th><th></th></tr></thead><tbody>
    ${CATALOG.agents.map((a) => { const b = SETTINGS.agents[a.name]; return `<tr data-agent="${esc(a.name)}"><td><b class="mono">${esc(a.name)}</b><div class="small muted">${esc(a.description)}</div></td>
      <td><select data-k="provider_id">${provOpts(b.provider_id)}</select></td>
      <td><input data-k="model" list="dl-${esc(a.name)}" value="${esc(b.model)}"><datalist id="dl-${esc(a.name)}">${suggestions(b.provider_id).map((m) => `<option value="${esc(m)}">`).join("")}</datalist></td>
      <td><select data-k="effort">${CATALOG.effort_levels.map((e) => `<option ${e === b.effort ? "selected" : ""}>${e}</option>`).join("")}</select></td>
      <td><input data-k="max_tokens" type="number" value="${esc(b.max_tokens)}" style="width:100px"></td>
      <td class="keyst">${keyBadge(b.provider_id)}</td>
      <td><button class="btn small" data-test="${esc(a.name)}">Test</button></td></tr>`; }).join("")}
    </tbody></table></div><p class="small muted">Model names are free text - any model your provider serves. Effort maps to the provider's reasoning-depth control where one exists. Bindings are snapshotted into each run at creation.</p></div>`;
  const pd = () => ($("#presetDesc").textContent = CATALOG.team_presets[$("#presetSel").value].description);
  pd(); $("#presetSel").onchange = pd;
  $("#applyPreset").onclick = async () => { await guard(() => api("POST", "/settings/agents/preset", { preset: $("#presetSel").value }), "Team preset applied"); navigate(); };
  $("#simToggle").onchange = async () => { await guard(() => api("PUT", "/settings/runtime", { simulate_unavailable_providers: $("#simToggle").checked }), "Saved"); navigate(); };
  const fillDl = (dl, pid) => (dl.innerHTML = suggestions(pid).map((m) => `<option value="${esc(m)}">`).join(""));
  fillDl($("#dl-all"), $("#allProv").value);
  $("#allProv").onchange = () => fillDl($("#dl-all"), $("#allProv").value);
  $$("tr[data-agent] select[data-k=provider_id]").forEach((s) => (s.onchange = () => {
    const tr = s.closest("tr"); fillDl($(`#dl-${tr.dataset.agent}`), s.value); $(".keyst", tr).innerHTML = keyBadge(s.value);
    const sug = suggestions(s.value); if (sug.length) $("input[data-k=model]", tr).value = sug[0];
  }));
  $("#applyAll").onclick = () => $$("tr[data-agent]").forEach((tr) => {
    $("select[data-k=provider_id]", tr).value = $("#allProv").value;
    const m = $("#allModel").value || suggestions($("#allProv").value)[0] || "";
    $("input[data-k=model]", tr).value = m; $("select[data-k=effort]", tr).value = $("#allEffort").value;
  });
  const gather = () => Object.fromEntries($$("tr[data-agent]").map((tr) => [tr.dataset.agent, Object.fromEntries($$("[data-k]", tr).map((x) => [x.dataset.k, x.value]))]));
  $("#saveAgents").onclick = async () => { await guard(() => api("PUT", "/settings/agents", gather()), "Agent bindings saved"); await refreshSettings(); };
  $$("[data-test]").forEach((b) => (b.onclick = async () => {
    const tr = b.closest("tr"); const pid = $("select[data-k=provider_id]", tr).value; const model = $("input[data-k=model]", tr).value;
    b.disabled = true; b.textContent = "…";
    try { const r = await api("POST", `/providers/${pid}/test`, { model }); toast(r.ok ? `${model}: OK (“${r.reply}”)` : r.error, r.ok ? "ok" : "err"); }
    catch (e) { toast(e.message, "err"); } finally { b.disabled = false; b.textContent = "Test"; }
  }));
});

// ------------------------------------------------------------------ providers & keys
route("providers", async () => {
  await refreshSettings();
  const secrets = await api("GET", "/secrets");
  const types = CATALOG.provider_types;
  main().innerHTML = `<h1>Providers &amp; API keys</h1><div class="sub">Configure model providers. API keys are stored encrypted in the vault and referenced by name - they are never shown again, logged, written to run artifacts, or sent to a model.</div>
    <div class="grid g2">
      <div class="card"><h2>Configured providers</h2><div id="provList"></div></div>
      <div class="card"><h2>Add or update a provider</h2>
        <div class="field-row"><div><label>Type</label><select id="pType">${Object.entries(types).filter(([k]) => k !== "simulator").map(([k, t]) => `<option value="${k}">${esc(t.label)}</option>`).join("")}</select></div>
        <div><label>ID</label><input id="pId" placeholder="e.g. anthropic-prod"></div></div>
        <label>Display name</label><input id="pLabel" placeholder="e.g. Anthropic (enterprise key)">
        <div id="pTypeDesc" class="small muted" style="margin-top:6px"></div>
        <label>Base URL / endpoint</label><input id="pBase">
        <div id="pOpts"></div>
        <label>API key</label>
        <select id="pKeyMode"><option value="new">Enter a new key (stored encrypted)</option><option value="vault">Use a key already in the vault</option><option value="env">Read from an environment variable</option><option value="none">No key (local endpoint)</option></select>
        <div id="pKeyBox"></div>
        <div class="row" style="margin-top:14px"><button class="btn primary" id="pSave">Save provider</button></div>
      </div>
    </div>
    <div class="card"><h2>Secret vault</h2><div class="table-wrap"><table><thead><tr><th>Name</th><th>Hint</th><th>Description</th><th>Updated</th><th></th></tr></thead><tbody>${secrets.map((s) => `<tr><td class="mono">${esc(s.name)}</td><td class="mono">${esc(s.hint)}</td><td>${esc(s.description)}</td><td class="small">${fmtTime(s.updated)}</td><td><button class="btn small bad" data-del="${esc(s.name)}">Delete</button></td></tr>`).join("") || '<tr><td colspan="5" class="muted">Empty</td></tr>'}</tbody></table></div></div>`;
  const renderList = () => ($("#provList").innerHTML = SETTINGS.providers.map((p) => `<div class="card tight"><div class="spread"><div><b>${esc(p.label)}</b> ${badge("", types[p.type]?.label || p.type)}<div class="small muted mono">${esc(p.id)} · ${esc(p.base_url || types[p.type]?.default_base_url || "")} · key: ${esc(p.api_key_ref || "none")}</div></div>
    <div class="row"><input class="tm" data-pid="${esc(p.id)}" list="tdl-${esc(p.id)}" style="width:170px" value="${esc(types[p.type]?.models?.[0]?.id || "")}"><datalist id="tdl-${esc(p.id)}">${(types[p.type]?.models || []).map((m) => `<option value="${esc(m.id)}">`).join("")}</datalist>
    <button class="btn small" data-ptest="${esc(p.id)}">Test</button>${p.type !== "simulator" ? `<button class="btn small" data-pmodels="${esc(p.id)}">Discover models</button><button class="btn small" data-pedit="${esc(p.id)}">Edit</button><button class="btn small bad" data-premove="${esc(p.id)}">Remove</button>` : ""}</div></div></div>`).join(""));
  renderList();
  const keyBox = () => {
    const m = $("#pKeyMode").value;
    $("#pKeyBox").innerHTML = m === "new" ? `<input id="pKey" type="password" autocomplete="off" placeholder="Paste the key - it is encrypted and never displayed again"><label>Vault name</label><input id="pKeyName" placeholder="e.g. anthropic-prod-key">`
      : m === "vault" ? `<select id="pKeyVault">${secrets.map((s) => `<option value="secret:${esc(s.name)}">${esc(s.name)} (${esc(s.hint)})</option>`).join("")}</select>`
      : m === "env" ? `<input id="pKeyEnv" placeholder="ANTHROPIC_API_KEY">` : "";
  };
  const typeChange = () => {
    const t = types[$("#pType").value];
    $("#pTypeDesc").textContent = t.description; $("#pBase").placeholder = t.default_base_url || "";
    $("#pOpts").innerHTML = Object.entries(t.options || {}).map(([k, v]) => `<label>${esc(k)}</label><input data-opt="${esc(k)}" value="${esc(v)}">`).join("");
    if (!$("#pId").value) $("#pId").value = $("#pType").value.replace("_", "-");
    if (!$("#pLabel").value) $("#pLabel").value = t.label;
  };
  $("#pType").onchange = () => { $("#pId").value = ""; $("#pLabel").value = ""; typeChange(); };
  $("#pKeyMode").onchange = keyBox; typeChange(); keyBox();
  $("#pSave").onclick = async () => {
    const mode = $("#pKeyMode").value; let ref = "";
    if (mode === "new") {
      const name = $("#pKeyName").value || `${$("#pId").value}-key`;
      if (!$("#pKey").value) { toast("Enter the API key", "err"); return; }
      await guard(() => api("POST", "/secrets", { name, value: $("#pKey").value, description: `API key for ${$("#pLabel").value}` }));
      $("#pKey").value = ""; ref = `secret:${name}`;
    } else if (mode === "vault") ref = $("#pKeyVault").value; else if (mode === "env") ref = `env:${$("#pKeyEnv").value}`;
    const prov = { id: $("#pId").value.trim(), type: $("#pType").value, label: $("#pLabel").value.trim(), base_url: $("#pBase").value.trim(), api_key_ref: ref,
      options: Object.fromEntries($$("[data-opt]").map((x) => [x.dataset.opt, x.value])) };
    const list = SETTINGS.providers.filter((p) => p.id !== prov.id).concat([prov]);
    await guard(() => api("PUT", "/settings/providers", list), "Provider saved");
    navigate();
  };
  main().onclick = async (e) => {
    const t = e.target;
    if (t.dataset.ptest) {
      const model = $(`.tm[data-pid="${t.dataset.ptest}"]`).value; t.textContent = "…";
      try { const r = await api("POST", `/providers/${t.dataset.ptest}/test`, { model }); toast(r.ok ? `Connected: ${r.model} replied “${r.reply}”` : r.error, r.ok ? "ok" : "err"); } finally { t.textContent = "Test"; }
    }
    if (t.dataset.pmodels) {
      const r = await api("GET", `/providers/${t.dataset.pmodels}/models`);
      if (r.ok) { store.set(`adef_models_${t.dataset.pmodels}`, r.models); modal(`<h2>Models available (${r.models.length})</h2><p class="muted small">Added as suggestions on Agents &amp; models.</p><pre class="code" style="max-height:50vh">${esc(r.models.join("\n"))}</pre><button class="btn" onclick="closeModal()">Close</button>`); }
      else toast(r.error, "err");
    }
    if (t.dataset.pedit) {
      const p = providerById(t.dataset.pedit);
      $("#pType").value = p.type; $("#pId").value = p.id; $("#pLabel").value = p.label; $("#pBase").value = p.base_url || ""; typeChange();
      Object.entries(p.options || {}).forEach(([k, v]) => { const el = $(`[data-opt="${k}"]`); if (el) el.value = v; });
      if (p.api_key_ref?.startsWith("secret:")) { $("#pKeyMode").value = "vault"; keyBox(); $("#pKeyVault").value = p.api_key_ref; }
      else if (p.api_key_ref?.startsWith("env:")) { $("#pKeyMode").value = "env"; keyBox(); $("#pKeyEnv").value = p.api_key_ref.slice(4); }
    }
    if (t.dataset.premove) {
      if (Object.values(SETTINGS.agents).some((a) => a.provider_id === t.dataset.premove)) { toast("Rebind the agents using this provider first.", "err"); return; }
      await guard(() => api("PUT", "/settings/providers", SETTINGS.providers.filter((p) => p.id !== t.dataset.premove)), "Removed"); navigate();
    }
    if (t.dataset.del) { if (confirm(`Delete secret ${t.dataset.del}?`)) { await guard(() => api("DELETE", `/secrets/${t.dataset.del}`), "Deleted"); navigate(); } }
  };
});

// ------------------------------------------------------------------ stacks
route("stacks", async () => {
  await refreshSettings();
  const list = allStacks();
  let cur = JSON.parse(JSON.stringify(list[0]));
  main().innerHTML = `<h1>Technology stacks</h1><div class="sub">Agents reason in capability slots; a Stack Profile binds each slot to a tool. Pick a reference stack, adjust any slot, validate (stack-binding T1) and save it for your runs.</div>
    <div class="option-cards" id="stackCards"></div>
    <div class="card" style="margin-top:16px"><div class="spread"><h2 id="stackTitle"></h2><div class="row"><button class="btn" id="valBtn">Validate</button><button class="btn primary" id="saveStack">Save as custom profile</button></div></div>
      <div class="field-row"><div><label>Profile ID</label><input id="sId"></div><div><label>Label</label><input id="sLabel"></div><div><label>Naming case</label><select id="sCase"><option>upper_snake</option><option>lower_snake</option></select></div>
      <div><label>Max compute size</label><input id="sSize"></div><div><label>Monthly cost cap</label><input id="sCap" type="number"></div><div><label>Org prefix variable</label><input id="sPrefix"></div></div>
      <label>Layers (comma separated)</label><input id="sLayers">
      <h3>The three pipelines</h3><div id="flowBox"></div>
      <h3>Capability slots</h3><div class="slot-grid" id="slotGrid"></div>
      <div id="valOut" style="margin-top:14px"></div></div>`;
  const cards = () => ($("#stackCards").innerHTML = list.map((s) => `<div class="option ${s.profile_id === cur.profile_id ? "sel" : ""}" data-s="${esc(s.profile_id)}"><div class="t">${esc(s.label || s.profile_id)}</div><div class="small muted">${esc(s.description || "custom profile")}</div>${CATALOG.presets.some((p) => p.profile_id === s.profile_id) ? "" : `<div style="margin-top:6px"><span class="badge b-violet">custom</span> <a href="#" data-sdel="${esc(s.profile_id)}" class="small">delete</a></div>`}</div>`).join(""));
  const form = () => {
    $("#stackTitle").textContent = cur.label || cur.profile_id;
    $("#sId").value = CATALOG.presets.some((p) => p.profile_id === cur.profile_id) ? `${cur.profile_id}-custom` : cur.profile_id;
    $("#sLabel").value = cur.label || ""; $("#sCase").value = cur.standards.naming_case; $("#sSize").value = cur.limits.max_compute_size;
    $("#sCap").value = cur.limits.monthly_cost_cap; $("#sPrefix").value = cur.variables.org_prefix; $("#sLayers").value = cur.standards.layers.join(", ");
    $("#slotGrid").innerHTML = CATALOG.slots.map((sl) => { const t = cur.slots[sl.slot]?.tool || ""; const opts = [...new Set([...sl.options, ...(sl.required ? [] : ["none"]), t].filter(Boolean))];
      return `<div class="slot"><div class="name">${esc(sl.slot)} ${sl.required ? '<span class="badge b-info">required</span>' : ""}</div><div class="job">${esc(sl.job)}</div><select data-slot="${esc(sl.slot)}">${opts.map((o) => `<option ${o === t ? "selected" : ""}>${esc(o)}</option>`).join("")}<option value="__custom">other…</option></select></div>`; }).join("");
    $$("[data-slot]").forEach((s) => (s.onchange = () => { if (s.value === "__custom") { const v = prompt(`Tool for ${s.dataset.slot}`); if (v) { s.insertAdjacentHTML("afterbegin", `<option selected>${esc(v)}</option>`); } } $("#flowBox").innerHTML = pipelineFlow(gather()); }));
    $("#flowBox").innerHTML = pipelineFlow(cur);
    $("#valOut").innerHTML = "";
  };
  const gather = () => {
    const p = JSON.parse(JSON.stringify(cur));
    p.profile_id = $("#sId").value.trim(); p.label = $("#sLabel").value.trim(); p.description = p.description || "Custom Stack Profile";
    p.standards.naming_case = $("#sCase").value; p.limits.max_compute_size = $("#sSize").value; p.limits.monthly_cost_cap = +$("#sCap").value;
    p.variables.org_prefix = $("#sPrefix").value; p.standards.layers = $("#sLayers").value.split(",").map((x) => x.trim()).filter(Boolean);
    $$("[data-slot]").forEach((s) => (p.slots[s.dataset.slot] = s.value === "none" ? { tool: "none", reason: "not required for this client" } : { tool: s.value, version: "current" }));
    return p;
  };
  const showVal = (v) => ($("#valOut").innerHTML = `${v.ok ? '<div class="notice">No blocking gaps - this profile can pass G0.</div>' : `<div class="notice bad">${v.blocking.map(esc).join("<br>")}</div>`}
    ${v.warnings.length ? `<details style="margin-top:8px"><summary class="small">${v.warnings.length} warnings</summary><ul class="small">${v.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></details>` : ""}`);
  cards(); form();
  $("#stackCards").addEventListener("click", async (e) => {
    if (e.target.dataset.sdel) { e.preventDefault(); await guard(() => api("DELETE", `/stacks/${e.target.dataset.sdel}`), "Deleted"); navigate(); return; }
    const o = e.target.closest("[data-s]"); if (!o) return;
    cur = JSON.parse(JSON.stringify(list.find((s) => s.profile_id === o.dataset.s))); cards(); form();
  });
  $("#valBtn").onclick = async () => showVal(await guard(() => api("POST", "/stacks/validate", gather())));
  $("#saveStack").onclick = async () => { const r = await guard(() => api("POST", "/stacks", gather()), "Stack Profile saved"); showVal(r.validation); await refreshSettings(); };
});

// ------------------------------------------------------------------ integrations
route("integrations", async () => {
  await refreshSettings();
  const secrets = await api("GET", "/secrets");
  const j = SETTINGS.jira;
  main().innerHTML = `<h1>Integrations</h1><div class="sub">Connect the systems where your project knowledge lives: Jira, Confluence, GitHub, ServiceNow, catalogs and source databases. All read-only (action class A0) and all optional.</div>
    <div class="card" id="integCards"></div>
    <div class="grid g2">
      <div class="card"><h2>Jira connection</h2>
        <div class="field-row"><div><label>Mode</label><select id="jMode"><option value="demo" ${j.mode === "demo" ? "selected" : ""}>Demo Jira (built-in projects UTIL, TEL, FIN, RET)</option><option value="live" ${j.mode === "live" ? "selected" : ""}>Live Jira</option></select></div>
        <div><label>Deployment</label><select id="jDep"><option value="cloud" ${j.deployment === "cloud" ? "selected" : ""}>Jira Cloud (email + API token)</option><option value="server" ${j.deployment === "server" ? "selected" : ""}>Data Center / Server (PAT)</option></select></div></div>
        <label>Base URL</label><input id="jBase" value="${esc(j.base_url)}" placeholder="https://your-company.atlassian.net">
        <label>Account email (Cloud)</label><input id="jEmail" value="${esc(j.email)}">
        <label>API token</label><select id="jTokMode"><option value="keep">${j.token_ref ? `Keep ${esc(j.token_ref)}` : "Not set"}</option><option value="new">Enter a new token (stored encrypted)</option>${secrets.map((s) => `<option value="secret:${esc(s.name)}">Use vault secret ${esc(s.name)}</option>`).join("")}</select>
        <div id="jTokBox"></div>
        <label>Default JQL</label><input id="jJql" value="${esc(j.default_jql)}">
        <label>Acceptance-criteria custom field (optional)</label><input id="jAc" value="${esc(j.acceptance_field || "")}" placeholder="customfield_10035">
        <div class="row" style="margin-top:14px"><button class="btn primary" id="jSave">Save</button><button class="btn" id="jTest">Test connection</button></div>
        <hr><label>Preview a query</label><div class="row"><input id="jQ" value="${esc(j.mode === "demo" ? "project = UTIL" : j.default_jql)}" style="flex:1"><button class="btn" id="jSearch">Search</button></div>
        <label>…or preview a Jira export file (no connection needed)</label><input type="file" id="jFile" accept=".csv,.json">
        <div id="jOut" style="margin-top:10px"></div>
      </div>
      <div class="card"><h2>Import source metadata</h2>
        <p class="muted small">Accepted: CSV data dictionary / catalog export (table, column, type, nullable, pk, description, classification - common column names are recognised), ADEF or generic JSON model, DBML, and CREATE TABLE DDL from modelling tools. Contents are treated as untrusted data.</p>
        <input type="file" id="mFile" accept=".csv,.json,.dbml,.sql,.ddl,.txt">
        <div id="mOut" style="margin-top:12px"></div>
      </div>
    </div>
    <div class="card"><div class="spread"><div><h2>Demo data packs</h2><div class="small muted">Synthetic, deterministic files per industry: Jira exports, source catalog and DDL, source data, data model exports, catalog payloads and lineage. Regenerate with <code>python -m adef demo-data</code>.</div></div>
      <select id="ddDomain" style="width:auto">${CATALOG.domain_packs.map((p) => `<option value="${esc(p.pack_id)}">${esc(p.pack_id)}</option>`).join("")}</select></div>
      <div id="ddOut" style="margin-top:12px"></div></div>`;
  renderIntegrationCards($("#integCards"));
  const demo = await api("GET", "/demo-files");
  const kitDomains = new Set(demo.filter((f) => f.folder === "client-demo-kit").map((f) => f.domain));
  $$("#ddDomain option").forEach((o) => { if (kitDomains.has(o.value)) o.textContent = `${o.value} (client demo kit)`; });
  if (kitDomains.size) $("#ddDomain").value = [...kitDomains][0];
  // what a demo file can be fed into, decided by its name
  const actionFor = (f) => {
    const n = f.name;
    if (/jira-export.*\.(csv|json)$/.test(n)) return ["Preview issues", "jira"];
    if (/legacy-warehouse|logical-model\.json$|\.model\.dbml$/.test(n)) return ["Open in studio", "studio"];
    if (/(catalog-export|source-catalog|source-model|source-ddl).*\.(csv|sql|dbml)$/.test(n)) return ["Import as metadata", "meta"];
    return null;
  };
  const FOLDER_ORDER = ["client-demo-kit", "jira", "source-metadata", "source-data", "model", "catalog", "lineage", "-"];
  const renderDemo = () => {
    const dom = $("#ddDomain").value;
    const files = demo.filter((f) => f.domain === dom);
    const groups = {};
    files.forEach((f) => (groups[f.folder || "-"] = groups[f.folder || "-"] || []).push(f));
    const ordered = Object.entries(groups).sort((a, b) => FOLDER_ORDER.indexOf(a[0]) - FOLDER_ORDER.indexOf(b[0]));
    $("#ddOut").innerHTML = files.length ? `${groups["client-demo-kit"] ? `<div class="notice" style="margin-bottom:10px"><b>Client demo kit</b>: the input files a client hands over, numbered in upload order. See <code>00-README.md</code> for where each one goes.</div>` : ""}
    <div class="table-wrap"><table><thead><tr><th>Folder</th><th>File</th><th>Size</th><th></th></tr></thead><tbody>${ordered.map(([g, fs]) => fs.map((f, i) => {
      const act = actionFor(f);
      const head = i === 0 ? `<b>${esc(g)}</b>${g !== "-" ? `<div><button class="btn small" data-zip="${esc(`${dom}/${g}`)}" style="margin-top:4px">Download all (.zip)</button></div>` : ""}` : "";
      return `<tr><td>${head}</td><td class="mono small">${esc(f.name)}</td><td class="small muted">${(f.bytes / 1024).toFixed(1)} KB</td><td style="white-space:nowrap"><button class="btn small" data-dl="${esc(f.path)}">Download</button>${act ? ` <button class="btn small" data-act="${act[1]}" data-path="${esc(f.path)}">${act[0]}</button>` : ""}</td></tr>`;
    }).join("")).join("")}</tbody></table></div>` : '<div class="empty">No demo files found. Run <code>python -m adef demo-data</code>.</div>';
    $$("[data-dl]").forEach((b) => (b.onclick = () => download(`/demo-files/file?path=${encodeURIComponent(b.dataset.dl)}`, b.dataset.dl.split("/").pop())));
    $$("[data-zip]").forEach((b) => (b.onclick = () => download(`/demo-files/zip?folder=${encodeURIComponent(b.dataset.zip)}`, `${b.dataset.zip.replace("/", "-")}.zip`)));
    $$("[data-act]").forEach((b) => (b.onclick = async () => {
      const path = b.dataset.path;
      if (b.dataset.act === "jira") showIssues(await guard(() => importDemoFile(path, "/jira/import")));
      if (b.dataset.act === "meta") showMeta(await guard(() => importDemoFile(path, "/metadata/import")));
      if (b.dataset.act === "studio") { const m = await guard(() => importDemoFile(path, "/metadata/import")); store.set("adef_studio_model", m.logical_model); location.hash = "#/studio"; }
    }));
  };
  $("#ddDomain").onchange = renderDemo;
  renderDemo();
  const showIssues = (is) => {
    $("#jOut").innerHTML = `<div class="table-wrap"><table><thead><tr><th>Key</th><th>Type</th><th>Summary</th><th>AC</th><th>Findings</th></tr></thead><tbody>${is.map((i) => `<tr><td class="mono">${esc(i.key)}</td><td>${esc(i.type)}</td><td>${esc(i.summary)}</td><td>${(i.acceptance_criteria || []).length}</td><td>${i.untrusted_findings?.injection?.length ? badge("fail", "instruction-like text") : ""}</td></tr>`).join("")}</tbody></table></div>`;
    $("#jOut").scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  const showMeta = (m) => {
    const model = m.logical_model; delete m.logical_model;
    $("#mOut").innerHTML = metaSummary(m) + `<div class="row" style="margin-top:10px"><button class="btn primary" id="useMeta">Use in next run</button><button class="btn" id="toStudio">Open in model studio</button></div>`;
    $("#useMeta").onclick = () => { store.set("adef_pending_metadata", m); WZ.data = null; toast("Attached to the next run", "ok"); location.hash = "#/new"; };
    $("#toStudio").onclick = () => { store.set("adef_studio_model", model); location.hash = "#/studio"; };
    if ($("#metaClear")) $("#metaClear").onclick = () => ($("#mOut").innerHTML = "");
  };
  $("#jFile").onchange = async (e) => showIssues(await guard(() => uploadFile(e.target.files[0], "/jira/import")));
  // ---- source databases (Pipeline 1 extracts from these)
  main().insertAdjacentHTML("beforeend", `<div class="card"><div class="spread"><div><h2>Source databases</h2><div class="small muted">Where Pipeline 1 extracts from. Synthetic SQLite sources are built in for every industry; add Oracle, Db2 or PostgreSQL (for example the containers from <code>docker compose --profile oracle</code>). Passwords go to the encrypted vault.</div></div></div>
    <div id="srcList" style="margin-top:10px"></div>
    <h3>Add a connection</h3><div class="field-row">
      <div><label>Type</label><select id="sType"><option value="oracle">Oracle</option><option value="db2">IBM Db2</option><option value="postgres">PostgreSQL</option></select></div>
      <div><label>ID</label><input id="sId" placeholder="oracle-demo"></div><div><label>Label</label><input id="sLabel" placeholder="Oracle Free (container)"></div></div>
    <div class="field-row"><div><label>DSN (Oracle host:port/service, PostgreSQL DSN)</label><input id="sDsn" placeholder="localhost:1521/FREEPDB1"></div>
      <div><label>Host (Db2)</label><input id="sHost" placeholder="localhost"></div><div><label>Port (Db2)</label><input id="sPort" placeholder="50000"></div><div><label>Database (Db2)</label><input id="sDb" placeholder="ADEF"></div></div>
    <div class="field-row"><div><label>User</label><input id="sUser" placeholder="system / db2inst1"></div><div><label>Password (stored encrypted, never shown again)</label><input id="sPw" type="password" autocomplete="off"></div></div>
    <div class="row" style="margin-top:12px"><button class="btn primary" id="sSave">Save connection</button></div></div>`);
  const renderSources = async () => {
    const list = await api("GET", "/sources");
    $("#srcList").innerHTML = `<div class="table-wrap"><table><thead><tr><th>Source</th><th>Type</th><th>Connection</th><th></th></tr></thead><tbody>${list.map((x) => `<tr><td><b>${esc(x.label || x.id)}</b><div class="small muted mono">${esc(x.id)}</div></td><td>${esc(x.type)}</td><td class="small mono">${esc(x.built_in ? `${x.pack} synthetic data` : x.dsn || `${x.host}:${x.port}/${x.database}`)} ${x.password_ref ? `· ${esc(x.password_ref)}` : ""}</td>
      <td style="white-space:nowrap"><button class="btn small" data-stest="${esc(x.id)}">Test</button> ${x.built_in ? "" : `<select data-sdom="${esc(x.id)}" style="width:auto;padding:4px">${CATALOG.domain_packs.map((p) => `<option>${esc(p.pack_id)}</option>`).join("")}</select> <button class="btn small" data-sseed="${esc(x.id)}">Seed synthetic data</button> <button class="btn small bad" data-sdel="${esc(x.id)}">Remove</button>`}</td></tr>`).join("")}</tbody></table></div><div id="srcOut" style="margin-top:8px"></div>`;
    $$("[data-stest]").forEach((b) => (b.onclick = async () => {
      b.textContent = "…"; const r = await api("POST", `/sources/${b.dataset.stest}/test`); b.textContent = "Test";
      $("#srcOut").innerHTML = r.ok ? `<div class="notice">${esc(b.dataset.stest)}: ${Object.keys(r.tables).length} tables · ${esc(Object.entries(r.tables).map(([t, n]) => `${t} (${n})`).join(", "))}</div>` : `<div class="notice bad">${esc(r.error)}</div>`;
    }));
    $$("[data-sseed]").forEach((b) => (b.onclick = async () => {
      b.textContent = "Seeding…"; const r = await api("POST", `/sources/${b.dataset.sseed}/seed`, { domain: $(`[data-sdom="${b.dataset.sseed}"]`).value }); b.textContent = "Seed synthetic data";
      $("#srcOut").innerHTML = r.ok ? `<div class="notice">Seeded: ${esc(JSON.stringify(r.tables))}</div>` : `<div class="notice bad">${esc(r.error)}</div>`;
    }));
    $$("[data-sdel]").forEach((b) => (b.onclick = async () => { await guard(() => api("PUT", "/settings/sources", list.filter((x) => !x.built_in && x.id !== b.dataset.sdel)), "Removed"); renderSources(); }));
    $("#sSave").onclick = async () => {
      const id = $("#sId").value.trim(); let ref = "";
      if ($("#sPw").value) { await guard(() => api("POST", "/secrets", { name: `${id}-password`, value: $("#sPw").value, description: `Source database ${id}` })); ref = `secret:${id}-password`; $("#sPw").value = ""; }
      const item = { id, type: $("#sType").value, label: $("#sLabel").value || id, dsn: $("#sDsn").value || null, host: $("#sHost").value || null,
        port: $("#sPort").value ? +$("#sPort").value : null, database: $("#sDb").value || null, user: $("#sUser").value, password_ref: ref };
      await guard(() => api("PUT", "/settings/sources", list.filter((x) => !x.built_in && x.id !== id).concat([item])), "Source saved");
      renderSources();
    };
  };
  renderSources();
  $("#jTokMode").onchange = () => ($("#jTokBox").innerHTML = $("#jTokMode").value === "new" ? '<input id="jTok" type="password" autocomplete="off" placeholder="Token is encrypted and never displayed again"><label>Vault name</label><input id="jTokName" value="jira-token">' : "");
  $("#jSave").onclick = async () => {
    let ref = j.token_ref; const m = $("#jTokMode").value;
    if (m === "new") { if (!$("#jTok").value) { toast("Enter the token", "err"); return; } await guard(() => api("POST", "/secrets", { name: $("#jTokName").value, value: $("#jTok").value, description: "Jira API token" })); ref = `secret:${$("#jTokName").value}`; }
    else if (m !== "keep") ref = m;
    await guard(() => api("PUT", "/settings/jira", { mode: $("#jMode").value, deployment: $("#jDep").value, base_url: $("#jBase").value.trim(), email: $("#jEmail").value.trim(), token_ref: ref, default_jql: $("#jJql").value, acceptance_field: $("#jAc").value.trim() }), "Jira settings saved");
    await refreshSettings();
  };
  $("#jTest").onclick = async () => { const r = await guard(() => api("POST", "/jira/test")); toast(r.ok ? `Connected as ${r.user} (${r.mode})` : r.error, r.ok ? "ok" : "err"); };
  $("#jSearch").onclick = async () => showIssues(await guard(() => api("POST", "/jira/search", { jql: $("#jQ").value, max_results: 50 })));
  $("#mFile").onchange = async (e) => showMeta(await guard(() => uploadFile(e.target.files[0], "/metadata/import")));
});

// ------------------------------------------------------------------ model studio
route("studio", async () => {
  const runs = (await api("GET", "/runs")).filter((r) => ["design", "build", "test", "release", "operations", "consumption", "assembly", null].includes(r.current) || r.status === "completed");
  let model = store.get("adef_studio_model", null);
  main().innerHTML = `<h1>Model &amp; catalog studio</h1><div class="sub">Convert between data-modelling and data-catalog formats: load a model from a run or import an export, then download it for another tool or stack.</div>
    <div class="card"><div class="field-row"><div><label>Load from a run</label><select id="stRun"><option value="">-</option>${runs.map((r) => `<option value="${esc(r.run_id)}">${esc(r.run_id)} · ${esc(r.use_case)}</option>`).join("")}</select></div>
      <div><label>…or import a file</label><input type="file" id="stFile" accept=".csv,.json,.dbml,.sql,.ddl,.txt"></div>
      <div><label>…or a sample model</label><select id="stSample"><option value="">-</option>${CATALOG.domain_packs.map((p) => `<option>${esc(p.pack_id)}</option>`).join("")}</select></div>
      <div><label>Target Stack Profile (physical naming &amp; types)</label><select id="stProf"><option value="">none (logical)</option>${allStacks().map((s) => `<option value="${esc(s.profile_id)}">${esc(s.label || s.profile_id)}</option>`).join("")}</select></div></div></div>
    <div id="stBody"></div>`;
  const render = () => {
    if (!model) { $("#stBody").innerHTML = '<div class="card empty">Load or import a model.</div>'; return; }
    $("#stBody").innerHTML = `<div class="card"><div class="spread"><h2>${esc(model.name)}</h2><span class="muted small">${model.entities.length} entities</span></div><div class="er">${erSvg(model)}</div>${erLegend}
      <p class="small muted">Imported attributes with unknown classification default to <b>restricted</b> until a Data Steward classifies them.</p></div>
      <div class="card"><h2>Export</h2><div class="table-wrap"><table><tbody>${CATALOG.exporters.map((x) => `<tr><td><b>${esc(x.label)}</b><div class="small muted">${esc(x.desc)}</div></td><td>${badge("", x.category)}</td><td style="white-space:nowrap">${x.id === "ddl" ? `<select id="stDialect" style="width:auto;padding:4px">${CATALOG.dialects.map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select> ` : ""}<button class="btn small" data-sx="${x.id}">Download</button></td></tr>`).join("")}</tbody></table></div></div>`;
    $$("[data-sx]").forEach((b) => (b.onclick = async () => {
      const r = await guard(() => api("POST", "/models/export", { model, format: b.dataset.sx, profile_id: $("#stProf").value || undefined, dialect: b.dataset.sx === "ddl" ? $("#stDialect").value : undefined }, true));
      const blob = await r.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = (r.headers.get("content-disposition") || "").split("filename=")[1]?.replaceAll('"', "") || "export.txt"; a.click();
    }));
  };
  $("#stRun").onchange = async () => { if (!$("#stRun").value) return; model = await guard(() => api("GET", `/runs/${$("#stRun").value}/model`)); store.set("adef_studio_model", model); render(); };
  $("#stFile").onchange = async (e) => { const m = await guard(() => uploadFile(e.target.files[0], "/metadata/import")); model = m.logical_model; store.set("adef_studio_model", model); render(); };
  $("#stSample").onchange = async () => {
    const dom = $("#stSample").value; if (!dom) return;
    const f = (await api("GET", "/demo-files")).find((x) => x.domain === dom && x.name.endsWith(".logical-model.json"));
    if (!f) { toast("No sample model found - run python -m adef demo-data", "err"); return; }
    model = (await guard(() => importDemoFile(f.path, "/metadata/import"))).logical_model; store.set("adef_studio_model", model); render();
  };
  render();
});

// ------------------------------------------------------------------ guardrails
route("guardrails", async () => {
  const cls = (c) => ({ A0: "", A1: "b-info", A2: "b-warn", A3: "b-violet", A4: "b-bad" }[c]);
  main().innerHTML = `<h1>Guardrails</h1><div class="sub">Rules are enforced outside the prompts: every action is classified A0-A4 by a pre-tool-call hook, approvals are bound to artifact hashes, logs are hash-chained, and every write is scanned.</div>
    <div class="card"><div class="spread"><h2>Guardrail scenario suite (GT-01 … GT-14)</h2><button class="btn primary" id="runSuite">Run suite</button></div>
    <p class="muted small">Executes each scenario from the build specification against the real enforcement code in a temporary workspace, then cleans up.</p><div id="suiteOut"></div></div>
    <div class="card"><h2>Action classes</h2><div class="table-wrap"><table><thead><tr><th>Action</th><th>Class</th><th>Requires gate</th><th>Per-action approval</th></tr></thead><tbody>${CATALOG.action_table.map((a) => `<tr><td class="mono">${esc(a.action)}</td><td><span class="badge ${cls(a.class)}">${esc(a.class)}</span></td><td>${esc(a.gate || "-")}</td><td>${a.per_action ? "yes" : "-"}</td></tr>`).join("")}</tbody></table></div><p class="small muted">Unlisted actions default to A3. A4 actions are refused even if someone approves them in chat.</p></div>
    <div class="card"><h2>Gate approvers</h2><table>${Object.entries(CATALOG.gate_roles).map(([g, roles]) => `<tr><td><b>${esc(g)}</b></td><td>${esc(CATALOG.gate_labels[g])}</td><td>${roles.map((r) => esc(CATALOG.role_labels[r])).join(" + ")}</td></tr>`).join("")}</table></div>`;
  $("#runSuite").onclick = async () => {
    $("#suiteOut").innerHTML = '<div class="loading">Running 14 scenarios…</div>';
    const res = await guard(() => api("POST", "/guardrails/suite"));
    const passed = res.filter((r) => r.result === "pass").length;
    $("#suiteOut").innerHTML = `<div class="notice ${passed === res.length ? "" : "bad"}">${passed}/${res.length} scenarios pass</div><div class="table-wrap" style="margin-top:10px"><table><thead><tr><th>ID</th><th>Scenario</th><th>Expected</th><th>Result</th><th>Evidence</th></tr></thead><tbody>${res.map((r) => `<tr><td class="mono">${esc(r.id)}</td><td>${esc(r.scenario)}</td><td class="small">${esc(r.expected)}</td><td>${badge(r.result)}</td><td class="small">${esc(r.evidence)}</td></tr>`).join("")}</tbody></table></div>`;
  };
});

// ------------------------------------------------------------------ boot
(function theme() {
  const saved = store.get("adef_theme", null);
  if (saved) document.documentElement.dataset.theme = saved;
  $("#themeToggle").onclick = () => {
    const dark = document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    store.set("adef_theme", document.documentElement.dataset.theme);
  };
})();
window.closeModal = closeModal;
(async () => {
  try {
    await loadBase();
    const h = await api("GET", "/health");
    $("#version").textContent = `v${h.version}`;
    if (h.brand) {
      $(".brand-name").textContent = h.brand.name; $(".brand-sub").textContent = h.brand.tagline;
      $(".logo").textContent = h.brand.name.trim().charAt(0).toUpperCase(); document.title = `${h.brand.name} Console`;
    }
    await navigate();
  } catch (e) { main().innerHTML = `<div class="card"><div class="notice bad">Cannot reach the API: ${esc(e.message)}</div></div>`; }
})();
