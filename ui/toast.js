import { loadContour, fillContours } from "/contour.js";
import { attach } from "/package.js";

const $ = (selector) => document.querySelector(selector);
// Rows and controls are rebuilt from state on every poll. Tag the painted ones once they
// are in the document so the contour applies to the element that is actually visible, not
// just to the static page shell. Loaders are deliberately absent: a spinner is geometry,
// not a contour surface.
const CONTOUR_SURFACES = [
  ".status", ".icon", ".tabs button", ".voice-chips button",
  ".participant-name", ".participant-actions button", ".lane-chip", ".commons-lane",
  ".owner-say input", ".owner-say button", "#contact-search", ".contact-actions button",
  ".contact-book", ".workdoc", ".window-row", ".settings",
  ".settings-head button", ".settings-row button", ".settings-tabs button", ".style-option",
  ".planet-filter button", ".planet-readout button", ".palette-editor button", ".palette-editor input[type=text]",
  ".palette-editor select", ".action", ".voice",
  ".facts", ".doc-wrap", ".windows", "#mind-log", ".foot",
].join(",");

function decorateContours() {
  document.querySelectorAll(CONTOUR_SURFACES).forEach((node) => {
    if (!node.hasAttribute("data-contour")) node.setAttribute("data-contour", "card");
  });
}

let lastShot = 0;
let busy = false;
let latest = {};
let lastDebianShot = 0;
let lastHeardId = 0;
const PHANTOM = new Set([
  "thanks for watching", "thank you for watching", "thank you so much for watching",
  "please subscribe", "whoa", "i'll see you in the next video",
  "see you in the next video", "i will see you in the next video",
  "see you next time", "i'll see you next time",
  "see you in the next one", "i'll see you in the next one",
]);
const heardText = (row) => String(row.text || "").toLowerCase().replace(/[.!?,;:]+$/g, "").trim();
let popitWindow = null;
// The pinned window clips to its own frame; a browser tab is a document. The stylesheet
// keys its scroll model on this, before the Qt bridge finishes connecting.
document.documentElement.dataset.host = window.qt?.webChannelTransport ? "window" : "browser";
let streamKey = "";
let streamTimer = null;
let streamQueue = [];
let streamIndex = 0;
let streamDone = true;
let micKey = "";
let micTimer = null;
let micWords = [];
let micIndex = 0;

const setText = (selector, text) => {
  const node = $(selector);
  if (node) node.textContent = text;
};

// The family roster is the design authority. It carries the Popit shell's own
// family register, Brass Meridian, Archive, the family web register, Popit suite,
// Deadlock, Alpha, Holo Dark/Light, Material, iOS, TouchWiz and the simulator
// legacy schemes, with all 37 player colours as one source inside that roster.
// The contour stays one nine-slice; a scheme changes colour, material and motion,
// never the silhouette or the slot geometry.
const FALLBACK_FAMILY = {
  id: "family", name: "Popit Family", group: "Popit shell", kind: "shell",
  source: "family", origin: "popit-shell docs/family-look.md + ui/toast.css",
  surface: "#14100b", deep: "#0b0906", primary: "#b08d57", secondary: "#14100b",
  tertiary: "#d9c9a6", emphasis: "#e2c188", text: "#d9c9a6", muted: "#9c8a6b",
  line: "#b08d57", raised: "#241a10", alert: "#d06a4e", material: "family", motion: "reveal",
};
let POPIT_THEMES = [FALLBACK_FAMILY];
let currentTheme = "family";
let currentSource = "family";
const GROUP_ORDER = [
  "Popit shell", "Family register", "Popit suite", "Deadlock", "Openlock shell",
  "Android", "Material Design", "iOS", "TouchWiz", "Simulator legacy",
  "Popit Forge default", "LittleBigPlanet", "LittleBigPlanet 3",
];
const LEGACY_THEME_IDS = {
  "cool-island": "lbp3-cool-island",
  "twit-twoo": "lbp3-twit-twoo",
  "candy-floss": "lbp3-candy-floss",
  "forest-surprise": "lbp3-forest-surprise",
  "night-time-coral": "lbp3-night-time-coral",
  "candy-jar": "lbp3-candy-jar",
};

// The two settings modes share one family contour. The left column changes the
// clipped material inside that contour; the right column changes the reveal.
// Neither column may introduce a second silhouette.
// The four forms openlock actually ships. They inherit the one measured contour;
// a form carries identity and colour rules, never a second silhouette.
// Source: openlock/shell/alpha-shell/forms/{popit,ios,material,touchwiz}.form.
const CONTOUR_FRAMES = [
  { id: "popit", label: "Popit", note: "LBP3 · crowned contour", source: "forms/popit.form" },
  { id: "ios", label: "iOS 6", note: "SpringBoard · inherited", source: "forms/ios.form" },
  { id: "material", label: "Material", note: "MD1 · inherited", source: "forms/material.form" },
  { id: "touchwiz", label: "TouchWiz", note: "Nature UX · inherited", source: "forms/touchwiz.form" },
  { id: "springboard", label: "SpringBoard", note: "phone · home", source: "ui/phone.html" },
];

// The Goodies Bag material stack, read from the Popit evidence rather than invented:
// openlock/docs/UI-PASS.md §"Goodies Bag" and
// openlock/clientaddon/panorama/scripts/openlock_popit.js (MATERIALS / paintPopitCell).
// wash is the palette role the shell writes: panel, title, meta, player colour, ink, accent or none.
const CONTOUR_TYPES = [
  { id: "paper", label: "Paper", note: "panel wash", wash: "panel", swatch: "var(--panel)" },
  { id: "card", label: "Card", note: "title wash", wash: "title", swatch: "var(--card)" },
  { id: "glass", label: "Glass", note: "meta wash", wash: "meta", swatch: "var(--meta)" },
  { id: "tint", label: "Tint", note: "player colour", wash: "color", swatch: "var(--primary)" },
  { id: "ink", label: "Ink", note: "ink wash", wash: "ink", swatch: "var(--text)" },
  { id: "accent", label: "Accent", note: "accent wash", wash: "accent", swatch: "var(--tertiary)" },
  { id: "bare", label: "Bare", note: "form surface", wash: "none", swatch: "repeating-linear-gradient(135deg, transparent 0 4px, var(--muted) 4px 5px)" },
];
const LEGACY_MATERIAL_IDS = {
  family: "paper",
  metal: "card",
  gloss: "glass",
  flat: "paper",
  translucent: "glass",
  parchment: "paper",
};
const MOTION_TYPES = [
  { id: "reveal", label: "Reveal", note: "settle" },
  { id: "pop", label: "Pop", note: "spring" },
  { id: "fold", label: "Fold", note: "hinge" },
  { id: "snap", label: "Snap", note: "quick" },
  { id: "sweep", label: "Sweep", note: "slide" },
];
const PALETTE_ROLES = ["primary", "secondary", "tertiary", "emphasis"];
const CUSTOM_PALETTES_KEY = "popit.customPalettes";
const STYLE_OVERRIDES_KEY = "popit.styleOverrides";
let activeFrame = "popit";

// The shell has two surfaces: the DialIn desk and the phone's existing SpringBoard. The
// frame option switches this window to that surface; it does not build a second launcher.
const SURFACE_KEY = "popit.surface";
let activeSurface = "desk";
// Where a package window goes when it closes: the surface it was opened from. A window opened
// from the home returns to the home, and a home that is not painted is loaded again, because a
// blank window is not a state this application may reach.
let returnSurface = "desk";
let activeMaterial = "paper";
let activeMotion = "reveal";
let customPalettes = [];
let styleOverrides = {};
let paletteDraft = null;
let paletteBase = null;
let paletteHistory = [];
let paletteFuture = [];
let settingsTab = "surface";
let planetSource = "family";
let planetBodies = [];
let planetRaf = 0;
let planetLast = 0;

