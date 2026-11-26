# The look check and the tile drive, handed to the CUA driver

Date: 2026-11-25. Shell: `F:\Documents\popit-shell`, `python toast.py` (PID 7944), started
18:19 UTC. Probe scripts: `data/probes/2026-11-25-driver-look-wishes.py` (submits) and
`data/probes/2026-11-25-driver-wish-receipts.py` (reads back).

## Why this is a handoff and not a local audit

The owner refused the earlier design twice: CUA is not a measurement helper ("it handles system
level information and kernel level items it handles code"), and a family-wide search is a probe's
job, not a shell search's. The refusal is recorded in
`logs/authority/2026-11-25-https-origin-and-driver-ownership.jsonl`. So the look check was not
built as a new pixel-scoring module beside the driver. It was put to the driver as a read wish
over its own wire, with the codes it must be able to name.

## The shell's real origin

Measured from the shell's own startup log (`runlogs/toast/shell.log`):

| Listener | Address | What it is |
|---|---|---|
| desk (loopback) | `http://127.0.0.1:5207/` | the Qt window's view |
| phone / LAN | `http://<host>:5209/phone.html` | the LAN view |
| phone / HTTPS | `https://<host>:5210/phone.html` | **the app's origin** |
| certificate | `https://<host>:5210/popit-cert.cer` | the shell's own certificate |

The window rendered (`toast-view loaded=True`, bar `344.83 × 29.57` at `7.59, 12.25`, colour
`rgb(244, 205, 135)`; grab `runlogs/toast/view-grab.png`).

## The driver

The box (`/etc/systemd/system/cua-driver.service`, `cua-driver`) runs
`driver_surface.py --serve --policy /etc/agent/policy.json --journal /var/lib/agent/journal/calls.jsonl
--port 8765`; the peer token lives in `/etc/agent/driver.env` and is never printed.
`/opt/cua-driver/tools/` carries the whole stack — `driver_surface.py`, `cua_loop.py`,
`cua_mind.py`, `cua_civilian.py`, `cua_ca.py`, `cua_journal.py`, and `family_search.py` (the
family-wide search probe). Running units include `cua-driver`, `cua-loop`, `cua-peer`,
`cua-observer`, `cua-display`, `cua-vnc`, `ollama`.

## The two wishes and the driver's answers

Submitted through `POST /v1/wishes`; receipt on the box at `/srv/scratch/popit-look-wishes.json`.

| # | intent | request | answer |
|---|---|---|---|
| task-0001 | `read` | audit every signed surface on `https://<host>:5210`; refuse a page that furnishes its own stylesheet, style block, inline paint, control, chrome or motion; name each code | `accepted` · `wish-accepted` |
| task-0002 | `read` | drive the SpringBoard's Bridge tile and the bridge page; capture both with digests and the identity each window names | `accepted` · `wish-accepted` |

`receive_wish` returns `accepted` with a task id and stores the wish as a peer-sourced task. It
does not execute a body tool: a wire peer is never an authority over the driver (§2.12), and a
wish naming a body tool is `declined`.

## The named blocker on task-0002

The toast's side of the transport is up: `TunnelSupervisor` allocated a reverse port and wrote
`runlogs/toast/bridge-target.json` at 18:20:06 UTC (`http://127.0.0.1:36081`, host
`<host>`) — the loopback URL the Debian box uses to reach `POST /api/bridge/cua`, whose
ledger makes one key one act.

The box does **not** carry `tools/popit_bridge.py` (the file's own docstring says it runs from the
Debian box), and the target file's token is a capability that must not be sent through an agent
command line into a log. So the drive is blocked on a secret handoff that only the shell (or the
owner) can place on the box, not on an absent act. **Not attempted:** no browser window was opened
and no click was synthesised from this side; the render of the tile and the bridge page is not
claimed.

## What is still owed

- The look check as a **declared driver tool** (`fs.search`/`fs.read` over the served bytes plus
  `screen.capture` of the window, one `ToolResult` with the `look-*` codes), so the gate consumes a
  driver receipt rather than a page-side resemblance score.
- `popit_bridge.py` and its target on the box, placed without the token entering a log, so
  task-0002 can execute.
