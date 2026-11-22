// The contour is the framing authority and the scale authority. Its measured box is
// 81.9 by 121.348 units; every surface takes its clip from that box and its ink (the
// inset its content must keep) from the same uniform scale, exactly as the Go shell's
// Outline and ContourInk did.

const UNITS_W = 81.9;
const UNITS_H = 121.348;
const SVG_NS = "http://www.w3.org/2000/svg";
// The corner blend the measured path actually turns through, in the drawing's own units.
const CORNER_BAND_X = 16.38;
const CORNER_LEFT = 445.05;
const CORNER_RIGHT = 526.95;
const CORNER_BAND_Y = 23.48;
// The corner's depth along the long rail, at the bar's own height: one number for the
// whole family. Every surface keeps this corner whatever its size, so a card, a bar cell
// and the launcher are cut the same way and none of them flowers out when it grows.
const CORNER_UNITS = 27.8;
// A window frame uses the accepted family corner, the same numbers a bar button uses: the
// corner never grows with the window, and only the rails take up the extra span.
const BAR_HEIGHT = 48;
// The clip runs a pixel inside the box, so a one pixel frame is never cut in half at the
// boundary. Without this the stroke aliases against the clip on a 1080p screen.
const CLIP_PAD = 0.5; // the clip sits outside the frame
const FRAME_PAD = 1.5; // the frame sits inside the clip, so no half of it is cut
// 48px bar height is the family's scale, 26 of the drawing's 121.348 units of corner
// depth lands the accepted 11px corner, and every surface uses that one size.
export const CORNER_PX = (CORNER_UNITS * BAR_HEIGHT) / UNITS_H;

let shape = null;
let seq = 0;

export async function loadContour(url) {
  // The drawing is served beside this module, not at the server root: a project Pages site lives
  // under /<repo>/, and an absolute path there asked the domain root for contour.json (404), so the
  // published page drew rectangles with no contour at all. The page may pass its own cache-busted
  // URL; the module still resolves one beside itself when it does not.
  const shapeUrl = url ? new URL(url, import.meta.url) : new URL("contour.json", import.meta.url);
  // A published drawing must not come from a browser cache: `reload` revalidates with the server, so
  // a returning visitor reads the shape this deployment serves rather than the one it remembered.
  shape = await (await fetch(shapeUrl, { cache: "reload" })).json();
  return shape;
}

export function contour() {
  return shape;
}

// scaleOf is the one uniform scale a surface of this size takes: the contour never
// stretches, so the smaller of the two fits governs.
export function scaleOf(width, height) {
  return Math.min(width / UNITS_W, height / UNITS_H);
}

// nineSlice is the only shape this shell may draw: the measured contour cut into nine
// regions, crowns keeping the profile at one uniform scale and the middle carrying the
// slack. Anything that is not this shape is refused rather than drawn.
// The profile is the page 9 drawing, and a surface is cut from it by exact arithmetic: the
// four corners are the drawing's own cubics scaled by ONE factor, and the four rails between
// them are extended by moving their end points while their control offsets are kept. Every
// drawn control point is a rigid translation of a measured one, so nothing is stretched and
// the crown of the drawing survives on all four sides.
const PROFILE_END = [
  // start and end of each measured segment, in the drawing's own coordinates
  [461.43, 634.0, 510.57, 634.0],
  [510.57, 634.0, 525.0, 612.17],
  [525.0, 612.17, 525.0, 537.83],
  [525.0, 537.83, 510.57, 516.0],
  [510.57, 516.0, 461.43, 516.0],
  [461.43, 516.0, 447.0, 537.83],
  [447.0, 537.83, 447.0, 612.17],
  [447.0, 612.17, 461.43, 634.0],
];