function hexRgb(hex) {
  const value = String(hex || "").replace("#", "");
  if (value.length !== 6) return { r: 0, g: 0, b: 0 };
  const n = Number.parseInt(value, 16);
  if (!Number.isFinite(n)) return { r: 0, g: 0, b: 0 };
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function rgbHex({ r, g, b }) {
  const channel = (v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0");
  return `#${channel(r)}${channel(g)}${channel(b)}`;
}

function mix(a, b, amount) {
  const one = hexRgb(a);
  const two = hexRgb(b);
  return rgbHex({
    r: one.r + (two.r - one.r) * amount,
    g: one.g + (two.g - one.g) * amount,
    b: one.b + (two.b - one.b) * amount,
  });
}

function rgba(hex, alpha) {
  const { r, g, b } = hexRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function luminance(hex) {
  const channel = (value) => {
    const v = value / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  const { r, g, b } = hexRgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a, b) {
  const one = luminance(a);
  const two = luminance(b);
  return (Math.max(one, two) + 0.05) / (Math.min(one, two) + 0.05);
}

function inkOn(background) {
  return contrast(background, "#10131a") >= contrast(background, "#f4f2ea")
    ? "#10131a" : "#f4f2ea";
}

function pickTitle(background, candidates) {
  let best = { color: "#f4f2ea", ratio: 0 };
  for (const color of candidates.filter(Boolean)) {
    const ratio = contrast(color, background);
    if (ratio > best.ratio) best = { color, ratio };
  }
  if (best.ratio >= 3) return best.color;
  for (let lift = 0.18; lift <= 0.72; lift += 0.18) {
    const raised = mix(best.color, "#ffffff", lift);
    if (contrast(raised, background) >= 3) return raised;
  }
  return "#f4f2ea";
}

// A family scheme declares eleven slots; the painter reads four roles and keeps
// the provenance. The four roles stay in the family's order: highlight, surface,
// accent, emphasised text.
function familyTheme(row) {
  return {
    ...row,
    source: "family",
    origin: row.source,
    game: row.group,
    frame: frameForTheme(row),
    material: row.material || "paper",
    motion: row.motion || "reveal",
  };
}

// A player colour is four roles and no ink. LBP3 assigns secondary to the menu
// background and primary to the highlight; LBP1 and the Forge default are the
// inverse. The pair keeps its own four roles, and the surface follows the
// generation's role map rather than treating every pair as a menu background.
function pairTheme(pair) {
  const lbp3 = pair.game === "LittleBigPlanet 3";
  const surface = lbp3 ? pair.secondary : pair.primary;
  const bubble = lbp3 ? pair.primary : pair.secondary;
  const effective = mix(surface, "#000000", 0.42);
  const text = inkOn(effective);
  return {
    ...pair,
    source: "player",
    origin: "popit-blender/design/popit-pairs.json",
    group: pair.game,
    kind: "popit",
    surface,
    deep: mix(surface, "#000000", 0.58),
    primary: bubble,
    secondary: surface,
    tertiary: pair.tertiary,
    emphasis: pair.emphasis,
    text,
    muted: rgba(text, 0.64),
    line: rgba(text, 0.24),
    raised: mix(surface, "#ffffff", 0.06),
    alert: "#e2664f",
    // LBP1 is glossy, LBP2 flat and LBP3 translucent (POPIT-AUDIT §3–§4, §7).
    // Glass is the Goodies wash for the glossy/translucent generations; Paper is the flat one.
    frame: "popit",
    material: lbp3 || pair.game !== "LittleBigPlanet 2" ? "glass" : "paper",
    motion: lbp3 ? "fold" : "pop",
  };
}

function allowedFrame(id) {
  return CONTOUR_FRAMES.some((row) => row.id === id) ? id : "popit";
}

function allowedMaterial(id) {
  const value = LEGACY_MATERIAL_IDS[id] || id;
  return CONTOUR_TYPES.some((row) => row.id === value) ? value : "paper";
}

function frameForTheme(theme) {
  const id = String(theme?.id || "").toLowerCase();
  if (CONTOUR_FRAMES.some((row) => row.id === id)) return id;
  if (id === "popit-suite") return "popit";
  if (id === "material") return "material";
  if (id === "ios") return "ios";
  if (id === "touchwiz") return "touchwiz";
  return "popit";
}

function allowedMotion(id) {
  return MOTION_TYPES.some((row) => row.id === id) ? id : "reveal";
}

function slug(value) {
  return String(value || "palette").toLowerCase().replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "").slice(0, 32) || "palette";
}

function newPaletteId(name) {
  return `custom-${slug(name)}-${Math.random().toString(36).slice(2, 6)}`;
}

function normalizePalette(raw) {
  if (!raw || typeof raw !== "object") return null;
  const name = String(raw.name || "").trim().slice(0, 48) || "Untitled palette";
  const colors = {};
  for (const role of PALETTE_ROLES) {
    const value = String(raw[role] || (role === "secondary" ? raw.surface : "") || "").trim();
    if (!/^#[0-9a-f]{6}$/i.test(value)) return null;
    colors[role] = value.toLowerCase();
  }
  const id = typeof raw.id === "string" && raw.id.startsWith("custom-")
    ? raw.id.slice(0, 80) : newPaletteId(name);
  return {
    id, name, ...colors,
    frame: allowedFrame(raw.frame), material: allowedMaterial(raw.material), motion: allowedMotion(raw.motion),
  };
}

function customTheme(row) {
  const surface = row.secondary;
  const text = inkOn(surface);
  return {
    ...row,
    source: "custom", group: "Mine", kind: "custom",
    origin: "custom palette · Popit shell",
    frame: allowedFrame(row.frame),
    surface, deep: mix(surface, "#000000", 0.58),
    primary: row.primary, secondary: surface, tertiary: row.tertiary,
    emphasis: row.emphasis, text, muted: rgba(text, 0.64), line: rgba(text, 0.24),
    raised: mix(surface, "#ffffff", 0.06), alert: "#e2664f",
  };
}

function loadCustomPalettes() {
  try {
    const rows = JSON.parse(localStorage.getItem(CUSTOM_PALETTES_KEY) || "[]");
    customPalettes = Array.isArray(rows) ? rows.map(normalizePalette).filter(Boolean) : [];
  } catch (error) {
    customPalettes = [];
  }
  try {
    const saved = JSON.parse(localStorage.getItem(STYLE_OVERRIDES_KEY) || "{}");
    styleOverrides = saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
  } catch (error) {
    styleOverrides = {};
  }
}

function persistCustomPalettes() {
  localStorage.setItem(CUSTOM_PALETTES_KEY, JSON.stringify(customPalettes));
}

function persistStyleOverrides() {
  localStorage.setItem(STYLE_OVERRIDES_KEY, JSON.stringify(styleOverrides));
}

// The panel is the authoring surface. It hands the values it already holds to the
// package service, and the package window reads them back; nothing here re-derives a
// choice, so the served document can never disagree with the panel the owner used.
// The roles the surface theme paints from, read from the variables paintTheme just set, so
// the package carries the colours the panel is actually showing.
function themeColors() {
  const styles = getComputedStyle(document.documentElement);
  const colors = {};
  for (const role of ["surface", "primary", "tertiary", "emphasis", "ink", "line",
    "panel", "card", "meta", "deep"]) {
    const value = styles.getPropertyValue(`--popit-${role}`).trim();
    if (/^#[0-9a-f]{6}$/i.test(value)) colors[role] = value;
  }
  return colors;
}

let settingsPushTimer = 0;
// A publish is an edit, not a paint: only a control in the settings panel sets this, so neither
// a window's boot paint nor merely opening the settings window can replace the saved profile.
let settingsAuthoring = false;

function pushSettingsState() {
  if (!settingsAuthoring) return;
  clearTimeout(settingsPushTimer);
  settingsPushTimer = setTimeout(() => {
    fetch("/api/toast/settings/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        theme: currentTheme,
        frame: activeFrame,
        material: activeMaterial,
        motion: activeMotion,
        motionPreference: motionPreference(),
        dpi: Number(localStorage.getItem("popit.zoom") || 100),
        palettes: customPalettes,
        colors: themeColors(),
      }),
    }).catch(() => {});
    settingsAuthoring = false;
  }, 250);
}

function refreshCustomThemes() {
  POPIT_THEMES = [...POPIT_THEMES.filter((theme) => theme.source !== "custom"),
    ...customPalettes.map(customTheme)];
}

function paletteSnapshot() {
  if (!paletteDraft) return null;
  const row = { name: paletteDraft.name, frame: paletteDraft.frame, material: paletteDraft.material, motion: paletteDraft.motion };
  for (const role of PALETTE_ROLES) row[role] = paletteDraft[role];
  return row;
}

function resolvedStyle(theme) {
  if (theme.source === "custom") {
    return {
      frame: allowedFrame(theme.frame || "popit"),
      material: allowedMaterial(theme.material),
      motion: allowedMotion(theme.motion),
    };
  }
  const override = styleOverrides[theme.id] || {};
  return {
    frame: allowedFrame(override.frame || theme.frame || frameForTheme(theme)),
    material: allowedMaterial(override.material || theme.material),
    motion: allowedMotion(override.motion || theme.motion),
  };
}

async function loadThemes() {
  try {
    const [rosterReply, pairsReply] = await Promise.all([
      fetch("/family-roster.json", { cache: "no-store" }),
      fetch("/popit-pairs.json", { cache: "no-store" }),
    ]);
    if (!rosterReply.ok || !pairsReply.ok) {
      throw new Error(`roster ${rosterReply.status} · pairs ${pairsReply.status}`);
    }
    const roster = await rosterReply.json();
    const pairs = await pairsReply.json();
    const familyRows = Array.isArray(roster.themes) ? roster.themes.map(familyTheme) : [];
    const pairRows = Array.isArray(pairs.pairs) ? pairs.pairs.map(pairTheme) : [];
    if (!familyRows.some((theme) => theme.id === "family")) familyRows.unshift(familyTheme(FALLBACK_FAMILY));
    if (pairRows.length !== 37) throw new Error(`expected 37 player colours, got ${pairRows.length}`);
    POPIT_THEMES = [...familyRows, ...pairRows];
    loadCustomPalettes();
    refreshCustomThemes();
    setText("#theme-note", "");
  } catch (error) {
    POPIT_THEMES = [familyTheme(FALLBACK_FAMILY)];
    loadCustomPalettes();
    refreshCustomThemes();
    // A fallback is named by its refusal code, not described: the note is not copy.
    setText("#theme-note", String(error.message || "theme-refused"));
  }
}

function storedTheme() {
  const saved = localStorage.getItem("popit.theme");
  const migrated = LEGACY_THEME_IDS[saved] || saved;
  return POPIT_THEMES.some((theme) => theme.id === migrated) ? migrated : "family";
}

function themePaint(theme) {
  const lightSurface = luminance(theme.surface) > 0.55;
  const effective = lightSurface ? theme.surface : mix(theme.surface, "#000000", 0.42);
  const text = lightSurface ? "#10131a" : "#f4f2ea";
  return {
    surface: theme.surface,
    deep: theme.deep || mix(theme.surface, "#000000", 0.58),
    bubble: theme.primary,
    accent: theme.tertiary,
    emphasis: theme.emphasis,
    text,
    muted: rgba(text, 0.64),
    line: rgba(text, 0.24),
    title: pickTitle(effective, [theme.primary, theme.tertiary, theme.emphasis, theme.text]),
    onBubble: inkOn(theme.primary),
    raised: theme.raised || mix(theme.surface, "#ffffff", 0.06),
    lightSurface,
    overlayTop: lightSurface ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.26)",
    overlayBottom: lightSurface ? "rgba(255, 255, 255, 0.16)" : "rgba(0, 0, 0, 0.60)",
  };
}

function updateStyleChoices() {
  setText("#material-value", activeMaterial);
  setText("#frame-value", activeFrame);
  setText("#motion-profile", activeMotion);
  setText("#contour-frame-current", activeFrame);
  setText("#contour-type-current", activeMaterial);
  setText("#motion-type-current", activeMotion);
  setText("#palette-material", activeMaterial);
  setText("#palette-motion", activeMotion);
  for (const button of document.querySelectorAll("[data-contour-frame-choice]")) {
    const name = button.dataset.contourFrameChoice;
    const pressed = name === "springboard"
      ? activeSurface === "springboard"
      : activeSurface !== "springboard" && name === activeFrame;
    button.setAttribute("aria-pressed", String(pressed));
  }
  for (const button of document.querySelectorAll("[data-contour-type-choice]")) {
    button.setAttribute("aria-pressed", String(button.dataset.contourTypeChoice === activeMaterial));
  }
  for (const button of document.querySelectorAll("[data-motion-type-choice]")) {
    button.setAttribute("aria-pressed", String(button.dataset.motionTypeChoice === activeMotion));
  }
  updatePlanetSelection();
}

// The home is a delivered window of its own. It is shown once its package has painted, and the
// frame's own document is read for that paint: a window whose home only waited for a message
// showed its bar with no frame whenever the message had already gone by.
function showHome() {
  const board = document.querySelector("#springboard");
  const frame = document.querySelector("#springboard-frame");
  if (!board || !frame) return false;
  board.hidden = false;
  frame.hidden = false;
  const tiles = () => {
    try { return frame.contentDocument?.querySelectorAll(".tile").length || 0; }
    catch (error) { return 0; }
  };
  const settle = () => {
    if (!tiles()) { frame.dataset.pending = "true"; return false; }
    frame.dataset.ready = "true";
    frame.dataset.pending = "false";
    // The bar names the surface that is showing: the home's own brand is its word for itself.
    const name = document.querySelector("#window-name");
    const brand = frame.contentDocument?.querySelector(".brand strong");
    if (name && brand && brand.textContent.trim()) name.textContent = brand.textContent.trim();
    return true;
  };
  if (settle()) return true;
  let tries = 0;
  const poll = window.setInterval(() => {
    tries += 1;
    if (settle() || tries >= 40) window.clearInterval(poll);
  }, 250);
  return true;
}

// Closing a package window returns to the surface it was opened from. The surface function is the
// only place that decides what a surface shows, so close and tile-click cannot disagree.
function closePackageWindow() {
  const panel = document.querySelector("#settings-panel");
  if (panel) panel.hidden = true;
  try { window.popitProse && window.popitProse.close && window.popitProse.close(); }
  catch (error) { /* this window carries no prose body */ }
  delete document.body.dataset.windowMode;
  const back = window.__popitReturnSurface === "springboard" ? "springboard" : "desk";
  window.__popitReturnSurface = "desk";
  setSurface(back);
}

// The window's name is its surface's name. A bar reading SPRINGBOARD over the desk's body is the
// same defect as a frame that does not match the package: it names something it is not showing.
function nameSurface() {
  const node = document.querySelector("#window-name");
  if (!node) return;
  if (activeSurface === "springboard") {
    const brand = document.querySelector("#springboard-frame")
      ?.contentDocument?.querySelector(".brand strong");
    if (brand && brand.textContent.trim()) node.textContent = brand.textContent.trim();
    return;
  }
  const key = document.body.dataset.windowMode === "prose" ? "prose" : "dialin";
  const title = (window.__popitTitles || {})[key];
  if (title) node.textContent = title;
}

// A window paints the settings package's frame, material and motion or it refuses. This is the
// check the refusal hangs on: a surface with a look of its own is not a variant, it is wrong.
function styleMatchesPackage() {
  const want = window.__popitPackageStyle;
  if (!want) return false;
  const root = document.documentElement.dataset;
  return (!want.frame || root.contourFrame === want.frame)
    && (!want.material || root.material === want.material)
    && (!want.motion || root.motionProfile === want.motion);
}

function setSurface(name) {
  // Every surface change is kept, so a window that loses its surface can say what moved it.
  window.__popitSurfaces = window.__popitSurfaces || [];
  if (window.__popitSurfaces.length > 40) window.__popitSurfaces.shift();
  // The caller is kept too: a surface change with no visible cause is the thing being hunted.
  const caller = String(new Error().stack || "").split("\n")[2] || "";
  window.__popitSurfaces.push({ at: Date.now(), name, by: caller.trim().slice(0, 120) });
  activeSurface = name === "springboard" ? "springboard" : "desk";
  const toast = document.querySelector(".toast");
  if (toast) toast.dataset.surface = activeSurface;
  const board = $("#springboard");
  if (board) board.hidden = activeSurface !== "springboard";
  const frame = $("#springboard-frame");
  if (frame && activeSurface === "springboard") {
    // The home is served on the same origin as this window: when the window is delivered over
    // the pinned https origin, the SpringBoard package is loaded over https too, never as a
    // loopback page beside a secure window.
    const frameSrc = new URL(frame.dataset.src || "/phone.html?embedded=1",
                             location.origin).toString();
    // A frame that has not painted stays hidden: the window shows its ground, never a
    // half-applied page. Entering the home re-reads the signed package, so a settings change
    // published while the desk was open is what the SpringBoard paints.
    if (!frame.getAttribute("src")) {
      frame.dataset.ready = "false";
      frame.setAttribute("src", frameSrc);
    } else if (frame.dataset.ready !== "true") {
      try { frame.contentWindow.location.reload(); } catch (error) { /* still loading */ }
    }
    showHome();
  }
  // The settings dialog is the desk's authoring panel; the home is not behind it. A window mode
  // belongs to the package window that was open: the home has none, and leaving the mode set hid
  // the home behind `.toast > *:not(.bar):not(#settings-panel)`, which is a bar with no frame.
  if (activeSurface === "springboard") {
    delete document.body.dataset.windowMode;
    const panel = $("#settings-panel");
    if (panel) panel.hidden = true;
  }
  try { localStorage.setItem(SURFACE_KEY, activeSurface); } catch (error) { /* storage refused */ }
  nameSurface();
  updateStyleChoices();
}

// The settings package is the only first author of a window's appearance. A paint attempted
// before that package's document has arrived is refused, not applied: this is what stopped the
// window from drawing its own default theme while the package was still being read.
function paintTheme(theme, persist = true) {
  if (!window.__popitThemeAuthor) {
    document.body.dataset.packageRefused = "theme-not-from-settings-package";
    document.body.dataset.windowState = "refused";
    return;
  }
  const style = resolvedStyle(theme);
  // The settings package owns the contour, material and motion. A later local repaint may change
  // which palette is painted, but never the frame the package chose for this window.
  const pinned = window.__popitPackageStyle;
  if (pinned) {
    if (pinned.frame) style.frame = pinned.frame;
    if (pinned.material) style.material = pinned.material;
    if (pinned.motion) style.motion = pinned.motion;
  }
  const resolved = { ...theme, ...style };
  const panel = $("#settings-panel");
  if (!panel) return;
  currentTheme = resolved.id;
  currentSource = resolved.source;
  activeFrame = style.frame;
  activeMaterial = style.material;
  activeMotion = style.motion;
  const paint = themePaint(resolved);
  panel.dataset.theme = resolved.id;
  panel.dataset.contourFrame = style.frame;
  panel.dataset.material = style.material;
  panel.dataset.motionProfile = style.motion;
  panel.dataset.lightSurface = String(paint.lightSurface);
  document.documentElement.dataset.contourFrame = style.frame;
  document.documentElement.dataset.material = style.material;
  document.documentElement.dataset.motionProfile = style.motion;
  for (const [name, value] of Object.entries({
    "--primary": paint.bubble,
    "--secondary": paint.surface,
    "--tertiary": paint.accent,
    "--emphasis": paint.emphasis,
    "--surface": paint.surface,
    "--surface-deep": paint.deep,
    "--text": paint.text,
    "--muted": paint.muted,
    "--line": paint.line,
    "--bubble": paint.bubble,
    "--title": paint.title,
    "--panel": paint.surface,
    "--card": paint.raised,
    "--meta": paint.deep,
    "--on-bubble": paint.onBubble,
    "--raised": paint.raised,
    "--settings-overlay-top": paint.overlayTop,
    "--settings-overlay-bottom": paint.overlayBottom,
  })) panel.style.setProperty(name, value);
  // The palette this surface paints is also the palette it publishes: the same ten roles
  // an app package reads. Every value is hex, because the settings package validates a
  // colour per role and an rgba line would refuse the whole document.
  const roleValues = {
    surface: paint.surface,
    primary: paint.bubble,
    tertiary: paint.accent,
    emphasis: paint.emphasis,
    ink: paint.text,
    line: mix(paint.text, paint.surface, 0.72),
    panel: mix(paint.surface, paint.deep, 0.35),
    card: paint.raised,
    meta: mix(paint.deep, "#ffffff", 0.10),
    deep: paint.deep,
  };
  for (const [role, value] of Object.entries(roleValues)) {
    if (typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value)) {
      document.documentElement.style.setProperty(`--popit-${role}`, value);
    }
  }
  if (persist) localStorage.setItem("popit.theme", resolved.id);
  setText("#theme-name", resolved.name);
  setText("#style-name", resolved.name);
  setText("#theme-origin", resolved.origin || "");
  // A window wears the package's frame, material and motion or it refuses. Measured after the
  // paint, so the refusal names a look the window actually has.
  if (window.__popitPackageStyle) {
    if (styleMatchesPackage()) {
      if (document.body.dataset.packageRefused === "window-style-mismatch") {
        delete document.body.dataset.packageRefused;
        document.body.dataset.windowState = "ready";
      }
    } else {
      document.body.dataset.packageRefused = "window-style-mismatch";
      document.body.dataset.windowState = "refused";
    }
  }
  updateStyleChoices();
  pushSettingsState();
}

