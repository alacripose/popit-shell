# Popit shell

A Windows desktop shell whose taskbar and windows are framed by one measured contour.
Python 3.13, PySide6 QtWebEngine for the host, and an HTML/CSS/JS view served over
loopback on `127.0.0.1:5199`.

This repository is also the pinned **family look**: the visual example every family
application is measured against. The look is written down in
[`docs/family-look.md`](docs/family-look.md) and pinned in
[`tools/family_look.json`](tools/family_look.json).

![The launcher above the strip](docs/hero.png)

## Run

```
pip install -r requirements.txt
python shell.py                  # the bar that owns the strip, plus its launcher
python server.py                 # only the view, on http://127.0.0.1:5199/
python window.py                 # only the launcher window, masked to the contour
python toast.py                  # the pinned agent toast, on http://127.0.0.1:5207/
python tools/toast_probe.py      # the toast's capture, CUA, voice and microphone receipt
```

`POPIT_PORT` moves the port; `window.py <port>` follows it.

The same process also serves the toast to a phone on the same network. The secure surface
is `https://<Ethernet IPv4>:5210/phone.html`; its certificate is at
`https://<Ethernet IPv4>:5210/popit-cert.cer`, and the exact address is printed at launch.
The old `/popit-cert.pem` URL remains an alias for the same DER certificate.
Plain `http://<Ethernet IPv4>:5209/phone.html` remains a read-only view. It ships
`/manifest.webmanifest` and `/popit-sw.js`, so a phone can Add to Home Screen. The
The Springboard's tiles are the live lanes and its own voice surface; the separate
`/civilians.html` life desk is retired. If the LAN listener cannot bind, start with
`--lan-bind <address>`; `--no-lan` keeps the toast loopback-only.

Accepting the local certificate is described in [`docs/phone-commons.md`](docs/phone-commons.md).
The separate contact-book and MCP desk is published at
`https://alacripose.github.io/popit-call/`; its companion and signed caller flow are in
[`call-client/README.md`](call-client/README.md).

Starting `shell.py` hides Explorer's own bar, reserves the bottom 48 px as an AppBar, and
keeps both true while it runs. `Start`, then `Close the shell`, releases the strip and
shows Explorer's bar again. Drag the launcher by its header to move it.

`Session archive` opens its own contoured window from the launcher's tool rows or a right
click on the strip. It scans every local fixed or removable drive, not a hand-picked list
of roots: projects are found at any depth by their markers, every non-project top-level
folder and user-profile folder gets a row, and direct files at each drive or profile root
get a loose-files row. The rows exclude one another, so the index covers every file
outside the named OS, package, build, VCS and cache directories without counting a
project twice. It compares those files with the evidence copy under
`F:\Documents\_evidence-archive`. Source and record files are copied; a large asset is
recorded by size and time when the evidence drive cannot take a full copy. The window
names the family cache rule and removes only `__pycache__`, `.pytest_cache`,
`.mypy_cache` and `.ruff_cache`, after a second confirmation. The index is built in the
background and cached under `runlogs/` for an hour; `Rescan` forces a fresh walk. The
footer names the drives that were scanned and how many directories were inspected.

A right click belongs to the cell under it: a running window offers Activate, Minimize and
Close, a pinned shortcut opens its target or its folder, and the strip itself offers Task
view, Show desktop and closing the shell. Each tray control opens its own view; the chevron
is the one that shows them all.

Every pinned shortcut and running window carries its program's own picture: `/api/icon`
reads the icon the executable (or its shortcut) declares, encodes it once as a PNG and
streams it into the cell, so the contour holds the same mark Explorer would draw instead
of a name spelled in the strip. The cells re-render as windows open, activate, minimize or
close, and the picture lifts with the cell on hover.

Running-window buttons paginate. The strip shows one page of slots at a time; the badge
between the pages and the notification area names the page, a wheel over the page row (or
a click on the badge) turns it, and the last page is where new windows arrive. A window
keeps the slot it was given until it closes: activating or minimizing never reorders the
buttons, a closed window leaves its slot as an open hole, and a new window takes the last
open slot on the last page, starting a new page only when that page has no hole left. A
page holds however many 132 px slots fit the window row at the current width.

## What is here

| Path | What it is |
|---|---|
| `contour.json` | The measured contour: one start point and eight cubics, in the PDF's own units |
| `server.py` | Loopback server: `/api/state`, `/api/open`, `/api/move`, the UI files |
| `window.py` | Frameless Qt host, masked to the contour at its own size |
| `shell.py` | The process that owns the strip: bar window, launcher window, in-process server |
| `desktop.py` | The Windows calls: the AppBar reservation, Explorer's bar, the window list and their icons |
| `archive.py` | The archive window's files: project index, evidence copies, family cache rule |
| `ui/` | The launcher view: plate, Find row, application column, facts column, brass scrollbars |
| `ui/bar.*` | The bar: start, find, task view, pinned cells, paged running cells, tray, clock, show desktop |
| `ui/archive.*` | The session archive: projects, files, evidence state, backup and clean controls |
| `ui/tray.*` | The tray's views: volume, network, battery and date, one per control, plus quick settings |
| `ui/contour.js` | The only shape authority: `contourPath` and `contourWindowPath` |
| `toast.py` | The pinned agent toast: live Freebuff capture, delegated CUA drivers, voice queue |
| `cua.py` | The Windows CUA drivers: window capture, focus, pointer, keys, text and task receipts |
| `voice.py` | Per-driver generated voices, the civilian queue gate, and the default-microphone listener |
| `voice_profiles.json` | Pinned driver and individual profiles: drivers, Buffy, Qwen, Ash, Bram, and the civilian address |
| `civilian_features.py` | Feeling-wheel identity, typed decisions, contracts and the C9 life adapter |
| `civilian_scope.py` | All 46 life/contract/call requirements, with evidence, blocker and research fields |
| `envelope.py` | Ed25519 signed caller packages, the trust registry and single-use nonces |
| `call-client/` | Standalone contact book, MCP surface desk and the GitHub Pages landing page |
| `docs/civilians.md` | The 17-feature family register, 46-row scope, call grounding, limits and reproduction |
| `docs/civilians-contracts.md` | The full contract schema, narrowing rule and runtime blockers |
| `tools/toast_probe.py` | The toast receipt, including distinct waveforms, addressing, and the live microphone |
| `tools/civilian_audit.py` | The family civilian inventory, indexed report and Popit probe |
| `tools/gate.py` | 25 checks and a selftest: the contour, the pins, the toast frame and the refusals |

