"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
let lastReceived = null;

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
  $("#summary-line").textContent = `${rows.length} registered · ${rows.filter((b) => b.exists).length} present`;
  $("#registry-path").textContent = state.registry || "";
  const cell = (n, cls) => `<td class="num ${n ? cls : "faint"}">${n || "·"}</td>`;
  $("#boards-body").innerHTML = rows.length ? rows.map((b) => {
    const sc = b.status_counts || {};
    const name = b.exists ? `<a href="${esc(b.url)}">${esc(b.slug)}</a>` : `<span class="faint">${esc(b.slug)}</span>`;
    return `<tr>
      <td>${name}${b.exists ? "" : ' <span class="faint">(missing)</span>'}</td>
      ${cell(sc.in_progress, "state-active")}${cell(sc.open, "state-ready")}${cell(sc.blocked, "state-waiting")}${cell(b.decisions, "state-decision")}${cell(b.dreams, "state-dream")}${cell(sc.done, "state-done")}${cell(b.drift_count, "state-decision")}
      <td class="nowrap">${esc(fmtDate(b.latest_update))}</td>
      <td class="faint">${esc(b.root)}</td>
    </tr>`;
  }).join("") : '<tr><td colspan="10" class="empty">No boards registered yet.</td></tr>';
}

function receive(state) { lastReceived = new Date(); setConn(true, "live"); render(state); }
async function fetchState() {
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