// The settings package is the window's appearance: its document names the palette, material,
// contour frame, motion type and dpi, so the desk, the home and the settings window paint the
// one profile the owner saved instead of each keeping a look of its own.
function applyPackageLook(doc) {
  const look = (doc && doc.theme) || {};
  const row = POPIT_THEMES.find((theme) => theme.id === String(look.theme || ""));
  if (!row) return false;
  currentTheme = row.id;
  currentSource = row.source || "family";
  paintTheme({ ...row,
               frame: look.frame || row.frame,
               material: look.material || row.material,
               motion: look.motion || row.motion }, false);
  applyMotion(String(look.motionPreference || "full"));
  applyZoom(Number(look.dpi) || 100);
  return true;
}

function applyTheme(source, options = {}) {
  // The settings package is the only author of a window's appearance: its document names the
  // theme, frame, material and motion. A window whose package does not name a known theme is
  // refused rather than painted with some other surface's default.
  const authored = source && typeof source === "object" ? (source.theme || source) : null;
  const id = String((authored ? authored.theme : source) || "");
  const theme = POPIT_THEMES.find((row) => row.id === id);
  if (!theme) {
    document.documentElement.dataset.packageRefusal = "settings-theme-unknown";
    document.body.dataset.packageRefused = `theme-${id || "missing"}`;
    document.body.dataset.windowState = "refused";
    return false;
  }
  if (authored) {
    window.__popitThemeAuthor = true;
    delete document.body.dataset.packageRefused;
    document.documentElement.dataset.settingsTheme = id;
  }
  const styled = authored
    ? { ...theme,
        frame: authored.frame || theme.frame,
        material: authored.material || theme.material,
        motion: authored.motion || theme.motion }
    : theme;
  if (authored) {
    window.__popitPackageStyle = { theme: id, frame: styled.frame,
                                   material: styled.material, motion: styled.motion };
  }
  paintTheme(styled, authored ? Boolean(options.persist) : options.persist !== false);
  return true;
}

function renderStyleOptions() {
  const frameList = $("#contour-frames");
  const contourList = $("#contour-types");
  const motionList = $("#motion-types");
  if (!frameList || !contourList || !motionList) return;
  frameList.replaceChildren();
  contourList.replaceChildren();
  motionList.replaceChildren();
  for (const type of CONTOUR_FRAMES) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "style-option frame-option";
    button.dataset.contourFrameChoice = type.id;
    button.dataset.contour = "card";
    button.title = `Frame ${type.label} · ${type.source}`;
    const glyph = document.createElement("span");
    glyph.className = "frame-glyph";
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = type.id === "popit" ? "◒" : type.id === "ios" ? "▢" : type.id === "material" ? "▤" : "◇";
    const copy = document.createElement("span");
    copy.className = "style-copy";
    const label = document.createElement("b");
    label.textContent = type.label;
    const note = document.createElement("small");
    note.textContent = type.note;
    copy.append(label, note);
    button.append(glyph, copy);
    button.addEventListener("click", () => chooseStyle("frame", type.id));
    frameList.append(button);
  }
  for (const type of CONTOUR_TYPES) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "style-option";
    button.dataset.contourTypeChoice = type.id;
    button.dataset.contour = "card";
    button.title = `Contour ${type.label} · ${type.note}`;
    const swatch = document.createElement("span");
    swatch.className = "style-swatch";
    swatch.setAttribute("aria-hidden", "true");
    swatch.style.background = type.swatch;
    const copy = document.createElement("span");
    copy.className = "style-copy";
    const label = document.createElement("b");
    label.textContent = type.label;
    const note = document.createElement("small");
    note.textContent = type.note;
    copy.append(label, note);
    button.append(swatch, copy);
    button.addEventListener("click", () => chooseStyle("material", type.id));
    contourList.append(button);
  }
  for (const type of MOTION_TYPES) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "style-option motion-option";
    button.dataset.motionTypeChoice = type.id;
    button.dataset.contour = "card";
    button.title = `Motion ${type.label} · ${type.note}`;
    const glyph = document.createElement("span");
    glyph.className = "motion-glyph";
    glyph.textContent = type.id === "reveal" ? "▤" : type.id === "fold" ? "▥" : "≋";
    glyph.setAttribute("aria-hidden", "true");
    const copy = document.createElement("span");
    copy.className = "style-copy";
    const label = document.createElement("b");
    label.textContent = type.label;
    const note = document.createElement("small");
    note.textContent = type.note;
    copy.append(label, note);
    button.append(glyph, copy);
    button.addEventListener("click", () => chooseStyle("motion", type.id));
    motionList.append(button);
  }
  updateStyleChoices();
  decorateContours();
  fillContours(document);
}

function chooseStyle(kind, id) {
  // SpringBoard is not a contour: it is the shell's home surface, so its tile switches
  // this window to the app grid instead of repainting the desk.
  if (kind === "frame" && id === "springboard") {
    setSurface("springboard");
    return;
  }
  if (kind === "frame") setSurface("desk");
  const value = kind === "frame" ? allowedFrame(id)
    : kind === "material" ? allowedMaterial(id) : allowedMotion(id);
  if (kind === "frame") activeFrame = value;
  else if (kind === "material") activeMaterial = value;
  else activeMotion = value;
  // The panel is the settings package's authoring surface: its choice is the package's style
  // from here on, so the pin that keeps a boot paint from overriding the package follows it
  // instead of freezing the frame the window happened to open with.
  window.__popitPackageStyle = {
    theme: currentTheme || (window.__popitPackageStyle || {}).theme || "",
    frame: activeFrame, material: activeMaterial, motion: activeMotion,
  };
  settingsAuthoring = true;
  if (paletteDraft) {
    paletteDraft[kind] = value;
    pushPaletteHistory();
    previewPalette();
    updateStyleChoices();
    return;
  }
  const theme = POPIT_THEMES.find((row) => row.id === currentTheme);
  if (!theme) return;
  if (theme.source === "custom") {
    const row = customPalettes.find((palette) => palette.id === theme.id);
    if (row) {
      row.frame = activeFrame;
      row.material = activeMaterial;
      row.motion = activeMotion;
      persistCustomPalettes();
      paintTheme(customTheme(row));
      return;
    }
  }
  styleOverrides[theme.id] = { ...(styleOverrides[theme.id] || {}), [kind]: value };
  persistStyleOverrides();
  paintTheme(theme);
}

function planetRows() {
  return POPIT_THEMES.filter((theme) => theme.source === planetSource);
}

function updatePlanetSelection() {
  const theme = POPIT_THEMES.find((row) => row.id === currentTheme);
  for (const node of document.querySelectorAll(".planetoid")) {
    node.dataset.selected = String(node.dataset.planetId === currentTheme);
  }
  if (theme) {
    setText("#planet-name", theme.name);
    setText("#planet-meta", `${theme.group || "Palette"} · ${activeMaterial} / ${activeMotion}`);
  }
}

function renderPlanetoids() {
  stopPlanetLoop();
  const field = $("#planet-field");
  if (!field) return;
  const rows = planetRows();
  field.replaceChildren();
  const size = rows.length > 28 ? 19 : rows.length > 17 ? 22 : 27;
  for (const theme of rows) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "planetoid";
    button.dataset.planetId = theme.id;
    button.style.setProperty("--planet-size", `${size}px`);
    button.style.setProperty("--planet-primary", theme.primary);
    button.style.setProperty("--planet-secondary", theme.secondary || theme.surface);
    button.style.setProperty("--planet-tertiary", theme.tertiary);
    button.style.setProperty("--planet-emphasis", theme.emphasis);
    button.setAttribute("aria-label", `${theme.name} · ${theme.group || "palette"}`);
    button.title = `${theme.name} · ${theme.group} · ${theme.material}/${theme.motion}`;
    const glyph = document.createElement("span");
    glyph.className = "planet-glyph";
    glyph.textContent = theme.name.slice(0, 2).toUpperCase();
    glyph.setAttribute("aria-hidden", "true");
    button.append(glyph);
    field.append(button);
  }
  setText("#planet-count", `${rows.length} ${planetSource}`);
  updatePlanetSelection();
  resetPlanetBodies();
  if (settingsTab === "palettes" && !paletteDraft) startPlanetLoop();
}

function resetPlanetBodies() {
  stopPlanetLoop();
  const stage = $("#planet-stage");
  const field = $("#planet-field");
  if (!stage || !field) return;
  const nodes = [...field.querySelectorAll(".planetoid")];
  const width = Math.max(180, Math.floor(stage.clientWidth || 252));
  const height = Math.max(150, Math.floor(stage.clientHeight || 190));
  const count = Math.max(1, nodes.length);
  const radius = nodes.length > 28 ? 9 : nodes.length > 17 ? 11 : 13;
  const cx = width / 2;
  const cy = height / 2;
  planetBodies = nodes.map((node, index) => {
    const angle = (index / count) * Math.PI * 2 + (index % 3) * 0.27;
    const orbit = Math.min(width, height) * (0.18 + (index % 4) * 0.075);
    const x = cx + Math.cos(angle) * orbit;
    const y = cy + Math.sin(angle) * orbit;
    const body = {
      node, x, y, orbit, radius, mass: radius * radius,
      vx: -Math.sin(angle) * (18 + (index % 3) * 5),
      vy: Math.cos(angle) * (18 + (index % 3) * 5),
      dragging: false, dragMoved: false, suppressClick: false,
    };
    node.style.width = `${radius * 2}px`;
    node.style.height = `${radius * 2}px`;
    bindPlanetPointer(body, stage);
    node.addEventListener("click", (event) => {
      if (body.suppressClick) {
        body.suppressClick = false;
        event.preventDefault();
        return;
      }
      choosePlanet(node.dataset.planetId);
    });
    return body;
  });
  drawPlanets();
}

function bindPlanetPointer(body, stage) {
  const node = body.node;
  let lastX = body.x;
  let lastY = body.y;
  node.addEventListener("pointerdown", (event) => {
    event.stopPropagation();
    body.dragging = true;
    body.dragMoved = false;
    body.suppressClick = false;
    lastX = body.x;
    lastY = body.y;
    node.dataset.dragging = "true";
    try { node.setPointerCapture(event.pointerId); } catch (error) { /* pointer capture is optional */ }
  });
  node.addEventListener("pointermove", (event) => {
    if (!body.dragging) return;
    const box = stage.getBoundingClientRect();
    const x = Math.max(body.radius, Math.min(box.width - body.radius, event.clientX - box.left));
    const y = Math.max(body.radius, Math.min(box.height - body.radius, event.clientY - box.top));
    if (Math.hypot(x - lastX, y - lastY) > 2) body.dragMoved = true;
    body.vx = (x - body.x) * 12;
    body.vy = (y - body.y) * 12;
    body.x = x;
    body.y = y;
    drawPlanets();
  });
  const release = () => {
    if (!body.dragging) return;
    body.dragging = false;
    body.suppressClick = body.dragMoved;
    node.dataset.dragging = "false";
  };
  node.addEventListener("pointerup", release);
  node.addEventListener("pointercancel", release);
}

function drawPlanets() {
  for (const body of planetBodies) {
    body.node.style.transform = `translate3d(${body.x - body.radius}px, ${body.y - body.radius}px, 0)`;
  }
}

function stepPlanets(dt) {
  const stage = $("#planet-stage");
  if (!stage || !planetBodies.length) return;
  const width = Math.max(180, stage.clientWidth || 252);
  const height = Math.max(150, stage.clientHeight || 190);
  const cx = width / 2;
  const cy = height / 2;
  for (const body of planetBodies) {
    if (body.dragging) continue;
    const dx = cx - body.x;
    const dy = cy - body.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    // A Box2D-style central field: spring toward the orbit, a tangential push,
    // then circle collision and boundary restitution. This is a real 2D field,
    // not a CSS keyframe orbit, so dragging a planetoid moves the others.
    const spring = (distance - body.orbit) * 2.2;
    body.vx += (dx / distance) * spring * dt;
    body.vy += (dy / distance) * spring * dt;
    body.vx += (-dy / distance) * 18 * dt;
    body.vy += (dx / distance) * 18 * dt;
    body.vx *= 0.992;
    body.vy *= 0.992;
    body.x += body.vx * dt;
    body.y += body.vy * dt;
    if (body.x < body.radius) { body.x = body.radius; body.vx = Math.abs(body.vx) * 0.65; }
    if (body.x > width - body.radius) { body.x = width - body.radius; body.vx = -Math.abs(body.vx) * 0.65; }
    if (body.y < body.radius) { body.y = body.radius; body.vy = Math.abs(body.vy) * 0.65; }
    if (body.y > height - body.radius) { body.y = height - body.radius; body.vy = -Math.abs(body.vy) * 0.65; }
  }
  for (let i = 0; i < planetBodies.length; i += 1) {
    for (let j = i + 1; j < planetBodies.length; j += 1) {
      const a = planetBodies[i];
      const b = planetBodies[j];
      if (a.dragging || b.dragging) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.max(0.001, Math.hypot(dx, dy));
      const minimum = a.radius + b.radius;
      if (distance >= minimum) continue;
      const nx = dx / distance;
      const ny = dy / distance;
      const overlap = minimum - distance;
      a.x -= nx * overlap * 0.5;
      a.y -= ny * overlap * 0.5;
      b.x += nx * overlap * 0.5;
      b.y += ny * overlap * 0.5;
      const relative = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
      if (relative < 0) {
        const impulse = -(1.3 * relative) / (1 / a.mass + 1 / b.mass);
        a.vx -= (impulse / a.mass) * nx;
        a.vy -= (impulse / a.mass) * ny;
        b.vx += (impulse / b.mass) * nx;
        b.vy += (impulse / b.mass) * ny;
      }
    }
  }
  drawPlanets();
}

function startPlanetLoop() {
  stopPlanetLoop();
  if (!planetBodies.length || paletteDraft || settingsTab !== "palettes") return;
  if (document.querySelector(".toast")?.dataset.motion === "reduced") {
    drawPlanets();
    return;
  }
  planetLast = performance.now();
  const tick = (now) => {
    const dt = Math.min(0.033, (now - planetLast) / 1000);
    planetLast = now;
    stepPlanets(dt);
    planetRaf = requestAnimationFrame(tick);
  };
  planetRaf = requestAnimationFrame(tick);
}

