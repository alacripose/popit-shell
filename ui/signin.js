// The remote desk sign-in: hand the host a signed package or a one-time desk code, keep the
// cookie it answers, and go to the page that asked for it. Nothing here holds a private key.

const state = document.getElementById("state");
const result = document.getElementById("result");
const note = document.getElementById("note");
const signedIn = document.getElementById("signed-in");
const signedNote = document.getElementById("signed-note");
const nextLink = document.getElementById("continue");
const origin = document.getElementById("origin");

function say(text, mode) {
  result.textContent = text;
  if (mode) result.dataset.state = mode;
  else delete result.dataset.state;
}

function setState(text, mode) {
  state.textContent = text;
  state.dataset.state = mode || "waiting";
}

function target() {
  const wanted = new URLSearchParams(location.search).get("next") || "/toast.html";
  // A next that leaves this origin, or names one with no leading slash, is not a place this
  // page may send a signed-in browser.
  if (!wanted.startsWith("/") || wanted.startsWith("//")) return "/toast.html";
  return wanted;
}

function showSession(session) {
  const signed = Boolean(session && session.signed_in);
  setState(signed ? "signed in" : "signed out", signed ? "signed-in" : "waiting");
  signedIn.hidden = !signed;
  note.hidden = signed;
  document.getElementById("form-envelope").hidden = signed;
  document.getElementById("form-code").hidden = signed;
  document.querySelector(".tabs").hidden = signed;
  if (!signed) return;
  document.querySelectorAll(".pane").forEach((pane) => { pane.hidden = true; });
  signedNote.textContent = session.caller
    ? `Signed in as ${session.caller}. This browser keeps the session until ${session.expires}.`
    : `Signed in. This browser keeps the session until ${session.expires}.`;
  nextLink.href = target();
}

async function readState() {
  try {
    const response = await fetch("/api/toast/signin/state", { credentials: "same-origin",
                                                              cache: "no-store" });
    const body = await response.json();
    showSession(body);
  } catch (error) {
    setState("unreachable", "refused");
    say(`The listener did not answer: ${error.message}`, "refused");
  }
}

async function admit(payload) {
  say("checking…");
  try {
    const response = await fetch("/api/toast/signin", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || !body.ok) {
      const refused = body.refused || {};
      const code = typeof refused === "string" ? refused : refused.code || "signin-refused";
      const detail = typeof refused === "string" ? "" : refused.detail || "";
      setState("refused", "refused");
      say(`${code}${detail ? " · " + detail : ""}`, "refused");
      return;
    }
    setState("signed in", "signed-in");
    say(`Signed in as ${body.caller || "remote"}.`);
    showSession({ signed_in: true, caller: body.caller || "remote",
                  expires: body.session ? body.session.expires : "" });
    location.assign(target());
  } catch (error) {
    setState("refused", "refused");
    say(`The listener did not answer: ${error.message}`, "refused");
  }
}

document.querySelectorAll(".tabs button").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((other) => {
      other.setAttribute("aria-selected", String(other === tab));
    });
    document.querySelectorAll(".pane").forEach((pane) => {
      pane.hidden = pane.dataset.pane !== tab.dataset.mode;
    });
    say("");
  });
});

document.getElementById("form-envelope").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = document.getElementById("package").value.trim();
  if (!text) {
    say("Paste the signed package this machine minted.", "refused");
    return;
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    say(`That is not JSON: ${error.message}`, "refused");
    return;
  }
  await admit({ mode: "envelope", envelope: parsed });
});

document.getElementById("package-file").addEventListener("change", async (event) => {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  document.getElementById("package").value = await file.text();
  say(`Read ${file.name}. Press Sign in.`);
});

document.getElementById("form-code").addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = document.getElementById("code").value.trim();
  if (!code) {
    say("A desk code is eight characters.", "refused");
    return;
  }
  await admit({ mode: "code", code });
});

document.getElementById("signout").addEventListener("click", async () => {
  try {
    await fetch("/api/toast/signout", { method: "POST", credentials: "same-origin" });
  } catch (error) {
    // A failed sign-out still reloads: the page then says what the host says.
  }
  location.assign("/signin.html");
});

origin.textContent = location.origin;
readState();
