import { loadContour, fillContours, auditSurfaces } from "/contour.js";

const $ = (sel) => document.querySelector(sel);

function esc(text) {
  return String(text ?? "").replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
}

function clockText() {
  const now = new Date();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const date = now.toLocaleDateString([], { weekday: "short", day: "2-digit", month: "short" });
  return { time, date };
}

async function post(path, body) {
  const reply = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  return reply.json();
}

let pins = [];
let winsByHwnd = new Map();
// slots is the strip's own map of window locations. A window keeps the index it was
// given until it closes; a null is a hole the owner left behind. Pages are read from
// this map, never from the window list's order (which is the Z order and would move
// buttons every time focus changed).
let slots = [];
let page = 0;
let capacity = 1;
let pinsKey = "";
let windowsKey = "";
let warm = false;
const SLOT_MIN = 132;

// The picture is the program's own, streamed from /api/icon: the same mark Explorer
// would draw, held inside the cell's contour rather than spelled as a name.
function appIcon(source) {
  return `<img class="appicon" src="${source}" alt="" onerror="this.remove()">`;
}

function pinCell(pin, index) {
  const source = `/api/icon?path=${encodeURIComponent(pin.target)}`;
  return `
    <div class="cell pin" data-pin="${index}" title="${esc(pin.target)}" data-contour>${appIcon(source)}<span class="fit">${esc(pin.label)}</span></div>`;
}

function windowCell(win) {
  return `
    <div class="cell${win.active ? " on" : ""}${win.minimized ? " min" : ""}"
         data-hwnd="${win.hwnd}" title="${esc(win.title)}" data-contour>${appIcon(`/api/icon?hwnd=${win.hwnd}`)}<span class="fit">${esc(win.title)}</span></div>`;
}

function renderPins() {
  const key = JSON.stringify(pins.map((pin) => [pin.target, pin.label]));
  if (key === pinsKey) return;
  pinsKey = key;
  $("#cells").innerHTML = pins.map(pinCell).join("");
  fillContours($("#cells"));
  auditSurfaces(document);
}

// How many slots a page holds at this width. A slot is at least SLOT_MIN wide; the row
// shares its width evenly among that many slots.
function captureCapacity() {
  const box = $("#pages");
  const pager = $("#pager");
  const gap = parseFloat(getComputedStyle(pager).columnGap) || 0;
  const width = box.clientWidth;
  capacity = Math.max(1, Math.floor((width + gap) / (SLOT_MIN + gap)));
  const slot = (width - (capacity - 1) * gap) / capacity;
  pager.style.setProperty("--slot-w", `${Math.max(SLOT_MIN, slot)}px`);
}

// A new window takes the last open slot on the last page: the first free position after
// the buttons already placed. The capacity is deliberately not consulted here, because
// the room for a page changes as pins and the badge load; placement must not scatter
// while that settles. A closed window leaves its hole in place, so nothing already
// placed ever slides; only a hole at the very end is reused by the next window.
function reconcile(windows) {
  const alive = new Set(windows.map((win) => win.hwnd));
  for (let i = 0; i < slots.length; i += 1) {
    if (slots[i] !== null && !alive.has(slots[i])) slots[i] = null;
  }
  while (slots.length && slots[slots.length - 1] === null) slots.pop();
  const known = new Set(slots.filter(Boolean));
  const cap = capacity;
  let landed = -1;
  for (const win of windows) {
    if (known.has(win.hwnd)) continue;
    // The last page's highest hole is the last open slot; only when it has none does
    // the window start the next page.
    const pages = Math.max(1, Math.ceil(slots.length / cap));
    const lastStart = (pages - 1) * cap;
    let index = -1;
    for (let i = slots.length - 1; i >= lastStart; i -= 1) {
      if (slots[i] === null) { index = i; break; }
    }
    if (index === -1) index = slots.length;
    while (slots.length < index) slots.push(null);
    slots[index] = win.hwnd;
    known.add(win.hwnd);
    landed = index;
  }
  winsByHwnd = new Map(windows.map((win) => [win.hwnd, win]));
  return landed;
}

