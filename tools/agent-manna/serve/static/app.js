"use strict";

// ------------------------------------------------------------ state
const app = {
  state: null, boards: null,
  slug: decodeURIComponent(location.pathname.split("/").filter(Boolean)[0] || ""),
  sheet: "board", mode: "list", chips: { done: false, dreams: false }, track: "", grep: "",
  selected: null, // {kind: "item"|"peer", id}
  lastReceived: null, paletteIndex: 0, paletteEntries: [],
};
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const api = (p) => `/${encodeURIComponent(app.slug)}/${p}`;
const clip = (t, n) => { const v = String(t || "").replace(/\s+/g, " ").trim(); return v.length > n ? v.slice(0, n - 1) + "…" : v; };
const shortTrack = (t) => String(t || "").replace(/^\s*track\s*:\s*/i, "").replace(/\s*\([^)]*\)\s*$/, "").trim();

const LABEL = { active: "in progress", ready: "ready", waiting: "blocked", decision: "decision", dream: "dream", done: "done", track: "track" };
const label = (s) => LABEL[s] || String(s || "").replaceAll("_", " ");
const ATTN = { "needs-user": "needs you", failed: "failed", working: "working", present: "present", idle: "idle", finished: "finished", ended: "ended", gone: "gone", unseen: "unseen" };
const attn = (a) => ATTN[a] || String(a || "");
const cls = (s) => "c-" + String(s || "faint").replace(/[^a-z-]/g, "");

const fmtDate = (v) => { if (!v) return "—"; const d = new Date(v); return Number.isNaN(d.valueOf()) ? v : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(d); };
const ago = (v) => { if (!v) return "never"; const d = new Date(v); if (Number.isNaN(d.valueOf())) return v; const m = Math.floor((Date.now() - d.getTime()) / 60000); return m < 1 ? "now" : m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h` : `${Math.floor(m / 1440)}d`; };
const rel = (d) => { if (!d) return "waiting for state"; const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000)); return s < 3 ? "updated now" : s < 60 ? `updated ${s}s ago` : `updated ${Math.floor(s / 60)}m ago`; };

function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("visible"); window.clearTimeout(toast.timer); toast.timer = window.setTimeout(() => t.classList.remove("visible"), 1800); }

// ------------------------------------------------------------ derived
const rowText = (r) => r.digest || r.title;
function matches(r) {
  if (!app.grep) return true;
  const hay = [r.id, r.title, r.digest, r.track_title, r.claimant?.label, r.description].filter(Boolean).join(" ").toLowerCase();
  return hay.includes(app.grep.toLowerCase());
}
function trackOk(r) { return !app.track || r.track === app.track || (app.track === "(none)" && !r.track); }

// The inbox is asks only: every row is who/what · the ask · the verb you perform.
const VERB_RANK = ["grant", "fix", "rule", "split", "close", "read", "launch"];
function inboxRows(s) {
  const out = [];
  for (const p of s.peers || []) {
    if (p.attention === "needs-user") out.push({ kind: "peer", color: "needs-user", text: `${p.alias || p.agent_id} · ${p.pulse?.latest_prompt ? "“" + clip(p.pulse.latest_prompt, 90) + "”" : p.goal || "waiting on you"}`, verb: "grant", target: { kind: "peer", id: p.agent_id } });
    if (p.attention === "failed") out.push({ kind: "peer", color: "failed", text: `${p.alias || p.agent_id} · ${p.goal || "failed"}`, verb: "fix", target: { kind: "peer", id: p.agent_id } });
  }
  for (const r of s.decisions || []) out.push({ kind: "decision", color: "decision", text: rowText(r), verb: "rule", target: { kind: "item", id: r.id } });
  for (const c of (s.coord?.contention || [])) out.push({ kind: "contention", color: "waiting", text: `${c.paths.join(", ")} · ${c.owners.join(" and ")}`, verb: "split", target: { kind: "sheet", id: "coord" } });
  for (const f of (s.drift?.findings || [])) if (f.kind === "landed_open" && f.issue_id) out.push({ kind: "landed", color: "decision", text: `${f.issue_id} landed (${f.evidence || "commit"}) but is still open`, verb: "close", target: { kind: "item", id: f.issue_id } });
  for (const d of (s.coord?.drops || [])) out.push({ kind: "drop", color: "muted", text: `${Array.isArray(d.path) ? d.path.join(", ") : d.path || "note"} · ${clip(d.note || "", 80)} · from ${d.owner}`, verb: "read", target: { kind: "sheet", id: "coord" } });
  const first = (s.next || [])[0];
  if (first) out.push({ kind: "ready", color: "ready", text: `${rowText(first)} · priority #${(first.order ?? 0) + 1}`, verb: "launch", target: { kind: "item", id: first.id } });
  out.sort((a, b) => VERB_RANK.indexOf(a.verb) - VERB_RANK.indexOf(b.verb));
  return out.filter((x) => !app.grep || x.text.toLowerCase().includes(app.grep.toLowerCase()));
}

