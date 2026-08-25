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
  $("#summary-line").textContent = String(rows.length);
  const t = state.totals || {};
  $("#totals").innerHTML = [
    t.needs_you ? `<span class="n c-needs-user">${t.needs_you}</span> <span class="muted">need you</span>` : `<span class="n faint">0</span> <span class="muted">need you</span>`,
    `<span class="n c-working">${t.working || 0}</span> <span class="muted">working</span>`,
    `<span class="n">${t.here || 0}</span> <span class="muted">sessions here</span>`,
  ].map((h) => `<span>${h}</span>`).join("");
  $("#registry-path").textContent = state.registry || "";
  const cell = (n, cls) => `<td class="num ${n ? cls : "faint"}">${n ? (cls === "attn-needs-user" ? `<span class="pill c-needs-user">${n}</span>` : n) : "·"}</td>`;
  $("#boards-body").innerHTML = rows.length ? rows.map((b) => {
    const sc = b.status_counts || {};
    const name = b.exists ? `<a href="${esc(b.url)}" title="${esc(b.root)}">${esc(b.slug)}</a>` : `<span class="faint" title="${esc(b.root)}">${esc(b.slug)}</span>`;
    return `<tr>
      <td class="nowrap">${name}${b.exists ? "" : ' <span class="faint">(missing)</span>'}</td>
      ${cell(b.coord?.needs_you, "attn-needs-user")}${cell(b.coord?.working, "c-working")}${cell(b.coord?.here, "")}${cell(sc.in_progress, "c-active")}${cell(sc.open, "c-ready")}${cell(sc.blocked, "c-waiting")}${cell(b.decisions, "c-decision")}${cell(b.dreams, "c-dream")}${cell(sc.done, "c-done")}${cell(b.drift_count, "c-decision")}
      <td class="nowrap">${esc(fmtDate(b.latest_update))}</td>
    </tr>`;
  }).join("") : '<tr><td colspan="12" class="empty">No boards registered yet.</td></tr>';
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
