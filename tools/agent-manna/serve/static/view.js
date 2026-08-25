"use strict";
// Viewer conveniences: inspector width, font family, font size. Stored per browser
// (localStorage), never on the server; the page renders correctly with nothing stored.
(function () {
  const KEY = "manna-serve-view";
  const FONTS = [
    ["system", '"SFMono-Regular", "Cascadia Code", "JetBrains Mono", "Roboto Mono", Menlo, Consolas, monospace'],
    ["SF Mono", '"SF Mono", "SFMono-Regular", Menlo, monospace'],
    ["JetBrains Mono", '"JetBrains Mono", Menlo, monospace'],
    ["Cascadia Code", '"Cascadia Code", "Cascadia Mono", Menlo, monospace'],
    ["Fira Code", '"Fira Code", "Fira Mono", Menlo, monospace'],
    ["IBM Plex Mono", '"IBM Plex Mono", Menlo, monospace'],
    ["Menlo", 'Menlo, Monaco, monospace'],
    ["Courier", '"Courier New", Courier, monospace'],
  ];
  // 12px is the dpt floor; 18px is where a 72-character digest stops fitting the measure.
  const SIZE_MIN = 12, SIZE_MAX = 18, SIZE_DEFAULT = 12;
  const INSPECTOR_MIN = 220, INSPECTOR_MAX = 600, INSPECTOR_DEFAULT = 300;

  const $ = (s, r = document) => r.querySelector(s);
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch { return {}; } }
  function save(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch {} }
  const view = Object.assign({ font: "system", size: SIZE_DEFAULT, inspector: INSPECTOR_DEFAULT }, load());

  function apply() {
    const root = document.documentElement.style;
    const stack = (FONTS.find(([n]) => n === view.font) || FONTS[0])[1];
    root.setProperty("--mono", stack);
    const size = Math.min(SIZE_MAX, Math.max(SIZE_MIN, Number(view.size) || SIZE_DEFAULT));
    root.setProperty("--t-body", `${size}px`); root.setProperty("--t-small", `${size}px`); root.setProperty("--t-meta", `${size}px`);
    root.setProperty("--t-h", `${size + 1}px`); root.setProperty("--t-h1", `${size + 4}px`);
    root.setProperty("--row-h", `${size * 2 + 2}px`);
    const w = Math.min(INSPECTOR_MAX, Math.max(INSPECTOR_MIN, Number(view.inspector) || INSPECTOR_DEFAULT));
    root.setProperty("--inspector-w", `${w}px`);
    const sizeEl = $("#view-size"); if (sizeEl) sizeEl.textContent = `${size}px`;
    const fontEl = $("#view-font"); if (fontEl && fontEl.value !== view.font) fontEl.value = view.font;
  }

  function popover() {
    const host = $("#view-host"); if (!host) return;
    host.innerHTML = `<button class="text-button" id="view-button" type="button">view ▾</button>
      <div class="view-pop" id="view-pop" hidden>
        <label>font <select id="view-font">${FONTS.map(([n]) => `<option value="${n}">${n}</option>`).join("")}</select></label>
        <label>size <button type="button" id="view-smaller" aria-label="smaller">−</button><span id="view-size"></span><button type="button" id="view-larger" aria-label="larger">+</button></label>
        <button type="button" id="view-reset" class="text-button">reset</button>
      </div>`;
    $("#view-button").addEventListener("click", () => { $("#view-pop").hidden = !$("#view-pop").hidden; });
    $("#view-font").addEventListener("change", (e) => { view.font = e.target.value; save(view); apply(); });
    $("#view-smaller").addEventListener("click", () => { view.size = Math.max(SIZE_MIN, (Number(view.size) || SIZE_DEFAULT) - 1); save(view); apply(); });
    $("#view-larger").addEventListener("click", () => { view.size = Math.min(SIZE_MAX, (Number(view.size) || SIZE_DEFAULT) + 1); save(view); apply(); });
    $("#view-reset").addEventListener("click", () => { view.font = "system"; view.size = SIZE_DEFAULT; view.inspector = INSPECTOR_DEFAULT; save(view); apply(); });
    document.addEventListener("click", (e) => { if (!e.target.closest("#view-host")) { const p = $("#view-pop"); if (p) p.hidden = true; } });
    apply();
  }

  function resizer() {
    const handle = $("#resizer"); const cockpit = $(".cockpit"); if (!handle || !cockpit) return;
    let dragging = false;
    handle.addEventListener("mousedown", (e) => { dragging = true; handle.classList.add("active"); e.preventDefault(); });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const right = cockpit.getBoundingClientRect().right;
      view.inspector = Math.min(INSPECTOR_MAX, Math.max(INSPECTOR_MIN, Math.round(right - e.clientX)));
      apply();
    });
    window.addEventListener("mouseup", () => { if (dragging) { dragging = false; handle.classList.remove("active"); save(view); } });
    handle.addEventListener("dblclick", () => { view.inspector = INSPECTOR_DEFAULT; save(view); apply(); });
  }

  apply();
  document.addEventListener("DOMContentLoaded", () => { popover(); resizer(); });
})();
