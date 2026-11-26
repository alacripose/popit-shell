# The family prose program — inventory, external documents, driver staging

Date: 2026-11-25. Project: `F:\Documents\popit-shell`. Owner instruction, verbatim:

> it is not enough for it to be just prose in "r: HTML/JS/TS/Python/JSON/Markdown extractors, " prose
> was already determined in family to have external visible html documents similar to rustdoc, so every
> family project and where prose is included inside code, needs to be sorted out autologially within the
> family using a popit shell program with cua drivers handling it all, so I have spinning loaders and
> progress per project. That's why i mentioned a whole quesioning round?

## What was built

| Piece | Where | What it does |
|---|---|---|
| one rule set | `~/Documents/portal-shell/tools/ui_prose.py` | the family checker, extended: `go` lexer, `js` (`'…'`, `"…"`, `` `…` ``), `html` (text nodes outside `script`/`style`, plus copy attributes), `py` (`ast`, docstrings excluded, copy named by `LABEL`/`title=`), `json` (values, keys and ids excluded), `md` prose lines; `--root`, `--tree`, `--doc`, `--floor`, `--extended`, `--family` |
| family program | `tools/prose_family.py` | imports that checker by path (no copied ban list), reads all 11 family projects, renders `docs/prose/<project>/index.html`, asks the box what it has staged, stages what it does not, runs the box's corpus ingest |
| the surface | `tools/prose_ui/index.html` | one row per project: spinner while queued or running, a bar for the phase, extractor counts, drawn strings, hits, the driver's state and the document link; polls `/progress.json` |
| staging route | `toast.py` `GET /api/toast/prose/stage/<name>.tar.gz` and `.json` | the bundle and the ingest profile, served on the shell's own origin so the box pulls from the shell rather than from a second server |
| freshness | `tools/freshness.py` family `prose` | a document older than the checker is stale; a project the box has not staged is stale and names the stage act; a refused corpus write is `blocked` and names the root act |
| gate | `tools/gate.py` | four legs: the program imports the family rules; every family project has a document; the driver's staging is asked, not assumed; the surface ships spinner, progress and a probe |

## What the box said

- `bridge.py status` → `cua-driver`, Linux 6.12, 8 cores, the driver's own `/srv/ingest/family-prose`
  already holding four projects (`agent_god_files`, `brass-meridian`, `deadlock-model-forge`,
  `popit-shell`), and `/opt/cua-driver/tools/cua_family_prose_profile.json` and
  `cua_ingest_profile.py`.
- Staging the other eight (portal-shell, mc3-client13, db-mc-indev, ala-system, alacripose-landing,
  AWA3D, income-engine, laya-cua-agent) into `/srv/scratch/prose-staging` succeeded: the box now lists
  **12 staged projects**, and `/srv/scratch/prose-staging/portal-shell/AGENTS.md` is one of the files.
- `/srv/ingest/family-prose` itself is root-owned; `mkdir` there is `Permission denied`. `/etc/agent`
  is root-only too, so a wish needs a root-side handoff.
- The corpus write is the driver's own: `cua_ingest_profile.py --profile …` reads the profile
  (`profile-schema-read cua.corpus.ingest-profile/2`) and then refuses on
  `PermissionError: '/opt/cua-driver/artifacts/corpus/corpus.jsonl'`. That is recorded as
  `corpus-write-permission` and the freshness row is `blocked`, with the act named.

## Failures found on the way, and their cause

1. **A stale root guess.** `HOME/Documents` is not the family root here; the projects are on
   `F:\Documents` and two (`deadlock-model-forge`, `db-mc-indev`) on the home drive. The roster now
   resolves each project from whichever root carries it, and `project-absent` is named when neither does.
2. **A toolchain counted as prose.** portal-shell's `.toolchain/go/src/...` was read and one file was
   `Permission denied`. The checker now skips `.toolchain`, `site-packages`, `.cargo`, `.rustup` and
   friends, and `sources()` skips a file it cannot open instead of failing the pass.
3. **A pass that never finished.** The first inventory read every file whole and then read them again
   to render. A pass over the family took more than ten minutes. Now the read is capped at 512 KB per
   file with binary skipped, the strings are collected once, and the whole family takes about 45 s.
4. **The profile fetched as a tar.** The staging URL template ends in `.tar.gz`, so the profile was
   requested as `prose-profile.tar.gz` and the shell answered `prose-stage-absent`. The profile has its
   own URL now.
5. **The box's output read as a pass.** `bridge.py` exits 0 when the remote command ran; its rows carry
   what the command said. `run_on_box` returns those words now, and ingest classifies them, so a
   `PermissionError` cannot be read as `ok`.
6. **A cp1252 crash in the bridge** when a binary body was printed. Not fixed here (it is
   `mc3-client13/tools/bridge.py`); the probe avoids printing binary.

## Measured

- `python tools/prose_family.py run` → **11 of 11 projects documented**, every one `driver=staged`,
  `docs/prose/index.html` 5 318 bytes, per-project documents 17 KB to 351 KB.
- `python tools/prose_family.py probe --port 5221` → **10 passed, 0 failed**; the first
  `/progress.json` read shows 11 rows queued, the page carries the spinner and the bar, the driver
  answer is `read: 12 project(s) staged`, and every document is served and on disk with
  `data-doc="prose"` and its project name.
- `python tools/freshness.py report` → **0 stale of 14 rows**.
- `python tools/gate.py` → **69 checks, 0 refusals**.
- `python ~/Documents/portal-shell/tools/ui_prose.py --selftest` → **24 checks**; its own `--check` →
  **0 hits, 211 drawn strings in 34 files**.
- `python ~/Documents/portal-shell/tools/ui_prose.py --family` → portal-shell `passed`; the rest are
  read and counted (popit-shell 363 hits, brass-meridian 330, ala-system 818, income-engine 114,
  AWA3D 134 at the time of that pass). Those counts are the copy-sweep work list, not a green.

## What this does not claim

The copy itself has not been rewritten: the documents show every drawn string and the rule it breaks,
and the hits are the next unit's work. The corpus does not contain the eight newly staged projects yet,
because writing it is the driver's service. No browser was opened; every reading above comes from the
program's own page over loopback or from the box's own words over the bridge.
