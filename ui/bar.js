import { loadContour, fillContours, contourInk, auditSurfaces } from "/contour.js";

const $ = (sel) => document.querySelector(sel);

function esc(text) {
  return String(text ?? "").replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
}

function clockText() {
  const now = new Date();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${now.getDate().toString().padStart(2, "0")} ${now.toLocaleString([], { month: "short" })}  ${time}`;
}

async function post(path, body) {
  const reply = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  return reply.json();
}

function render(windows) {
  $("#cells").innerHTML = windows
    .map((win) => `
      <div class="cell${win.active ? " on" : ""}${win.minimized ? " min" : ""}"
           data-hwnd="${win.hwnd}" title="${esc(win.title)}" data-contour>${esc(win.title)}</div>`)
    .join("");
  fillContours($("#cells"));
  auditSurfaces(document);
}

async function poll() {
  try {
    const body = await (await fetch("/api/windows")).json();
    render(body.windows);
  } catch (error) {
    $("#cells").innerHTML = "";
  }
}

// The strip is all crown, so its scale is the crown's own width: every metric below is
// a fraction of the cap the contour gives a window this tall.
function rescale() {
  const bar = $(".bar");
  const ink = contourInk(bar.clientWidth, bar.clientHeight);
  const cap = (ink.x * 2).toFixed(2);
  bar.style.setProperty("--cap", `${cap}px`);
  bar.style.setProperty("--ink-x", `${ink.x.toFixed(1)}px`);
  bar.style.setProperty("--ink-y", `${ink.y}px`);
}

async function start() {
  await loadContour();
  rescale();
  new ResizeObserver(rescale).observe($(".bar"));
  fillContours(document);
  $("#clock").textContent = clockText();
  setInterval(() => { $("#clock").textContent = clockText(); }, 1000);

  $("#start").addEventListener("click", () => post("/api/open", { target: "launcher" }));

  $("#cells").addEventListener("click", async (event) => {
    const cell = event.target.closest(".cell");
    if (!cell) return;
    const hwnd = Number(cell.dataset.hwnd);
    if (cell.classList.contains("on")) {
      await post("/api/minimize", { hwnd });
    } else {
      await post("/api/activate", { hwnd });
    }
    poll();
  });
  $("#cells").addEventListener("contextmenu", async (event) => {
    event.preventDefault();
    const cell = event.target.closest(".cell");
    if (!cell) return;
    await post("/api/close", { hwnd: Number(cell.dataset.hwnd) });
    poll();
  });

  await poll();
  setInterval(poll, 900);
}

start();
