# TICKET-0009 — the composer is read by the agent that asks

## Requirement

Owner, verbatim: *"The agent is supposed to own the decision to inspect its own communication
channel. Popit should provide the capability, not perform the action on the agent's behalf."*
The audit that followed named the two defects: `Toast.start()` probed Freebuff every four
seconds from a daemon thread, and the probe only measured image regions, so `textbox probed`
was evidence of a screenshot rather than of anything an agent had read.

## Acceptance

- **A1** — No timer reads the composer. `Toast._loop` repairs the archive and nothing else; a
  bare `/api/toast/probe` capture reports `state: captured`, never `read`.
- **A2** — `/mcp` lists `freebuff.composer.read`, taking `agent` (required) and `task`, and
  refuses `composer-reader-unnamed` when the asker is not named.
- **A3** — The read returns the composer's text, separated from its placeholder, through UI
  Automation (`comtypes`, `cua.py`); when the tree cannot be read it returns the composer
  crop as an MCP image content block and says `source: image`. A path or a digest alone is
  not a reading.
- **A4** — The read is read-only: no focus call, no `type`, no `key`, no click, `submitted`
  false, `keys_sent` empty. The receipt in `runlogs/toast/composer-reads.jsonl` carries the
  agent, task, time, field, text, digest, region and those negatives.
- **A5** — The window reports `read by <agent>` with the character count; the shell no longer
  turns the age of a capture into a refusal, and `ask_mind` answers without one.
- **A6** — `tools/gate.py` carries `composer-read-is-agent-initiated` and `tools/toast_probe.py`
  measures the new contract: unread before any call, captured after a bare probe, read after
  the tool call, and the reader named.

## Evidence

- `python tools/gate.py` — 88 checks, the one family-wide `family-prose-ratchet` refusal.
- `python tools/toast_probe.py` — the contract rows above.
- `logs/authority/2026-11-27-composer-read-is-agent-initiated.jsonl` — the correction row.
