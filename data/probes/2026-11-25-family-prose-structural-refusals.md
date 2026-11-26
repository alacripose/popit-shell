# Structural prose refusals — no brand headers, no live-lanes bar, no family-surface footer, no full digests

Date: 2026-11-25. Project: `F:\Documents\popit-shell`. Checker: `F:\Documents\portal-shell\tools\ui_prose.py`.

Owner instruction, verbatim:

> family prose rules, no brand headers anymore, the popit and springboard text is not supposed to be
> here, the springboard home button it supposed to be in the top bar on all views, the redundant live
> and "2 live lanes - mic listening text", the 2 llive lanes bar is to be outright refused in its
> construction for anything, it still says "the family surface" and displays non-shortened blake3
> hashes, this is not to be only done on this one surface these are family rules through the prose tool

## Rules added to the checker (family-wide, one list)

| Rule | Pattern | Why it is a refusal |
|---|---|---|
| `structure: brand-header` | a drawn string that is exactly `POPIT` or `SPRINGBOARD` (capitals) | the surface does not name itself; a lowercase `popit` is a frame value and stays |
| `structure: live-lanes` | `N live lane(s)`, `live lanes`, `no live lanes` | the lane-count bar is refused in its construction, not restyled |
| `structure: mic-listening` | `mic listening`, `listening only` | the microphone state sentence is the redundant half of that bar |
| `structure: family-surface` | `the family surface`, `family surface` | invented footer copy |
| `structure: hash-unshortened` | `blake3:` followed by 13 or more hex characters | a drawn identity is `app@rev+blake3:` and at most 12 hex; a full digest is cut |

These five live in `HARD_RULES`, which fails a project by name (`prose-refused: <rule> <file>:<line>`)
whatever its `prose-baseline.json` says: a ratchet can hold unfinished copy, it cannot license one of
these shapes. The refusal is applied to drawn surfaces (`.html .htm .js .mjs .cjs .jsx .ts .tsx .css
.svg .vue .svelte`); a data file's own digest and a document describing the old bar are counted, not
refused.

Two checker defects were fixed to make the rules read the drawing at all:

- `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` in `main()`: a Windows console could
  not encode the family's glyphs and the checker died on the first hit it found.
- `docs/prose` is skipped in `sources()`: the prose pass writes its own receipts there and the checker
  was grading the copy those receipts quote.

## Markup and script changes

| Surface | Before | After |
|---|---|---|
| `ui/phone.html` | brand block `POPIT` / `SPRINGBOARD`, `live-pill LIVE`, a `← HOME` key per view, footer `THE FAMILY SURFACE · HH:MM` | brand block, live pill and per-view keys deleted; `#home-key` is the only home, in `data-region="bar"` on every view; the foot is the clock; `#secure-pill` carries `data-region="status"` so the window still has bar/status/body/foot |
| `ui/phone.js` | `` `${count} live lane${…} · commons ${…}` ``, `` `${activeLanes().length} live lanes · mic ${mic}` ``, `The room is listening.`, a 30-second `Listening.` sentence | the status lines are gone; the archive-refused fallback writes the secure pill; empty and voice states are one word |
| `ui/toast.html` | `<h1>Popit</h1>`, `planet-core <span>Popit</span>`, a frame value baked as `popit`, `Popit shell · docs/family-look.md` note, `aria-label="SpringBoard"`, `<span id="voice-state">listening</span>` | the heading and planet name are deleted, values start empty and are filled from the package, the note and the label are gone |
| `ui/toast.js` | `Commons addresses every live lane automatically`, `answers unaddressed turns` / `listening only` chips, `no live lanes` | `Commons: every lane`, `lane.name · lane.channel`, `no lanes` |
| `ui/package.js` | `node.textContent = doc.identity` — the whole digest | `shortIdentity()`: `app@rev+blake3:` keeps eight hex, the full identity stays in `dataset.identity` |

## Measured

- Checker, popit-shell (`--root . --tree ui`): 987 drawn strings in 38 files, extractors
  `{'css': 9, 'html': 10, 'js': 16, 'json': 2}`; 0 hits of the five new rules on drawn surfaces.
- Family (`tools/ui_prose.py --family` and `tools/prose_family.py family`): 11 of 11 projects,
  0 regressed, 0 `prose-refused`; receipt `artifacts/receipts/prose-ratchet.json`.
- Gate: 80 checks, 0 refusals, including `every-window-carries-the-family-regions` and
  `family-prose-ratchet`.
- Window, over TLS through `/api/toast/window/eval`: desk `paint` → `family / material / paper / fold
  match True ready`; home frame text reads `SECURE VOICE SIGNED · DialIn app-dialin@138 · 15a22a …` —
  no brand heading, no lane count, no mic sentence, identities shortened.

## What is not claimed

The copy that remains in the shell's own docs (`README.md`, `docs/phone-commons.md`) still describes
the old live-lanes bar and the family surface. Those lines are documentation, so the refusal does not
fire on them; they are counted in the per-rule budgets and are the sweep's work list, not a pass.
