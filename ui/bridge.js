// The bridge package window. It carries readings, not furniture.
//
// The frame, material, motion, DPI and palette are the settings package's: attach("bridge")
// verifies this page's signed identity, applies the published theme and sets data-motion, and
// loadContour/fillContours paint the measured nine-slice. The bar, tabs, body and foot are the
// shell's window chrome classes. This module sets text and toggles the tab the way the desk
// does — it defines no colour, no shape, no transition and no button of its own.
import { loadContour, fillContours, auditSurfaces } from "/contour.js";
import { attach } from "/package.js";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = { body: null, lane: "host" };
let contourReady = false;

loadContour("/contour.json")
  .then(() => { contourReady = true; fillContours(document); })
  .catch(() => undefined);

attach("bridge", { identitySelector: "#app-identity" }).catch(() => undefined);

function setText(selector, value) {
  const node = $(selector);
  if (node) node.textContent = value;
}

function status(value, label) {
  const node = $("#bridge-state");
  if (!node) return;
  node.dataset.state = value;
  node.textContent = label;
}

// One reading is a line of the facts body: the name in the desk's own figure style, the value
// beside it, and the state word only where the reading is a command that exists or does not.
function fact(name, value, state) {
  const line = document.createElement("p");
  line.className = "drawer-note";
  line.dataset.fact = name;
  if (state) line.dataset.state = state;
  line.textContent = `${name} · ${value || "—"}`;
  return line;
}

const HOST = ["host", "os", "cores", "mem", "disk", "python", "gpu", "vulkan", "srv",
              "steamdir", "steamapps"];
const TOOLS = ["steam", "steam-runtime", "proton", "wine", "vulkaninfo", "glxinfo",
               "flatpak", "xrandr"];

function draw(body) {
  state.body = body;
  const rows = body.checks || [];
  const hostRows = $("#host-rows");
  const toolRows = $("#tool-rows");
  if (hostRows) {
    hostRows.replaceChildren(...rows.filter((row) => HOST.includes(row.name))
      .map((row) => fact(row.name, row.detail)));
  }
  if (toolRows) {
    toolRows.replaceChildren(...rows.filter((row) => TOOLS.includes(row.name))
      .map((row) => fact(row.name, row.state, row.state)));
  }
  const live = body.source === "live";
  status(live ? "live" : "waiting", live ? "live" : (body.source || "receipt"));
  setText("#checked", `${rows.length} rows · ${body.at || "—"}`);
  setText("#refusal", body.ok === false ? `refused ${body.refused || "bridge-offline"}` : "");
  if (contourReady) { fillContours(document); auditSurfaces(document); }
}

async function refresh() {
  try {
    const reply = await fetch("/api/toast/bridge", { cache: "no-store" });
    draw(await reply.json());
  } catch (error) {
    status("refused", "offline");
    setText("#refusal", "refused bridge-unreachable");
  }
}

$$("[data-lane]").forEach((button) => {
  button.addEventListener("click", () => {
    state.lane = button.dataset.lane;
    $$("[data-lane]").forEach((other) => {
      const active = other === button;
      other.classList.toggle("active", active);
      other.setAttribute("aria-selected", active ? "true" : "false");
    });
    $$("[data-page]").forEach((page) => { page.hidden = page.dataset.page !== state.lane; });
  });
});

$("#bridge-refresh")?.addEventListener("click", refresh);

$("#queue-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const command = ($("#queue-command")?.value || "").trim();
  if (!command) return;
  const body = $("#queue-rows");
  if (body) body.replaceChildren(fact("running", command));
  try {
    const reply = await fetch("/api/toast/bridge/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    const result = await reply.json();
    if (!result.ok) {
      setText("#refusal", `refused ${result.refused || "bridge-run-failed"}`);
      if (body) body.replaceChildren(fact("refused", result.refused || "bridge-run-failed"));
      return;
    }
    const lines = (result.stdout || "").trim().split("\n").filter(Boolean);
    if (body) {
      body.replaceChildren(
        fact("exit", `${result.code} in ${result.seconds}s`, result.code === 0 ? "live" : "refused"),
        ...lines.map((line) => fact("out", line)),
      );
    }
    setText("#refusal", "");
  } catch (error) {
    setText("#refusal", "refused bridge-run-unreachable");
  }
  refresh();
});

refresh();
setInterval(refresh, 15000);