function stopPlanetLoop() {
  if (planetRaf) cancelAnimationFrame(planetRaf);
  planetRaf = 0;
}

function choosePlanet(id) {
  const theme = POPIT_THEMES.find((row) => row.id === id);
  if (!theme) return;
  if (theme.source === "family" || theme.source === "player" || theme.source === "custom") {
    planetSource = theme.source;
  }
  applyTheme(theme.id);
  openPaletteEditor(theme);
}

function paletteDraftTheme() {
  return paletteDraft ? customTheme(normalizePalette(paletteDraft) || paletteDraft) : null;
}

function previewPalette() {
  const theme = paletteDraftTheme();
  if (!theme) return;
  paintTheme(theme, false);
  fillPaletteEditor();
}

function pushPaletteHistory() {
  const snapshot = paletteSnapshot();
  if (!snapshot) return;
  const last = paletteHistory[paletteHistory.length - 1];
  if (JSON.stringify(snapshot) === JSON.stringify(last)) return;
  paletteHistory.push(snapshot);
  if (paletteHistory.length > 64) paletteHistory.shift();
  paletteFuture = [];
}

function fillPaletteEditor() {
  if (!paletteDraft) return;
  for (const role of PALETTE_ROLES) {
    const input = $(`#palette-${role}`);
    if (input) input.value = paletteDraft[role];
    setText(`#palette-${role}-value`, paletteDraft[role]);
  }
  const name = $("#palette-name");
  if (name && document.activeElement !== name) name.value = paletteDraft.name;
  setText("#palette-editor-title", `${paletteDraft.name || "Untitled palette"} · editor`);
  setText("#palette-material", paletteDraft.material);
  setText("#palette-motion", paletteDraft.motion);
  setText("#palette-frame", paletteDraft.frame);
  updatePaletteLibrary();
}

function updatePaletteLibrary() {
  const select = $("#palette-library");
  if (!select) return;
  const current = paletteDraft?.id || "";
  select.replaceChildren();
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = customPalettes.length ? "— load a saved palette —" : "— no saved palettes yet —";
  select.append(empty);
  for (const row of customPalettes) {
    const option = document.createElement("option");
    option.value = row.id;
    option.textContent = row.name;
    select.append(option);
  }
  select.value = customPalettes.some((row) => row.id === current) ? current : "";
}

function openPaletteEditor(theme) {
  paletteBase = theme;
  const id = theme.source === "custom" && customPalettes.some((row) => row.id === theme.id)
    ? theme.id : newPaletteId(theme.name);
  paletteDraft = normalizePalette({
    id, name: theme.name, primary: theme.primary,
    secondary: theme.secondary || theme.surface,
    tertiary: theme.tertiary, emphasis: theme.emphasis,
    frame: activeFrame, material: activeMaterial, motion: activeMotion,
  });
  if (!paletteDraft) return;
  paletteHistory = [paletteSnapshot()];
  paletteFuture = [];
  const pane = document.querySelector(".settings-palettes");
  pane?.classList.add("is-editing");
  const editor = $("#palette-editor");
  if (editor) editor.hidden = false;
  stopPlanetLoop();
  fillPaletteEditor();
  setText("#palette-status", "Live preview. Save to keep this community palette on this machine.");
  decorateContours();
  fillContours(document);
}

function closePaletteEditor() {
  const base = paletteBase;
  paletteDraft = null;
  paletteHistory = [];
  paletteFuture = [];
  const pane = document.querySelector(".settings-palettes");
  pane?.classList.remove("is-editing");
  const editor = $("#palette-editor");
  if (editor) editor.hidden = true;
  if (base) {
    if (base.source === "family" || base.source === "player" || base.source === "custom") {
      planetSource = base.source;
    }
    applyTheme(base.id);
  }
  renderPlanetoids();
  startPlanetLoop();
}

function savePaletteDraft() {
  const normalized = normalizePalette(paletteDraft);
  if (!normalized) {
    setText("#palette-status", "Palette needs a name and four six-digit colours.");
    return;
  }
  const index = customPalettes.findIndex((row) => row.id === normalized.id);
  if (index >= 0) customPalettes[index] = normalized;
  else customPalettes.push(normalized);
  persistCustomPalettes();
  refreshCustomThemes();
  paletteDraft = normalized;
  paletteBase = customTheme(normalized);
  paletteHistory = [paletteSnapshot()];
  paletteFuture = [];
  planetSource = "custom";
  applyTheme(normalized.id);
  fillPaletteEditor();
  renderPlanetoids();
  setText("#palette-status", `Saved “${normalized.name}” · ${customPalettes.length} community palettes.`);
}

function loadSelectedPalette() {
  const id = $("#palette-library")?.value || "";
  const row = customPalettes.find((palette) => palette.id === id);
  if (!row) {
    setText("#palette-status", "Choose a saved palette first.");
    return;
  }
  applyTheme(row.id);
  openPaletteEditor(customTheme(row));
}

function undoPalette() {
  if (paletteHistory.length <= 1) return;
  paletteFuture.push(paletteHistory.pop());
  const previous = paletteHistory[paletteHistory.length - 1];
  paletteDraft = { ...paletteDraft, ...previous };
  previewPalette();
  setText("#palette-status", "Undo · live preview restored.");
}

function redoPalette() {
  if (!paletteFuture.length) return;
  const next = paletteFuture.pop();
  paletteHistory.push(next);
  paletteDraft = { ...paletteDraft, ...next };
  previewPalette();
  setText("#palette-status", "Redo · live preview restored.");
}

function newPalette() {
  const family = POPIT_THEMES.find((row) => row.id === "family") || POPIT_THEMES[0];
  applyTheme(family.id);
  openPaletteEditor(family);
  if (!paletteDraft) return;
  paletteDraft.id = newPaletteId("Untitled palette");
  paletteDraft.name = "Untitled palette";
  paletteHistory = [paletteSnapshot()];
  fillPaletteEditor();
  previewPalette();
  setText("#palette-status", "New palette. Tune the four roles and save.");
}

function paletteExportRows() {
  if (paletteDraft) return [paletteDraft];
  return customPalettes;
}

function exportPalettes() {
  const rows = paletteExportRows();
  if (!rows.length) {
    setText("#palette-status", "Nothing to export yet. Open a planetoid first.");
    return;
  }
  const bundle = {
    schema: "popit.community-palette/1",
    generator: "popit-shell",
    at: new Date().toISOString(),
    palettes: rows.map(({ id, name, primary, secondary, tertiary, emphasis, frame, material, motion }) => ({
      id, name, primary, secondary, tertiary, emphasis, frame, material, motion,
    })),
  };
  const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `popit-community-palettes-${slug(new Date().toISOString().slice(0, 10))}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  setText("#palette-status", `Exported ${rows.length} palette${rows.length === 1 ? "" : "s"}.`);
}

function importPalettes(text) {
  let data;
  try { data = JSON.parse(text); } catch (error) {
    setText("#palette-status", "Import refused: not valid JSON.");
    return;
  }
  const rows = Array.isArray(data?.palettes) ? data.palettes : [data];
  const normalized = rows.map(normalizePalette).filter(Boolean);
  if (!normalized.length) {
    setText("#palette-status", "Import refused: no palette with four six-digit colours.");
    return;
  }
  for (const row of normalized) {
    const index = customPalettes.findIndex((palette) => palette.id === row.id || palette.name === row.name);
    if (index >= 0) customPalettes[index] = row;
    else customPalettes.push(row);
  }
  persistCustomPalettes();
  refreshCustomThemes();
  planetSource = "custom";
  applyTheme(normalized[0].id);
  openPaletteEditor(customTheme(normalized[0]));
  renderPlanetoids();
  setText("#palette-status", `Imported ${normalized.length} community palette${normalized.length === 1 ? "" : "s"}.`);
}

function showSettingsPane(name) {
  settingsTab = name === "palettes" ? "palettes" : "surface";
  const panel = $("#settings-panel");
  if (panel) panel.dataset.settingsTab = settingsTab;
  for (const button of document.querySelectorAll("[data-settings-tab-choice]")) {
    button.setAttribute("aria-selected", String(button.dataset.settingsTabChoice === settingsTab));
  }
  for (const pane of document.querySelectorAll("[data-settings-pane]")) {
    pane.hidden = pane.dataset.settingsPane !== settingsTab;
  }
  if (settingsTab === "palettes") {
    if (!paletteDraft) {
      document.querySelector(".settings-palettes")?.classList.remove("is-editing");
      const editor = $("#palette-editor");
      if (editor) editor.hidden = true;
      renderPlanetoids();
      startPlanetLoop();
    }
  } else {
    stopPlanetLoop();
  }
  decorateContours();
  fillContours(document);
}

function motionPreference() {
  const saved = localStorage.getItem("popit.motion");
  if (saved === "full" || saved === "reduced") return saved;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ? "reduced" : "full";
}

function applyMotion(mode, author = false) {
  if (author) settingsAuthoring = true;
  const value = mode === "reduced" ? "reduced" : "full";
  $(".toast")?.setAttribute("data-motion", value);
  localStorage.setItem("popit.motion", value);
  setText("#motion-value", value);
  for (const button of document.querySelectorAll("[data-motion-choice]")) {
    button.setAttribute("aria-pressed", String(button.dataset.motionChoice === value));
  }
  if (settingsTab === "palettes" && !paletteDraft) startPlanetLoop();
  pushSettingsState();
}

function renderLines(lines) {
  const list = $("#lines");
  list.replaceChildren();
  for (const line of lines.slice().reverse()) {
    const item = document.createElement("li");
    item.textContent = line.text;
    item.dataset.tone = line.tone;
    item.title = `${line.at} ${line.text}`;
    list.append(item);
  }
  if (!lines.length) {
    const item = document.createElement("li");
    item.textContent = "waiting for the cua-chat probe";
    list.append(item);
  }
}

function renderDrivers(fleet) {
  const list = $("#drivers");
  list.replaceChildren();
  for (const driver of fleet.drivers || []) {
    const item = document.createElement("li");
    const name = document.createElement("b");
    name.textContent = driver.id;
    const role = document.createElement("span");
    role.textContent = driver.role;
    const tasks = document.createElement("em");
    tasks.textContent = `${driver.tasks} ${driver.last || "idle"}`;
    item.append(name, role, tasks);
    list.append(item);
  }
}

function renderVoice(state) {
  const voice = state.voice || {};
  const mic = state.mic || {};
  const speaking = voice.speaking;
  const last = voice.last;
  const queued = (voice.queue || []).length;
  const status = $("#voice-state");
  const call = (state.calls || {}).active;
  let stage = "idle";
  if (speaking) stage = "speaking";
  else if (last && last.state === "refused") stage = "refused";
  else if (queued) stage = "queued";
  else if (call && call.listening) stage = "listening";
  else if (call) stage = "calling";
  status.dataset.state = stage;
  status.textContent = speaking ? "speaking" : queued ? `${queued} queued` : stage;
  setText("#voice-profile", (speaking || last || {}).label || "assistant");
  setText("#voice-line", (speaking || last || {}).text || "—");
  const open = ["starting", "listening", "heard"].includes(mic.state);
  const heard = $("#heard-line");
  if (heard) {
    heard.textContent = (mic.last || {}).text
      || (mic.state === "refused" ? `refused · ${(mic.detail || "microphone").slice(0, 34)}` : "—");
    heard.title = mic.detail || heard.textContent;
    heard.dataset.state = mic.state || "";
  }
  const micButton = $("#mic");
  if (micButton) {
    micButton.textContent = open ? "Mic on" : "Mic off";
    micButton.setAttribute("aria-pressed", String(open));
    micButton.dataset.on = String(open);
    micButton.title = mic.detail || (open ? "Turn the default microphone off" : "Turn the default microphone on");
  }
}

function streamText(text, speaker, key) {
  const words = $("#stream-words");
  if (!words) return;
  streamKey = key;
  streamQueue = String(text || "").split(/\s+/).filter(Boolean);
  streamIndex = 0;
  streamDone = false;
  words.replaceChildren();
  setText("#stream-speaker", speaker || "");
  if (streamTimer) clearInterval(streamTimer);
  if (!streamQueue.length) {
    streamDone = true;
    return;
  }
  streamTimer = setInterval(() => {
    // Long answers arrive whole from the Debian mind; stream them in small breaths so
    // the owner can read along instead of seeing a wall of text replace the line.
    for (let step = 0; step < 2 && streamIndex < streamQueue.length; step += 1) {
      const word = document.createElement("span");
      word.className = "stream-word";
      word.textContent = streamQueue[streamIndex];
      words.append(word);
      streamIndex += 1;
    }
    words.scrollTop = words.scrollHeight;
    if (streamIndex >= streamQueue.length) {
      clearInterval(streamTimer);
      streamTimer = null;
      streamDone = true;
      renderStream(latest);
    }
  }, 38);
}

function renderVoiceInput(state) {
  const input = $("#voice-input");
  if (!input) return;
  const mic = state.mic || {};
  const last = mic.last || {};
  const partial = mic.partial || {};
  const text = String(last.text || "").trim();
  const key = text ? `${last.at || ""}:${text}` : "";
  if (partial.text && (!last.at || String(partial.at || "") >= String(last.at || ""))) {
    // Provisional Whisper phrases arrive while the owner is still speaking.
    if (!input.value.trim() || input.dataset.auto === "true") {
      input.value = partial.text;
      input.dataset.auto = "true";
      input.dataset.streaming = "true";
      input.scrollTop = input.scrollHeight;
    }
  }
  if (key && key !== micKey) {
    micKey = key;
    // Do not overwrite a correction the owner is typing. A fresh empty box streams
    // the heard phrase word by word, then remains editable for a fix or a send.
    if (!input.value.trim() || input.dataset.auto === "true") {
      micWords = text.split(/\s+/).filter(Boolean);
      micIndex = 0;
      input.value = "";
      input.dataset.auto = "true";
      input.dataset.streaming = "true";
      if (micTimer) clearInterval(micTimer);
      micTimer = setInterval(() => {
        if (micIndex >= micWords.length) {
          clearInterval(micTimer);
          micTimer = null;
          input.dataset.streaming = "false";
          return;
        }
        input.value = `${input.value}${input.value ? " " : ""}${micWords[micIndex]}`;
        micIndex += 1;
        input.scrollTop = input.scrollHeight;
        if (micIndex >= micWords.length) {
          clearInterval(micTimer);
          micTimer = null;
          input.dataset.streaming = "false";
        }
      }, 46);
    }
  }
  input.placeholder = mic.state === "refused"
    ? `microphone refused · ${(mic.detail || "check the device").slice(0, 38)}`
    : "Your voice appears here — read only";
}

function renderStream(state) {
  const panel = $("#voice-stream");
  if (!panel) return;
  const responders = state.responders || [];
  const working = Boolean(state.working) || responders.length > 0;
  const archive = (state.archive && state.archive.rows) || [];
  const answers = archive.filter((row) => row.kind === "cua" && row.text);
  const latestAnswer = answers.length ? answers[answers.length - 1] : null;
  const users = archive.filter((row) => row.kind === "user" && row.text);
  const latestUser = users.length ? users[users.length - 1] : null;
  if (latestAnswer) {
    const key = `${latestAnswer.role || "agent"}:${latestAnswer.at || ""}:${latestAnswer.text}`;
    if (key !== streamKey) {
      streamText(latestAnswer.text, latestAnswer.role || "agent", key);
    }
  } else if (latestUser) {
    const key = `you:${latestUser.at || ""}:${latestUser.text}`;
    if (key !== streamKey) {
      streamText(latestUser.text, "you", key);
    }
  }
  panel.dataset.state = working ? "processing" : (streamDone ? "idle" : "streaming");
  const label = working
    ? `processing${responders.length ? ` · ${responders.join(" ")}` : ""}`
    : (streamDone ? (latestAnswer ? "answer" : "listening") : "streaming");
  setText("#stream-state", label);
}

async function callParticipant(row) {
  if (row.kind === "human") {
    setText("#refusal", "this line is you");
    return;
  }
  const reply = await post("/api/toast/call/participant", { name: row.name });
  if (!reply.ok) setText("#refusal", reply.refused?.code || "call refused");
  else setText("#refusal", `${reply.call.agent} on the line`);
  await poll();
}

async function endParticipant(row) {
  const actives = (latest.calls || {}).actives || [];
  const active = actives.find((call) => [call.civilian, call.agent].includes(row.name));
  if (!active) return;
  const evidence = (latest.harness || {}).path || "runlogs/toast/view-grab.png";
  const reply = await post("/api/toast/call/close", { id: active.id, evidence });
  if (!reply.ok) setText("#refusal", reply.refused?.code || "close refused");
  else setText("#refusal", "call closed");
  await poll();
}

function renderParticipants(state) {
  const dialin = state.dialin || {};
  const rows = dialin.civilians || [];
  const box = $("#participants");
  if (!box) return;
  setText("#call-mode", "voice");
  const actives = (state.calls || {}).actives || [];
  const responders = new Set(state.responders || []);
  const activeNames = new Set(actives.flatMap((call) => [call.civilian, call.agent]));
  // The strip is a working set, not the whole seeded population. A new civilian
  // enters it only when their line is live; everyone else is in the contact book.
  // The owner is the human on the line, never a civil lane. The pinned strip is the
  // agent working set; the owner enters it only when their own line is active.
  const pinned = new Set(["Buffy", "Qwen", "Whisper", "Ash", "Bram", ...activeNames]);
  const owner = rows.find((row) => row.kind === "human");
  if (owner && activeNames.has(owner.name)) pinned.add(owner.name);
  const visible = rows.filter((row) => pinned.has(row.name));
  setText("#contacts-toggle", `Contacts · ${rows.filter((row) => row.kind !== "human").length}`);
  const key = visible.map((row) => `${row.id}:${row.kind}:${row.verified}:${row.number}`).join("|")
    + `|${actives.map((call) => call.id).join(",")}|${[...responders].join(",")}|${state.working}`;
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren();
  for (const row of visible) {
    const wrap = document.createElement("div");
    wrap.className = "participant";
    wrap.dataset.verified = String(Boolean(row.verified));
    wrap.dataset.active = String(activeNames.has(row.name));
    wrap.dataset.working = String(Boolean(state.working && row.kind !== "human" && responders.has(row.name)));
    const name = document.createElement("div");
    name.className = "participant-name";
    name.setAttribute("role", "button");
    name.tabIndex = 0;
    name.setAttribute("aria-label", `${row.name} · ${row.number}`);
    name.title = `${row.name} · ${row.number}`;
    const label = document.createElement("span");
    label.className = "participant-label";
    label.textContent = row.kind === "human" ? "you" : row.name;
    const number = document.createElement("span");
    number.className = "participant-number-text";
    number.textContent = row.number;
    const dot = document.createElement("i");
    dot.className = "participant-dot";
    const actions = document.createElement("div");
    actions.className = "participant-actions";
    if (row.kind !== "human") {
      const call = document.createElement("button");
      call.type = "button";
      call.textContent = "☎";
      call.disabled = activeNames.has(row.name);
      call.title = `Call ${row.name}`;
      call.setAttribute("aria-label", `Call ${row.name}`);
      call.addEventListener("click", (event) => {
        event.stopPropagation();
        callParticipant(row);
      });
      const end = document.createElement("button");
      end.type = "button";
      end.textContent = "✕";
      end.disabled = !activeNames.has(row.name);
      end.title = `End ${row.name}'s call`;
      end.setAttribute("aria-label", `End ${row.name}'s call`);
      end.addEventListener("click", (event) => {
        event.stopPropagation();
        endParticipant(row);
      });
      actions.append(call, end);
    }
    name.append(label, number, dot, actions);
    wrap.append(name);
    box.append(wrap);
  }
}

