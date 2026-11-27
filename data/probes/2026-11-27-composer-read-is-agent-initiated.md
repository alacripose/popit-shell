# The composer is read by the agent that asks

Owner, verbatim: *"The agent is supposed to own the decision to inspect its own communication
channel. Popit should provide the capability, not perform the action on the agent's behalf."*

## What was measured before the change

`Toast.start()` started a daemon thread, `_loop` called `self.run_probe()` every four seconds,
and `Fleet.probe_freebuff` submitted `probe_chat` to the `cua-chat` driver. The probe captured
the window, cropped history, working area and textbox, and compared PNG digests. It returned
paths and a 24-character digest; it never returned the draft. With Freebuff showing
`Mission stopped`, the desk still reported `textbox probed`.

## What is measured now

- **No timer reads.** `_loop` repairs the archive only. The desk starts at
  `harness.state = unread` (`composer-unread`) and stays there until an agent calls the tool.
  Measured: desk up with the timer running, `/api/toast` reported `unread`.
- **The tool exists and is typed.** `/mcp` `tools/list` returns 14 tools including
  `freebuff.composer.read` (`agent` required, `task` optional).
- **The read returns text.** A call with `{"agent":"Buffy","task":"the composer read unit"}`
  returned `source: uia`, `chars: 34`, `field: Message Freebuff`, and the draft's own text. The
  text is not copied into this document; the receipt in `runlogs/toast/composer-reads.jsonl`
  holds it on the machine. A warm desk answers in under a second; Chromium builds the
  renderer's accessibility tree in about ten seconds after a client asks, and the read waits
  that long before it falls back to the crop (`refusal: composer-field-not-found`).
- **It is read-only.** The same receipt carries `focus_stolen: false`, `had_focus: false`,
  `keys_sent: []`, `submitted: false`. The read path in `cua.py` has no `focus(`, `type_text`
  or `click(` call.
- **The desk reports the reader.** `/api/toast` reported `state: read`, `by: Buffy`, with the
  character count; 41 seconds later it still did, so nothing on a timer overwrote it.
- **A bare capture is not a read.** `POST /api/toast/probe` reported `state: captured`, and the
  next agent call reported `read by Buffy` again.
- **An unnamed reader is refused.** A call with no `agent` returned
  `composer-reader-unnamed: a composer read names the agent that asked for it`.
- **No freshness gate.** `harness_fresh`/`require_harness` and their `harness-unprobed`
  refusal are gone; `ask_mind` answers without one, and the window's age field is reported
  without being turned into a refusal.

## Checks

`python tools/app_store.py` — 6 packages, 1 refused. `python tools/freshness.py report` — 0
stale of 17 rows. `python tools/gate.py` — 88 checks, 1 refusal (`family-prose-ratchet`, the
family-wide prose regression, host-bound on a runner). `tools/toast_probe.py` measures the
contract rows: unread, captured, read, reader named, no freshness gate.