// ------------------------------------------------------------ rendering: rows
function itemRow(r) {
  const sel = app.selected?.kind === "item" && app.selected.id === r.id;
  const st = r.effective;
  const needs = st === "active" && r.claimant?.attention === "needs-user";
  const stateText = st === "waiting" && r.blockers?.length ? `blocked · ${r.blockers.map((b) => b.id.replace(/^mn-/, "")).slice(0, 3).join(", ")}` : needs ? "needs you" : label(st);
  return `<div class="row ${needs ? "s-needs-user" : "s-" + esc(st)}${sel ? " selected" : ""}" data-item="${esc(r.id)}" role="button" tabindex="0">
    <span class="id">${esc(r.id)}</span>
    <span class="digest${r.digest ? "" : " fallback"}" title="${esc(r.title)}">${esc(rowText(r))}</span>
    <span class="track">${esc(shortTrack(r.track_title))}</span>
    <span class="pill ${needs ? "c-needs-user" : cls(st)}">${esc(stateText)}</span>
    <span class="prio">${r.order != null ? `#${r.order + 1}` : ""}</span>
  </div>`;
}
function section(lbl, cap, rows, empty) {
  return `<div class="sheet-head"><span class="prompt">manna ${esc(lbl)}</span><span class="cap">${esc(cap)}</span></div><div class="list">${rows.length ? rows.map(itemRow).join("") : `<p class="empty">${esc(empty)}</p>`}</div>`;
}
function renderBoard(s) {
  const el = $("#board-list");
  if (app.mode === "timeline") { el.innerHTML = renderTimeline(s); return; }
  const f = (rows) => rows.filter((r) => trackOk(r) && matches(r));
  let html = "";
  html += section("now", `${f(s.now || []).length} · claimed · liveness from coord`, f(s.now || []), "nothing claimed");
  html += section("next", `${f(s.next || []).length} · unblocked · handoff order`, f(s.next || []), "nothing is ready");
  const waiting = [];
  for (const w of s.waves || []) for (const r of w.items) waiting.push(r);
  for (const r of s.unlayered || []) waiting.push(r);
  html += section("waiting", `${f(waiting).length} · waves from the blocker graph`, f(waiting), "nothing is blocked");
  if (app.chips.dreams) html += section("dreams", `${f(s.dreams || []).length} · parked · not claimable`, f(s.dreams || []), "no dreams parked");
  if (app.chips.done) {
    const done = (s.all || []).filter((r) => r.effective === "done").sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    html += section("done", `${f(done).length}`, f(done), "nothing done yet");
  }
  el.innerHTML = html;
}
function renderTimeline(s) {
  const f = (rows) => rows.filter((r) => trackOk(r) && matches(r));
  const lane = (lbl, colorCls, rows) => rows.length ? `<div class="tl ${colorCls}"><span class="lbl">${esc(lbl)}</span><span class="bar"></span><div class="items">${rows.map((r) => `<span class="item${app.selected?.kind === "item" && app.selected.id === r.id ? " selected" : ""}" data-item="${esc(r.id)}" title="${esc(r.title)}"><span class="id">${esc(r.id)}</span>${esc(clip(rowText(r), 60))}${r.blockers?.length ? ` <span class="faint">← ${esc(r.blockers.map((b) => b.id.replace(/^mn-/, "")).join(", "))}</span>` : ""}</span>`).join("")}</div></div>` : "";
  let html = `<div class="sheet-head"><span class="prompt">manna timeline</span><span class="cap">now → ready → waves → done</span></div>`;
  html += lane("now", "c-active", f(s.now || []));
  html += lane("ready", "c-ready", f(s.next || []));
  for (const w of s.waves || []) html += lane(`wave ${w.wave}`, "c-waiting", f(w.items));
  if ((s.unlayered || []).length) html += lane("unlayered", "c-faint", f(s.unlayered));
  if (app.chips.done) html += lane("done", "c-faint", f((s.all || []).filter((r) => r.effective === "done")));
  return html;
}
function renderInbox(s) {
  const rows = inboxRows(s);
  $("#inbox-cap").textContent = rows.length ? `${rows.length} ask${rows.length === 1 ? "" : "s"} · ranked by verb` : "nothing wants you";
  $("#inbox-list").innerHTML = rows.length ? rows.map((x) => `<div class="row inbox s-${esc(x.color)}" data-target-kind="${esc(x.target.kind)}" data-target-id="${esc(x.target.id)}" role="button" tabindex="0">
      <span class="kind">${esc(x.kind)}</span><span class="text">${esc(x.text)}</span><span class="pill verb ${cls(x.color)}">${esc(x.verb)}</span>
    </div>`).join("") : `<p class="empty">Nothing is waiting on you.</p>`;
}
function peerRow(p) {
  const sel = app.selected?.kind === "peer" && app.selected.id === p.agent_id;
  const what = p.goal || (p.pulse?.latest_prompt ? "“" + clip(p.pulse.latest_prompt, 100) + "”" : "");
  const holding = (p.holding || []).map((h) => `<a href="#item/${esc(h.id)}" data-item="${esc(h.id)}">${esc(h.id)}</a>`).join(" ");
  return `<div class="row peer s-${esc(p.attention)}${sel ? " selected" : ""}" data-peer="${esc(p.agent_id)}" role="button" tabindex="0">
    <span class="id" title="${esc(p.agent_id)}">${esc(p.alias || p.agent_id)}</span>
    <span class="text">${what ? esc(what) : '<span class="faint">no focus declared</span>'}${p.pulse?.activity ? `<span class="sub">${esc(p.pulse.activity)}</span>` : ""}</span>
    <span class="track">${holding}</span>
    <span class="pill ${cls(p.attention)}">${esc(attn(p.attention))}</span>
    <span class="age">${esc(p.age || "")}</span>
  </div>`;
}
function renderCoord(s) {
  const peers = (s.peers || []).filter((p) => !app.grep || [p.agent_id, p.alias, p.goal, p.pulse?.latest_prompt].filter(Boolean).join(" ").toLowerCase().includes(app.grep.toLowerCase()));
  const needs = peers.filter((p) => p.attention === "needs-user" || p.attention === "failed");
  const here = peers.filter((p) => p.attention !== "gone" && !needs.includes(p));
  const gone = peers.filter((p) => p.attention === "gone");
  const c = s.coord || { claims: [], contention: [], drops: [] };
  const head = (l, cap) => `<div class="sheet-head"><span class="prompt">coord ${esc(l)}</span><span class="cap">${esc(cap)}</span></div>`;
  let html = head("needs you", `${needs.length}`) + `<div class="list">${needs.length ? needs.map(peerRow).join("") : '<p class="empty">Nobody is waiting on you.</p>'}</div>`;
  html += head("peers", `${here.length} here · ${gone.length} gone`) + `<div class="list">${here.length ? here.map(peerRow).join("") : '<p class="empty">No live sessions.</p>'}</div>`;
  const claims = c.claims.filter((x) => !app.grep || `${x.path} ${x.owner} ${x.reason || ""}`.toLowerCase().includes(app.grep.toLowerCase()));
  html += head("claims", `${claims.filter((x) => !x.stale).length} live${c.contention.length ? ` · ${c.contention.length} contended` : ""}`) + `<div class="list">${claims.length ? claims.map((x) => `<div class="row claim ${x.contended ? "s-waiting" : x.stale ? "s-gone" : "s-ready"}">
      <span class="text" title="${esc(x.path)}">${esc(x.path)}${x.reason ? `<span class="sub">${esc(x.reason)}</span>` : ""}</span>
      <span class="id" title="${esc(x.owner)}">${esc(x.owner_alias || x.owner)}</span>
      <span class="pill ${x.contended ? "c-waiting" : x.stale ? "c-faint" : "c-ready"}">${x.contended ? "contended" : x.stale ? `stale · ${esc(x.owner_status || "gone")}` : esc(x.strength || "claimed")}</span>
      <span class="age">${esc(ago(x.updated_at))}</span></div>`).join("") : '<p class="empty">No advisory claims.</p>'}</div>`;
  html += head("drops", `${c.drops.length}`) + `<div class="list">${c.drops.length ? c.drops.map((d) => `<div class="row drop s-muted">
      <span class="id">${esc(d.owner)} → ${esc(d.for || "any")}</span>
      <span class="text">${esc(Array.isArray(d.path) ? d.path.join(", ") : d.path || "")}${d.note ? `<span class="sub">${esc(d.note)}</span>` : ""}</span>
      <span class="age">${esc(ago(d.created_at))}</span></div>`).join("") : '<p class="empty">No drops waiting.</p>'}</div>`;
  if (gone.length) html += head("gone", `${gone.length} · dead, stopped, or stale`) + `<div class="list">${gone.map(peerRow).join("")}</div>`;
  $("#coord-list").innerHTML = html;
}
function renderDebug(s) {
  const d = s.drift || {};
  const kv = (k, v) => `<span>${esc(k)}</span><b>${v}</b>`;
  let html = `<div class="sheet-head"><span class="prompt">manna debug</span><span class="cap">the record about the record</span></div>`;
  html += `<div class="kv">
    ${kv("drift", d.source === "reconcile" ? `${d.count} live · ${Object.entries(d.kinds || {}).map(([k, n]) => `${esc(k)} ${n}`).join(", ") || "clean"}` : `${d.count ?? 0} from file`)}
    ${kv("drift file", d.file?.present ? `${d.file.count} findings · written ${esc(ago(d.file.generated_at))} ago` : "no drift.yaml written yet")}
    ${kv("board", `${s.total} rows · workflow ${esc(s.board?.workflow || "unknown")} · ${s.board?.order_count} in handoff order · issues written ${esc(ago(s.board?.issues_modified_at))} ago`)}
    ${kv("repo", s.git?.is_repo ? `${esc(s.git.branch || "(detached)")} / HEAD ${esc(s.git.head)} / ${s.git.dirty_paths} dirty` : "not a git repository")}
    ${kv("coord", `presence ${esc(s.coord_refreshed_ago)}s old · ${(s.peers || []).length} rows`)}
    ${kv("digests", `${s.digests?.ready ?? 0} ready · ${s.digests?.missing ?? 0} missing${s.digests?.generating ? " · generating" : ""}${s.digests?.model ? ` · ${esc(s.digests.model)}` : ""}`)}
    ${kv("root", esc(s.root))}
    ${kv("markers", (s.board?.decision_markers || []).map(esc).join(" "))}
  </div>`;
  const rows = (d.findings || []).filter((f) => !app.grep || JSON.stringify(f).toLowerCase().includes(app.grep.toLowerCase()));
  html += `<div class="sheet-head"><span class="prompt">manna reconcile</span><span class="cap">${rows.length} finding${rows.length === 1 ? "" : "s"}</span></div><div class="list">`;
  html += rows.length ? rows.map((f) => `<div class="row finding s-decision"><span class="kind">${esc(f.kind)}</span><span class="id">${f.issue_id ? `<a href="#item/${esc(f.issue_id)}" data-item="${esc(f.issue_id)}">${esc(f.issue_id)}</a>` : ""}</span><span class="text">${esc(f.detail || "")}${f.evidence ? ` <span class="faint">(${esc(f.evidence)})</span>` : ""}${f.proposed_fix ? `<span class="sub">fix: ${esc(f.proposed_fix)}</span>` : ""}</span></div>`).join("") : '<p class="empty">No findings.</p>';
  html += "</div>";
  $("#debug-list").innerHTML = html;
}

// ------------------------------------------------------------ inspector
function renderInspector(s) {
  const el = $("#inspector");
  const sel = app.selected;
  if (!sel) { el.innerHTML = '<p class="empty">select a row · ⌘K to jump</p>'; return; }
  if (sel.kind === "peer") {
    const p = (s.peers || []).find((x) => x.agent_id === sel.id);
    if (!p) { el.innerHTML = '<p class="empty">that session is no longer on the board</p>'; return; }
    const pu = p.pulse || {};
    el.innerHTML = `<div class="head"><span class="pill ${cls(p.attention)}">${esc(attn(p.attention))}</span><span>${esc(p.runtime || "")}${p.role ? " · " + esc(p.role) : ""}</span></div>
      <h2>${esc(p.alias || p.agent_id)}</h2>
      ${p.goal ? `<div class="digest-line">${esc(p.goal)}</div>` : ""}
      ${pu.latest_prompt ? `<div class="desc">“${esc(pu.latest_prompt)}”</div>` : ""}
      <div class="meta">
        <span>session</span><b>${esc(p.agent_id)}</b>
        <span>liveness</span><b><span class="${cls(p.status)}">${esc(p.status)}</span> ${esc(p.age || "")}</b>
        ${pu.status ? `<span>pulse</span><b>${esc(pu.status)}${pu.activity ? " · " + esc(pu.activity) : ""}${pu.updated_at ? ` <span class="faint">${esc(ago(pu.updated_at))} ago</span>` : ""}</b>` : ""}
        ${pu.todo?.total ? `<span>todo</span><b>${esc(pu.todo.done)}/${esc(pu.todo.total)}${pu.todo.current ? " · " + esc(pu.todo.current) : ""}</b>` : ""}
        ${(p.holding || []).length ? `<span>holding</span><b>${p.holding.map((h) => `<a href="#item/${esc(h.id)}" data-item="${esc(h.id)}">${esc(h.id)}</a> ${esc(h.title)}`).join("<br>")}</b>` : ""}
        ${(p.paths || []).length ? `<span>paths</span><b>${p.paths.map(esc).join("<br>")}</b>` : ""}
      </div>
      <div class="actions"><span class="muted">copy:</span><button type="button" data-copy="${esc(p.agent_id)}" data-label="session">[session]</button><button type="button" data-copy="agent-do coord pulse show ${esc(p.agent_id)}" data-label="pulse cmd">[pulse cmd]</button></div>`;
    bindCopy(); return;
  }
  const r = (s.all || []).find((x) => x.id === sel.id);
  if (!r) { el.innerHTML = '<p class="empty">that item is no longer on the board</p>'; return; }
  const st = r.effective;
  const cl = r.claimant;
  el.innerHTML = `<div class="head"><span>${esc(r.id)}</span><span class="pill ${cls(st)}">${esc(label(st))}</span>${r.order != null ? `<span>#${r.order + 1}</span>` : ""}${r.kind !== "item" ? `<span>${esc(r.kind)}</span>` : ""}</div>
    <h2>${esc(r.title)}</h2>
    ${r.digest ? `<div class="digest-line">${esc(r.digest)}</div>` : ""}
    ${r.description ? `<div class="desc">${esc(r.description)}</div>` : ""}
    <div class="meta">
      <span>track</span><b>${esc(shortTrack(r.track_title) || "—")}</b>
      <span>updated</span><b>${esc(fmtDate(r.updated_at))} <span class="faint">${esc(ago(r.updated_at))} ago</span></b>
      ${r.source ? `<span>source</span><b>${esc(r.source)}</b>` : ""}
      ${cl ? `<span>claimed by</span><b>${esc(cl.label)} <span class="${cls(cl.attention)}">${esc(attn(cl.attention))}</span>${cl.pulse?.activity ? ` · ${esc(cl.pulse.activity)}` : ""}${cl.goal ? `<br><span class="faint">${esc(cl.goal)}</span>` : ""}</b>` : ""}
      ${r.blockers?.length ? `<span>waits on</span><b>${r.blockers.map((b) => `<a href="#item/${esc(b.id)}" data-item="${esc(b.id)}">${esc(b.id)}</a> <span class="${cls(b.status === "blocked" ? "waiting" : b.status)}">${esc(label(b.status))}</span> ${esc(clip(b.title, 48))}`).join("<br>")}</b>` : ""}
      ${r.dependents?.length ? `<span>unblocks</span><b>${r.dependents.map((d) => `<a href="#item/${esc(d)}" data-item="${esc(d)}">${esc(d)}</a>`).join(", ")}</b>` : ""}
      ${r.commits?.length ? `<span>commits</span><b>${r.commits.map((c) => `<span class="commit"><span class="sha">${esc(c.sha)}</span> ${esc(clip(c.subject, 56))} <span class="faint">${esc(ago(c.at))}</span></span>`).join("<br>")}</b>` : `<span>commits</span><b class="faint">none yet</b>`}
      ${r.prompt ? `<span>handoff</span><b class="faint">${esc(r.prompt)}</b>` : ""}
    </div>
    <div class="actions"><span class="muted">copy:</span>${r.prompt ? `<button type="button" data-copy="${esc(r.prompt)}" data-label="handoff">[handoff]</button>` : ""}<button type="button" data-copy="${esc(r.id)}" data-label="id">[id]</button><button type="button" data-copy="agent-do manna show ${esc(r.id)}" data-label="show cmd">[show cmd]</button></div>`;
  bindCopy();
}
function bindCopy() {
  $$("[data-copy]").forEach((b) => b.addEventListener("click", async (e) => {
    e.preventDefault(); e.stopPropagation();
    const text = b.dataset.copy;
    try { await navigator.clipboard.writeText(text); b.textContent = "[copied]"; b.classList.add("copied"); toast(`copied ${text}`); window.setTimeout(() => { b.textContent = `[${b.dataset.label}]`; b.classList.remove("copied"); }, 1600); }
    catch { toast(`copy failed; select it: ${text}`); }
  }));
}

// ------------------------------------------------------------ chrome
function renderChrome(s) {
  document.title = `manna / ${s.name}`;
  $("#crumb-name").textContent = s.name;
  const asks = inboxRows(s).length;
  $("[data-badge=inbox]").textContent = asks ? String(asks) : "";
  const needs = (s.attention?.["needs-user"] || 0) + (s.attention?.failed || 0);
  $("[data-badge=coord]").textContent = needs ? String(needs) : "";
  const d = s.drift || {};
  $("#strip-slug").textContent = `[${s.name}]`;
  $("#strip-drift").innerHTML = d.count ? `<span class="warn">▲ ${d.count} drift</span>` : `drift clean`;
  $("#strip-file").textContent = d.file?.present ? `file ${ago(d.file.generated_at)}` : "no drift file";
  $("#strip-health").textContent = `presence ${s.coord_refreshed_ago ?? "?"}s · ${s.git?.dirty_paths ?? 0} dirty · ${(s.peers || []).filter((p) => p.attention !== "gone").length} here`;
  const dg = s.digests || {};
  $("#strip-digests").textContent = dg.missing ? `digests ${dg.ready}/${dg.ready + dg.missing}${dg.generating ? " …" : ""}` : (dg.ready ? `digests ${dg.ready}` : "");
  const sel = $("#track-filter");
  const current = sel.value;
  const tracks = (s.tracks || []).map((t) => [t.id || "(none)", shortTrack(t.title)]);
  sel.innerHTML = `<option value="">track ▾</option>` + tracks.map(([id, t]) => `<option value="${esc(id)}"${id === current ? " selected" : ""}>${esc(t)}</option>`).join("");
}
function showSheet(name) {
  app.sheet = name;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.sheet === name));
  for (const id of ["inbox", "board", "coord", "debug"]) $(`#sheet-${id}`).hidden = id !== name;
  $("#debug-button").textContent = name === "debug" ? "debug ▾" : "debug ▸";
}
function renderAll() {
  const s = app.state; if (!s) return;
  renderChrome(s); renderInbox(s); renderBoard(s); renderCoord(s); renderDebug(s); renderInspector(s);
}