function renderContactBook(state) {
  const list = $("#contact-list");
  if (!list) return;
  const rows = ((state.dialin || {}).civilians || []).filter((row) => row.kind !== "human");
  const search = String(($("#contact-search") || {}).value || "").trim().toLowerCase();
  const actives = (state.calls || {}).actives || [];
  const activeNames = new Set(actives.flatMap((call) => [call.civilian, call.agent]));
  const filtered = rows.filter((row) => !search || [row.name, row.number, row.role, row.culture]
    .some((value) => String(value || "").toLowerCase().includes(search)));
  setText("#contact-count", `${filtered.length} of ${rows.length} civilians`);
  const key = `${search}|${filtered.map((row) => `${row.id}:${activeNames.has(row.name)}`).join(",")}`;
  if (list.dataset.key === key) return;
  list.dataset.key = key;
  list.replaceChildren();
  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "doc-empty";
    empty.textContent = "No civilian matches that search.";
    list.append(empty);
    return;
  }
  for (const row of filtered) {
    const wrap = document.createElement("div");
    wrap.className = "contact-row";
    wrap.dataset.active = String(activeNames.has(row.name));
    const identity = document.createElement("div");
    identity.className = "contact-id";
    const name = document.createElement("span");
    name.className = "contact-name";
    name.textContent = row.name;
    const meta = document.createElement("span");
    meta.className = "contact-meta";
    meta.textContent = [row.number, row.role, row.culture].filter(Boolean).join(" · ");
    identity.append(name, meta);
    const actions = document.createElement("div");
    actions.className = "contact-actions";
    const call = document.createElement("button");
    call.type = "button";
    call.textContent = "☎";
    call.disabled = activeNames.has(row.name);
    call.title = `Call ${row.name}`;
    call.setAttribute("aria-label", `Call ${row.name}`);
    call.addEventListener("click", (event) => { event.stopPropagation(); callParticipant(row); });
    const end = document.createElement("button");
    end.type = "button";
    end.textContent = "✕";
    end.disabled = !activeNames.has(row.name);
    end.title = `End ${row.name}'s call`;
    end.setAttribute("aria-label", `End ${row.name}'s call`);
    end.addEventListener("click", (event) => { event.stopPropagation(); endParticipant(row); });
    actions.append(call, end);
    wrap.append(identity, actions);
    list.append(wrap);
  }
}

function renderCalls(state) {
  const calls = state.calls || {};
  const actives = calls.actives || [];
  const line = $("#wish-line");
  const clock = $("#wish-clock");
  const queue = $("#call-queue");
  if (!line || !clock) return;
  if (queue) queue.replaceChildren();
  if (!actives.length) {
    clock.textContent = "no call";
    line.textContent = "no call";
    line.title = "";
    return;
  }
  clock.textContent = `${actives.length} persistent`;
  line.textContent = `${actives.length} lines open`;
  line.title = actives.map((call) => `${call.agent}: ${(call.opening || []).map((row) => row.presence).join(", ")} · task #${call.task_id}`).join(" | ");
}

function renderWorkspace(state) {
  const tasks = (state.fleet.tasks || []).filter((task) => ["queued", "running"].includes(task.status));
  const active = Boolean(state.working) || tasks.length > 0;
  const node = $("#workspace-state");
  if (node) {
    node.dataset.on = String(active);
    node.title = tasks.length
      ? tasks.map((task) => `${task.driver} · ${task.status} · ${task.actions} action`).join(" | ")
      : state.working ? "the Debian mind is working in the workspace" : "no workspace task is running";
  }
  setText("#workspace-label", active
    ? (tasks.length ? `workspace · ${tasks.length} task${tasks.length === 1 ? "" : "s"}` : "workspace · responding")
    : "workspace idle");
}

let chatKey = "";
let docPrimed = false;
let docProgress = {};
let docSeen = new Set();
let docLaneSeen = new Set();

function chatRow(lineNo, speaker, text, meta, kind, threadState) {
  const row = document.createElement("div");
  row.className = "chat-row";
  row.dataset.kind = kind;
  if (threadState) row.dataset.state = threadState;
  const number = document.createElement("span");
  number.className = "line-no";
  number.textContent = lineNo;
  const who = document.createElement("span");
  who.className = "chat-speaker";
  who.textContent = speaker;
  const body = document.createElement("span");
  body.className = "chat-text";
  if (kind === "thread") {
    const mark = document.createElement("i");
    mark.className = ["responding", "queued", "thinking", "composing", "speaking"].includes(threadState)
      ? "thread-spinner" : "thread-dot";
    body.append(mark, document.createTextNode(text));
  } else {
    body.textContent = text;
  }
  const detail = document.createElement("span");
  detail.className = "chat-meta";
  detail.textContent = meta || "";
  row.append(number, who, body, detail);
  return row;
}

function docRow(lineNo, speaker, text, meta, kind, options = {}) {
  const row = document.createElement("div");
  row.className = "doc-row";
  row.dataset.kind = kind;
  if (options.state) row.dataset.state = options.state;
  if (options.new) row.dataset.new = "true";
  if (options.live) row.dataset.live = "true";
  if (options.placeholder) row.dataset.placeholder = "true";
  const line = document.createElement("span");
  line.className = "doc-line";
  line.textContent = lineNo;
  const who = document.createElement("span");
  who.className = "doc-speaker";
  who.textContent = speaker;
  const body = document.createElement("span");
  body.className = "doc-text";
  if (kind === "thread") {
    const mark = document.createElement("i");
    mark.className = options.spinner ? "doc-spinner" : "doc-dot";
    body.append(mark, document.createTextNode(text));
  } else {
    body.textContent = text;
  }
  if (options.caret) {
    const caret = document.createElement("span");
    caret.className = "doc-caret";
    body.append(caret);
  }
  const detail = document.createElement("span");
  detail.className = "doc-meta";
  detail.textContent = meta || "";
  row.append(line, who, body, detail);
  return row;
}

function renderLanes(state) {
  const box = $("#lane-chips");
  if (!box) return;
  const lanes = (state.lanes && state.lanes.active) || [];
  const selected = new Set((state.lanes && state.lanes.selected) || []);
  const commons = $("#commons-lane");
  // Empty selection means commons: every live lane is addressed automatically.
  const all = selected.size === 0;
  if (commons) {
    // The commons lane is constant: it cannot be closed. It addresses every
    // live lane on an unaddressed owner turn; a lane chip narrows that selection.
    commons.dataset.on = "true";
    commons.setAttribute("aria-pressed", "true");
    commons.textContent = all ? "Commons · all lanes" : "Commons · unrestricted";
    commons.title = all ? "Commons: every lane" : "Commons";
  }
  const key = lanes.map((lane) => `${lane.name}:${lane.channel}:${selected.has(lane.name)}`).join("|")
    + `|${all}|${commons ? commons.dataset.on : ""}`;
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren();
  for (const lane of lanes) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "lane-chip";
    chip.dataset.on = String(selected.has(lane.name));
    chip.textContent = lane.name;
    chip.title = `${lane.name} · ${lane.channel}`;
    chip.setAttribute("aria-pressed", String(selected.has(lane.name)));
    chip.addEventListener("click", async () => {
      // Lane chips are an exclusive selector; clicking the active lane returns
      // to the constant commons lane, which addresses every live lane.
      const names = selected.has(lane.name) ? [] : [lane.name];
      await post("/api/toast/lanes", { names });
      await poll();
    });
    box.append(chip);
  }
  if (!lanes.length) {
    const empty = document.createElement("span");
    empty.className = "lane-empty";
    empty.textContent = "no lanes";
    box.append(empty);
  }
}

