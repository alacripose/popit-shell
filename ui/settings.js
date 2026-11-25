// The settings package window reads one document from the running shell and shows it.
// It never re-derives the panel's choices: the settings app pushes what it holds, and
// this surface renders the published package that carries those choices.

import { attach } from "/package.js";

const $ = (selector) => document.querySelector(selector);

// The settings app is an app package itself: its own signed identity sits beside the
// settings package it publishes, and it takes the same family theme.
attach("settings", { identitySelector: "#app-identity" });

function setText(selector, value) {
  const node = $(selector);
  if (node) node.textContent = value;
}

function row(label, value) {
  const tr = document.createElement("tr");
  const key = document.createElement("th");
  key.textContent = label;
  const cell = document.createElement("td");
  cell.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
  tr.append(key, cell);
  return tr;
}

function short(value, keep = 18) {
  const text = String(value || "");
  return text.length > keep * 2 ? `${text.slice(0, keep)}…${text.slice(-keep)}` : text;
}

function renderIdentity(state) {
  setText("#package-identity", state.identity || "unpublished");
  setText("#package-digest", short(state.digest));
  setText("#package-payload", short(state.payload_digest));
  setText("#package-publisher", short(state.publisher_fingerprint));
  setText("#package-signature", short(state.signature || "", 14));
  const signature = $("#package-signature");
  if (signature) signature.title = state.signature || "";
  const chip = $("#package-state");
  if (chip) {
    chip.dataset.state = state.identity ? "held" : "unpublished";
    chip.textContent = state.identity ? `rev ${state.revision}` : "unpublished";
  }
}

function renderSettings(state) {
  const settings = state.settings || {};
  const body = $("#settings-rows");
  if (!body) return;
  body.replaceChildren(
    row("theme", settings.theme),
    row("frame", settings.frame),
    row("material", settings.material),
    row("motion type", settings.motion),
    row("motion", settings.motionPreference),
    row("DPI", settings.dpi ? `${settings.dpi}%` : ""),
    row("palettes", `${(settings.palettes || []).length} community`),
  );
  setText("#palette-note", (settings.palettes || []).length
    ? (settings.palettes || []).map((palette) => palette.name).join(" · ")
    : "palettes —");
}

function renderDevice(state) {
  const device = state.device || {};
  const body = $("#device-rows");
  if (!body) return;
  const screen = Array.isArray(device.screen) ? device.screen.join(" × ") : "";
  const virtual = Array.isArray(device.virtual_screen) ? device.virtual_screen.join(" × ") : "";
  body.replaceChildren(
    row("platform", device.platform),
    row("machine", device.machine),
    row("screen", screen),
    row("virtual", virtual),
    row("monitors", device.monitors),
    row("DPI", device.dpi),
    row("reported", device.reported_at),
  );
}

function renderSubscribers(state) {
  const rows = state.subscribers || [];
  setText("#subscriber-count", String(rows.length));
  const list = $("#subscriber-list");
  if (!list) return;
  list.replaceChildren();
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No window has subscribed yet.";
    list.append(empty);
    return;
  }
  for (const row of rows) {
    const item = document.createElement("article");
    item.className = "subscriber";
    const name = document.createElement("b");
    name.textContent = row.window || "window";
    const meta = document.createElement("small");
    meta.textContent = `${row.deliveries || 0} deliveries · ${short(row.fingerprint, 10)}`;
    item.append(name, meta);
    list.append(item);
  }
}

function render(state) {
  renderIdentity(state);
  renderSettings(state);
  renderDevice(state);
  renderSubscribers(state);
  setText("#checked", state.identity ? `verified ${new Date().toLocaleTimeString()}` : "not published");
}

async function read() {
  try {
    const reply = await fetch("/api/toast/settings", { cache: "no-store" });
    const body = await reply.json();
    if (!reply.ok) {
      setText("#refusal", body.refused || "settings refused");
      return;
    }
    render(body);
    setText("#refusal", "");
  } catch (error) {
    setText("#refusal", `settings unavailable · ${error.message}`);
  }
}

async function publish() {
  const button = $("#publish");
  if (button) button.disabled = true;
  try {
    const reply = await fetch("/api/toast/settings/publish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const body = await reply.json();
    if (!reply.ok) {
      setText("#refusal", body.refused?.code || body.refused || "publish refused");
      return;
    }
    setText("#refusal", `published ${body.identity}`);
    await read();
  } catch (error) {
    setText("#refusal", `publish refused · ${error.message}`);
  } finally {
    if (button) button.disabled = false;
  }
}

$("#publish")?.addEventListener("click", publish);
read();
setInterval(read, 4000);
