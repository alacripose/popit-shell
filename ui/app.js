import { loadContour, fillContours, windowScale, auditSurfaces } from "/contour.js";

const state = { tools: [], apps: [], rows: [], selected: 0 };

const $ = (sel) => document.querySelector(sel);

const esc = (text) =>
  String(text ?? "").replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));

function visibleRows() {
  const q = $("#q").value.trim().toLowerCase();
  const all = [...state.tools, ...state.apps];
  if (!q) return all;
  return all.filter(
    (row) => row.label.toLowerCase().includes(q) || row.detail.toLowerCase().includes(q),
  );
}

function renderTotals() {
  $("#totals").innerHTML =
    `<span><b>${state.apps.length}</b> apps</span>` +
    `<span><b>${state.rows.length}</b> shown</span>` +
    `<span><b>${state.tools.length}</b> tools</span>`;
}

function renderRows() {
  state.rows = visibleRows();
  if (state.selected > state.rows.length - 1) state.selected = Math.max(0, state.rows.length - 1);
  const list = $("#rows");
  list.innerHTML = state.rows
    .map((row, index) => `
      <li class="card${index === state.selected ? " on" : ""}" data-index="${index}" data-contour>
        <span class="glyph">▶</span>
        <span class="name">${esc(row.label)}</span>
        <span class="detail">${esc(row.detail)}</span>
        <span class="meta">${esc(row.kind)}</span>
      </li>`)
    .join("");
  // Every card is its own surface, so every card takes its own contour clip and ink.
  fillContours(list);
  auditSurfaces(document);
  renderTotals();
  renderFacts();
  const on = list.querySelector(".card.on");
  if (on) on.scrollIntoView({ block: "nearest" });
}

function renderFacts() {
  const row = state.rows[state.selected];
  if (!row) {
    $("#facts-head").textContent = "Selection";
    $("#facts").innerHTML = '<p class="empty">No row is selected</p>';
    return;
  }
  $("#facts-head").textContent = row.label;
  $("#facts").innerHTML = [
    ["Kind", row.kind],
    ["Folder", row.detail || "the Start Menu root"],
    ["Target", row.target],
  ]
    .map(([key, value]) => `
      <div class="field" data-contour>
        <div class="key">${esc(key)}</div>
        <div class="value">${esc(value)}</div>
      </div>`)
    .join("");
  fillContours($("#facts"));
  auditSurfaces(document);
}

async function openSelected() {
  const row = state.rows[state.selected];
  if (!row) return;
  const reply = await fetch("/api/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target: row.target }),
  });
  const result = await reply.json();
  if (!result.ok) {
    $("#facts").insertAdjacentHTML("afterbegin", `<p class="empty">refused ${esc(result.refused)}</p>`);
    return;
  }
  if (result.result === "quit") fetch("/api/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target: "quit" }),
  });
  if (result.result === "reload") await load();
}

async function load() {
  const wanted = state.selected;
  const body = await (await fetch("/api/state")).json();
  state.tools = body.tools;
  state.apps = body.apps;
  state.selected = wanted;
  renderRows();
}

function move(delta) {
  if (!state.rows.length) return;
  state.selected = Math.min(state.rows.length - 1, Math.max(0, state.selected + delta));
  renderRows();
}

function rescaled() {
  const shell = $(".shell");
  windowScale(shell, shell.clientWidth, shell.clientHeight);
}

// dragByHeader lets the owner move the window: the header is the handle, and the drag is
// sent as a delta of screen pixels, because the window's own coordinates move with it.
function dragByHeader() {
  const handle = $(".plate");
  if (!handle) return;
  handle.style.cursor = "move";
  let last = null;
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest("input")) return;
    last = { x: event.screenX, y: event.screenY };
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add("dragging");
  });
  handle.addEventListener("pointermove", (event) => {
    if (!last) return;
    const dx = event.screenX - last.x;
    const dy = event.screenY - last.y;
    if (!dx && !dy) return;
    last = { x: event.screenX, y: event.screenY };
    fetch("/api/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dx, dy }),
    });
  });
  const stop = (event) => {
    last = null;
    document.body.classList.remove("dragging");
    if (handle.hasPointerCapture?.(event.pointerId)) handle.releasePointerCapture(event.pointerId);
  };
  handle.addEventListener("pointerup", stop);
  handle.addEventListener("pointercancel", stop);
}

async function start() {
  await loadContour();
  rescaled();
  new ResizeObserver(rescaled).observe($(".shell"));
  fillContours(document);
  await load();

  $("#q").addEventListener("input", () => {
    state.selected = 0;
    renderRows();
  });
  $("#q").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") { event.preventDefault(); move(1); }
    if (event.key === "ArrowUp") { event.preventDefault(); move(-1); }
    if (event.key === "Enter") { event.preventDefault(); openSelected(); }
    if (event.key === "Escape") { $("#q").value = ""; state.selected = 0; renderRows(); }
  });
  $("#rows").addEventListener("click", (event) => {
    const card = event.target.closest(".card");
    if (!card) return;
    state.selected = Number(card.dataset.index);
    renderRows();
    openSelected();
  });
  dragByHeader();
  $("#q").focus();
}

start();