function renderChatLog(state) {
  const doc = $("#workdoc");
  const body = $("#workdoc-body");
  if (!doc || !body) return;
  const actives = (state.calls && state.calls.actives) || [];
  const responders = new Set(state.responders || []);
  const archive = (state.archive && state.archive.rows) || [];
  const recent = archive.filter((row) => {
    if (row.quarantined) return false;
    if (row.kind === "user") return !PHANTOM.has(heardText(row));
    return row.kind === "cua";
  }).slice(-32);
  const mic = state.mic || {};
  const partial = String((mic.partial || {}).text || "").trim();
  const last = String((mic.last || {}).text || "").trim();
  const latestUser = [...recent].reverse().find((row) => row.kind === "user");
  let liveUser = partial || last;
  if (liveUser && latestUser && latestUser.text.trim() === liveUser) liveUser = "";
  if (liveUser && PHANTOM.has(liveUser.toLowerCase().replace(/[.!?,;:]+$/g, "").trim())) liveUser = "";
  if (liveUser && !liveUser.includes(" ") && !["yes", "no", "stop", "buffy", "qwen", "whisper", "ash", "bram"].includes(liveUser.toLowerCase())) liveUser = "";
  const threads = actives.map((call) => {
    const lane = (state.lane_threads || []).find((item) => item.name === call.agent) || {};
    const responding = responders.has(call.agent);
    const stage = lane.stage || (responding ? "responding" : (state.working ? "queued" : (call.listening ? "listening" : "opening")));
    return { call, stage, detail: lane.detail || "", at: lane.at || "" };
  });
  const writing = [];
  for (const row of recent) {
    if (row.kind !== "cua") continue;
    const key = `a${row.id}`;
    const words = String(row.text || "").split(/\s+/).filter(Boolean);
    if (!(key in docProgress)) docProgress[key] = docPrimed ? 0 : words.length;
    if (docPrimed && docProgress[key] < words.length) {
      // The SSE transport delivers about 3.5 frames a second; three words a frame is
      // a readable document pace with a caret that visibly travels through the line.
      docProgress[key] = Math.min(words.length, docProgress[key] + 3);
    }
    if (docProgress[key] < words.length) writing.push(row.role || "agent");
  }
  const key = recent.map((row) => `${row.id}:${docProgress[`a${row.id}`] || 0}`).join(",")
    + `|${liveUser}|${mic.state}|${threads.map((thread) => `${thread.call.id}:${thread.stage}:${thread.at}`).join(",")}`;
  if (doc.dataset.key === key) return;
  const stuck = !body.firstChild || body.scrollTop + body.clientHeight >= body.scrollHeight - 10;
  doc.dataset.key = key;
  body.replaceChildren();
  let sequence = 0;
  for (const row of recent) {
    sequence += 1;
    const lineNo = String(row.id ?? sequence).padStart(4, "0");
    if (row.kind === "user") {
      const targets = (row.targets || []).join(", ") || "no line";
      const heard = (row.heard_by || []).join(", ") || "none";
      body.append(docRow(lineNo, "you", row.text, `to ${targets} · heard ${heard}`, "user"));
    } else {
      const words = String(row.text || "").split(/\s+/).filter(Boolean);
      const start = docProgress[`a${row.id}`] || 0;
      const text = words.slice(0, start).join(" ");
      const live = start < words.length;
      const fresh = !docSeen.has(`a${row.id}`);
      docSeen.add(`a${row.id}`);
      const tools = (row.tools || []).length;
      body.append(docRow(lineNo, row.role || "agent", text || "…",
        `${row.role || "agent"} lane${tools ? ` · ${tools} tool` : ""}`, "agent",
        { caret: live, live: fresh }));
    }
  }
  if (liveUser) {
    body.append(docRow("LIVE", "you", liveUser, "live voice", "user",
      { caret: true, live: true }));
  }
  threads.forEach((thread, index) => {
    const detail = thread.detail ? ` · ${thread.detail}` : "";
    const text = thread.stage === "thinking"
      ? `thinking${detail}`
      : thread.stage === "composing" ? `composing${detail}`
      : thread.stage === "speaking" ? `speaking${detail}`
      : thread.stage === "queued" ? `queued${detail}`
      : thread.stage === "listening" ? "listening · own thread" : "opening · own thread";
    const spinner = ["thinking", "composing", "speaking", "queued", "responding"].includes(thread.stage);
    const fresh = !docLaneSeen.has(`${thread.call.id}:${thread.stage}`);
    docLaneSeen.add(`${thread.call.id}:${thread.stage}`);
    body.append(docRow(`T${index + 1}`, thread.call.agent, text, thread.stage,
      "thread", { spinner, state: thread.stage, caret: spinner, live: fresh }));
  });
  if (!body.childElementCount) {
    // With nothing else on the desk the document reports the microphone's own state. It
    // carries no sentence of its own: what the desk says about the room comes from the room.
    const micState = String(mic.state || "starting");
    body.append(docRow("LIVE", "you", micState, "", "user",
      { caret: micState === "listening", placeholder: true }));
  }
  if (stuck) body.scrollTop = body.scrollHeight;
  setText("#doc-count", `${recent.length + 1} lines · ${threads.length} threads`);
  setText("#doc-cursor", liveUser
    ? "you · live voice"
    : writing.length ? `${writing[0]} · caret moving`
    : mic.state === "listening" ? "voice line · listening" : "caret · idle");
  docPrimed = true;
}

function renderAxis(state) {
  const axis = state.axis || {};
  const health = axis.health || {};
  const last = axis.last || {};
  const node = $("#axis-line");
  let text = "connecting to Debian";
  let tone = "waiting";
  if (axis.state === "live") {
    text = last.answer || `${health.documents ?? "?"} documents · loop ${health.ticks ?? "?"}`;
    tone = "ok";
  } else if (axis.state === "refused") {
    text = axis.detail || "axis refused";
    tone = "refused";
  }
  if (node) {
    node.textContent = text;
    node.dataset.state = tone;
    node.title = axis.detail || text;
  }
}

function renderMind(state) {
  const mind = state.mind || {};
  const node = $("#mind-state");
  if (node) {
    node.dataset.state = mind.state || "idle";
    node.textContent = mind.state || "idle";
  }
  const live = $("#live");
  if (live) {
    live.dataset.on = String(state.live !== false);
    live.setAttribute("aria-pressed", String(state.live !== false));
    live.title = state.live === false ? "Hold each transcript for correction" : "Send each heard transcript to the Debian mind";
  }
  const log = $("#mind-log");
  if (!log) return;
  const history = mind.history || [];
  const lines = [];
  for (let index = 0; index < history.length; index += 2) {
    const you = history[index] || {};
    const answer = history[index + 1] || {};
    if (you.content) lines.push(`you: ${you.content}`);
    if (answer.content) lines.push(`cua: ${answer.content}`);
    lines.push("");
  }
  const last = mind.last;
  if (last) {
    const already = history.some((row) => row.role === "user" && row.content === last.question);
    if (!already) {
      lines.push(`you: ${last.question}`, `cua: ${last.answer}`, "");
    }
    const tools = (last.tool_runs || []).map((run) => `$ ${run.command} · exit ${run.exit}`);
    setText("#mind-tools", tools.length ? tools.join("  |  ") : "no tools called");
  } else if (mind.state === "thinking") {
    lines.push("cua: thinking…");
  }
  const text = lines.join("\n").trim() || "—";
  if (log.textContent !== text) {
    log.textContent = text;
    log.scrollTop = log.scrollHeight;
  }
}

function renderDebian(state) {
  const debian = state.debian || {};
  const chip = $("#debian-chip");
  if (chip) {
    chip.dataset.state = debian.state || "starting";
    chip.textContent = debian.state === "live" ? "desktop live" : debian.state || "starting";
  }
  setText("#debian-state", debian.state || "starting");
  $("#debian-state").dataset.state = debian.state || "starting";
  setText("#debian-size", debian.width ? `${debian.width}×${debian.height}` : "—");
  setText("#debian-at", debian.at ? debian.at.slice(11, 19) : "—");
  if (debian.capture_ts && debian.capture_ts !== lastDebianShot) {
    lastDebianShot = debian.capture_ts;
    const image = $("#debian-shot");
    image.src = `/api/toast/debian.png?ts=${debian.capture_ts}`;
  }
  const output = $("#debian-output");
  if (!output) return;
  if (debian.state === "refused" && debian.detail) {
    output.hidden = false;
    setText("#debian-output", `desktop refused\n${debian.detail}`);
  } else if (debian.last) {
    const run = debian.last;
    output.hidden = false;
    const text = `$ ${run.command}\n${run.output}\n[exit ${run.exit ?? "timeout"} · ${run.seconds ?? "?"}s]`;
    if (output.textContent !== text) {
      output.textContent = text;
      output.scrollTop = output.scrollHeight;
    }
  } else {
    output.hidden = true;
  }
}

function renderWindows(state) {
  const list = $("#window-list");
  if (!list) return;
  const deb = state.debian || {};
  const probe = state.probe || {};
  const harness = state.harness || {};
  const rows = [
    { source: "debian", name: "Debian LXDE", state: deb.state || "starting",
      size: deb.width ? `${deb.width}×${deb.height}` : "—", at: deb.at || "",
      note: deb.detail || "display :0" },
    { source: "windows", name: "Freebuff harness", state: probe.state || "waiting",
      size: probe.width ? `${probe.width}×${probe.height}` : "—", at: probe.at || "",
      note: harness.code || `textbox ${harness.width || "—"}×${harness.height || "—"}` },
  ];
  const key = rows.map((row) => `${row.name}:${row.state}:${row.size}:${row.at}`).join("|");
  if (list.dataset.key === key) return;
  list.dataset.key = key;
  list.replaceChildren();
  for (const row of rows) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "window-row";
    item.dataset.state = row.state;
    const name = document.createElement("span");
    name.className = "window-name";
    name.textContent = row.name;
    const source = document.createElement("span");
    source.className = "window-source";
    source.textContent = row.source;
    const size = document.createElement("span");
    size.className = "window-size";
    size.textContent = row.size;
    const stateLabel = document.createElement("span");
    stateLabel.className = "window-state";
    stateLabel.textContent = row.state;
    item.append(name, source, size, stateLabel);
    item.title = `${row.name} · ${row.note}${row.at ? ` · ${row.at.slice(11, 19)}` : ""}`;
    list.append(item);
  }
}

function renderHarness(state) {
  const harness = state.harness || {};
  const node = $("#harness-state");
  if (!node) return;
  node.dataset.state = harness.state || "waiting";
  node.textContent = harness.state === "live"
    ? (harness.changed ? "new input" : "textbox probed")
    : (harness.code || "unprobed");
  const regions = harness.regions || {};
  const boxes = Object.entries(regions).map(([name, value]) => `${name} ${value.width}×${value.height}`).join(" · ");
  node.title = [harness.detail, boxes, harness.digest].filter(Boolean).join(" · ");
  setText("#harness-regions", "regions " + (boxes || "—"));
  setText("#harness-age", harness.age == null ? "" : `${harness.age}s`);
  if (harness.state === "refused" && !busy) {
    setText("#refusal", `${harness.code || "harness-unprobed"} · ${harness.detail || ""}`.slice(0, 86));
  }
}

function applyZoom(percent, author = false) {
  if (author) settingsAuthoring = true;
  const value = Math.max(60, Math.min(180, Math.round(Number(percent) || 100)));
  const range = $("#dpi-range");
  if (range) {
    range.value = String(value);
    range.style.setProperty("--range-progress", `${((value - 60) / 120) * 100}%`);
  }
  setText("#dpi-value", `${value}%`);
  localStorage.setItem("popit.zoom", String(value));
  // The Qt window scales the page and reflows it; a browser without that bridge gets the
  // same scale as CSS zoom, which is also what a phone browser uses.
  // The window and the browser get the same cap: a scale that leaves less than 360 layout
  // pixels turns the control rows into overlaps.
  const wanted = Math.min(value / 100, Math.max(1, (window.innerWidth || 400) / 400));
  if (popitWindow) {
    popitWindow.set_zoom(wanted);
  } else {
    // CSS zoom already narrows the layout box by the same factor; narrowing it again made the
    // page's own measurements disagree with what it paints.
    document.documentElement.style.zoom = String(wanted);
  }
  document.documentElement.dataset.scale = String(Number(wanted.toFixed(3)));
  pushSettingsState();
}

function render(state) {
  latest = state;
  const probe = state.probe || {};
  const status = $("#status");
  status.dataset.state = probe.state || "waiting";
  status.textContent = probe.state === "live"
    ? "live"
    : probe.state === "refused" ? "refused" : "waiting";

  if (probe.state === "live") {
    setText("#shot-window", (probe.window || "window").slice(0, 34));
    setText("#shot-size", `${probe.width}×${probe.height}`);
    setText("#probe-age", probe.age == null ? "—" : `${probe.age}s`);
    setText("#probe-digest", probe.digest || "—");
    setText("#refusal", "");
    if (state.capture_ts && state.capture_ts !== lastShot) {
      lastShot = state.capture_ts;
      const image = $("#shot");
      image.src = `/api/toast/capture.png?ts=${state.capture_ts}`;
      image.alt = `Live capture of ${probe.window}`;
    }
  } else if (probe.state === "refused") {
    setText("#shot-window", "Freebuff not captured");
    setText("#shot-size", "");
    setText("#probe-age", "—");
    setText("#probe-digest", "—");
    setText("#refusal", `${probe.code} · ${probe.detail || ""}`.slice(0, 70));
  }

  const tasks = (state.fleet.drivers || []).reduce((sum, driver) => sum + driver.tasks, 0);
  setText("#task-count", String(tasks));
  renderDrivers(state.fleet || {});
  renderVoice(state);
  renderStream(state);
  renderVoiceInput(state);
  renderParticipants(state);
  renderLanes(state);
  renderContactBook(state);
  renderCalls(state);
  renderChatLog(state);
  renderWorkspace(state);
  renderAxis(state);
  renderDebian(state);
  renderWindows(state);
  renderHarness(state);
  renderMind(state);
  renderLines(state.lines || []);
  decorateContours();
  fillContours(document);
}

async function poll() {
  try {
    const reply = await fetch("/api/toast", { cache: "no-store" });
    render(await reply.json());
  } catch (error) {
    setText("#refusal", `toast server · ${error}`);
    $("#status").dataset.state = "refused";
  }
  setTimeout(poll, 4000);
}

async function post(path, body = {}) {
  const reply = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return reply.json();
}

function showTab(name) {
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.classList.toggle("active", button.dataset.tab === name);
  }
  for (const pane of document.querySelectorAll("[data-pane]")) {
    pane.hidden = pane.dataset.pane !== name;
  }
  decorateContours();
  fillContours(document);
}

async function askMind(text) {
  const clean = String(text || "").trim();
  if (!clean || busy) return;
  busy = true;
  const button = $("#mind-go");
  button.disabled = true;
  button.textContent = "Asking";
  setText("#mind-state", "thinking");
  try {
    const reply = await post("/api/toast/ask", { text: clean, profile: "cua-chat" });
    if (!reply.ok) setText("#refusal", reply.refused?.code || "mind refused");
    await poll();
  } finally {
    busy = false;
    button.disabled = false;
    button.textContent = "Ask";
  }
}

async function runDebian() {
  const input = $("#debian-command");
  const command = (input?.value || "").trim();
  if (!command || busy) return;
  busy = true;
  const button = $("#debian-go");
  button.disabled = true;
  button.textContent = "Running";
  try {
    const reply = await post("/api/toast/debian/run", { command, timeout: 30 });
    if (!reply.ok) {
      setText("#refusal", reply.refused?.code || reply.run?.refused?.code || "command refused");
    } else {
      setText("#refusal", `${reply.run.command.slice(0, 28)} · exit ${reply.run.exit}`);
    }
    await poll();
  } finally {
    busy = false;
    button.disabled = false;
    button.textContent = "Run";
  }
}

