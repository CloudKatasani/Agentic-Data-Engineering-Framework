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

// ------------------------------------------------------------------ dashboard
route("dashboard", async () => {
  const runs = await api("GET", "/runs");
  const pending = runs.reduce((n, r) => n + r.pending_gates.length, 0);
  const llm = new Set(Object.values(SETTINGS.agents).map((a) => providerById(a.provider_id)?.type || "?"));
  main().innerHTML = `
    <div class="spread"><div><h1>Delivery dashboard</h1><div class="sub">Approval-gated agent team: business intent → requirements → mapping → design → build → test → release → operations → consumption.</div></div>
      <div class="row"><a class="btn primary" href="#/new">New run</a></div></div>
    <div class="grid g4">
      <div class="card kpi"><div class="l">Runs</div><div class="v">${runs.length}</div></div>
      <div class="card kpi"><div class="l">Completed</div><div class="v">${runs.filter((r) => r.status === "completed").length}</div></div>
      <div class="card kpi"><div class="l">Gates awaiting you</div><div class="v">${pending}</div></div>
      <div class="card kpi"><div class="l">Agent team</div><div class="v">${llm.size} <span class="small muted" style="font-size:13px">providers · ${new Set(Object.values(SETTINGS.agents).map((a) => a.model)).size} models</span></div><div class="small muted">${[...llm].map((t) => esc(CATALOG.provider_types[t]?.label || t)).join(" · ")}</div></div>
    </div>
    <div class="card" style="margin-top:16px">
      <h2>Runs</h2>
      ${runs.length ? `<div class="table-wrap"><table><thead><tr><th>Run</th><th>Client</th><th>Use case</th><th>Domain</th><th>Stack</th><th>Status</th><th>Current</th><th>Waiting on</th><th>Updated</th></tr></thead><tbody>
      ${runs.map((r) => `<tr class="click" data-run="${esc(r.run_id)}"><td class="mono">${esc(r.run_id)}</td><td>${esc(r.client_code)}</td><td>${esc(r.use_case)}</td><td>${esc(r.domain_pack)}</td><td>${esc(r.stack)}</td><td>${badge(r.status)}</td><td>${esc(r.current || "-")}</td><td>${r.pending_gates.map((g) => `<span class="chip pending">${esc(g)}</span>`).join(" ")}</td><td class="small muted">${fmtTime(r.updated)}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">No runs yet. <a href="#/new">Start one</a> - the offline Demo Simulator needs no API key.</div>`}
    </div>
    <div class="grid g3" style="margin-top:16px">
      <div class="card"><h2>1 · Bind models</h2><p class="muted">Pick a provider and model per agent. Keys live in the encrypted vault, never in chat or artifacts.</p><a href="#/agents">Agents &amp; models →</a></div>
      <div class="card"><h2>2 · Choose the stack</h2><p class="muted">Five reference stacks or your own Stack Profile, validated slot by slot.</p><a href="#/stacks">Technology stacks →</a></div>
      <div class="card"><h2>3 · Connect sources</h2><p class="muted">Read requirements from Jira; import catalog or modelling-tool exports.</p><a href="#/integrations">Jira &amp; metadata →</a></div>
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
    approvers: { ...SETTINGS.approver_defaults }, compute_cost_cap: 500, autopilot: true,
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
  return `<div class="option-cards">${stacksList.map((s) => `<div class="option ${s.profile_id === d.stack_id ? "sel" : ""}" data-stack="${esc(s.profile_id)}"><div class="t">${esc(s.label || s.profile_id)}</div><div class="small muted">${esc(s.description || "")}</div></div>`).join("")}</div>
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
  const agents = CATALOG.agents.map((a) => { const b = SETTINGS.agents[a.name]; const p = providerById(b.provider_id); return [a.name, p?.label || b.provider_id, b.model, b.effort]; });
  return `<div class="kv"><div class="k">Client</div><div>${esc(d.client_code)}</div><div class="k">Domain</div><div>${esc(d.domain_pack)}</div>
    <div class="k">Stack</div><div>${esc(stack?.label || d.stack_id)}</div><div class="k">Requirements</div><div>${d.req_source !== "text" ? `${d.selected_keys.length} Jira issues` : ""} ${d.request ? "· request text" : ""}</div>
    <div class="k">Metadata</div><div>${d.source_metadata ? esc(d.source_metadata.source_file) : "none"}</div><div class="k">Cost cap</div><div>${esc(d.compute_cost_cap)}</div></div>
    <h3>Agent team and models</h3><div class="table-wrap"><table><thead><tr><th>Agent</th><th>Provider</th><th>Model</th><th>Effort</th></tr></thead><tbody>${agents.map((r) => `<tr><td class="mono">${esc(r[0])}</td><td>${esc(r[1])}</td><td class="mono">${esc(r[2])}</td><td>${esc(r[3])}</td></tr>`).join("")}</tbody></table></div>
    <p class="small muted">Change bindings on <a href="#/agents">Agents &amp; models</a>.</p>`;
}
function bindWizard() {
  const d = WZ.data;
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
  const body = { client_code: d.client_code, domain_pack: d.domain_pack, use_case: d.use_case || undefined,
    request: d.req_source === "jira" ? "" : d.request, documents: d.req_source === "jira" ? "" : d.documents,
    jira_issues: issues, stack_profile: allStacks().find((s) => s.profile_id === d.stack_id),
    source_metadata: d.source_metadata, approvers: d.approvers, compute_cost_cap: +d.compute_cost_cap, autopilot: d.autopilot };
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
  main().innerHTML = `<div id="runHead"></div><div id="stepper" class="stepper"></div>
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
  $("#stepper").innerHTML = st.stage_defs.map((s, i) => {
    const ss = st.stages[s.key]; const disp = ss.display || ss.status;
    return `<div class="step s-${esc(disp)}" title="${esc(ss.error || ss.summary || disp)}"><div class="n">${i} · ${esc(disp)}</div><div class="t">${esc(s.label)}</div>
      <div class="gates">${s.gates.map((g) => `<span class="chip ${esc(st.gates_detail[g]?.state || "")}">${esc(g)}</span>`).join("")}</div></div>`;
  }).join("");
  const tabs = [["approvals", "Approvals"], ["artifacts", "Artifacts"], ["model", "Data model & exports"], ["code", "Code"], ["handoffs", "Handoffs"], ["audit", "Audit logs"], ["metrics", "Agents & cost"]];
  $("#runTabs").innerHTML = tabs.map(([k, l]) => `<div class="tab ${RUN.tab === k ? "active" : ""}" data-tab="${k}">${l}</div>`).join("");
  $$("#runTabs .tab").forEach((t) => (t.onclick = () => { RUN.tab = t.dataset.tab; store.set("adef_run_tab", RUN.tab); renderRunHead(st); renderRunBody(); }));
}
async function renderRunBody() {
  const st = RUN.status; const el = $("#runBody");
  if (RUN.tab === "approvals") return renderApprovals(st, el);
  if (RUN.tab === "artifacts") return renderArtifacts(el);
  if (RUN.tab === "model") return renderRunModel(el);
  if (RUN.tab === "code") return renderCode(el);
  if (RUN.tab === "handoffs") return renderHandoffs(el);
  if (RUN.tab === "audit") return renderAudit(el);
  if (RUN.tab === "metrics") return renderMetrics(st, el);
}
function renderApprovals(st, el) {
  const blocks = [];
  st.stage_defs.forEach((s) => {
    const ss = st.stages[s.key];
    if (["failed", "blocked", "rejected"].includes(ss.status)) {
      blocks.push(`<div class="card gate-card rejected"><div class="spread"><h2>${esc(s.label)} · ${badge(ss.status)}</h2></div>
        <div class="notice bad">${esc(ss.error || "")}</div>
        <label>Rework instructions for ${esc(s.agent)}</label><textarea id="fb-${s.key}" placeholder="What exactly must change (artifact, section, defect)"></textarea>
        <div class="row" style="margin-top:8px"><button class="btn primary" data-rework="${s.key}">Send back for rework</button><button class="btn" data-retry="${s.key}">Retry as-is</button></div></div>`);
    }
  });
  const gates = Object.entries(st.gates_detail).filter(([, g]) => g.state !== "not-requested");
  const order = { pending: 0, stale: 1, rejected: 2, approved: 3, expired: 4 };
  gates.sort((a, b) => (order[a[1].state] ?? 9) - (order[b[1].state] ?? 9) || b[0].localeCompare(a[0]));
  gates.forEach(([g, gd]) => blocks.push(gateCard(st, g, gd)));
  const running = st.stage_defs.filter((s) => st.stages[s.key].status === "running");
  if (running.length) blocks.unshift(`<div class="card"><div class="notice">${running.map((s) => `<b>${esc(s.label)}</b> in progress - ${esc(s.agent)} is working…`).join("<br>")}</div></div>`);
  if (st.status === "completed") blocks.unshift(`<div class="card"><div class="notice">Run complete. <a href="#" id="openPack">Open the delivery pack</a> · exports are under <b>Data model &amp; exports</b>.</div></div>`);
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
  $$("[data-rereq]").forEach((b) => (b.onclick = () => guard(() => api("POST", `/runs/${RUN.id}/gates/${b.dataset.rereq}/rerequest`), "Gate re-opened").then(() => refreshRun(true))));
  $$("[data-open]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); RUN.tab = "artifacts"; RUN.file = a.dataset.open; renderRunHead(st); renderRunBody(); }));
  if ($("#openPack")) $("#openPack").onclick = (e) => { e.preventDefault(); RUN.tab = "artifacts"; RUN.file = "final/delivery-pack.md"; renderRunHead(st); renderRunBody(); };
}
function gateCard(st, g, gd) {
  const req = gd.request || {};
  const roles = req.required_roles || [];
  const decided = Object.fromEntries((gd.decisions || []).map((d) => [d.role_key, d]));
  const roleRows = roles.map((r) => {
    const d = decided[r];
    return `<div class="role-row"><div><b>${esc(st.role_labels[r])}</b><div class="small muted">named approver</div></div>
      <input id="a-${g}-${r}" value="${esc(st.run.approvers[r] || "")}" ${d || gd.state !== "pending" ? "disabled" : ""}>
      <div class="row">${d ? badge(d.decision.startsWith("approved") ? "approved" : "rejected", `${d.decision} · ${short(d.approval_id, 8)}`) : gd.state === "pending"
        ? `<button class="btn ok small" data-decide="${g}|${r}|approved">Approve</button><button class="btn bad small" data-decide="${g}|${r}|rejected">Reject</button>` : ""}</div></div>`;
  }).join("");
  const arts = Object.entries(req.artifacts || {});
  return `<div class="card gate-card ${esc(gd.state)}">
    <div class="spread"><div><h2>${esc(g)} · ${esc(st.gate_labels[g])}</h2><div class="small muted">${esc(req.request_id)} · ${esc(req.action_class)} · expires ${esc(req.expires)}</div></div>${badge(gd.state === "pending" ? "awaiting-approval" : gd.state, gd.state)}</div>
    ${gd.state === "stale" ? `<div class="notice warn" style="margin:10px 0">Approval drift: ${esc(gd.changed_artifacts.join(", "))} changed after the request. The approval no longer covers these hashes. <button class="btn small" data-rereq="${g}">Re-request ${g}</button></div>` : ""}
    <p>${esc(req.summary)}</p>
    <div class="kv"><div class="k">Risk</div><div>${esc(req.risk)}</div><div class="k">Cost</div><div>${esc(req.cost)}</div><div class="k">Rollback</div><div>${esc(req.rollback)}</div>
    <div class="k">Options</div><div>${(req.options || []).map(esc).join(" · ")}</div>
    <div class="k">Evidence</div><div>${(req.evidence || []).map((p) => `<a href="#" data-open="${esc(p)}">${esc(p)}</a>`).join("<br>") || "-"}</div>
    <div class="k">Bundle hash</div><div class="hash">${esc(req.artifact_sha256)}</div></div>
    <details style="margin-top:8px"><summary class="small muted">${arts.length} artifacts bound to this approval</summary>
      <table class="small">${arts.map(([p, h]) => `<tr><td><a href="#" data-open="${esc(p)}">${esc(p)}</a></td><td class="hash">${short(h, 16)}</td></tr>`).join("")}</table></details>
    ${gd.conditions?.length ? `<div class="notice" style="margin-top:8px">Binding conditions: ${gd.conditions.map(esc).join("; ")}</div>` : ""}
    ${gd.state === "pending" ? `<label>Comment (required to reject: exact artifact, section and defect)</label><input id="c-${g}"><label>Conditions (optional, one per line - become binding constraints downstream)</label><textarea id="k-${g}" style="min-height:44px"></textarea>` : `<input id="c-${g}" type="hidden">`}
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
  el.innerHTML = `<div class="grid g3"><div class="card kpi"><div class="l">LLM tokens</div><div class="v">${tot.t.toLocaleString()}</div></div><div class="card kpi"><div class="l">LLM cost (list price)</div><div class="v">$${tot.c.toFixed(3)}</div></div><div class="card kpi"><div class="l">Guardrail blocks</div><div class="v">${st.metrics.guardrail_blocks || 0}</div></div></div>
    <div class="card"><h2>Agent team for this run</h2><div class="table-wrap"><table><thead><tr><th>Agent</th><th>Bound to</th><th>Served by</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td class="${i < 3 ? "mono small" : ""}">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    <p class="small muted">"Served by" shows what actually ran. A simulated stage means the bound provider had no key or could not be reached and the demo fallback was on. Bindings are captured when the run is created.</p></div>`;
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
    $$("[data-slot]").forEach((s) => (s.onchange = () => { if (s.value === "__custom") { const v = prompt(`Tool for ${s.dataset.slot}`); if (v) { s.insertAdjacentHTML("afterbegin", `<option selected>${esc(v)}</option>`); } } }));
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
  main().innerHTML = `<h1>Jira &amp; metadata</h1><div class="sub">Read requirements from Jira (read-only, action class A0) and bring in catalog or data-modelling exports as source metadata.</div>
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
      <select id="ddDomain" style="width:auto">${CATALOG.domain_packs.map((p) => `<option>${esc(p.pack_id)}</option>`).join("")}</select></div>
      <div id="ddOut" style="margin-top:12px"></div></div>`;
  const demo = await api("GET", "/demo-files");
  const ACTIONS = { jira: ["Preview issues", "jira"], "source-metadata": ["Import as metadata", "meta"], model: ["Open in studio", "studio"] };
  const renderDemo = () => {
    const dom = $("#ddDomain").value;
    const files = demo.filter((f) => f.domain === dom);
    const groups = {};
    files.forEach((f) => (groups[f.folder || "-"] = groups[f.folder || "-"] || []).push(f));
    $("#ddOut").innerHTML = files.length ? `<div class="table-wrap"><table><thead><tr><th>Folder</th><th>File</th><th>Size</th><th></th></tr></thead><tbody>${Object.entries(groups).map(([g, fs]) => fs.map((f, i) => {
      const act = ACTIONS[g]; const canAct = act && (g !== "model" || f.name.endsWith(".logical-model.json") || f.name.endsWith(".dbml")) && (g !== "source-metadata" || f.name.endsWith(".csv") || f.name.endsWith(".sql"));
      return `<tr><td>${i === 0 ? `<b>${esc(g)}</b>` : ""}</td><td class="mono small">${esc(f.name)}</td><td class="small muted">${(f.bytes / 1024).toFixed(1)} KB</td><td style="white-space:nowrap"><button class="btn small" data-dl="${esc(f.path)}">Download</button>${canAct ? ` <button class="btn small" data-act="${act[1]}" data-path="${esc(f.path)}">${act[0]}</button>` : ""}</td></tr>`;
    }).join("")).join("")}</tbody></table></div>` : '<div class="empty">No demo files found. Run <code>python -m adef demo-data</code>.</div>';
    $$("[data-dl]").forEach((b) => (b.onclick = () => download(`/demo-files/file?path=${encodeURIComponent(b.dataset.dl)}`, b.dataset.dl.split("/").pop())));
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
    await navigate();
  } catch (e) { main().innerHTML = `<div class="card"><div class="notice bad">Cannot reach the ADEF API: ${esc(e.message)}</div></div>`; }
})();
