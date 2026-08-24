"use strict";

const app = { state: null, filter: "all", grep: "", lastReceived: null, slug: decodeURIComponent(location.pathname.split("/").filter(Boolean)[0] || "") };
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const api = (p) => `/${encodeURIComponent(app.slug)}/${p}`;

const LABEL = { active: "in progress", ready: "ready", waiting: "blocked", decision: "needs decision", dream: "dream", done: "done", track: "track", missing: "missing" };
const label = (s) => LABEL[s] || String(s || "").replaceAll("_", " ");
const mark = (s) => ({ done: "[x]", active: "[~]", decision: "[!]", waiting: "[-]", dream: "[*]", track: "[#]" }[s] || "[ ]");
const cls = (s) => `state-${s || "missing"}`;

const fmtDate = (v) => {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.valueOf()) ? v : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(d);
};
const rel = (d) => {
  if (!d) return "waiting for state";
  const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  return s < 3 ? "updated now" : s < 60 ? `updated ${s}s ago` : `updated ${Math.floor(s / 60)}m ago`;
};
const ago = (v) => {
  if (!v) return "never";
  const d = new Date(v); if (Number.isNaN(d.valueOf())) return v;
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.floor(m / 60)}h ago` : `${Math.floor(m / 1440)}d ago`;
};

// "TRACK: Agentic Work OS (program umbrella)" -> "Agentic Work OS": the row
// is already inside a board; the label's job is to name the program, not
// explain what a track is.
const shortTrack = (t) => String(t || "").replace(/^\s*track\s*:\s*/i, "").replace(/\s*\([^)]*\)\s*$/, "").trim();

function matches(row) {
  if (!app.grep) return true;
  const hay = [row.id, row.title, row.track_title, row.track, row.claimant?.label, row.description].filter(Boolean).join(" ").toLowerCase();
  return hay.includes(app.grep.toLowerCase());
}

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("visible");
  window.clearTimeout(toast.timer); toast.timer = window.setTimeout(() => t.classList.remove("visible"), 2200);
}

function taskRow(row, opts = {}) {
  const st = row.effective;
  const claimant = row.claimant
    ? `<p><span class="label">claimed by</span><strong>${esc(row.claimant.label)} <span class="live-${esc(row.claimant.liveness)}">${esc(row.claimant.liveness)}</span>${row.claimant.age ? ` <span class="faint">${esc(row.claimant.age)}</span>` : ""}${row.claimant.goal ? `<br><span class="faint">${esc(row.claimant.goal)}</span>` : ""}</strong></p>`
    : "";
  const blockers = row.blockers?.length
    ? `<p><span class="label">waits on</span><strong>${row.blockers.map((b) => `<a href="#row-${esc(b.id)}">${esc(b.id)}</a> <span class="${cls(b.status === "blocked" ? "waiting" : b.status)}">${esc(label(b.status))}</span> ${esc(b.title)}`).join("<br>")}</strong></p>`
    : "";
  const dependents = row.dependents?.length ? `<p><span class="label">unblocks</span><strong>${row.dependents.map((d) => `<a href="#row-${esc(d)}">${esc(d)}</a>`).join(", ")}</strong></p>` : "";
  const commits = row.commits?.length
    ? `<p><span class="label">commits</span><strong>${row.commits.map((c) => `<span class="commit"><span class="sha">${esc(c.sha)}</span> ${esc(c.subject)} <span class="faint">${esc(ago(c.at))}</span></span>`).join("<br>")}</strong></p>`
    : "";
  const actions = [];
  if (row.prompt) actions.push(`<a href="${api("handoff")}?path=${encodeURIComponent(row.prompt)}" target="_blank" rel="noreferrer">[open handoff]</a>`);
  actions.push(`<button type="button" data-copy="${esc(row.id)}">[copy id]</button>`);
  actions.push(`<button type="button" data-copy="agent-do manna show ${esc(row.id)}">[copy show cmd]</button>`);
  const track = opts.showTrack !== false && row.track_title ? shortTrack(row.track_title) : "";
  return `
    <details class="task" id="row-${esc(row.id)}">
      <summary>
        <span class="task-check ${cls(st)}">${mark(st)}</span>
        <span class="task-id">${esc(row.id)}</span>
        <span class="task-title">${esc(row.title)}</span>
        <span class="task-track" title="${esc(row.track_title || "")}">${esc(track)}</span>
        <span class="task-state ${cls(st)}">${esc(label(st))}</span>
        <span class="task-prio">${row.order != null ? `#${row.order + 1}` : ""}</span>
      </summary>
      <div class="task-body">
        ${row.description ? `<p class="desc">${esc(row.description)}</p>` : ""}
        <div class="task-meta">
          <p><span class="label">status</span><strong>${esc(row.status)}${row.kind !== "item" ? ` · ${esc(row.kind)}` : ""}</strong></p>
          <p><span class="label">updated</span><strong>${esc(fmtDate(row.updated_at))} <span class="faint">${esc(ago(row.updated_at))}</span></strong></p>
          ${row.source ? `<p><span class="label">source</span><strong>${esc(row.source)}</strong></p>` : ""}
          ${claimant}${blockers}${dependents}${commits}
        </div>
        <div class="task-actions">${actions.join("")}</div>
      </div>
    </details>`;
}

function renderList(sel, rows, empty, opts) {
  const visible = rows.filter(matches);
  $(sel).innerHTML = visible.length ? visible.map((r) => taskRow(r, opts)).join("") : `<p class="empty">${esc(empty)}</p>`;
}

function renderHeader(s) {
  document.title = `manna / ${s.name}`;
  $("#prompt-name").textContent = s.name;
  $("#page-title").textContent = s.name.toUpperCase();
  $("#command-line").textContent = "$ agent-do manna serve";
  const g = s.git || {};
  $("#repo-state").textContent = g.is_repo ? `${g.branch || "(detached)"} / HEAD ${g.head} / ${g.dirty_paths} dirty path${g.dirty_paths === 1 ? "" : "s"}` : "not a git repository";
  $("#board-state").textContent = `${s.total} rows · workflow ${s.board.workflow || "unknown"} · ${s.board.order_count} in handoff order · issues written ${ago(s.board.issues_modified_at)}`;
  const d = s.drift;
  const drift = $("#drift-state");
  drift.textContent = !d.present ? "no drift.yaml (reconcile has not run here)" : d.count ? `${d.count} finding${d.count === 1 ? "" : "s"} as of ${ago(d.generated_at)}: ${Object.entries(d.kinds).map(([k, n]) => `${k} ${n}`).join(", ")}` : `clean as of ${ago(d.generated_at)}`;
  drift.className = d.count ? "state-decision" : "state-done";
  const live = (s.peers || []).filter((p) => p.status === "active");
  const idle = (s.peers || []).filter((p) => p.status === "idle");
  $("#peers-state").textContent = s.peers?.length ? `${live.length} active, ${idle.length} idle, ${s.peers.length - live.length - idle.length} gone` : "none on the coord board";
  const c = s.counts || {};
  $("#counts").innerHTML = [["active", "now"], ["ready", "next"], ["decision", "decisions"], ["waiting", "waiting"], ["dream", "dreams"], ["done", "all"]]
    .map(([k, anchor]) => `<a href="#${anchor}"><span class="n ${cls(k)}">${c[k] || 0}</span> <span class="muted">${label(k)}</span></a>`).join("");
}

function renderWaves(s) {
  const waves = (s.waves || []).map((w) => ({ ...w, items: w.items.filter(matches) })).filter((w) => w.items.length);
  const stray = (s.unlayered || []).filter(matches);
  let html = waves.map((w) => `
    <section class="wave">
      <div class="wave-heading"><strong>Wave ${w.wave}</strong><span>${w.items.length} item${w.items.length === 1 ? "" : "s"} · ${w.wave === 1 ? "waits on unblocked work" : `waits on wave ${w.wave - 1}`}</span></div>
      <div class="task-list">${w.items.map((r) => taskRow(r)).join("")}</div>
    </section>`).join("");
  if (stray.length) html += `<section class="wave"><div class="wave-heading"><strong>Unlayered</strong><span>${stray.length} item${stray.length === 1 ? "" : "s"} · cycle or missing blocker</span></div><div class="task-list">${stray.map((r) => taskRow(r)).join("")}</div></section>`;
  $("#waves").innerHTML = html || '<p class="empty">Nothing is blocked.</p>';
}

function renderDrift(s) {
  const d = s.drift;
  $("#drift-age").textContent = d.present ? `${d.count} finding${d.count === 1 ? "" : "s"} · ${ago(d.generated_at)}` : "no drift file";
  const rows = (d.findings || []).filter((f) => !app.grep || JSON.stringify(f).toLowerCase().includes(app.grep.toLowerCase()));
  $("#drift-list").innerHTML = rows.length
    ? rows.map((f) => `<p><span class="log-kind">${esc(f.kind)}</span><span>${f.issue_id ? `<a href="#row-${esc(f.issue_id)}">${esc(f.issue_id)}</a>` : ""}</span><span>${esc(f.detail || "")}${f.evidence ? ` <span class="faint">(${esc(f.evidence)})</span>` : ""}</span>${f.proposed_fix ? `<span class="log-fix">fix: ${esc(f.proposed_fix)}</span>` : ""}</p>`).join("")
    : `<p class="empty">${d.present ? "No findings." : "Run agent-do manna reconcile in the project to populate this."}</p>`;
}

function renderTracks(s) {
  $("#track-list").innerHTML = (s.tracks || []).map((t) => {
    const items = t.items.filter(matches);
    const open = items.filter((r) => r.effective !== "done").length;
    return `<details class="track" ${app.grep ? "open" : ""}>
      <summary><span class="task-check state-track">[#]</span><strong>${esc(shortTrack(t.title))}</strong><span>${open} open · ${items.length} shown${t.id ? " · " + esc(t.id) : ""}</span></summary>
      <div class="task-list">${items.length ? items.map((r) => taskRow(r, { showTrack: false })).join("") : '<p class="empty">nothing matches</p>'}</div>
    </details>`;
  }).join("") || '<p class="empty">No tracks on this board.</p>';
}

function renderInventory(s) {
  const rows = (s.all || []).filter((r) => r.kind !== "track").filter((r) => app.filter === "all" || r.effective === app.filter).filter(matches);
  const total = (s.all || []).filter((r) => r.kind !== "track").length;
  $("#inventory-count").textContent = `${rows.length}/${total}`;
  $("#inventory-body").innerHTML = rows.length ? rows.map((r) => `
    <tr>
      <td class="${cls(r.effective)}">${mark(r.effective)}</td>
      <td class="nowrap"><a href="#row-${esc(r.id)}">${esc(r.id)}</a></td>
      <td>${esc(r.title)}</td>
      <td class="faint nowrap">${esc(shortTrack(r.track_title || ""))}</td>
      <td class="${cls(r.effective)}">${esc(label(r.effective))}</td>
      <td class="nowrap">${esc(fmtDate(r.updated_at))}</td>
    </tr>`).join("") : '<tr><td colspan="6" class="empty">Nothing matches.</td></tr>';
}

function bindCopy() {
  $$("[data-copy]").forEach((b) => b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(b.dataset.copy); toast(`copied: ${b.dataset.copy}`); } catch { toast(b.dataset.copy); }
  }));
}

function renderAll() {
  const s = app.state; if (!s) return;
  const openIds = new Set($$("details.task[open]").map((d) => d.id));
  renderHeader(s);
  renderList("#now-list", s.now || [], "Nothing claimed right now.");
  renderList("#next-list", s.next || [], "Nothing is ready: every open item is blocked or awaiting a decision.");
  renderList("#decision-list", s.decisions || [], "No decisions pending.");
  renderWaves(s);
  renderDrift(s);
  renderTracks(s);
  renderList("#dream-list", s.dreams || [], "No dreams parked.");
  renderInventory(s);
  $("#root-path").textContent = s.root;
  $("#source-path").textContent = s.board.path;
  openIds.forEach((id) => { const el = document.getElementById(id); if (el) el.open = true; });
  bindCopy();
}

function setConn(ok, text) { $("#connection-mark").textContent = ok ? "●" : "○"; $("#connection-mark").classList.toggle("live", ok); $("#connection-label").textContent = text; }
function receive(state) { app.state = state; app.lastReceived = new Date(); setConn(true, "live"); renderAll(); }
async function fetchState() {
  try { const r = await fetch(api("api/state"), { cache: "no-store" }); if (!r.ok) throw new Error(`state request failed: ${r.status}`); receive(await r.json()); }
  catch (e) { setConn(false, "disconnected"); toast(e.message); }
}
function connect() {
  const src = new EventSource(api("api/events"));
  src.addEventListener("state", (ev) => { try { receive(JSON.parse(ev.data)); } catch { setConn(false, "bad state"); } });
  src.onopen = () => setConn(true, "live");
  src.onerror = () => setConn(false, "reconnecting");
}
$("#refresh-button").addEventListener("click", fetchState);
$("#grep").addEventListener("input", (e) => { app.grep = e.target.value.trim(); renderAll(); });
$$(".filter").forEach((b) => b.addEventListener("click", () => { app.filter = b.dataset.state; $$(".filter").forEach((x) => x.classList.toggle("active", x === b)); if (app.state) renderInventory(app.state); }));
fetchState();
connect();
window.setInterval(() => { $("#last-sync").textContent = rel(app.lastReceived); }, 1000);
