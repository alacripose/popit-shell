# TICKET-0004 — the desk is witnessed, not described

**State:** open
**Owner:** ala
**Opened:** 2026-11-26

## Requirement

The owner's words, verbatim:

> because you fake probing the window with the cua drivers instead of actually probing the window with
> the cua driver to see the current view in the desk

So: a statement about what the desk shows is made from a CUA capture of the window, read as an image.
A `/api/toast` JSON field, a page that reports its own numbers, or a receipt that says `pass` is not a
witness. When the harness needs to know whether a lane is live, whether a line rang, or whether a
button has text, it captures the window first.

## Acceptance

- `A1` — every claim about the desk's view in a report names a PNG produced by
  `python tools/witness.py --window "Popit toast"` (the shell's `cua.py` driver) at or after the
  moment it describes.
- `A2` — the capture is read as an image, and what it shows is stated: lane rows and their states, the
  owner's lines, the button labels, the persistent-line count.
- `A3` — a claim that contradicts the capture is corrected in the same turn, with the capture named.

## Evidence

| Item | Where | Reading |
|---|---|---|
| First capture this session | `runlogs/toast/popit-toast-20261125-183632-804.png` | `2 PERSISTENT · 2 lines open`, T1 Qwen listening, T2 Buffy listening |
| A later capture | `runlogs/toast/popit-toast-20261125-183904-303.png` | T1 Qwen `queued`, T2 Buffy `thinking · reading your line`, owner live voice "Thank you." |
| The owner's own capture | attached 2026-11-26 | T1 Qwen `queued`, T2 Buffy `thinking · reading your line`, `2 lines · 2 threads` |
| The driver | `cua.py` via `mc3-client13/tools/witness.py` | `WITNESS present driver=cua-2 window='Popit toast' 674x989` |

## What went wrong, recorded

From the first capture I wrote "there is no session behind either line". The lanes were live: Qwen
queued, Buffy thinking. The statement was an inference from `calls.json`, not a reading of the desk.
`A3` is that failure written down: the capture was available and cheaper than the inference.