export function contourPath(width, height, pad = FRAME_PAD, cornerPx = CORNER_PX) {
  if (!shape) return "";
  const inset = Math.min(pad, width / 6, height / 6);
  const boxW = Math.max(2, width - 2 * inset);
  const boxH = Math.max(2, height - 2 * inset);
  const scale = Math.min(cornerPx / CORNER_BAND_Y, boxH / 3 / CORNER_BAND_Y, boxW / 3 / CORNER_BAND_X);
  const right = inset + boxW;
  const bottom = inset + boxH;
  // Each corner is placed by the one factor and a translation that puts the drawing's own
  // box corner on the surface's box corner, so the crown reaches the frame exactly and the
  // rails sit where the drawing puts them. Every loop point belongs to one corner.
  const corners = {
    BL: [inset - shape.left * scale, bottom - shape.bottom * scale],
    BR: [right - shape.right * scale, bottom - shape.bottom * scale],
    TR: [right - shape.right * scale, inset - shape.top * scale],
    TL: [inset - shape.left * scale, inset - shape.top * scale],
  };
  const owner = ["BL", "BR", "BR", "TR", "TR", "TL", "TL", "BL"];
  const loop = [
    [461.43, 634.0], [510.57, 634.0], [525.0, 612.17], [525.0, 537.83],
    [510.57, 516.0], [461.43, 516.0], [447.0, 537.83], [447.0, 612.17],
  ].map((point, index) => {
    const [tx, ty] = corners[owner[index]];
    return [point[0] * scale + tx, point[1] * scale + ty];
  });
  // A frame is stroked on the pixel grid, so every coordinate is snapped to a half pixel:
  // a straight edge then lands on one, and no edge aliases along its length.
  const fmt = (value) => ((Math.round(value * 2) / 2).toFixed(1));
  const xy = (x, y) => `${fmt(x)} ${fmt(y)}`;
  let d = `M ${xy(loop[0][0], loop[0][1])}`;
  for (let i = 0; i < shape.segments.length; i += 1) {
    const seg = shape.segments[i];
    const [sx, sy, ex, ey] = PROFILE_END[i];
    const [dsx, dsy] = loop[i];
    const [dex, dey] = loop[(i + 1) % loop.length];
    // Controls keep their offset from the end they belong to, scaled by the one factor.
    d += ` C ${xy(dsx + (seg[0] - sx) * scale, dsy + (seg[1] - sy) * scale)},`;
    d += ` ${xy(dex + (seg[2] - ex) * scale, dey + (seg[3] - ey) * scale)}, ${xy(dex, dey)}`;
  }
  return `${d} Z`;
}

// contourWindowPath is the window's frame: the same page 9 profile as a button, cut with
// the button's own corner size and extended to the window's size. The crown is scaled by
// the one factor, so a window frame and a taskbar button read as one surface at two sizes.
export function contourWindowPath(width, height, pad = FRAME_PAD) {
  return contourPath(width, height, pad);
}

// contourInk is the inset a drawn string takes inside a surface's own contour. The corner
// band is what the outline claims at the ends, so the ink starts after it.
export function contourInk(width, height) {
  const inset = Math.min(FRAME_PAD, width / 6, height / 6);
  const boxW = Math.max(2, width - 2 * inset);
  const boxH = Math.max(2, height - 2 * inset);
  const scale = Math.min(CORNER_PX / CORNER_BAND_Y, boxH / 3 / CORNER_BAND_Y, boxW / 3 / CORNER_BAND_X);
  return { x: Math.max(3, Math.round(CORNER_BAND_X * scale + 2)), y: 3 };
}

// contourFits reports whether every coordinate the path draws stays inside its own box. A
// crown that runs past the frame is a clipped outline, and a clipped outline is refused
// rather than drawn.
export function contourFits(path, width, height, pad) {
  const numbers = path.match(/-?\d+(\.\d+)?/g) || [];
  const xs = [];
  const ys = [];
  for (let i = 0; i + 1 < numbers.length; i += 2) {
    xs.push(Number(numbers[i]));
    ys.push(Number(numbers[i + 1]));
  }
  const low = pad - 0.75;
  return xs.every((x) => x >= low && x <= width - pad + 0.75)
    && ys.every((y) => y >= low && y <= height - pad + 0.75);
}

