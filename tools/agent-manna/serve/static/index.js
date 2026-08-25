"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
let lastReceived = null;
let buildingSince = null;
const SPIN = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
function renderBuilding(state) {
  const el = document.getElementById("building"); if (!el) return;
  if (!(state?.building)) { el.hidden = true; buildingSince = null; return; }
  if (!buildingSince) buildingSince = Date.now();
  el.hidden = false;
}
window.setInterval(() => {
  const el = document.getElementById("building");
  if (!el || el.hidden || !buildingSince) return;
  const s = Math.floor((Date.now() - buildingSince) / 1000);
  el.querySelector(".spin").textContent = SPIN[Math.floor(Date.now() / 120) % SPIN.length];
  document.getElementById("building-text").textContent = ` reading coord presence across the estate · ${s}s`;
}, 120);

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
const setConn = (ok, label) => { $("#connection-mark").textContent = ok ? "●" : "○"; $("#connection-mark").classList.toggle("live", ok); $("#connection-label").textContent = label; };

function render(state) {
  const rows = state.boards || [];
  $("#summary-line").textContent = String(rows.length);
  renderBuilding(state);
  const t = state.totals || {};
  if (state.building) { $("#totals").innerHTML = ""; return finishRender(rows, state); }
  $("#totals").innerHTML = [
    t.needs_you ? `<span class="n c-needs-user">${t.needs_you}</span> <span class="muted">need you</span>` : `<span class="n faint">0</span> <span class="muted">need you</span>`,
    `<span class="n c-working">${t.working || 0}</span> <span class="muted">working</span>`,
    `<span class="n">${t.here || 0}</span> <span class="muted">sessions here</span>`,
  ].map((h) => `<span>${h}</span>`).join("");
  $("#registry-path").textContent = state.registry || "";
  // each count links into the board: #<sheet>[/<section>] is what the board page reads on load
  finishRender(rows, state);
}
// null (not 0) means "not read yet": an honest ellipsis, never a fake zero
const cell = (n, cls, b, target) => n == null ? `<td class="num faint">…</td>` : `<td class="num ${n ? cls : "faint"}">${n ? `<a class="${cls}" href="${esc(b.url)}#${target}">${n}</a>` : "·"}</td>`;
function finishRender(rows, state) {
  $("#boards-body").innerHTML = rows.length ? rows.map((b) => {
    const sc = b.status_counts || {};
    const name = b.exists ? `<a href="${esc(b.url)}" title="${esc(b.root)}">${esc(b.slug)}</a>` : `<span class="faint" title="${esc(b.root)}">${esc(b.slug)}</span>`;
    return `<tr>
      <td class="nowrap">${name}${b.exists ? "" : ' <span class="faint">(missing)</span>'}</td>
      ${cell(b.coord ? b.coord.needs_you : null, "c-needs-user", b, "coord/needs")}${cell(b.coord ? b.coord.working : null, "c-working", b, "coord/peers")}${cell(b.coord ? b.coord.here : null, "", b, "coord/peers")}${cell(sc.in_progress, "c-active", b, "board/now")}${cell(sc.open, "c-ready", b, "board/next")}${cell(sc.blocked, "c-waiting", b, "board/waiting")}${cell(b.decisions, "c-decision", b, "inbox")}${cell(b.dreams, "c-dream", b, "board/dreams")}${cell(sc.done, "c-done", b, "board/done")}${cell(b.drift_count, "c-decision", b, "debug")}
      <td class="nowrap">${esc(fmtDate(b.latest_update))}</td>
    </tr>`;
  }).join("") : '<tr><td colspan="12" class="empty">No boards registered yet.</td></tr>';
}

function receive(state) { lastReceived = new Date(); setConn(true, "live"); render(state); }
async function fetchState() {
  // rows first (cheap), presence after (the slow read); the SSE stream keeps it live
  try { const r = await fetch("/api/boards?fast=1", { cache: "no-store" }); if (r.ok) receive(await r.json()); } catch (e) {}
  try { const r = await fetch("/api/boards", { cache: "no-store" }); if (!r.ok) throw new Error(`status ${r.status}`); receive(await r.json()); }
  catch (e) { setConn(false, "disconnected"); }
}
function connect() {
  const src = new EventSource("/api/events");
  src.addEventListener("state", (ev) => { try { receive(JSON.parse(ev.data)); } catch { setConn(false, "bad state"); } });
  src.onopen = () => setConn(true, "live");
  src.onerror = () => setConn(false, "reconnecting");
}
fetchState();
connect();
window.setInterval(() => { $("#last-sync").textContent = rel(lastReceived); }, 1000);
