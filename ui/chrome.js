// The window chrome's last line of defence.
//
// A Popit window is delivered with its own script, and that script is where the bar works
// from. When the script does not run (a package refused, a stale copy, an app with no body
// logic), the window must still answer: settings opens the settings window, home returns to
// the springboard, close closes, and a window whose surface is empty returns to the
// springboard instead of showing a blank sheet.
//
// This file binds those four controls only when the window's own script did not take the
// window: it reads the state the desk writes (`data-window-state="ready"`), waits, and then
// binds as a fallback. It never rebinds a working window, so a live desk is not double-driven.

(() => {
  const WAIT_MS = 1800;
  const CHECK_MS = 2000;
  const state = () => (document.body && document.body.dataset.windowState) || "";

  function go(target) {
    try {
      window.location.assign(target);
      return true;
    } catch (error) {
      return false;
    }
  }

  function openSettings() {
    const panel = document.getElementById("settings-panel");
    if (panel) {
      panel.hidden = false;
      const focus = panel.querySelector("button, input, select, [tabindex]");
      if (focus) focus.focus();
      return "panel";
    }
    return go("/settings.html?window=settings") ? "window" : "none";
  }

  function openHome() {
    const board = document.getElementById("springboard");
    if (board) {
      document.querySelectorAll("[data-surface]").forEach((node) => {
        node.hidden = node !== board;
      });
      board.hidden = false;
      return "springboard";
    }
    return go("/phone.html") ? "springboard-url" : "none";
  }

  function closeWindow() {
    window.close();
    return "close";
  }

  function surfaceIsEmpty() {
    // The sheet is empty when there is nothing below the bar: no words and no control a
    // person could press. Anything the body draws counts, whatever shape it is, so a
    // springboard or a call list is content and a blank pane is not.
    const bar = document.querySelector("[data-region='bar']");
    const all = (document.body.innerText || "").trim();
    const barText = bar ? (bar.innerText || "").trim() : "";
    const below = barText ? all.split(barText).join(" ").trim() : all;
    if (below.length > 0) return false;
    const controls = [...document.querySelectorAll("button, input, select, textarea, a[href]")]
      .filter((node) => !bar || !bar.contains(node))
      .filter((node) => !node.hidden && node.offsetParent !== null);
    return controls.length === 0;
  }

  function bind() {
    const actions = {
      settings: openSettings,
      home: openHome,
      close: closeWindow,
    };
    for (const [id, run] of Object.entries(actions)) {
      const node = document.getElementById(id);
      if (!node || node.dataset.chromeBound === "1") continue;
      node.dataset.chromeBound = "1";
      node.addEventListener("click", (event) => {
        // A desk that starts late still owns its window: the fallback only answers while the
        // window's own script has not taken it, so a working desk is never double-driven.
        if (state() === "ready") return;
        event.preventDefault();
        const how = run();
        document.body.dataset.chrome = `fallback:${id}:${how}`;
      });
    }
    document.body.dataset.chrome = "fallback";
  }

  function watch() {
    // An empty surface is not a window: it returns to the springboard, which always has a
    // tile for every signed app and its own settings door.
    if (state() === "ready") return;
    if (!surfaceIsEmpty()) return;
    const board = document.getElementById("springboard");
    if (board && !board.hidden) return;
    const how = openHome();
    document.body.dataset.chromeEmpty = how;
  }

  function start() {
    const deskTook = () => state() === "ready";
    if (deskTook()) return;
    window.setTimeout(() => {
      if (deskTook()) return;
      bind();
      watch();
      window.setInterval(() => {
        if (state() === "ready") return;
        watch();
      }, CHECK_MS);
    }, WAIT_MS);
  }

  // The one entry a probe uses to prove the fallback answers without breaking a live window.
  window.__popitChrome = { bind, watch, openSettings, openHome, surfaceIsEmpty, state };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
