import { loadContour, fillContours, auditSurfaces } from "/contour.js";

const $ = (sel) => document.querySelector(sel);

const state = { volume: null, muted: false, online: true, battery: null };
const current = { view: "all" };

const TITLES = {
  volume: "Volume",
  network: "Network",
  power: "Battery",
  clock: "Date & time",
  all: "Quick settings",
};

function clockText() {
  const now = new Date();
  return {
    time: now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }),
    date: now.toLocaleDateString([], { weekday: "long", day: "2-digit", month: "short", year: "numeric" }),
  };
}

function volumeText() {
  if (state.muted) return "muted";
  return typeof state.volume === "number" ? `${state.volume}%` : "unavailable";
}

function batteryText() {
  if (!state.battery) return "no battery";
  return `${state.battery.percent}%${state.battery.charging ? " charging" : ""}`;
}

function applyView() {
  const name = TITLES[current.view] ? current.view : "all";
  // Every view is its own plate, the combined one included: exactly one section is shown.
  document.querySelectorAll(".view").forEach((section) => {
    section.hidden = section.dataset.view !== name;
  });
  $("#title").textContent = TITLES[name];
}

function setView(name) {
  current.view = String(name ?? "all");
  applyView();
  render();
  // A view that was hidden had no box, so its contour is cut again now that it has one.
  fillContours(document);
  auditSurfaces(document);
}

window.setView = setView;

function render() {
  const text = volumeText();
  $("#volume-value").textContent = text;
  $("#volume-summary").textContent = text;
  $("#network-value").textContent = state.online ? "connected" : "offline";
  $("#network-summary").textContent = state.online ? "connected" : "offline";
  $("#battery-value").textContent = batteryText();
  $("#battery-summary").textContent = batteryText();
  $("#mute").textContent = state.muted ? "Unmute" : "Mute";

  const clock = clockText();
  $("#view-time").textContent = clock.time;
  $("#view-date").textContent = clock.date;

  const known = typeof state.volume === "number";
  const lit = known ? Math.round(state.volume / 10) : 0;
  const meter = $("#meter");
  meter.innerHTML = Array.from({ length: 10 }, (_, index) =>
    `<span class="cell pip${!state.muted && index < lit ? " lit" : ""}" data-contour></span>`).join("");
  fillContours(meter);
}

async function refresh() {
  try {
    const body = await (await fetch("/api/shell")).json();
    Object.assign(state, body.tray ?? {});
    // The bar names the view it opened; the poll is what puts a reloaded page back on it.
    if (body.view && body.view !== current.view) setView(body.view);
  } catch (error) {
    /* keep the last reading; the next poll retries */
  }
  render();
  const clock = clockText();
  $("#view-time").textContent = clock.time;
  $("#view-date").textContent = clock.date;
}

async function post(path, body) {
  await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  await refresh();
}

function step(delta) {
  const base = typeof state.volume === "number" ? state.volume : 50;
  post("/api/volume", { level: Math.max(0, Math.min(100, base + delta)) });
}

$("#down").addEventListener("click", () => step(-5));
$("#up").addEventListener("click", () => step(5));
$("#mute").addEventListener("click", () => post("/api/mute", { muted: !state.muted }));
$("#sound-settings").addEventListener("click", () => post("/api/open", { target: "ms-settings:sound" }));
$("#network-settings").addEventListener("click", () => post("/api/open", { target: "ms-settings:network" }));
$("#power-settings").addEventListener("click", () => post("/api/open", { target: "ms-settings:batterysaver" }));
$("#time-settings").addEventListener("click", () => post("/api/open", { target: "ms-settings:dateandtime" }));
$("#task").addEventListener("click", () => post("/api/taskview"));
$("#show").addEventListener("click", () => post("/api/showdesktop"));
$("#close").addEventListener("click", () => post("/api/tray", { view: current.view }));

async function start() {
  await loadContour();
  fillContours(document);
  applyView();
  await refresh();
  setInterval(refresh, 1000);
}

start();
