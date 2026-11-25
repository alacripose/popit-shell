const $ = (selector) => document.querySelector(selector);
const feed = $("#feed");
let lastFrame = 0;
let lastRowsKey = "";
let stick = true;
let busy = false;

const setText = (selector, text) => {
  const node = $(selector);
  if (node) node.textContent = text;
};

feed.addEventListener("scroll", () => {
  const gap = feed.scrollHeight - feed.scrollTop - feed.clientHeight;
  stick = gap < 42;
  $("#jump").hidden = stick;
});

$("#jump").addEventListener("click", () => {
  stick = true;
  feed.scrollTop = feed.scrollHeight;
  $("#jump").hidden = true;
});

function rowLine(row) {
  const text = row.text || "";
  if ((row.kind === "tool" || row.kind === "command") && row.output) {
    return `${text}\n${row.output}`;
  }
  return text;
}

function renderRows(rows) {
  const key = rows.map((row) => row.id).join(",");
  if (key === lastRowsKey) return;
  lastRowsKey = key;
  setText("#count", `${rows.length} rows`);
  feed.replaceChildren();
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "row";
    empty.innerHTML = '<span class="at">—</span><span class="role">system</span><span class="text">The archive is open. Speak or send a turn.</span>';
    feed.append(empty);
    return;
  }
  for (const row of rows) {
    const item = document.createElement("div");
    item.className = "row";
    item.dataset.kind = row.kind || "event";
    const at = document.createElement("span");
    at.className = "at";
    at.textContent = String(row.at || "").slice(11, 19) || "—";
    const role = document.createElement("span");
    role.className = "role";
    role.textContent = row.role || row.kind || "system";
    const text = document.createElement("span");
    text.className = "text";
    text.textContent = rowLine(row);
    item.append(at, role, text);
    feed.append(item);
  }
  if (stick) feed.scrollTop = feed.scrollHeight;
}

function renderCall(state) {
  const calls = state.calls || {};
  const active = calls.active;
  const clock = $("#call-clock");
  const line = $("#call-line");
  const opening = $("#call-opening");
  const feed = $("#call-queue");
  if (!clock || !line || !opening || !feed) return;
  opening.replaceChildren();
  feed.replaceChildren();
  if (!active) {
    clock.textContent = "no open call";
    line.textContent = "A call opens with name, presence, and want.";
    return;
  }
  const phase = active.phase === "opening" ? "opening" : active.listening ? "listening" : active.phase;
  const left = Math.max(0, active.remaining_sec || 0);
  clock.textContent = `${phase} · ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
  line.textContent = `${active.agent} on the line · ${phase}`;
  for (const row of active.opening || []) {
    const item = document.createElement("li");
    const name = document.createElement("b");
    name.textContent = `${row.name} `;
    const presence = document.createElement("span");
    presence.textContent = `${row.presence} · wants ${row.want}`;
    item.append(name, presence);
    opening.append(item);
  }
  for (const row of (active.queue || []).slice(-4)) {
    const item = document.createElement("li");
    item.textContent = `${row.speaker} · ${row.text}`;
    feed.append(item);
  }
}

function renderDialin(state) {
  const dialin = state.dialin || {};
  const rows = dialin.civilians || [];
  const list = $("#queue-roster");
  if (!list) return;
  setText("#call-mode", dialin.call === "natural-language" ? "in call · natural language" : "call");
  const key = rows.map((row) => `${row.id}:${row.verified}`).join("|");
  if (list.dataset.key === key) return;
  list.dataset.key = key;
  list.replaceChildren();
  for (const row of rows) {
    const item = document.createElement("li");
    item.dataset.verified = String(Boolean(row.verified));
    const name = document.createElement("b");
    name.textContent = row.name;
    const number = document.createElement("span");
    number.textContent = row.number;
    const role = document.createElement("small");
    role.textContent = row.role;
    item.append(name, number, role);
    item.title = row.package_identity || "package pending";
    list.append(item);
  }
}

function render(state) {
  const link = $("#link");
  const deb = state.debian || {};
  const mind = state.mind || {};
  link.dataset.state = deb.state === "live" ? "live" : deb.state === "refused" ? "refused" : "waiting";
  link.textContent = deb.state === "live" ? "desktop live" : deb.state || "connecting";
  $("#spinner").hidden = !state.working;
  setText("#mind-state", mind.state || "idle");
  setText("#frame-at", deb.at ? deb.at.slice(11, 19) : "—");
  setText("#frame-cap", deb.width ? `Debian ${deb.width}×${deb.height} · display :0` : "waiting for the Debian view");
  const archive = state.archive || {};
  const rows = archive.rows || [];
  renderRows(rows);
  const latest = rows[rows.length - 1];
  setText("#turn-kind", latest ? `${latest.role || latest.kind} · turn ${latest.id}` : "—");
  renderDialin(state);
  renderCall(state);
  if (deb.capture_ts && deb.capture_ts !== lastFrame) {
    lastFrame = deb.capture_ts;
    $("#frame").src = `/api/toast/debian.png?ts=${deb.capture_ts}`;
  }
}

async function poll() {
  try {
    const reply = await fetch("/api/toast", { cache: "no-store" });
    render(await reply.json());
  } catch (error) {
    setText("#notice", `toast link · ${error}`);
    $("#link").dataset.state = "refused";
    $("#link").textContent = "link lost";
  }
  setTimeout(poll, 1000);
}

poll();
