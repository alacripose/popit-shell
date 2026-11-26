// Surface audit. An app package is only signed when the page it ships can be drawn: the
// audit measures the rendered document and reports overlap, clipped readings and a locked
// horizontal axis. It runs on demand (`?uiaudit=1`) and posts its evidence to the server,
// which is what the publisher reads before it signs a revision.

const MIN_OVERLAP_PX = 6;
const INTERACTIVE = "button, a[href], input, select, textarea, [role='button'], .tile, summary";

function visible(el) {
  const style = getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  if (Number(style.opacity) === 0) return false;
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function contains(a, b) {
  return a !== b && a.contains(b);
}

function overlapArea(a, b) {
  const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return x > 0 && y > 0 ? x * y : 0;
}

function label(el) {
  return (el.id || el.className || el.tagName || "").toString().split(/\s+/)[0].slice(0, 40);
}

function overlaps(doc) {
  const nodes = Array.from(doc.querySelectorAll(INTERACTIVE)).filter(visible);
  const findings = [];
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i];
      const b = nodes[j];
      if (contains(a, b) || contains(b, a)) continue;
      const area = overlapArea(a.getBoundingClientRect(), b.getBoundingClientRect());
      if (area >= MIN_OVERLAP_PX) {
        findings.push({ code: "ui-overlap", detail: `${label(a)} over ${label(b)} (${Math.round(area)}px²)` });
      }
    }
  }
  return findings.slice(0, 12);
}

// The contour frame and its material layer paint past the nine-slice on purpose; their
// overhang is decoration, not text a reader loses.
function decorativeOverflow(el) {
  let extra = 0;
  const box = el.getBoundingClientRect();
  for (const child of el.children) {
    const tag = child.tagName.toLowerCase();
    const decorative = tag === "svg" || child.getAttribute("aria-hidden") === "true"
      || child.classList.contains("contour-material")
      || child.classList.contains("contour-frame");
    if (!decorative) continue;
    extra = Math.max(extra, Math.round(child.getBoundingClientRect().right - box.right));
  }
  return Math.max(extra, 0);
}

// A surface that scales itself with CSS zoom reports the body's layout box in unzoomed pixels
// while its scroll extent is painted at the scale: the body's client width has to be compared
// at the same scale or a page that fits reads as 30px clipped.
function pageZoom(doc) {
  const html = Number(getComputedStyle(doc.documentElement).zoom) || 1;
  const body = Number(getComputedStyle(doc.body).zoom) || 1;
  return html * body;
}

function clipped(doc) {
  const findings = [];
  const zoom = pageZoom(doc);
  for (const el of doc.querySelectorAll("*")) {
    if (!visible(el)) continue;
    const style = getComputedStyle(el);
    const locked = style.overflowX === "hidden" || style.overflowX === "clip";
    if (!locked) continue;
    // A declared ellipsis is the page naming its own truncation, not content it lost.
    if (style.textOverflow === "ellipsis") continue;
    const client = el === doc.body ? el.clientWidth * zoom : el.clientWidth;
    if (el.scrollWidth <= client + 2 + decorativeOverflow(el)) continue;
    const text = (el.textContent || "").trim();
    if (text.length < 2) continue;
    if (el.closest(".messages, #messages, .stream-words")) continue;
    findings.push({ code: "ui-clipped", detail: `${label(el)} hides ${Math.round(el.scrollWidth - client)}px of "${text.slice(0, 24)}"` });
  }
  return findings.slice(0, 12);
}

// A phone surface that overflows sideways is not "scrollable": the reader has to drag the
// page to read a control that should have wrapped. Only a surface with room to pan (a
// window wider than its table) may overflow.
function xOverflow(doc) {
  const root = doc.scrollingElement || doc.documentElement;
  // A zoomed surface reports its scroll extent at the painted scale and its client box at the
  // layout scale; compared raw, a phone that fits reads as overflowing sideways.
  const overflow = root.scrollWidth - Math.round(root.clientWidth * pageZoom(doc));
  if (overflow <= 2 || window.innerWidth > 480) return [];
  return [{ code: "ui-x-overflow", detail: `${overflow}px past the phone's width` }];
}

function xLocked(doc) {
  const root = doc.scrollingElement || doc.documentElement;
  const overflowX = getComputedStyle(root).overflowX;
  const bodyX = getComputedStyle(doc.body).overflowX;
  const overflow = root.scrollWidth - Math.round(root.clientWidth * pageZoom(doc));
  if (overflow <= 2) return [];
  if (overflowX !== "visible" && overflowX !== "auto" && overflowX !== "scroll") {
    return [{ code: "ui-x-locked", detail: `${overflow}px cannot be reached (html overflow-x: ${overflowX}, body: ${bodyX})` }];
  }
  const before = root.scrollLeft;
  root.scrollLeft = Math.min(24, overflow);
  const moved = root.scrollLeft !== before;
  root.scrollLeft = before;
  if (!moved) return [{ code: "ui-x-locked", detail: `${overflow}px overflows but the axis does not move` }];
  return [];
}

export function auditSurface(doc = document) {
  const findings = [...overlaps(doc), ...clipped(doc), ...xOverflow(doc), ...xLocked(doc)];
  return {
    schema: "popit.ui-audit/1",
    app: doc.documentElement.dataset.packageApp || null,
    size: { width: window.innerWidth, height: window.innerHeight },
    at: new Date().toISOString(),
    findings,
  };
}

export async function reportAudit(app, endpoint = "/api/toast/ui-audit") {
  const report = auditSurface();
  // The page names the app it is being measured as: one page can be two packages (the desk's
  // page is the settings window too), and the measurement has to land on the one asked for.
  if (app) report.app = app;
  const body = JSON.stringify({ app: app || report.app, report });
  try {
    const reply = await fetch(endpoint, {
      method: "POST", headers: { "Content-Type": "application/json" }, body,
    }).then((response) => response.json().catch(() => null));
    // A passing measurement republished this app; read the new package so the surface
    // stops showing the refusal it booted with.
    if (reply && reply.package && reply.package.verified === true && !report.findings.length) {
      const client = await import("/package.js");
      await client.repaint();
    }
  } catch (error) {
    // A page opened without the server (file://, a cached shell) still carries its own report.
  }
  document.documentElement.dataset.uiAudit = JSON.stringify(report);
  return report;
}

export function autoAudit() {
  const params = new URLSearchParams(location.search);
  if (!params.get("uiaudit")) return;
  // The page names itself in the audit URL: a surface that is refused has no package
  // identity to read, and its own measurement is what lifts the refusal.
  const app = params.get("app") || document.documentElement.dataset.packageApp || null;
  const run = () => setTimeout(() => reportAudit(app), 500);
  if (document.readyState === "complete") run();
  else window.addEventListener("load", run, { once: true });
}

autoAudit();