## The agent toast and voices

The toast is a pinned Qt window in the family contour. Its probe is a delegated task on the
`cua-chat` driver: the driver captures the Freebuff window with `PrintWindow`, writes a PNG
artifact, and the toast serves that reading over loopback. `cua-2` through `cua-4` accept
delegated capture, focus, pointer, key and text tasks; every task has a receipt, and an
undeclared action is refused by name.

The Debian CUA host at the private address printed by the secure-shell restore is reached through WSL. It
is headless by measurement (`aplay`, `arecord` and an audio device are absent), so the voice
is generated on the Windows client. `voice_profiles.json` pins driver profiles plus one
individual profile per callable resident (Buffy, Qwen, Ash, Bram) and the slower civilian
address. Each profile carries its own base voice, rate and pitch; the probe synthesises one
sentence through three profiles and requires three different waveform digests.

The `civilian` profile is the queue gate: one sentence per breath, a 2.2-second floor between
lines, and a slower rate. The other profiles have shorter floors. Lines are written as WAV
artifacts and one receipt row is appended per line, naming the engine, the profile and the
digest.

The microphone is the Windows default capture device, read by `tools/mic_listen.ps1` through
the installed System.Speech dictation recognizer. While a line is playing, the listener ignores
its own output; heard phrases above the confidence floor appear under **Heard**. A microphone
or recognizer failure is a named `refused` state, not a silent empty field.

## The call bridge harness

`Buffy` is not limited to the local Qwen lane. A general coding agent can attach to an open
Buffy call, hear owner speech and sibling-agent lines, and speak in the same document and
voice without taking the desktop or the voice queue directly:

```
curl -X POST http://127.0.0.1:5207/api/toast/call/join \
  -H "Content-Type: application/json" -d '{"agent":"Buffy","profile":"buffy"}'
curl -X POST http://127.0.0.1:5207/api/toast/call/turns \
  -H "Content-Type: application/json" \
  -d '{"session":"callbridge-…","since":1234,"wait":20}'
curl -X POST http://127.0.0.1:5207/api/toast/call/say \
  -H "Content-Type: application/json" \
  -d '{"session":"callbridge-…","text":"I am here in the call."}'
```

While the harness session is attached, the local Buffy lane yields so two minds cannot
answer under one name. `call.leave` hands the lane back. The same operations are exposed as
MCP tools by `/mcp`; `tools/buffy_call_mcp.py` is a stdio proxy for an MCP client, with
`call.join`, `call.turns`, `call.say` and `call.leave`.

## The shape rule

The contour is the framing authority. It is a nine-slice of one profile: four corners
scaled by a single factor and rails that lengthen, so nothing is stretched on one axis and
no crown leaves its box. One corner, 7.67 by 11.00 px, is used by a bar cell, a card, a
field, the plate and a window frame alike.

The body paints through a path clip at 0.5 px and the frame is the same contour stroked at
1 px from 1.5 px, so the stroke is always whole. A window's mask sits at the window box and
never cuts the outline.

## Check

```
python tools/gate.py            # refusals are named, not argued with
python tools/gate.py --selftest # the gate rejects a planted break
```

The gate refuses a contour that stretches, a crown outside its frame, a window frame that
scales its corner to the window, a mask that cuts the stroke, and any change to the pinned
taskbar `tools/bar_pin.json`. `tools/family_look.json` is the family pin, and the gate
refuses a pin that no longer matches what the surfaces draw.

## Releases

CI runs the gate on every push and packages `dist/popit-shell.zip`. A `v*` tag runs the
same gate and attaches that archive to the release.

## The family client shell

`popit-shell` is the family's client shell for forward porting. A project that moves into it keeps
one contour: `ui/contour.js` is the shape authority and `window.py` mirrors it for the Qt mask, so a
taskbar button, a window frame and a landing-page card share the same crown and the same clip pads.

Its landing page is not written by hand. `tools/landing.py` reads the Debian machine's axis routes
(`/api/axis/system`, `/api/axis/civilians`, `/api/axis/stars`) for what the family says about itself,
reads `tools/family_look.json`, `contour.json`, the gate's check names and `requirements.txt` for what
this repository holds, and writes `docs/index.html` from both. The reading is sealed in
`docs/landing-copy.json`, and the family prose tools refuse a sentence over budget or off register.
The gate's `landing-generated` check refuses a page that no longer matches its copy.

```
python tools/landing.py          # on the machine, or with FAMILY_AXIS pointing at it
python tools/landing.py --check  # offline check of the page against its saved copy
```
