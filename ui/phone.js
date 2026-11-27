/* Popit Springboard: the phone's own chat and voice client. */
import { loadContour, fillContours } from "/contour.js";
import { attach } from "/package.js";

let contourReady = false;
function drawContours(root = document) {
  if (contourReady) fillContours(root);
}
loadContour("/contour.json")
  .then(() => { contourReady = true; fillContours(document); })
  .catch(() => undefined);

(() => {
  "use strict";

  // The home is delivered inside the agent window. Loaded as a page of its own it is the fake
  // SpringBoard, so this page refuses to paint rather than render a copy of the surface.
  if (window.parent === window) {
    document.body.innerHTML = "";
    const node = document.createElement("p");
    node.id = "standalone-refusal";
    node.textContent = "springboard-standalone-refused";
    document.body.append(node);
    return;
  }

  const $ = (id) => document.getElementById(id);
  const state = { lanes: null, archive: null, selected: null, view: "home", refreshTimer: 0 };
  const secure = window.isSecureContext === true;
  let media = null;
  let audio = null;
  let source = null;
  let processor = null;
  let silentGain = null;
  let chunks = [];
  let recording = false;
  let startedAt = 0;
  let timer = 0;
  let autoStop = 0;
  let streamQueue = Promise.resolve();
  let replyAudio = null;
  let replyUrl = "";

  const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));

  async function api(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const receipt = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(receipt.refused || receipt.detail || `http-${response.status}`);
    return receipt;
  }

  function setPill(element, text, kind) {
    if (!element) return;
    element.textContent = text;
    element.classList.toggle("ok", kind === "ok");
    element.classList.toggle("bad", kind === "bad");
  }

  function updateClock() {
    $("clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function shortTime(value) {
    if (!value) return "";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function activeLanes() {
    return (state.lanes && state.lanes.active) || [];
  }

  function laneLabel() {
    return state.selected || "COMMONS";
  }

  // The SpringBoard shows signed app packages, not lanes dressed as apps. DialIn is the
  // phone calling surface and Settings is the theme package; anything without a package
  // identity is not a tile, and a package that fails verification cannot be opened.
  // Names and marks only. A tile carries the app's name and its signed identity; the one-line
  // descriptions that used to sit here were copy nobody asked for, so they are gone.
  const APP_SURFACE = {
    dialin: { label: "DialIn", glyph: "◉" },
    settings: { label: "Settings", glyph: "⚙" },
    prose: { label: "Prose", glyph: "¶" },
    archive: { label: "Archive", glyph: "▦" },
    evidence: { label: "Evidence", glyph: "⧉" },
    bridge: { label: "Bridge", glyph: "⇄" },
  };
  // The settings tile opens the settings app package's window — the panel the desk draws —
  // never the package document page that names its revision.
  // The settings tile opens the settings package window itself — the desk's own page in its
  // settings-window mode — never the package document page, and never a copy of the panel.
  const APP_ROUTE = { settings: "/toast.html?window=settings", dialin: "/toast.html",
                      prose: "/toast.html?window=prose",
                      archive: "/toast.html?window=archive",
                      evidence: "/toast.html?window=evidence", bridge: "/bridge.html" };

  // Every app is delivered the way the settings window is delivered: its own signed page in
  // the window that delivered the SpringBoard, not a second OS window rendering a copy.

  function launchFor(name) {
    // The tile opens the launch the package signed, not a route the home remembers.
    const row = (appPackages && appPackages.apps && appPackages.apps[name]) || {};
    return row.launch || APP_ROUTE[name] || "";
  }

  function openApp(name) {
    const route = launchFor(name);
    if (!route) return;
    // An app opens in the window that delivered the SpringBoard, the way the desk is
    // delivered: no second OS window holding a copy of a surface.
    location.assign(route);
  }
  let appPackages = null;

  function shortIdentity(identity) {
    const match = /^app-([a-z]+)@(\d+)\+blake3:([0-9a-f]{6})/.exec(identity || "");
    return match ? `app-${match[1]}@${match[2]} · ${match[3]}` : "";
  }

  function packageTiles() {
    const apps = (appPackages && appPackages.apps) || {};
    // A name the registry lists as foreign is shown as refused: a rejection is named on the
    // home, never silently dropped from it.
    const foreign = (appPackages && appPackages.foreign) || {};
    return Object.keys(APP_SURFACE).filter((name) => apps[name] || foreign[name]).map((name) => {
      const row = apps[name] || foreign[name] || {};
      const refusal = row.refused || null;
      // An icon frame carries a signature only when the package proves it launches its mutated
      // window: the shell reads the signed entry page and reports that the launch opens it.
      const launch = row.launch || "";
      const proof = Boolean(launch) && Boolean(row.launch_proof && row.launch_proof.ok);
      return {
        key: name,
        ...APP_SURFACE[name],
        verified: row.verified === true && !refusal && proof,
        identity: row.identity || "",
        launch,
        refusal: refusal ? String(refusal.code || refusal)
          : (row.verified === true && !proof ? "app-tile-unproven-launch" : ""),
      };
    });
  }

  async function loadAppPackages() {
    try {
      const reply = await api("/api/toast/apps");
      appPackages = reply && reply.apps ? reply : null;
    } catch (error) {
      appPackages = null;
    }
    renderTiles();
  }

  function renderTiles() {
    const tiles = $("tiles");
    if (!tiles) return;
    const items = packageTiles();
    const signature = items
      .map((item) => `${item.key}:${item.verified}:${item.identity}:${item.refusal}`).join("|");
    if (tiles.dataset.signature === signature && items.length) return;
    tiles.dataset.signature = signature;
    if (!items.length) {
      tiles.innerHTML = `<p class="tile-empty">${appPackages
        ? "No signed app package is available."
        : "Reading the signed app packages…"}</p>`;
      return;
    }
    tiles.innerHTML = items.map((item) => `
      <button class="tile surface-motion${item.verified ? "" : " refused"}" type="button"
              data-kind="app" data-lane="${escapeHTML(item.key)}"
              data-verified="${item.verified}"
              data-package-identity="${escapeHTML(item.identity)}"
              ${item.verified ? "" : "disabled"}
              title="${escapeHTML(item.identity || item.refusal)}"
              data-contour="card">
        <span class="tile-badge">${item.verified ? "SIGNED" : "REFUSED"}</span>
        <span class="tile-glyph" data-contour="window">${escapeHTML(item.glyph)}</span>
        <span class="tile-name">${escapeHTML(item.label)}</span>
        <span class="tile-package">${escapeHTML(item.verified
          ? shortIdentity(item.identity) : item.refusal)}</span>
      </button>
    `).join("");
    drawContours(tiles);
    tiles.querySelectorAll(".tile").forEach((tile) => {
      if (tile.dataset.verified !== "true") return;
      tile.addEventListener("click", () => {
        // Every tile opens the way dialin does: embedded in the shell, the tile hands control
        // back to the window that delivered it, and that window shows the app itself. A tile
        // that opened its own OS window would be a copy of the surface, not the surface.
        if (window.parent !== window) {
          window.parent.postMessage({ source: "popit-springboard", app: tile.dataset.lane },
                                    location.origin);
          return;
        }
        openApp(tile.dataset.lane);
      });
    });
  }

  function visibleRows() {
    const rows = (state.archive && state.archive.rows) || [];
    const lane = state.selected;
    return rows.filter((row) => {
      if (!row || !["user", "cua"].includes(row.kind)) return false;
      if (lane) {
        if (row.kind === "user") return (row.targets || []).includes(lane);
        return row.role === lane;
      }
      return true;
    }).slice(-80);
  }

  function renderMessages() {
    const box = $("messages");
    if (!box) return;
    const rows = visibleRows();
    if (!rows.length) {
      box.innerHTML = `<p class="empty">No lines in ${escapeHTML(laneLabel())} yet.</p>`;
      return;
    }
    box.innerHTML = rows.map((row) => `
      <article class="message ${row.kind === "user" ? "you" : "agent"}">
        <div class="message-head">
          <span class="message-who">${escapeHTML(row.kind === "user" ? "YOU" : (row.role || "AGENT"))}</span>
          <span class="message-time">${escapeHTML(shortTime(row.at))}</span>
        </div>
        <div class="message-text">${escapeHTML(row.text || "")}</div>
      </article>
    `).join("");
    drawContours(box);
    box.scrollTop = box.scrollHeight;
  }

  function renderChatMeta() {
    const meta = $("chat-meta");
    if (!meta) return;
    const lanes = activeLanes().map((lane) => lane.name);
    meta.innerHTML = state.selected
      ? `<span>PRIVATE LANE · ${escapeHTML(state.selected)}</span><span>${lanes.length} LIVE</span>`
      : `<span>COMMONS · ALL LANES</span><span>${lanes.length} LIVE</span>`;
    $("chat-eyebrow").textContent = state.selected ? "AGENT LANE" : "COMMONS · ALL LANES";
    $("chat-title").textContent = state.selected || "Shared room";
  }

  async function refresh() {
    try {
      const next = await api("/api/toast");
      state.lanes = next.lanes;
      state.archive = next.archive;
      renderTiles();
      renderChatMeta();
      if (state.view === "chat") renderMessages();
    } catch (error) {
      // A home that cannot read the archive shows the refusal in the bar, not a status sentence:
      // the count of lanes and the microphone state were a construction the family refuses.
      const pill = $("secure-pill");
      if (pill) pill.textContent = `archive refused · ${error.message}`;
    }
  }

  function scheduleRefresh() {
    window.clearTimeout(state.refreshTimer);
    state.refreshTimer = window.setTimeout(refresh, 260);
  }

  function switchScreen(name) {
    state.view = name;
    $("home-screen").hidden = name !== "home";
    $("chat-screen").hidden = name !== "chat";
    $("voice-screen").hidden = name !== "voice";
    $("agents-screen").hidden = name !== "agents";
    if (name === "chat") renderMessages();
  }

  function pushSurface(name) {
    if (window.history && window.history.pushState) window.history.pushState({ surface: name }, "", location.pathname + location.search);
  }

  function home() {
    stopVoice(false);
    state.selected = null;
    state.view = "home";
    if (window.PopitAgents) window.PopitAgents.close();
    switchScreen("home");
    if (window.history && window.history.replaceState) window.history.replaceState({ surface: "home" }, "", location.pathname + location.search);
  }

  async function openChat(lane) {
    state.selected = lane;
    switchScreen("chat");
    renderChatMeta();
    renderMessages();
    pushSurface("chat");
    if (secure) {
      try {
        await api("/api/toast/lanes", { method: "POST", body: JSON.stringify({ names: lane ? [lane] : [] }) });
      } catch (error) {
        $("composer-note").textContent = `Lane selection refused · ${error.message}`;
      }
    }
    refresh();
  }

  function openVoice() {
    state.selected = null;
    switchScreen("voice");
    pushSurface("voice");
    if (secure) {
      api("/api/toast/lanes", { method: "POST", body: JSON.stringify({ names: [] }) }).catch(() => undefined);
    }
    refresh();
  }

  function openAgents() {
    state.selected = null;
    switchScreen("agents");
    pushSurface("agents");
    if (window.PopitAgents) window.PopitAgents.open();
    else $("agents-note").textContent = "The external line module did not load.";
  }

  async function sendOwner(text) {
    const clean = String(text || "").trim();
    if (!clean) return;
    if (!secure) {
      $("composer-note").textContent = "Read-only over plain HTTP. Open the HTTPS URL and accept the certificate to write or speak.";
      return;
    }
    const input = $("owner-text");
    const button = $("owner-say");
    input.value = "";
    input.disabled = true;
    button.disabled = true;
    try {
      await api("/api/toast/phone/hear", {
        method: "POST", body: JSON.stringify({ text: clean, lane: state.selected || "" }),
      });
      $("composer-note").textContent = "Sent into the live archive. The lanes are answering.";
      await refresh();
    } catch (error) {
      $("composer-note").textContent = `The room refused · ${error.message}`;
    } finally {
      input.disabled = false;
      button.disabled = false;
      input.focus();
    }
  }

  function writeString(view, offset, text) {
    for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index));
  }

  function encodeWav(buffers, rate) {
    const length = buffers.reduce((sum, buffer) => sum + buffer.length, 0);
    const data = new DataView(new ArrayBuffer(44 + length * 2));
    writeString(data, 0, "RIFF");
    data.setUint32(4, 36 + length * 2, true);
    writeString(data, 8, "WAVE");
    writeString(data, 12, "fmt ");
    data.setUint32(16, 16, true);
    data.setUint16(20, 1, true);
    data.setUint16(22, 1, true);
    data.setUint32(24, rate, true);
    data.setUint32(28, rate * 2, true);
    data.setUint16(32, 2, true);
    data.setUint16(34, 16, true);
    writeString(data, 36, "data");
    data.setUint32(40, length * 2, true);
    let offset = 44;
    for (const buffer of buffers) {
      for (let index = 0; index < buffer.length; index += 1) {
        const sample = Math.max(-1, Math.min(1, buffer[index]));
        data.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
        offset += 2;
      }
    }
    return data.buffer;
  }

  function updateVoiceTimer() {
    if (!recording) return;
    const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    $("voice-timer").textContent = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;
    if (elapsed >= 30) stopVoice(true);
  }

  async function startVoice() {
    if (!secure) {
      $("voice-status").textContent = "Mic capture needs the HTTPS Popit URL. Plain HTTP is view-only.";
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      $("voice-status").textContent = "This browser does not expose microphone capture.";
      return;
    }
    try {
      media = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      audio = new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") await audio.resume();
      source = audio.createMediaStreamSource(media);
      processor = audio.createScriptProcessor(4096, 1, 1);
      silentGain = audio.createGain();
      silentGain.gain.value = 0;
      chunks = [];
      processor.onaudioprocess = (event) => {
        if (!recording) return;
        chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      };
      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audio.destination);
      recording = true;
      startedAt = Date.now();
      $("voice-orb").classList.add("recording");
      $("voice-start").disabled = true;
      $("voice-stop").disabled = false;
      $("transcript").textContent = "";
      $("voice-status").textContent = "Speaking.";
      timer = window.setInterval(updateVoiceTimer, 250);
      autoStop = window.setTimeout(() => stopVoice(true), 30000);
    } catch (error) {
      $("voice-status").textContent = `Microphone refused · ${error.message}`;
      await stopVoice(false);
    }
  }

  async function stopVoice(send = true) {
    if (!recording && !media) return;
    const wasRecording = recording;
    const sampleRate = audio ? audio.sampleRate : 48000;
    recording = false;
    window.clearInterval(timer);
    window.clearTimeout(autoStop);
    $("voice-orb").classList.remove("recording");
    $("voice-start").disabled = false;
    $("voice-stop").disabled = true;
    if (processor) processor.onaudioprocess = null;
    try { if (source) source.disconnect(); } catch (_) {}
    try { if (processor) processor.disconnect(); } catch (_) {}
    try { if (silentGain) silentGain.disconnect(); } catch (_) {}
    try { if (media) media.getTracks().forEach((track) => track.stop()); } catch (_) {}
    try { if (audio) await audio.close(); } catch (_) {}
    media = null; audio = null; source = null; processor = null; silentGain = null;
    if (!send || !wasRecording) return;
    if (!chunks.length) {
      $("voice-status").textContent = "No audio was captured. Try again and speak after the listener starts.";
      return;
    }
    $("voice-status").textContent = "Encoding the clip and asking Buffy through the endpoint…";
    const wav = encodeWav(chunks, sampleRate);
    const lane = state.selected ? `lane=${encodeURIComponent(state.selected)}&` : "";
    try {
      const response = await fetch(`/api/toast/phone/audio?${lane}reply=1`, {
        method: "POST", cache: "no-store", headers: { "Content-Type": "audio/wav" }, body: wav,
      });
      const receipt = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(receipt.refused || `http-${response.status}`);
      }
      const text = receipt.transcript || "";
      const answer = receipt.answer || "";
      $("transcript").textContent = [
        text ? `YOU · ${text}` : "The recognizer heard silence.",
        answer ? `BUFFY · ${answer}` : (receipt.refused ? `VOICE · ${receipt.refused}` : ""),
      ].filter(Boolean).join("\n\n");
      if (receipt.audio_b64) {
        const bytes = Uint8Array.from(atob(receipt.audio_b64), (ch) => ch.charCodeAt(0));
        const blob = new Blob([bytes], { type: receipt.audio_mime || "audio/wav" });
        if (replyUrl) URL.revokeObjectURL(replyUrl);
        replyUrl = URL.createObjectURL(blob);
        if (!replyAudio) replyAudio = new Audio();
        replyAudio.src = replyUrl;
        await replyAudio.play().catch(() => undefined);
      }
      $("voice-status").textContent = answer
        ? `Buffy answered through the endpoint${receipt.voice_profile ? ` · ${receipt.voice_profile}` : ""}${receipt.audio_b64 ? " · playing on this phone" : " · text only"}.`
        : (text ? "The turn reached the room, but no answer came back." : "Silence was filtered before it could become an owner turn.");
      await refresh();
    } catch (error) {
      $("voice-status").textContent = `Voice refused · ${error.message}`;
    }
    chunks = [];
  }

  function wire() {
    document.body.dataset.secure = String(secure);
    setPill($("secure-pill"), secure ? "SECURE VOICE" : "READ ONLY", secure ? "ok" : "bad");
    setPill($("voice-secure"), secure ? "CERT-COVERED" : "HTTP READ ONLY", secure ? "ok" : "bad");
    $("foot-mode").textContent = secure ? "HTTPS · MIC READY" : "HTTP · VIEW ONLY";
    $("composer-note").textContent = secure
      ? "The phone sends through the same archive as the desktop."
      : "Read-only over HTTP. Open the HTTPS Popit URL to chat or speak.";
    if (!secure) {
      $("owner-text").disabled = true;
      $("owner-say").disabled = true;
      $("voice-start").disabled = true;
      $("voice-status").textContent = "Voice is disabled on plain HTTP. Open the HTTPS certificate URL to use the microphone.";
    }
    $("home-key").addEventListener("click", home);
    // The desk's bar carries this page's home key. Its press is this page's home button, so
    // the frame returns to its home screen (an open app, chat or voice screen included)
    // instead of being raised on whatever screen it had been left on.
    window.addEventListener("message", (event) => {
      if (event.origin !== location.origin) return;
      const data = event.data;
      if (!data || data.source !== "popit-desk" || data.intent !== "home") return;
      home();
    });
    document.querySelectorAll("[data-home]").forEach((node) => node.addEventListener("click", home));
    $("owner-form").addEventListener("submit", (event) => {
      event.preventDefault();
      sendOwner($("owner-text").value);
    });
    $("voice-start").addEventListener("click", startVoice);
    $("voice-stop").addEventListener("click", () => stopVoice(true));
    window.addEventListener("popstate", home);
    let touchStart = 0;
    document.addEventListener("touchstart", (event) => {
      touchStart = event.touches[0] ? event.touches[0].clientX : 0;
    }, { passive: true });
    document.addEventListener("touchend", (event) => {
      const end = event.changedTouches[0] ? event.changedTouches[0].clientX : 0;
      if (state.view !== "home" && end - touchStart > 76) home();
    }, { passive: true });
    if (window.history && window.history.replaceState) window.history.replaceState({ surface: "home" }, "", location.pathname + location.search);
    updateClock();
    window.setInterval(updateClock, 15000);
    refresh();
    loadAppPackages();
    window.setInterval(() => { if (state.view !== "voice") refresh(); }, 4000);
    // A package that was refused while this page was open turns green without a reload.
    window.setInterval(loadAppPackages, 20000);
    if (window.EventSource) {
      const events = new EventSource("/api/toast/events");
      events.onmessage = scheduleRefresh;
      events.onerror = () => undefined;
    }
    // The home is delivered inside the window that owns this origin, and that window registers
    // the family's shell worker at scope `/`. A second worker at the same scope replaces it
    // and the window's own page then arrives through a worker that does not know its routes,
    // which is how the home opened onto an empty frame. The window owns offline; the home
    // does not register a worker of its own.
    if (window.parent === window && "serviceWorker" in navigator && secure) {
      navigator.serviceWorker.getRegistrations()
        .then((rows) => rows.filter((row) => row.scope === new URL("/", location.origin).href)
          .forEach((row) => row.unregister()))
        .catch(() => undefined);
    }
  }

  wire();
})();

// The SpringBoard is a signed app package and takes the family theme the settings
// package published, rather than painting a private copy of the family look. The same
// document supplies the layout each app's window is opened with.
let settingsPublished = {};
// A home that never finished attaching must not hold the window on a blank frame: the ready
// message is sent once, by whichever happens first, and the window paints what it has.
let homeReady = false;
function tellReady() {
  if (homeReady || window.parent === window) return;
  homeReady = true;
  window.parent.postMessage({ source: "popit-springboard", ready: true }, location.origin);
}
window.setTimeout(tellReady, 4000);
attach("springboard", { identitySelector: "#package-identity" }).then((doc) => {
  settingsPublished = (doc && doc.theme) || {};
}).finally(() => {
  // The home tells the window that delivered it when it has painted its own package, so the
  // window shows a finished SpringBoard instead of a page that has not applied its theme,
  // layout and scale yet.
  tellReady();
});
