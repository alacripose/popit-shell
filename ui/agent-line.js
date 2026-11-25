/* External agent client: Ed25519 identity, one-time enrollment, WebRTC call to the phone. */
import { loadContour, fillContours } from "/contour.js";

let contourReady = false;
loadContour("/contour.json")
  .then(() => { contourReady = true; fillContours(document); })
  .catch(() => undefined);

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = { identity: null, publicKey: "", contact: null, call: "", pc: null, local: null, timer: 0, ice: [] };
  const secure = window.isSecureContext === true;

  const log = (text) => {
    const node = $("agent-log");
    if (node) node.textContent = `${new Date().toLocaleTimeString()}  ${text}\n${node.textContent}`.slice(0, 6000);
  };
  const status = (text, kind = "") => {
    const node = $("agent-status");
    if (!node) return;
    node.textContent = text;
    node.classList.toggle("ok", kind === "ok");
    node.classList.toggle("bad", kind === "bad");
  };
  const setPill = (text, kind) => {
    const node = $("agent-secure");
    if (!node) return;
    node.textContent = text;
    node.classList.toggle("ok", kind === "ok");
    node.classList.toggle("bad", kind === "bad");
  };

  function canonical(value) {
    if (value === null || typeof value !== "object") return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }

  function iso() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  function bytesToBase64(bytes) {
    let text = "";
    for (const byte of new Uint8Array(bytes)) text += String.fromCharCode(byte);
    return btoa(text);
  }

  function publicPem(spki) {
    const body = bytesToBase64(spki).match(/.{1,64}/g) || [];
    return `-----BEGIN PUBLIC KEY-----\n${body.join("\n")}\n-----END PUBLIC KEY-----`;
  }

  async function newIdentity() {
    if (!window.crypto?.subtle) {
      status("This browser has no Web Crypto. Use tools/external_agent.py instead.", "bad");
      return;
    }
    try {
      const pair = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
      state.identity = pair.privateKey;
      const spki = await crypto.subtle.exportKey("spki", pair.publicKey);
      state.publicKey = publicPem(spki);
      state.contact = null;
      state.call = "";
      $("agent-call").disabled = true;
      $("agent-end").disabled = true;
      $("agent-contact").textContent = "Identity generated in this tab. The private key is not stored.";
      status("Identity ready. Paste the owner's one-time code and enroll.", "ok");
      log("Ed25519 identity generated");
    } catch (error) {
      status(`Ed25519 unavailable · ${error.message}`, "bad");
      log(`identity refused: ${error.message}`);
    }
  }

  async function sign(value) {
    const bytes = new TextEncoder().encode(canonical(value));
    const signature = await crypto.subtle.sign("Ed25519", state.identity, bytes);
    return bytesToBase64(signature);
  }

  async function post(path, body) {
    const response = await fetch(path, {
      cache: "no-store", method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const receipt = await response.json().catch(() => ({}));
    if (!response.ok || receipt.ok === false) {
      const refused = receipt.refused;
      throw new Error(refused && typeof refused === "object"
        ? `${refused.code || "refused"}: ${refused.detail || ""}`
        : String(refused || `http-${response.status}`));
    }
    return receipt;
  }

  async function enroll() {
    if (!state.identity) await newIdentity();
    if (!state.identity) return;
    const name = $("agent-name").value.trim();
    const code = $("agent-code").value.trim();
    const endpoint = $("agent-endpoint").value.trim();
    if (!name || !code || !endpoint) {
      status("Name, the owner's code and an https endpoint are required.", "bad");
      return;
    }
    status("Signing the registration and asking the host to verify it…");
    try {
      const payload = {
        schema: "popit.agent-registration/1", name, endpoint,
        public_key: state.publicKey, issued_at: iso(), code,
      };
      payload.signature = await sign(payload);
      const receipt = await post("/api/toast/external/enroll", payload);
      state.contact = receipt.contact;
      $("agent-call").disabled = false;
      $("agent-contact").textContent = `${receipt.contact.name} · ${receipt.contact.line} · ${receipt.contact.fingerprint}\nworkspace ${receipt.workspace}`;
      status("Enrolled. The phone now has a verified external line for this agent.", "ok");
      log(`enrolled ${receipt.contact.id} ${receipt.contact.line}`);
    } catch (error) {
      status(`Enrollment refused · ${error.message}`, "bad");
      log(`enrollment refused: ${error.message}`);
    }
  }

  async function flushIce() {
    if (!state.call) return;
    const pending = state.ice.splice(0);
    for (const candidate of pending) {
      await post("/api/toast/external/call/ice", {
        call_id: state.call, side: "agent", candidate,
      }).catch(() => undefined);
    }
  }

  async function callPhone() {
    if (!state.contact) {
      status("Enroll first; a call needs a verified contact.", "bad");
      return;
    }
    if (!secure) {
      status("WebRTC needs the HTTPS Popit origin.", "bad");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
      status("This browser has no microphone/WebRTC path.", "bad");
      return;
    }
    status("Opening the microphone and collecting an SDP offer…");
    try {
      state.local = await navigator.mediaDevices.getUserMedia({ audio: true });
      const pc = new RTCPeerConnection({ iceServers: [] });
      state.pc = pc;
      state.ice = [];
      state.call = "";
      for (const track of state.local.getTracks()) pc.addTrack(track, state.local);
      pc.ontrack = (event) => {
        const audio = $("agent-audio");
        if (audio && event.streams?.[0]) audio.srcObject = event.streams[0];
        audio?.play().catch(() => undefined);
      };
      pc.onicecandidate = (event) => {
        const candidate = event.candidate ? event.candidate.toJSON() : null;
        if (state.call) {
          post("/api/toast/external/call/ice", {
            call_id: state.call, side: "agent", candidate,
          }).catch(() => undefined);
        } else {
          state.ice.push(candidate);
        }
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "connected") status("Connected. The phone line is live.", "ok");
        if (pc.connectionState === "failed") status("WebRTC failed; this path needs a TURN relay.", "bad");
      };
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await new Promise((resolve) => {
        if (pc.iceGatheringState === "complete") return resolve();
        const done = () => {
          if (pc.iceGatheringState === "complete") { pc.removeEventListener("icegatheringstatechange", done); resolve(); }
        };
        pc.addEventListener("icegatheringstatechange", done);
        window.setTimeout(resolve, 2500);
      });
      const payload = {
        schema: "popit.agent-call/1", agent: state.contact.id,
        nonce: [...crypto.getRandomValues(new Uint8Array(16))].map((byte) => byte.toString(16).padStart(2, "0")).join(""),
        issued_at: iso(), offer: pc.localDescription.sdp,
      };
      payload.signature = await sign(payload);
      const opened = await post("/api/toast/external/call", payload);
      state.call = opened.call_id;
      $("agent-end").disabled = false;
      status("Ringing the phone. The owner will see this verified line.", "ok");
      log(`call ${state.call} ringing`);
      await flushIce();
      state.timer = window.setInterval(pollCall, 900);
    } catch (error) {
      status(`Call refused · ${error.message}`, "bad");
      log(`call refused: ${error.message}`);
      stop();
    }
  }

  async function pollCall() {
    const call = state.call;
    const pc = state.pc;
    if (!call || !pc) return;
    try {
      const receipt = await post("/api/toast/external/call/state", { call_id: call });
      if (receipt.answer && !pc.remoteDescription) {
        await pc.setRemoteDescription({ type: "answer", sdp: receipt.answer });
        status("Answer received. Negotiating the audio path…", "ok");
      }
      const candidates = receipt.phone_ice || [];
      for (const candidate of candidates) {
        if (candidate) await pc.addIceCandidate(candidate).catch(() => undefined);
      }
      if (receipt.state === "ended" || receipt.state === "declined") {
        status("The phone ended the call.", "bad");
        stop();
      }
    } catch (error) {
      status(`Call state unavailable · ${error.message}`, "bad");
    }
  }

  function stop() {
    window.clearInterval(state.timer);
    state.timer = 0;
    if (state.pc) {
      try { state.pc.close(); } catch (_) {}
      state.pc = null;
    }
    if (state.local) {
      state.local.getTracks().forEach((track) => track.stop());
      state.local = null;
    }
    if (state.call) {
      post("/api/toast/external/call/end", { call_id: state.call, outcome: "ended" }).catch(() => undefined);
    }
    state.call = "";
    $("agent-end").disabled = true;
  }

  $("agent-identity")?.addEventListener("click", newIdentity);
  $("agent-enroll")?.addEventListener("click", enroll);
  $("agent-call")?.addEventListener("click", callPhone);
  $("agent-end")?.addEventListener("click", stop);
  setPill(secure ? "SECURE WEBRTC" : "HTTP READ ONLY", secure ? "ok" : "bad");
  if (!secure) status("Open the HTTPS origin to use the microphone and WebRTC.", "bad");
  newIdentity();
})();
