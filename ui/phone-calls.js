/* External agent lines: owner-issued enrollment, verified contacts and WebRTC calls. */
import { loadContour, fillContours } from "/contour.js";

let contourReady = false;
function drawContours(root = document) {
  if (contourReady) fillContours(root);
}
loadContour("/contour.json")
  .then(() => { contourReady = true; fillContours(document); })
  .catch(() => undefined);

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const secure = window.isSecureContext === true;
  const state = {
    contacts: [], incoming: null, active: "", pc: null, local: null,
    agentIceSeen: 0, incomingTimer: 0, callTimer: 0,
  };

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
    if (!response.ok || receipt.ok === false) {
      const refused = receipt.refused;
      const detail = refused && typeof refused === "object"
        ? `${refused.code || "refused"}: ${refused.detail || ""}`
        : String(refused || `http-${response.status}`);
      throw new Error(detail);
    }
    return receipt;
  }

  function setText(id, text) {
    const node = $(id);
    if (node) node.textContent = text;
  }

  function shortFingerprint(value) {
    const text = String(value || "");
    return text.startsWith("blake3:") ? `${text.slice(0, 15)}…` : text.slice(0, 15);
  }

  function renderContacts() {
    const list = $("agent-list");
    if (!list) return;
    list.innerHTML = state.contacts.map((row) => `
      <article class="agent-entry" data-contour="card">
        <div class="agent-entry-head">
          <span class="agent-entry-name">${escapeHTML(row.name)}</span>
          <span class="agent-entry-state">verified</span>
        </div>
        <div class="agent-entry-meta">${escapeHTML(row.line || "no line")} · ${escapeHTML(shortFingerprint(row.fingerprint))} · ${escapeHTML(row.endpoint || "no endpoint")}</div>
        <div class="agent-entry-meta">${row.number ? `${escapeHTML(row.number)} · declared, unverified` : "no declared number"}</div>
        <div class="agent-entry-meta">workspace ${escapeHTML(row.workspace || "owner-managed")}</div>
      </article>
    `).join("");
    setText("agent-list-note", state.contacts.length
      ? `${state.contacts.length} verified external line${state.contacts.length === 1 ? "" : "s"}`
      : "No verified external lines yet.");
    drawContours(list);
  }

  async function loadContacts() {
    if (!secure) {
      setText("agents-note", "External lines need the HTTPS phone origin. Plain HTTP is read-only.");
      return;
    }
    try {
      const receipt = await api("/api/toast/external/contacts");
      state.contacts = Array.isArray(receipt.contacts) ? receipt.contacts : [];
      renderContacts();
    } catch (error) {
      setText("agents-note", `Contact book refused · ${error.message}`);
    }
  }

  function showEnrollment(receipt) {
    const panel = $("enrollment");
    if (!panel) return;
    panel.hidden = false;
    setText("enrollment-code", receipt.code || "");
    const expires = receipt.expires_at ? new Date(receipt.expires_at) : null;
    setText("enrollment-expiry", expires && !Number.isNaN(expires.getTime())
      ? `Expires ${expires.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}. The agent signs the registration with its Ed25519 key.`
      : "Send this code to the agent out of band. It is single-use.");
    navigator.clipboard?.writeText(receipt.code || "").catch(() => undefined);
  }

  async function invite() {
    if (!secure) {
      setText("agents-note", "Open the HTTPS phone origin before inviting an agent.");
      return;
    }
    const name = window.prompt("Name the external agent", "External agent");
    if (!name || !name.trim()) return;
    try {
      const receipt = await api("/api/toast/external/enrollment", {
        method: "POST", body: JSON.stringify({ name: name.trim() }),
      });
      showEnrollment(receipt);
      setText("agents-note", "One-time code ready. Give it to the agent with the enrollment endpoint.");
    } catch (error) {
      setText("agents-note", `Invite refused · ${error.message}`);
    }
  }

  function requestScopes(call) {
    const scopes = call?.request?.scopes;
    return Array.isArray(scopes) ? scopes.filter((scope) => typeof scope === "string") : [];
  }

  function setCallSheet(visible, call = {}) {
    const sheet = $("call-sheet");
    if (!sheet) return;
    sheet.hidden = !visible;
    if (!visible) return;
    setText("call-name", call.name || "External agent");
    setText("call-line", call.line || "POPIT-LINE");
    setText("call-number", call.number ? `${call.number} · declared, unverified` : "no declared number");
    setText("call-status", "A verified agent is ringing this phone.");
    // The signed request is what the owner is answering, so it is shown before the buttons
    // and the share button only exists when there is something to share.
    const scopes = requestScopes(call);
    const block = $("call-request");
    if (block) {
      block.hidden = scopes.length === 0;
      block.textContent = scopes.length
        ? `Asks to read: ${scopes.join(", ")}${call.request?.note ? ` — ${call.request.note}` : ""}. Nothing is shared unless you answer with it.`
        : "";
    }
    const share = $("call-share");
    if (share) {
      share.hidden = scopes.length === 0;
      share.textContent = `SHARE ${scopes.join(" + ").toUpperCase()} & ANSWER`;
    }
    $("call-accept").hidden = false;
    $("call-accept").textContent = scopes.length ? "ANSWER WITHOUT SHARING" : "ACCEPT";
    $("call-decline").hidden = false;
    $("call-hangup").hidden = true;
  }

  function showIncoming(call) {
    state.incoming = call;
    setCallSheet(true, call);
    drawContours($("call-sheet"));
  }

  async function pollIncoming() {
    if (!secure || state.active || state.incoming) return;
    try {
      const receipt = await api("/api/toast/external/incoming");
      const calls = Array.isArray(receipt.calls) ? receipt.calls : [];
      // The newest ring is the one to answer: an older call that was never picked up must not
      // put its own request in front of the owner's current caller.
      if (calls.length) showIncoming(calls[calls.length - 1]);
    } catch (_) {
      // The phone can be away from the LAN; do not replace the contact view with a poll error.
    }
  }

  function clearPeer() {
    if (state.pc) {
      try { state.pc.close(); } catch (_) {}
      state.pc = null;
    }
    if (state.local) {
      state.local.getTracks().forEach((track) => track.stop());
      state.local = null;
    }
    const audio = $("call-audio");
    if (audio) audio.srcObject = null;
  }

  function closeCallSheet() {
    window.clearInterval(state.callTimer);
    state.callTimer = 0;
    state.incoming = null;
    state.active = "";
    state.agentIceSeen = 0;
    clearPeer();
    setCallSheet(false);
  }

  async function acceptCall(share = false) {
    const incoming = state.incoming;
    if (!incoming) return;
    const scopes = share ? requestScopes(incoming) : [];
    if (!secure) {
      setText("call-status", "WebRTC needs the HTTPS phone origin.");
      return;
    }
    if (!window.RTCPeerConnection || !navigator.mediaDevices?.getUserMedia) {
      setText("call-status", "This browser cannot open a WebRTC audio call.");
      return;
    }
    // The decision is recorded before the microphone is asked for, so a phone that cannot
    // capture audio still answers with exactly what the owner chose.
    if (scopes.length) {
      try {
        await api("/api/toast/external/call/consent", {
          method: "POST",
          body: JSON.stringify({ call_id: incoming.call_id, consent: { granted: true, scopes } }),
        });
      } catch (error) {
        $("call-accept").disabled = false;
        setText("call-status", `Share refused · ${error.message}`);
        return;
      }
    }
    $("call-accept").disabled = true;
    setText("call-status", scopes.length
      ? `Sharing ${scopes.join(", ")}. Opening the microphone to answer the signed offer…`
      : "Opening the microphone and answering the signed offer…");
    try {
      state.local = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const pc = new RTCPeerConnection({ iceServers: [] });
      state.pc = pc;
      for (const track of state.local.getTracks()) pc.addTrack(track, state.local);
      pc.ontrack = (event) => {
        const audio = $("call-audio");
        if (audio && event.streams && event.streams[0]) audio.srcObject = event.streams[0];
        audio?.play().catch(() => undefined);
      };
      pc.onicecandidate = (event) => {
        api("/api/toast/external/call/ice", {
          method: "POST",
          body: JSON.stringify({ call_id: incoming.call_id, side: "phone",
            candidate: event.candidate ? event.candidate.toJSON() : null }),
        }).catch(() => undefined);
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "failed") setText("call-status", "WebRTC failed. A TURN relay is needed off this LAN.");
        if (pc.connectionState === "connected") setText("call-status", "Connected. The line is live.");
      };
      await pc.setRemoteDescription({ type: "offer", sdp: incoming.offer });
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      await api("/api/toast/external/call/answer", {
        method: "POST",
        body: JSON.stringify({
          call_id: incoming.call_id,
          answer: pc.localDescription.sdp,
        }),
      });
      state.active = incoming.call_id;
      state.incoming = null;
      state.agentIceSeen = 0;
      $("call-accept").hidden = true;
      $("call-accept").disabled = false;
      $("call-decline").hidden = true;
      $("call-share") && ($("call-share").hidden = true);
      $("call-hangup").hidden = false;
      setText("call-status", scopes.length
        ? `Answer sent, sharing ${scopes.join(", ")}. Waiting for the agent's ICE candidates…`
        : "Answer sent without sharing data. Waiting for the agent's ICE candidates…");
      state.callTimer = window.setInterval(pollCall, 900);
    } catch (error) {
      $("call-accept").disabled = false;
      setText("call-status", `Call refused · ${error.message}`);
      clearPeer();
    }
  }

  async function pollCall() {
    const callId = state.active;
    const pc = state.pc;
    if (!callId || !pc) return;
    try {
      const receipt = await api("/api/toast/external/call/state", {
        method: "POST", body: JSON.stringify({ call_id: callId }),
      });
      const candidates = Array.isArray(receipt.agent_ice) ? receipt.agent_ice : [];
      while (state.agentIceSeen < candidates.length) {
        const candidate = candidates[state.agentIceSeen];
        state.agentIceSeen += 1;
        if (candidate) await pc.addIceCandidate(candidate).catch(() => undefined);
      }
      if (receipt.state === "ended" || receipt.state === "declined") {
        setText("call-status", "The external line ended the call.");
        closeCallSheet();
      } else if (receipt.state === "active") {
        setText("call-status", pc.connectionState === "connected" ? "Connected. The line is live." : "Connected to the call; negotiating audio.");
      }
    } catch (error) {
      setText("call-status", `Call state unavailable · ${error.message}`);
    }
  }

  async function declineCall() {
    const call = state.incoming;
    if (!call) return;
    try {
      await api("/api/toast/external/call/end", {
        method: "POST", body: JSON.stringify({ call_id: call.call_id, outcome: "declined" }),
      });
    } catch (_) {}
    closeCallSheet();
  }

  async function hangup() {
    const callId = state.active;
    clearPeer();
    window.clearInterval(state.callTimer);
    state.callTimer = 0;
    state.active = "";
    setCallSheet(false);
    if (callId) {
      await api("/api/toast/external/call/end", {
        method: "POST", body: JSON.stringify({ call_id: callId, outcome: "ended" }),
      }).catch(() => undefined);
    }
  }

  function open() {
    setText("agents-secure", secure ? "SECURE" : "HTTP READ ONLY");
    const pill = $("agents-secure");
    pill?.classList.toggle("ok", secure);
    pill?.classList.toggle("bad", !secure);
    loadContacts();
    if (secure) pollIncoming();
  }

  function close() {
    // Incoming calls stay visible on the home surface; this only releases the contact view.
  }

  $("agent-invite")?.addEventListener("click", invite);
  $("agent-refresh")?.addEventListener("click", loadContacts);
  $("enrollment-dismiss")?.addEventListener("click", () => { $("enrollment").hidden = true; });
  $("call-accept")?.addEventListener("click", () => acceptCall(false));
  $("call-share")?.addEventListener("click", () => acceptCall(true));
  $("call-decline")?.addEventListener("click", declineCall);
  $("call-hangup")?.addEventListener("click", hangup);

  window.PopitAgents = { open, close, refresh: loadContacts };
  if (secure) {
    state.incomingTimer = window.setInterval(pollIncoming, 1800);
    pollIncoming();
  }
})();