function renderWindows() {
  const cap = capacity;
  const pages = Math.max(1, Math.ceil(slots.length / cap));
  page = Math.max(0, Math.min(page, pages - 1));
  const start = page * cap;
  const end = Math.min(slots.length, start + cap);
  const parts = [];
  for (let i = start; i < end; i += 1) {
    const hwnd = slots[i];
    const win = hwnd === null ? null : winsByHwnd.get(hwnd);
    parts.push(win ? windowCell(win) : `<div class="slot" aria-hidden="true"></div>`);
  }
  const key = `${page}/${cap}/${parts.join("")}`;
  if (key !== windowsKey) {
    windowsKey = key;
    $("#pager").innerHTML = parts.join("");
    fillContours($("#pager"));
    auditSurfaces(document);
  }
  const info = $("#pagecell");
  info.classList.toggle("idle", slots.length === 0);
  info.textContent = `${page + 1}/${pages}`;
  info.title = `Window page ${page + 1} of ${pages}: scroll to change`;
}

function turnPage(delta) {
  const pages = Math.max(1, Math.ceil(slots.length / capacity));
  const next = Math.max(0, Math.min(page + delta, pages - 1));
  if (next === page) return;
  page = next;
  renderWindows();
}

// The notification area is drawn, not spelled: a tray cell is the speaker, the aerial,
// the cell or the chevron, the same marks Windows puts there.
const TRAY_GLYPHS = {
  volume: ["M4 9.5h3.2L12 5.5v13l-4.8-4H4z", "M15.4 8.7a4.7 4.7 0 0 1 0 6.6", "M18 6.1a8.4 8.4 0 0 1 0 11.8"],
  volumeOff: ["M4 9.5h3.2L12 5.5v13l-4.8-4H4z", "M15.8 9.4l5.2 5.2", "M21 9.4l-5.2 5.2"],
  network: ["M3.6 9.3a13 13 0 0 1 16.8 0", "M6.9 12.7a8.4 8.4 0 0 1 10.2 0", "M10.2 16.1a3.6 3.6 0 0 1 3.6 0", "M12 19.3v.01"],
  networkOff: ["M3.6 9.3a13 13 0 0 1 16.8 0", "M6.9 12.7a8.4 8.4 0 0 1 10.2 0", "M4.5 4.5l15 15"],
  battery: ["M3 8.2h13.6v7.6H3z", "M18 10.6v2.8"],
  chevron: ["M7 14.6l5-5 5 5"],
};

function trayGlyph(name, fillPath) {
  const paths = TRAY_GLYPHS[name] || [];
  const strokes = paths.map((d) => `<path d="${d}" />`).join("");
  const fill = fillPath ? `<path class="fill" d="${fillPath}" />` : "";
  return `<svg class="glyph" viewBox="0 0 24 24" aria-hidden="true">${strokes}${fill}</svg>`;
}

function renderTray(tray) {
  const volume = $("#volume");
  volume.innerHTML = trayGlyph(tray.muted ? "volumeOff" : "volume");
  volume.title = tray.muted
    ? "Muted"
    : typeof tray.volume === "number"
      ? `Volume ${tray.volume}%`
      : "Volume";
  volume.classList.toggle("off", Boolean(tray.muted));

  const net = $("#net");
  net.innerHTML = trayGlyph(tray.online ? "network" : "networkOff");
  net.title = tray.online ? "Connected" : "Offline";
  net.classList.toggle("off", !tray.online);

  const battery = $("#battery");
  if (tray.battery) {
    const level = Math.max(0, Math.min(100, tray.battery.percent));
    const width = (level / 100) * 11.4;
    battery.innerHTML = trayGlyph("battery", `M4.2 9.4h${width.toFixed(2)}v5.2H4.2z`);
    battery.title = `${tray.battery.percent}%${tray.battery.charging ? " charging" : ""}`;
    battery.hidden = false;
    battery.classList.toggle("off", tray.battery.percent <= 20 && !tray.battery.charging);
  } else {
    battery.hidden = true;
  }

  $("#settings").innerHTML = trayGlyph("chevron");
}