// clipToContour gives one element the contour at its own size and the ink that size
// implies, and repeats when the element changes size.
export function clipToContour(element) {
  if (!shape || !element) return;
  seq += 1;
  const apply = () => {
    const rect = element.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;
    // Whole pixels, floored so the frame can never stand proud of the box it sits in: a
    // fractional box puts the one pixel frame on a half pixel and the edge aliases
    // unevenly along its length.
    const w = Math.max(2, Math.floor(rect.width));
    const h = Math.max(2, Math.floor(rect.height));
    // A path clip is written straight onto the element, so the surface carries its
    // own contour at its own size and does not depend on an SVG definition elsewhere.
    // A window frame is cut with the same padding as a button, so the mask that shapes the
    // window and the frame drawn inside it are one and the same outline.
    // A window frame is the profile at the button's own corner size, not a bigger crown.
    const isWindow = element.dataset.contour === "window";
    const d = isWindow ? contourWindowPath(w, h) : contourPath(w, h, FRAME_PAD);
    // The clip is handed to the surface's own paint layer, so the element itself is never
    // clipped and the frame drawn inside it keeps both halves of its stroke.
    const clip = isWindow ? contourWindowPath(w, h, CLIP_PAD) : contourPath(w, h, CLIP_PAD);
    if (!contourFits(clip, w, h, CLIP_PAD)) {
      refuse(element, "contour-crown-outside-frame");
      return;
    }
    element.style.setProperty("--clip", `path('${clip}')`);
    // The frame is the contour itself, stroked, and it is a child of the surface. The
    // surface is no longer clipped, so the stroke is drawn whole at every edge.
    let frame = element.querySelector(":scope > .contour-frame");
    if (!frame) {
      frame = document.createElementNS(SVG_NS, "svg");
      frame.setAttribute("class", "contour-frame");
      frame.setAttribute("aria-hidden", "true");
      const stroke = document.createElementNS(SVG_NS, "path");
      stroke.setAttribute("fill", "none");
      frame.append(stroke);
      element.append(frame);
    }
    frame.setAttribute("width", String(w));
    frame.setAttribute("height", String(h));
    frame.setAttribute("viewBox", `0 0 ${w} ${h}`);
    frame.setAttribute("preserveAspectRatio", "none");
    frame.style.width = `${w}px`;
    frame.style.height = `${h}px`;
    const stroke = frame.firstElementChild;
    stroke.setAttribute("d", d);
    stroke.setAttribute("stroke-width", "1");
    stroke.setAttribute("stroke-linejoin", "round");
    stroke.setAttribute("shape-rendering", "geometricPrecision");
    const ink = contourInk(w, h);
    element.style.setProperty("--ink-x", `${ink.x.toFixed(1)}px`);
    element.style.setProperty("--ink-y", `${ink.y}px`);
  };
  apply();
  new ResizeObserver(apply).observe(element);
}

// fillContours clips every element that asks for it, which is every cell and card.
export function fillContours(root) {
  root.querySelectorAll("[data-contour]").forEach((element) => clipToContour(element));
}

// A painted surface that is not a nine-slice of the contour is refused by name. The
// refusal removes the paint, names the code and is recorded, so a rounded rectangle can
// never stand in for the contour again.
export function refuse(element, code) {
  if (!element || element.dataset.refused === code) return false;
  element.dataset.refused = code;
  element.style.background = "none";
  element.style.border = "0";
  element.style.clipPath = "none";
  element.setAttribute("title", `refused ${code}`);
  fetch("/api/refuse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, surface: String(element.className || element.tagName) }),
  }).catch(() => {});
  return true;
}

export function auditSurfaces(root) {
  let refused = 0;
  root.querySelectorAll("*").forEach((element) => {
    const style = getComputedStyle(element);
    const paints =
      (style.backgroundImage && style.backgroundImage !== "none") ||
      (style.backgroundColor && style.backgroundColor !== "rgba(0, 0, 0, 0)") ||
      (style.borderTopWidth && style.borderTopWidth !== "0px");
    if (!paints) return;
    if (element.hasAttribute("data-contour")) return;
    if (element === document.documentElement || element === document.body) return;
    if (refuse(element, "surface-not-nine-slice")) refused += 1;
  });
  return refused;
}

// windowScale sets the unit a window's layout is drawn at, from its own contour.
export function windowScale(root, width, height) {
  const unit = scaleOf(width, height);
  root.style.setProperty("--u", `${unit.toFixed(3)}px`);
  root.style.setProperty("--ink-x", `${contourInk(width, height).x.toFixed(1)}px`);
}