function attachWindowChannel() {
  // A plain browser has no qrc scheme. Load the Qt bridge only when the embedded
  // transport exists, so the chat surface does not log a guaranteed network error.
  if (!window.qt?.webChannelTransport) return;
  const connect = () => {
    if (typeof QWebChannel === "undefined") return;
    new QWebChannel(window.qt.webChannelTransport, (channel) => {
      popitWindow = channel.objects.popitWindow || null;
      document.documentElement.dataset.hostZoom = popitWindow ? "true" : "false";
      // The package may have scaled the page before the bridge arrived; the host owns the
      // scale now, so drop the CSS one rather than stacking the two.
      if (popitWindow) {
        document.documentElement.style.zoom = "";
        document.documentElement.style.width = "";
      }
      const zoom = Number(localStorage.getItem("popit.zoom") || 100);
      applyZoom(zoom);
    });
  };
  if (typeof QWebChannel !== "undefined") {
    connect();
    return;
  }
  const script = document.createElement("script");
  script.src = "qrc:///qtwebchannel/qwebchannel.js";
  script.onload = connect;
  document.head.append(script);
}

function wirePaletteForge() {
  for (const button of document.querySelectorAll("[data-settings-tab-choice]")) {
    button.addEventListener("click", () => showSettingsPane(button.dataset.settingsTabChoice));
  }
  for (const button of document.querySelectorAll("[data-planet-source-choice]")) {
    button.addEventListener("click", () => {
      planetSource = button.dataset.planetSourceChoice;
      for (const peer of document.querySelectorAll("[data-planet-source-choice]")) {
        peer.setAttribute("aria-pressed", String(peer.dataset.planetSourceChoice === planetSource));
      }
      renderPlanetoids();
    });
  }
  $("#planet-edit")?.addEventListener("click", () => {
    const theme = POPIT_THEMES.find((row) => row.id === currentTheme);
    if (theme) openPaletteEditor(theme);
  });
  $("#palette-back")?.addEventListener("click", closePaletteEditor);
  $("#palette-save")?.addEventListener("click", savePaletteDraft);
  $("#palette-undo")?.addEventListener("click", undoPalette);
  $("#palette-redo")?.addEventListener("click", redoPalette);
  $("#palette-new")?.addEventListener("click", newPalette);
  $("#palette-load")?.addEventListener("click", loadSelectedPalette);
  $("#palette-export")?.addEventListener("click", exportPalettes);
  $("#palette-import")?.addEventListener("click", () => $("#palette-import-file")?.click());
  $("#palette-import-file")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      importPalettes(await file.text());
    } catch (error) {
      setText("#palette-status", `Import refused: ${error.message}`);
    } finally {
      event.target.value = "";
    }
  });
  $("#palette-name")?.addEventListener("input", (event) => {
    if (!paletteDraft) return;
    paletteDraft.name = event.target.value;
    pushPaletteHistory();
    previewPalette();
  });
  for (const input of document.querySelectorAll("[data-palette-role]")) {
    input.addEventListener("input", () => {
      if (!paletteDraft) return;
      const role = input.dataset.paletteRole;
      paletteDraft[role] = input.value;
      setText(`#palette-${role}-value`, input.value);
      pushPaletteHistory();
      previewPalette();
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && paletteDraft) {
      event.stopImmediatePropagation();
      closePaletteEditor();
    }
  });
  const stage = $("#planet-stage");
  if (stage && !stage.dataset.planetObserved) {
    stage.dataset.planetObserved = "true";
    new ResizeObserver(() => {
      if (settingsTab === "palettes" && !paletteDraft) {
        resetPlanetBodies();
        startPlanetLoop();
      }
    }).observe(stage);
  }
}

function wire() {
  attachWindowChannel();
  $(".bar").addEventListener("mousedown", (event) => {
    if (event.button !== 0 || event.target.closest("button")) return;
    popitWindow?.begin_drag();
  });
  for (const grip of document.querySelectorAll("[data-resize]")) {
    grip.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      popitWindow?.begin_resize(grip.dataset.resize);
    });
  }
  const settingsPanel = $("#settings-panel");
  // Nothing is painted from this machine's storage: the window's material, frame, motion and
  // dpi are the settings package's, and they arrive with the package document.
  currentTheme = "";
  currentSource = "family";
  planetSource = "family";
  renderStyleOptions();
  applyMotion(motionPreference());
  wirePaletteForge();
  renderPlanetoids();
  for (const button of document.querySelectorAll("[data-motion-choice]")) {
    button.addEventListener("click", () => applyMotion(button.dataset.motionChoice, true));
  }
  $("#settings").addEventListener("click", () => {
    settingsPanel.hidden = !settingsPanel.hidden;
    if (!settingsPanel.hidden) showSettingsPane(settingsTab);
    else stopPlanetLoop();
    decorateContours();
    fillContours(document);
  });
  $("#settings-package")?.addEventListener("click", () => {
    window.open("/toast.html?window=settings", "popit-settings-package", "width=820,height=820");
  });
  $("#prose-run")?.addEventListener("click", () => popitProse.run());
  $("#prose-close")?.addEventListener("click", () => closePackageWindow());

  // The SpringBoard is the phone page, so an app on it hands control back by name rather
  // than by navigating the shell away.
  window.addEventListener("message", (event) => {
    if (event.origin !== location.origin) return;
    const data = event.data;
    if (!data || data.source !== "popit-springboard") return;
    // The home has painted its package: only now is it a finished surface.
    if (data.ready) {
      const frame = $("#springboard-frame");
      if (frame) {
        frame.dataset.ready = "true";
        frame.dataset.pending = "false";
      }
      return;
    }
    // Every app opens in this window, the way the desk does: the SpringBoard hands the app
    // back by name and the window that delivered it shows the app.
    if (data.app === "dialin") setSurface("desk");
    // The home hands itself back too: a window that came from the SpringBoard returns to it
    // through the same surface call, never left on a bar with no frame behind it.
    if (data.app === "springboard") setSurface("springboard");
    if (data.app === "settings") {
      returnSurface = activeSurface;
      window.__popitReturnSurface = activeSurface;
      setSurface("desk");
      document.body.dataset.windowMode = "settings";
      const panel = $("#settings-panel");
      if (panel.hidden) $("#settings").click();
    }
    if (data.app === "prose") {
      returnSurface = activeSurface;
      window.__popitReturnSurface = activeSurface;
      document.body.dataset.windowMode = "prose";
      popitProse.boot();
    }
    if (data.app === "bridge") {
      // The bridge's page is a re-creation of the window, and a re-creation is refused by
      // name. It opens again when it is the settings window with the bridge's body.
      setText("#refusal", "bridge · app-kind-foreign · a window page, not a package");
    }
  });

  try { setSurface(localStorage.getItem(SURFACE_KEY) || "desk"); } catch (error) { setSurface("desk"); }

  // The desk is an app package too: it reads the same signed identity the SpringBoard
  // and the settings window read, and takes its theme from the settings package.
  // The window's name is the delivered package's name, never a word this page carries: a name
  // that is not in the signed document is not the window.
  function nameWindow(doc, fallback, app) {
    const authored = (doc && doc.authored) || {};
    const title = String(authored.title || fallback || "");
    window.__popitTitles = window.__popitTitles || {};
    if (app) window.__popitTitles[app] = title;
    setText("#window-name", title);
  }

  // A window draws only after its package and the settings theme verify: an unverified package
  // leaves the bar and the refusal, never a plain page wearing the app's name.
  function refuseWindow(app) {
    const code = document.documentElement.dataset.packageRefusal || "app-refused";
    document.body.dataset.packageRefused = `${app}-${code}`;
    const node = document.querySelector("#refusal");
    if (node) node.textContent = `${app} · ${code}`;
    // The fallback is the home, never a themed bar with an empty body: the window keeps the
    // controls and the resize it is framed by only when a surface that owns them is showing.
    if (app !== "springboard") setSurface("springboard");
  }

  // A window paints only after the settings package's own document has been applied; until then
  // it is hidden, and it stays hidden with only a refusal if that never happens.
  function markReady() {
    if (!document.body.dataset.packageRefused) document.body.dataset.windowState = "ready";
  }
  window.setTimeout(() => {
    if (document.body.dataset.windowState === "pending") refuseWindow("dialin");
  }, 6000);

  attach("dialin", { identitySelector: "#package-identity" })
    .then((doc) => {
      nameWindow(doc, "", "dialin");
      if (!doc || !applyPackageLook(doc)) refuseWindow("dialin");
      else markReady();
    })
    .catch(() => {
      nameWindow(null, "dialin-refused", "dialin");
      refuseWindow("dialin");
    });
  if (document.body.dataset.windowMode === "prose") {
    attach("prose", { identitySelector: "#package-identity" })
      .then((doc) => {
        if (!doc) refuseWindow("prose"); else markReady();
        nameWindow(doc, "prose", "prose");
      })
      .catch(() => {
        nameWindow(null, "prose-refused", "prose");
        refuseWindow("prose");
      });
  }
  // A window that resolves to nothing is not a state this shell allows: if the page has not named
  // itself shortly after load, the desk is shown from its own baseline instead of a blank frame.
  window.setTimeout(() => {
    const name = $("#window-name");
    if (name && !name.textContent.trim()) {
      setText("#window-name", "dialin");
      setSurface("desk");
    }
  }, 6000);
  $("#settings-close").addEventListener("click", () => closePackageWindow());
  for (const button of document.querySelectorAll("[data-settings-tab-choice]")) {
    button.setAttribute("aria-selected", String(button.dataset.settingsTabChoice === settingsTab));
  }
  for (const button of document.querySelectorAll("[data-planet-source-choice]")) {
    button.setAttribute("aria-pressed", String(button.dataset.planetSourceChoice === planetSource));
  }
  showSettingsPane(settingsTab);
  settingsPanel.hidden = true;
  applyZoom(Number(localStorage.getItem("popit.zoom") || 100));
  $("#dpi-range").addEventListener("input", (event) => applyZoom(event.target.value, true));
  $("#dpi-down").addEventListener("click", () => applyZoom(Number($("#dpi-range").value) - 5, true));
  $("#dpi-up").addEventListener("click", () => applyZoom(Number($("#dpi-range").value) + 5, true));
  $("#dpi-reset").addEventListener("click", () => applyZoom(100, true));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !paletteDraft) {
      settingsPanel.hidden = true;
      stopPlanetLoop();
      delete document.body.dataset.windowMode;
      setSurface(returnSurface === "springboard" ? "springboard" : "desk");
      returnSurface = "desk";
    }
  });

  for (const button of document.querySelectorAll("[data-tab]")) {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  }
  $("#live").addEventListener("click", async () => {
    const on = $("#live").dataset.on !== "true";
    const reply = await post("/api/toast/live", { on });
    if (reply.live != null) latest.live = reply.live;
    renderMind(latest);
  });
  $("#debian-capture").addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    try {
      const reply = await post("/api/toast/debian/capture");
      if (!reply.ok) setText("#refusal", reply.refused?.code || "capture refused");
      await poll();
    } finally {
      busy = false;
    }
  });

  $("#probe").addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    $("#probe").textContent = "Probing…";
    try {
      const reply = await post("/api/toast/probe");
      if (!reply.ok) setText("#refusal", reply.refused?.code || "probe refused");
      await poll();
    } finally {
      busy = false;
      $("#probe").textContent = "Probe now";
    }
  });

  $("#delegate").addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    $("#delegate").textContent = "Delegating…";
    try {
      const reply = await post("/api/toast/delegate", {
        driver: "cua-2",
        actions: [{
          action: "capture",
          window: "Freebuff: The free coding agent",
        }],
        announce: true,
      });
      if (reply.ok) {
        setText("#refusal", `task ${reply.task.id} · ${reply.task.driver}`);
      } else {
        setText("#refusal", reply.refused?.code || "delegation refused");
      }
    } finally {
      busy = false;
      $("#delegate").textContent = "Delegate capture";
    }
  });

  const contactsToggle = $("#contacts-toggle");
  const contactBook = $("#contact-book");
  if (contactsToggle && contactBook) {
    contactsToggle.addEventListener("click", () => {
      contactBook.hidden = !contactBook.hidden;
      contactsToggle.setAttribute("aria-expanded", String(!contactBook.hidden));
      if (!contactBook.hidden) {
        renderContactBook(latest);
        decorateContours();
        fillContours(document);
        $("#contact-search")?.focus();
      }
    });
    $("#contact-search")?.addEventListener("input", () => renderContactBook(latest));
  }

  $("#commons-lane")?.addEventListener("click", async () => {
    const reply = await post("/api/toast/lanes", { all: true });
    if (!reply.ok) setText("#refusal", reply.refused?.code || "lane selection refused");
    await poll();
  });

  $("#owner-say")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("#owner-text");
    const button = $("#owner-send");
    const text = String((input && input.value) || "").trim();
    if (!text || busy) return;
    busy = true;
    button.disabled = true;
    try {
      const reply = await post("/api/toast/hear", { text });
      if (!reply.ok) setText("#refusal", reply.refused?.code || "owner line refused");
      if (reply.ok && input) input.value = "";
      await poll();
    } finally {
      busy = false;
      button.disabled = false;
      input?.focus();
    }
  });

  $("#mic").addEventListener("click", async () => {
    const open = ["starting", "listening", "heard"].includes((latest.mic || {}).state);
    const button = $("#mic");
    button.disabled = true;
    try {
      const reply = await post("/api/toast/mic", { on: !open });
      if (!reply.ok) {
        setText("#refusal", reply.refused?.code || "microphone refused");
      } else if (reply.mic) {
        latest.mic = reply.mic;
        renderVoice(latest);
      }
    } finally {
      button.disabled = false;
    }
  });

  $("#hide").addEventListener("click", () => post("/api/toast/hide"));
  $("#close").addEventListener("click", () => post("/api/toast/close"));
  $("#pin").addEventListener("click", async () => {
    const on = $("#pin").dataset.pinned !== "true";
    const reply = await post("/api/toast/pin", { pinned: on });
    $("#pin").dataset.pinned = String(Boolean(reply.pinned));
    $("#pin").style.color = on ? "var(--brass-lit)" : "";
  });
}