async function pollWindows() {
  try {
    const body = await (await fetch("/api/windows")).json();
    const landed = reconcile(body.windows);
    if (!warm) {
      warm = true;
      page = 0;
    } else if (landed >= 0) {
      page = Math.floor(landed / capacity);
    }
    renderWindows();
  } catch (error) {
    windowsKey = "";
    $("#pager").innerHTML = "";
  }
}

async function pollShell() {
  try {
    const body = await (await fetch("/api/shell")).json();
    pins = body.pinned ?? [];
    renderTray(body.tray ?? {});
    renderPins();
    renderWindows();
  } catch (error) {
    /* the bar keeps its last reading; the next poll retries */
  }
}

async function start() {
  await loadContour();
  fillContours(document);
  captureCapacity();
  // The room for pages changes when the strip is resized and when the page badge itself
  // appears or hides, so the slot count is measured from the pages box, not from the
  // window. Without this a page keeps slot widths from before the badge took its room.
  new ResizeObserver(() => {
    captureCapacity();
    windowsKey = "";
    renderWindows();
  }).observe($("#pages"));

  const tick = () => {
    const { time, date } = clockText();
    $("#clock-time").textContent = time;
    $("#clock-date").textContent = date;
  };
  tick();
  setInterval(tick, 1000);

  $("#start").addEventListener("click", () => post("/api/open", { target: "launcher" }));
  $("#search").addEventListener("click", () => post("/api/open", { target: "launcher" }));
  $("#task").addEventListener("click", () => post("/api/taskview"));
  $("#show").addEventListener("click", () => post("/api/showdesktop"));
  // Each tray control opens its own view: the chevron is the only one that shows them all.
  const TRAY_VIEWS = {
    volume: "volume",
    net: "network",
    battery: "power",
    clock: "clock",
    settings: "all",
  };
  for (const [id, view] of Object.entries(TRAY_VIEWS)) {
    $(`#${id}`).addEventListener("click", () => post("/api/tray", { view }));
  }

  for (const target of [$("#pages"), $("#pagecell")]) {
    target.addEventListener("wheel", (event) => {
      event.preventDefault();
      turnPage(event.deltaY > 0 ? 1 : -1);
    }, { passive: false });
  }
  $("#pagecell").addEventListener("click", () => turnPage(1));

  $(".bar").addEventListener("click", async (event) => {
    const cell = event.target.closest(".cell");
    if (!cell) return;
    if (cell.dataset.pin !== undefined) {
      const pin = pins[Number(cell.dataset.pin)];
      if (pin) await post("/api/open", { target: pin.target });
      return;
    }
    if (cell.dataset.hwnd === undefined) return;
    const hwnd = Number(cell.dataset.hwnd);
    if (cell.classList.contains("on")) {
      await post("/api/minimize", { hwnd });
    } else {
      await post("/api/activate", { hwnd });
    }
    pollWindows();
  });
  // The menu belongs to the cell that was hit: a window gets its own actions, a pin gets
  // its target's, and the strip itself gets the shell's. Nothing closes on a right click.
  $(".bar").addEventListener("contextmenu", (event) => {
    event.preventDefault();
    const cell = event.target.closest(".cell");
    const at = { x: Math.round(event.clientX), y: Math.round(event.clientY) };
    if (cell && cell.dataset.pin !== undefined) {
      const pin = pins[Number(cell.dataset.pin)];
      if (pin) post("/api/menu", { kind: "pin", target: pin.target, ...at });
      return;
    }
    if (cell && cell.dataset.hwnd !== undefined) {
      post("/api/menu", { kind: "window", hwnd: Number(cell.dataset.hwnd), ...at });
      return;
    }
    post("/api/menu", { kind: "bar", ...at });
  });

  await pollWindows();
  await pollShell();
  setInterval(pollWindows, 900);
  setInterval(pollShell, 2000);
}

start();
