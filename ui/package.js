/* Every Popit app surface reads its own signed package before it paints.
 *
 * The server hashes the bytes it serves, signs the identity with the family publisher
 * key, and verifies it against the same trust registry the phone and the settings window
 * use. This client refuses a document that does not verify, applies the theme the
 * settings package published (frame, material, motion, motion preference, DPI), and
 * names the identity it is running so the surface cannot claim a package it is not.
 */
const STATE = { app: "", identity: "", verified: false, code: "" };

export function current() {
  return { ...STATE };
}

// The family roles the surface theme paints from. The settings package carries them as
// hex values, so every app paints the palette the owner chose without re-deriving it.
const ROLE_VARS = {
  surface: "--popit-surface",
  primary: "--popit-primary",
  tertiary: "--popit-tertiary",
  emphasis: "--popit-emphasis",
  ink: "--popit-ink",
  line: "--popit-line",
  panel: "--popit-panel",
  card: "--popit-card",
  meta: "--popit-meta",
  deep: "--popit-deep",
};
const HEX = /^#[0-9a-f]{3,8}$/i;
// A scale that leaves less than this many layout pixels on screen turns every control row
// into an overlap. The published DPI is honoured up to what the viewport can carry.
const MIN_LAYOUT = 400;
// The floor each surface needs before its control rows collide. The SpringBoard is a phone
// layout and reflows at 320; the desk holds a document table and needs 400.
const LAYOUT_FLOOR = { springboard: 320, dialin: 400, settings: 360 };

export function scaleFor(dpi, viewport = window.innerWidth || MIN_LAYOUT,
  floor = MIN_LAYOUT) {
  const wanted = Number(dpi) / 100;
  if (!Number.isFinite(wanted) || wanted <= 0) return 1;
  return Math.min(wanted, Math.max(1, viewport / floor));
}

export function applyTheme(doc, root = document.documentElement) {
  const theme = doc.theme || {};
  if (theme.frame) root.dataset.contourFrame = theme.frame;
  if (theme.material) root.dataset.material = theme.material;
  if (theme.motion) root.dataset.motionProfile = theme.motion;
  if (theme.motionPreference) root.dataset.motionPreference = theme.motionPreference;
  if (theme.theme) root.dataset.theme = theme.theme;
  const colors = theme.colors || {};
  for (const [role, name] of Object.entries(ROLE_VARS)) {
    const value = String(colors[role] || "").trim();
    if (HEX.test(value)) root.style.setProperty(name, value);
  }
  // DPI is a scale, not a number a page remembers: the published value zooms the surface
  // itself, so the desk, the SpringBoard and the phone browser all scale from one setting.
  const dpi = Number(theme.dpi);
  if (Number.isFinite(dpi) && dpi > 0) {
    root.style.setProperty("--popit-dpi", String(dpi));
    // One scale per surface: the Qt host already scales this page and its embedded
    // SpringBoard, and an embedded frame inherits the host's scale.
    const embedded = window.parent !== window;
    const hostZoom = root.dataset.hostZoom === "true";
    const scale = scaleFor(dpi, window.innerWidth, LAYOUT_FLOOR[doc.app] || MIN_LAYOUT);
    if (!embedded && !hostZoom) {
      // Zoom paints the page larger without shrinking its layout box, so a fixed window
      // would clip its right edge. Narrowing the box by the same factor makes the desk
      // reflow to what the scaled window actually shows.
      root.style.zoom = String(scale);
      root.style.width = `${(100 / scale).toFixed(4)}%`;
    }
    root.dataset.scale = String(Number(scale.toFixed(3)));
    root.dataset.dpi = String(Math.round(dpi));
  }
}

function name(node, doc) {
  if (!node) return;
  const theme = doc.theme_identity ? ` · theme ${doc.theme_identity.split("+")[0]}` : "";
  node.textContent = `${doc.identity}${theme}`;
  node.dataset.verified = "true";
  node.title = `${doc.app} · ${doc.signature_algorithm} · publisher ${doc.theme_verifier}`;
}

function refuse(node, error) {
  if (!node) return;
  node.textContent = `package refused · ${error.code || "app-refused"}`;
  node.dataset.verified = "false";
}

// A surface refused at load is republished the moment its audit passes; the page then
// re-reads the package so its footer names the signature it is running.
let lastAttach = null;

export function repaint() {
  return lastAttach ? lastAttach() : null;
}

export async function attach(app, { identitySelector = "#package-identity" } = {}) {
  const node = identitySelector ? document.querySelector(identitySelector) : null;
  lastAttach = () => attach(app, { identitySelector });
  STATE.app = app;
  try {
    const reply = await fetch(`/api/toast/apps/${encodeURIComponent(app)}`, { cache: "no-store" });
    const doc = await reply.json().catch(() => null);
    if (!reply.ok || !doc || doc.verified !== true) {
      const code = (doc && doc.refused && doc.refused.code) || `app-http-${reply.status}`;
      throw Object.assign(new Error(code), { code });
    }
    STATE.identity = doc.identity || "";
    STATE.verified = true;
    applyTheme(doc);
    document.documentElement.dataset.packageApp = app;
    document.documentElement.dataset.packageIdentity = STATE.identity;
    document.documentElement.dataset.packageVerified = "true";
    name(node, doc);
    return doc;
  } catch (error) {
    STATE.verified = false;
    STATE.code = error.code || "app-refused";
    document.documentElement.dataset.packageVerified = "false";
    document.documentElement.dataset.packageRefusal = STATE.code;
    // A surface that cannot verify its package does not pretend to carry the theme.
    delete document.documentElement.dataset.contourFrame;
    refuse(node, error);
    return null;
  }
}