// ------------------------------------------------------------ selection + routing
function select(kind, id, opts = {}) {
  app.selected = { kind, id };
  if (kind === "peer" && !opts.keepSheet) showSheet("coord");
  if (kind === "item" && !opts.keepSheet && app.sheet !== "board" && app.sheet !== "debug") showSheet("board");
  history.replaceState(null, "", `#${kind}/${encodeURIComponent(id)}`);
  renderAll();
  const el = document.querySelector(`[data-${kind}="${CSS.escape(id)}"]`);
  if (el && opts.scroll !== false) el.scrollIntoView({ block: "nearest" });
}
function readHash() {
  const h = location.hash.replace(/^#/, "");
  if (!h) return;
  const [kind, id] = h.split("/");
  if (kind === "item" || kind === "peer") { app.selected = { kind, id: decodeURIComponent(id || "") }; if (kind === "peer") app.sheet = "coord"; }
  else if (["inbox", "board", "coord", "debug"].includes(kind)) app.sheet = kind;
}
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-item], [data-peer], [data-target-kind], .tab, .chip, .mode, #debug-button, #jump-button");
  if (!t) return;
  if (t.matches(".tab")) { showSheet(t.dataset.sheet); history.replaceState(null, "", `#${t.dataset.sheet}`); return; }
  if (t.matches("#debug-button")) { showSheet(app.sheet === "debug" ? "board" : "debug"); return; }
  if (t.matches("#jump-button")) { openPalette(); return; }
  if (t.matches(".chip")) { const c = t.dataset.chip; if (c === "live") { app.chips = { done: false, dreams: false }; } else { app.chips[c] = !app.chips[c]; } $$(".chip").forEach((x) => x.classList.toggle("active", x.dataset.chip === "live" ? !app.chips.done && !app.chips.dreams : !!app.chips[x.dataset.chip])); renderBoard(app.state); return; }
  if (t.matches(".mode")) { app.mode = t.dataset.mode; $$(".mode").forEach((x) => x.classList.toggle("active", x === t)); renderBoard(app.state); return; }
  if (t.dataset.targetKind) { e.preventDefault(); const k = t.dataset.targetKind, id = t.dataset.targetId; if (k === "sheet") { showSheet(id); history.replaceState(null, "", `#${id}`); } else select(k, id); return; }
  if (t.dataset.item) { e.preventDefault(); select("item", t.dataset.item, { keepSheet: app.sheet === "board" || app.sheet === "debug" }); return; }
  if (t.dataset.peer) { e.preventDefault(); select("peer", t.dataset.peer, { keepSheet: true }); return; }
});
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
  if (e.key === "Escape" && !$("#palette").hidden) { closePalette(); return; }
  if (e.key === "Enter" && e.target.matches(".row")) { e.target.click(); }
});
$("#track-filter").addEventListener("change", (e) => { app.track = e.target.value; renderBoard(app.state); });
$("#grep").addEventListener("input", (e) => { app.grep = e.target.value.trim(); renderAll(); });