async function main() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/popit-sw.js").catch(() => undefined);
  }
  // The desk does not publish its own paint into the settings package: the settings package is
  // the author every window subscribes to, and a boot-time push made the desk's local default
  // the baseline for every app. Only an edit in the settings panel publishes.
  await loadThemes();
  wire();
  $("#pin").dataset.pinned = "true";
  $("#pin").style.color = "var(--brass-lit)";
  showTab("local");
  $("#live").dataset.on = "true";
  if ($(".agent-drawer")) $(".agent-drawer").open = false;
  try {
    await loadContour("/contour.json");
    fillContours(document);
  } catch (error) {
    setText("#refusal", `contour · ${error.message}`);
  }
  // The settings package window is this page opened as a window: after the desk has painted,
  // its own settings control opens the panel. The panel, its motion and its logic are the
  // desk's — this window is the same page, never a second copy of it.
  if (new URLSearchParams(location.search).get("window") === "settings") {
    document.body.dataset.windowMode = "settings";
    $("#settings").click();
  }
  // The prose window is this page with the prose panel as its body: same bar, same frame. It is
  // booted once the probe below exists, so a failed load still leaves the window measurable.
  // The prose app: the family's written surface, drawn in this window. Rows come from the
  // shell's own receipts; a run is a request to the shell, never work the page performs.
  const popitProse = {
    last: { rows: [], driver: {}, report: {} },
    timer: 0,
    close() {
      if (this.timer) window.clearInterval(this.timer);
      this.timer = 0;
    },
    async fetchJson(path) {
      const reply = await fetch(path, { cache: "no-store" });
      return reply.ok ? reply.json() : null;
    },
    async load() {
      const [report, progress] = await Promise.all([
        this.fetchJson("/api/toast/prose/report.json"),
        this.fetchJson("/api/toast/prose/progress.json"),
      ]);
      const progressRows = (progress && progress.rows) || [];
      const rows = progressRows.length ? progressRows : ((report && report.rows) || []);
      this.last = { rows,
                    driver: (progress && progress.driver) || (report && report.driver) || {},
                    report: report || {} };
      this.paint();
      return this.last;
    },
    paint() {
      const table = $("#prose-table");
      if (!table) return;
      const { rows, driver } = this.last;
      const state = $("#prose-state");
      const refused = rows.filter((row) => row.refusal).length;
      const busy = rows.filter((row) => row.busy || row.phase === "queued").length;
      if (state) {
        state.textContent = !rows.length ? "reading"
          : busy ? `${busy} running of ${rows.length}`
          : `${rows.length - refused} of ${rows.length} documented`;
      }
      const driverNode = $("#prose-driver");
      if (driverNode) {
        driverNode.textContent = `driver ${driver.state || "unknown"} · ${driver.detail || "—"}`
          + (driver.projects && driver.projects.length ? ` · ${driver.projects.length} staged` : "");
      }
      table.textContent = "";
      if (!rows.length) {
        const row = document.createElement("div");
        row.className = "prose-row";
        row.id = "prose-reading";
        const spin = document.createElement("span");
        spin.className = "prose-spinner";
        const label = document.createElement("span");
        label.textContent = "reading the family…";
        row.append(spin, label);
        table.append(row);
        return;
      }
      for (const row of rows) {
        const line = document.createElement("div");
        line.className = "prose-row";
        line.id = `prose-${row.name}`;
        const refusal = row.refusal && row.refusal.code;
        line.dataset.refused = String(Boolean(refusal));
        const name = document.createElement("span");
        name.className = "prose-name";
        if (row.busy || row.phase === "queued") {
          const spin = document.createElement("span");
          spin.className = "prose-spinner";
          name.append(spin);
        }
        name.append(document.createTextNode(row.name));
        const progress = document.createElement("span");
        const bar = document.createElement("span");
        bar.className = "prose-bar";
        const fill = document.createElement("i");
        fill.style.width = `${row.percent || 0}%`;
        bar.append(fill);
        progress.append(bar);
        const phase = document.createElement("span");
        phase.className = "prose-phase";
        phase.textContent = row.phase || "";
        const extractors = document.createElement("span");
        extractors.textContent = Object.entries(row.extractors || {})
          .map(([kind, count]) => `${kind}:${count}`).join(" ");
        const drawn = document.createElement("span");
        drawn.textContent = String(row.visible ?? "");
        const hits = document.createElement("span");
        hits.textContent = String(row.hits ?? "");
        const driverCell = document.createElement("span");
        driverCell.textContent = refusal || row.driver || "";
        const doc = document.createElement("span");
        if (row.doc_url) {
          const link = document.createElement("a");
          link.href = row.doc_url;
          link.textContent = "read";
          doc.append(link);
        } else {
          doc.textContent = "—";
        }
        line.append(name, progress, phase, extractors, drawn, hits, driverCell, doc);
        table.append(line);
      }
    },
    async run() {
      const state = $("#prose-state");
      if (state) state.textContent = "starting";
      await fetch("/api/toast/prose/run", { method: "POST" }).catch(() => null);
      window.setTimeout(() => this.load(), 600);
    },
    async boot() {
      // The window's base is the page it was mutated from; the app now delivered in it is prose.
      // Both are named, so a reader sees the base was not replaced by a page of its own.
      this.base = document.documentElement.dataset.packageApp || "";
      document.body.dataset.windowMode = "prose";
      document.documentElement.dataset.packageApp = "prose";
      await this.load();
      const identity = $("#package-identity");
      const name = (this.last.report || {}).identity || "";
      if (identity && name) identity.textContent = name;
      this.timer = window.setInterval(() => this.load(), 1200);
    },
    // The measurement: what the delivered window actually shows, for the window probe.
    state() {
      const rows = this.last.rows || [];
      return JSON.stringify({
        window: document.body.dataset.windowMode || "",
        package: document.documentElement.dataset.packageApp || "",
        base: this.base || "",
        rows: rows.length,
        spinning: rows.filter((row) => row.busy || row.phase === "queued").length,
        drawn: rows.reduce((sum, row) => sum + (Number(row.visible) || 0), 0),
        refused: rows.filter((row) => row.refusal)
          .map((row) => `${row.name}:${row.refusal.code}`).slice(0, 12),
        driver: (this.last.driver || {}).state || "",
        staged: ((this.last.driver || {}).projects || []).length,
        documents: rows.filter((row) => row.doc_url).length,
        spinnerCss: Array.from(document.styleSheets).some((sheet) => {
          try {
            return Array.from(sheet.cssRules).some((rule) => String(rule.cssText).includes("prose-spin"));
          } catch (error) {
            return false;
          }
        }),
      });
    },
  };
  window.popitProse = popitProse;

  // The shell's harness probe: named acts the delivered window performs and reports back, so
  // a check reads the window instead of a browser tab beside it.
  window.popitProbe = {
    // The prose app's own measurement: what its window shows, read from the window.
    prose() {
      return popitProse.state();
    },
    // The act a tile performs: the home hands the app to this window by name, so the probe hands
    // it the same message the frame posts rather than reaching into the frame.
    openApp(name) {
      window.postMessage({ source: "popit-springboard", app: String(name || "") },
                         location.origin);
      return JSON.stringify({ surface: document.querySelector(".toast")?.dataset.surface || "",
                              mode: document.body.dataset.windowMode || "" });
    },
    // What the settings package actually painted: theme, contour frame, material and motion,
    // read from the live document rather than from the code that was supposed to set them.
    paint() {
      try {
        const toast = document.querySelector(".toast");
        const style = toast ? getComputedStyle(toast) : null;
        const root = getComputedStyle(document.documentElement);
        return JSON.stringify({
          state: document.body.dataset.windowState || "",
          refused: document.body.dataset.packageRefused || "",
          theme: document.documentElement.dataset.settingsTheme || "",
          frame: document.documentElement.dataset.contourFrame || "",
          material: document.documentElement.dataset.material || "",
          motion: document.documentElement.dataset.motionProfile || "",
          surface: root.getPropertyValue("--popit-surface").trim(),
          ground: root.getPropertyValue("--popit-ground").trim(),
          pinned: window.__popitPackageStyle || null,
          match: styleMatchesPackage(),
          dataTheme: document.documentElement.dataset.theme || "",
          author: Boolean(window.__popitThemeAuthor),
          height: toast ? Math.round(toast.getBoundingClientRect().height) : 0,
          visible: style ? style.visibility : "",
        });
      } catch (error) {
        return JSON.stringify({ error: String((error && error.message) || error) });
      }
    },
    // The act a style button performs, measured: frame, material and motion are the settings
    // package's, and the window must paint the one the panel chose.
    choose(arg) {
      const [kind, id] = String(arg || "").split("/");
      chooseStyle(kind, id);
      // A measurement must not author the package: the probe paints the choice and cancels the
      // publish that a real button press schedules, so probing never replaces the saved profile.
      settingsAuthoring = false;
      return window.popitProbe.paint();
    },
    // The act a failed package window performs: the window must fall back to the home, so the
    // measurement is the surface and the frame after the refusal, not a promise about it.
    fallback() {
      refuseWindow("dialin");
      return window.popitProbe.windowState();
    },
    // The act the close button performs, measured: the window must return to the surface it was
    // opened from, and a home that is not painted must be loaded again rather than left blank.
    windowClose() {
      try {
        closePackageWindow();
      } catch (error) {
        return JSON.stringify({ refused: String((error && error.message) || error) });
      }
      return window.popitProbe.windowState();
    },
    // What the window shows right now: which surface, which window mode, its name, and whether
    // the home frame is painted. This is the reading the close path is held to.
    windowState() {
      const frame = $("#springboard-frame");
      return JSON.stringify({
        surface: document.querySelector(".toast")?.dataset.surface || "",
        mode: document.body.dataset.windowMode || "",
        name: $("#window-name")?.textContent.trim() || "",
        identity: $("#package-identity")?.textContent.trim() || "",
        refused: document.body.dataset.packageRefused || "",
        theme: document.documentElement.dataset.contourFrame || "",
        panel: Boolean($("#settings-panel") && !$("#settings-panel").hidden),
        trace: (window.__popitSurfaces || []).slice(-6),
        board: Boolean($("#springboard") && !$("#springboard").hidden
                       && $("#springboard").getBoundingClientRect().height > 0),
        toast: Math.round((document.querySelector(".toast")?.getBoundingClientRect().height) || 0),
                frame: frame ? { hidden: Boolean(frame.hidden), src: frame.getAttribute("src") || "",
                          ready: frame.dataset.ready || "", pending: frame.dataset.pending || "",
                          doc: Boolean(frame.contentDocument),
                          theme: frame.contentDocument?.documentElement?.dataset?.contourFrame || "",
                          dpi: frame.contentDocument?.documentElement?.dataset?.dpi || "",
                          tiles: frame.contentDocument?.querySelectorAll(".tile").length || 0,
                          text: (frame.contentDocument?.body?.innerText || "").trim()
                            .replace(/\s+/g, " ").slice(0, 120),
                          height: Math.round(frame.getBoundingClientRect().height),
                          boardHeight: Math.round((document.querySelector("#springboard")||frame)
                            .getBoundingClientRect().height),
                         painted: frame.getBoundingClientRect().height > 0 } : null,
      });
    },
    // The home's measurement, read by the window that delivers it: the frame is this window's
    // own surface, so the tiles below are the ones the owner sees, not a second rendering.
    home() {
      const frame = $("#springboard-frame");
      if (!frame) return JSON.stringify({ frame: false });
      const src = frame.getAttribute("src") || "";
      let doc = null;
      try { doc = frame.contentDocument; } catch (error) { doc = null; }
      if (!doc) return JSON.stringify({ frame: true, src, readable: false });
      const tiles = Array.from(doc.querySelectorAll(".tile")).map((tile) => ({
        lane: tile.dataset.lane || "",
        verified: tile.dataset.verified || "",
        badge: tile.querySelector(".tile-badge")?.textContent.trim() || "",
        package: tile.querySelector(".tile-package")?.textContent.trim() || "",
      }));
      return JSON.stringify({
        frame: true, readable: true, src,
        embedded: src.includes("embedded=1"),
        secure: src.startsWith("https:"),
        identity: doc.querySelector("#package-identity")?.textContent.trim() || "",
        title: doc.querySelector(".brand strong")?.textContent.trim() || "",
        status: doc.querySelector("#home-status")?.textContent.trim() || "",
        tiles,
      });
    },
    springboard() {
      setSurface("springboard");
      return window.popitProbe.springboardState();  // the state at first paint
    },
    // The SpringBoard is measured where it lives: in the frame that the settings window
    // delivers, at the frame's own size. It is never loaded as a page of its own.
    springboardAudit() {
      setSurface("springboard");
      const frame = $("#springboard-frame");
      if (!frame) return JSON.stringify({ frame: false });
      frame.dataset.ready = "false";
      frame.dataset.pending = "true";
      const src = new URL("/phone.html?embedded=1&uiaudit=1&app=springboard", location.origin).toString();
      frame.setAttribute("src", src);
      // The audit flag is the measurement's, not the window's state: once it has reported, the
      // frame is loaded again as the plain signed page.
      window.setTimeout(() => {
        frame.dataset.ready = "false";
        frame.dataset.pending = "true";
        frame.setAttribute("src", new URL("/phone.html?embedded=1", location.origin).toString());
      }, 9000);
      return JSON.stringify({ pending: frame.dataset.pending || "", src,
                              origin: location.origin,
                              painted: getComputedStyle(frame).visibility !== "hidden" });
    },
    // Proof that the frame is the signed SpringBoard and nothing else: where it points, what
    // it says it is, and that this window has no second launcher.
    frameIntegrity() {
      const frame = $("#springboard-frame");
      if (!frame) return JSON.stringify({ frame: false });
      const src = frame.getAttribute("src") || "";
      let identity = "";
      let marker = "";
      let path = "";
      try {
        path = new URL(src, location.origin).pathname;
        const doc = frame.contentDocument;
        identity = doc?.querySelector("#package-identity")?.textContent.trim() || "";
        marker = doc?.documentElement?.dataset.packageApp || doc?.body?.dataset.popit || "";
      } catch (error) { /* a refused frame is reported as having no identity */ }
      // The home's tiles are read by the home itself, in its own window, not through this
      // frame: reading a surface through a bare iframe is what the family's probe rule forbids.
      return JSON.stringify({
        src, path, identity, marker,
        frames: document.querySelectorAll("iframe").length,
        launchers: document.querySelectorAll("[data-launcher]").length,
        surface: document.querySelector(".toast")?.dataset.surface || "",
      });
    },
    springboardState() {
      const frame = $("#springboard-frame");
      if (!frame) return JSON.stringify({ frame: false });
      const box = frame.getBoundingClientRect();
      return JSON.stringify({
        pending: frame.dataset.pending || "",
        ready: frame.dataset.ready || "",
        src: frame.getAttribute("src") || "",
        origin: location.origin,
        painted: getComputedStyle(frame).visibility !== "hidden",
        width: Math.round(box.width),
      });
    },
  };
  if (new URLSearchParams(location.search).get("window") === "prose") {
    popitProse.boot().catch((error) => {
      const state = $("#prose-state");
      if (state) state.textContent = `prose · ${error.message}`;
    });
  }
  await poll();
  if (typeof EventSource !== "undefined") {
    const events = new EventSource("/api/toast/events");
    events.onmessage = (event) => {
      try { render(JSON.parse(event.data)); } catch (error) { /* poll remains the fallback */ }
    };
  }
}

main();