// ------------------------------------------------------------ palette
function paletteEntries(q) {
  const s = app.state || {}; const ql = q.toLowerCase();
  const out = [];
  for (const [id, lbl] of [["inbox", "inbox"], ["board", "board"], ["coord", "coordination"], ["debug", "debug"]]) if (!ql || lbl.includes(ql)) out.push({ k: "sheet", what: lbl, sub: "", go: () => { showSheet(id); history.replaceState(null, "", `#${id}`); } });
  for (const r of s.all || []) if (r.kind !== "track" && (!ql || [r.id, r.title, r.digest].filter(Boolean).join(" ").toLowerCase().includes(ql))) out.push({ k: "item", what: rowText(r), sub: `${r.id} · ${label(r.effective)}`, go: () => select("item", r.id) });
  for (const p of s.peers || []) if (p.attention !== "gone" && (!ql || [p.agent_id, p.alias, p.goal].filter(Boolean).join(" ").toLowerCase().includes(ql))) out.push({ k: "peer", what: p.alias || p.agent_id, sub: `${attn(p.attention)}${p.goal ? " · " + clip(p.goal, 40) : ""}`, go: () => select("peer", p.agent_id) });
  for (const b of (app.boards || [])) if (b.slug !== app.slug && (!ql || b.slug.toLowerCase().includes(ql))) out.push({ k: "board", what: b.slug, sub: `${b.coord?.needs_you ? b.coord.needs_you + " need you · " : ""}${(b.status_counts || {}).open || 0} ready`, go: () => { location.href = b.url; } });
  return out.slice(0, 40);
}
function renderPalette() {
  const q = $("#palette-input").value.trim();
  const entries = paletteEntries(q);
  app.paletteEntries = entries;
  app.paletteIndex = Math.min(app.paletteIndex, Math.max(0, entries.length - 1));
  $("#palette-results").innerHTML = entries.length ? entries.map((e, i) => `<div class="presult${i === app.paletteIndex ? " active" : ""}" data-pi="${i}"><span class="k">${esc(e.k)}</span><span class="what">${esc(e.what)}</span><span class="k">${esc(e.sub)}</span></div>`).join("") : '<p class="empty">nothing matches</p>';
}
function openPalette() {
  $("#palette").hidden = false; app.paletteIndex = 0; $("#palette-input").value = ""; renderPalette(); $("#palette-input").focus();
  if (!app.boards) fetch("/api/boards", { cache: "no-store" }).then((r) => r.json()).then((d) => { app.boards = d.boards || []; renderPalette(); }).catch(() => {});
}
function closePalette() { $("#palette").hidden = true; }
$("#palette-input").addEventListener("input", () => { app.paletteIndex = 0; renderPalette(); });
$("#palette-input").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { e.preventDefault(); app.paletteIndex = Math.min(app.paletteIndex + 1, app.paletteEntries.length - 1); renderPalette(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); app.paletteIndex = Math.max(app.paletteIndex - 1, 0); renderPalette(); }
  else if (e.key === "Enter") { const en = app.paletteEntries[app.paletteIndex]; if (en) { closePalette(); en.go(); } }
});
$("#palette").addEventListener("click", (e) => { const r = e.target.closest(".presult"); if (r) { const en = app.paletteEntries[Number(r.dataset.pi)]; closePalette(); en?.go(); } else if (e.target === $("#palette")) closePalette(); });

// ------------------------------------------------------------ live
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
readHash();
showSheet(app.sheet);
fetchState();
connect();
window.setInterval(() => { $("#last-sync").textContent = rel(app.lastReceived); }, 1000);
