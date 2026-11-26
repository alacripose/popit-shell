# Family development policy — the bridge, the drivers, and the ledgers

**Owner instruction, verbatim:** *"from now on all development in the family projects must be done
honestly using the bridge with the debian machine over dialin with their local model, managing the cua
drivers for their side of projects, while the projects here run through the windows client for logging
failures and ledgers properly in the programs"*.

## The split

| side | what runs there | what it is for |
|---|---|---|
| `cua-driver` (the family Debian box; its address is `runlogs/toast/debian-host.txt`, a local fact and not a repository constant) | the family's local model, the CUA drivers, the tools that need Steam/Proton | the work and the judgement: projects and code are managed on that side, not watched through a window here |
| this machine (Windows) | the client programs | running the project, and logging its failures and ledger rows in the programs themselves |

A development pass is not two habits. It is one loop: the bridge carries the project state to the
Debian side, the local model and the drivers do the work there, the result comes back, and the Windows
program writes the row that says what was measured. A row written by hand after the fact is not the
program logging its own failure and is not what this policy asks for.

## The channel and its surface

- The box is reached with `F:\Documents\mc3-client13\tools\bridge.py` (`status`, `run`, `serve`,
  `probe`, `provision`). It reads the host from `POPIT_DEBIAN_HOST` / `POPIT_DEBIAN_USER` or this shell's
  `runlogs/toast/debian-host.txt` / `debian-user.txt`, and uses WSL's Debian distro with the key
  `/root/m0/id_ed25519`. `sh -s` on stdin, never `sh -c` argv: `wsl.exe` joins its arguments into one
  command line and the quoting is lost.
- The reverse direction is `tools/popit_bridge.py` and `bridge.py` here: they spool an act and drive the
  **Windows** CUA fleet from the box (`health`, `cua`, `capture`, `receipt`, `drain`, `spool`). That is the
  toast's fleet, not the Debian driver's wire. The two are named separately because a document that called
  both `tools/bridge.py` sent a session looking for a file that does not exist.
- Dialin is where the bridge is used: `dialin` hosts the `bridge` surface the same way it hosts the
  IDE, and the shell's own bridge pages (`bridge.py`, `mind_bridge.py`, `axis_bridge.py`) speak to the
  same box.
- **Modern Popit apps are HTTPS.** `toast.py` serves the desk's loopback view on `5207`, the LAN view on
  `5209`, and the HTTPS view on `5210` with the certificate `ensure_phone_cert()` generates. The app's
  origin is the HTTPS one: the microphone, the service worker, the phone install and a signed window only
  exist there. A reading of an app over the plain loopback port is a desk convenience, not the app.
- **The CUA drivers own the act.** A family-wide search, a look check of a rendered surface, or a drive
  of a page is a wish or a task to the CUA driver (`POST /v1/wishes`, `POST /v1/tasks`), whose declared
  tools — `fs.search`, `fs.read`, `shell.exec`, `screen.capture`, `window.list`, `test.run` — carry the
  act and whose journal carries the evidence. A local script that reimplements one of those acts beside
  the driver is not a probe; it is a second control path.
- **A weak reading is a refusal.** When a session's understanding of a family project is this thin — a
  port taken for an origin, a driver-owned act designed as a page measurement — the reading is recorded
  as a refusal (`family-understanding-weak`) and handed to the driver, not finished as if it were measured.

## The bridge app package

The bridge is a real package, not a page:

```
app-bridge@1+blake3:a481bdbba69c43b8a90c561ca8487ce64144c048c4fa82a77b79b341ebad4493
```

It is signed by the settings publisher key, verified against `runlogs/toast/envelope-trust.json`,
declares `kind: window` with the four furniture regions (`bar`, `status`, `body`, `foot`), derives
`theme`, `layout`, `motion` and `dpi` from the settings package, and carries **no stylesheet of its
own** — the look, the buttons, the chrome and the motion are the package's (`contour-theme.css`,
`toast.css`, `package.js`). Its springboard tile is signed with it: `ui/phone.js` lists `bridge` in
`APP_SURFACE`, so the launcher shows a tile only while that identity verifies.

## No shell searches — the search probe is the harness

**Owner instruction, verbatim:** *"never use a shell search again the cua machine drivers will handle
it eventually this is a family wide harness requirement"*, with the earlier ruling that a sweep *"does
not stop at the first piece of evidence"* because the ledgers already hold rows for that failure.

- **The rule.** No `rg`, `grep -r`, `find`, a piped `ls`, `xargs` over a file list, or any other shell
  invocation whose purpose is to locate evidence. A session that does not know where something is asks
  the family for it; it does not walk the disk from a command line.
- **Why it is a harness requirement and not a preference.** A shell search proves that a command ran. It
  leaves no receipt naming what was searched, what was excluded and which document answered, so the next
  session repeats the walk and the record cannot say whether the reading was complete or stopped at the
  first hit. The sweeps exist for the same reason: the failure sweep counts 168 rows across 49 codes and
  still refuses to call them adjudicated.
- **The surfaces that replace it.**

| Need | Use |
|---|---|
| ledger failures and their named refusals | `python tools/family_failures.py scan`, then `serve` / `probe` to read the page |
| family-wide documents, counts and provenance | `python tools/family_search.py` in the `openlock_modern` checkout; its receipt names the tool it ran and the roots it visited |
| code and text inside an open project | the editor's own search tools (`code_search`, `glob`, `read_files`) |
| the machine, its files, processes and code | the CUA driver's declared tools — `fs.search`, `fs.read`, `shell.exec`, `screen.capture`, `test.run` (§2.11 of `docs/CUA-DRIVER-DEBIAN-PLAN.md`) |

- **What is owed.** A general evidence-search probe over the roots `family_search.py` and
  `family_failures.py` already enumerate, returning every hit with its path, line and document digest.
  Until it lands, a reading is assembled from those two probes plus the editor's search, and the receipt
  names which one answered. The CUA machine drivers take the query when their `fs.search` is wired to
  these roots.
- **The record.** `logs/authority/2026-11-25-no-shell-searches.jsonl`.

## The failure sweep

`tools/family_failures.py scan` reads every ledger surface in the family projects
(`ledger/*.jsonl`, `logs/*.jsonl`, `logs/authority/*.jsonl`, `runlogs/**/*.jsonl`, `data/*.jsonl`) and
the hypergrilling documents under `Documents\.superpowers\hypergrilling`, and groups the failures by
their named refusal. `serve`/`probe` publish and check the Popit page over loopback.

Measured 2026-11-25: **168 rows · 49 codes · 4 projects**, every row traceable to a file and a line in
`runlogs/family-failures.json` and `docs/family-failures.md`. The largest groups are
`fail:gate` ×51 (deadlock-model-forge), `refused` ×14 and `blocked` ×11 from the hypergrilling docs,
`fail:compile` ×4, `fail:blender` ×3.

**What it does not claim.** Rows are counted, not adjudicated: the sweep says how often a name repeats
and where, not whether each instance was correct. A `fail:gate` row is the project gate refusing a
state, and the reading of whether that refusal was right is the gate's own record.

## Freshness is a driver duty, and a stale row is a refusal

Owner, verbatim: *"landing pages, ci, audits, failures, ledgers, refusals, signed app packages and
their signed tiles are not allowed to go stale across the family, handled by the cua drivers in
their projects."*

- **The register.** `tools/freshness.py` measures eight families — `landing`, `ci`, `audits`,
  `failures`, `ledgers`, `refusals`, `packages`, `tiles` — and every stale row names the driver act
  that clears it. It ships a Popit page (`data-popit="freshness"` on
  `http://127.0.0.1:5213`) and its `probe` reads `/` and `/report.json` over loopback, writing
  `artifacts/receipts/freshness.json`; a printed pass is not a reading.
- **The gate reads the receipt.** `freshness-register-covers-the-family` refuses a register that
  stops covering a family, and `freshness-no-stale-rows` refuses a stale landing, audit, receipt,
  ledger, refusal, package or tile. Those refusals are the work list handed to the drivers, not a
  state an agent may edit away.
- **A re-signed package without a measurement is pending, not fresh.** Hot reload's signing half is
  `POST /api/toast/apps/ensure` (loopback or TLS only): changed files are re-signed by the shell's
  publisher, attributed to the live driver, without a process restart. The re-signed package
  carries `ui_audit: pending` until the driver audits the page (`?uiaudit=1&app=<name>`) and the
  audit republishes it; the register names that act.

## Every app package subscribes to the settings app

Owner, verbatim: *"the new dialin app package would subscribe to the settings app this is
project convention from now on and the app we use must be able to still sign it's packages
properly where we bring in new features/dependencies and development must be driven in the
family byt the cua drivers"*.

- **Subscribed.** A signed script calls `attach("<name>")` from `/package.js`; frame, material,
motion type, motion preference, the ten colour roles, layout and DPI come from the verified
settings document. No script attaches → `app-not-subscribed`, refused before signing.
- **Fully signed.** Every served `.js`/`.css` a page loads must be in the package's `files`.
An undeclared asset → `app-dependency-undeclared`. This is what keeps signing correct as
features and dependencies arrive: `contour.js`, `contour-theme.css`, `phone-calls.js` and
`popit-sw.js` were served but unsigned before the rule and are declared now.
- **Driver-driven development.** Package work in the family is carried by the CUA drivers (the
desk rebuild is wish `task-0003`); the freshness register is the work list and the gate reads
its receipt.

- **Dialin is not hand-rolled.** The desk carried a private settings app (palette table, motion
  keyframes, its own panel). The owner retired that: the desk is rebuilt by the CUA drivers **from
  the signed settings app package** (wish `task-0003`, receipt `/srv/scratch/popit-dialin-rebuild.json`).
  The register carries the rebuild as `dialin-rebuild` so the retirement stays visible, and agent
  edits to the private copies are stopgaps, not the rebuild.

## Family prose is one program, external documents, and a driver that stages it

Owner, verbatim: *"it is not enough for it to be just prose in HTML/JS/TS/Python/JSON/Markdown
\x20extractors, prose was already determined in family to have external visible html documents similar
to rustdoc, so every family project and where prose is included inside code, needs to be sorted out
autologially within the family using a popit shell program with cua drivers handling it all, so I
have spinning loaders and progress per project."*

- **The rules are imported, never copied.** `tools/prose_family.py` loads
  `portal-shell/tools/ui_prose.py` by path. The checker reads Go, JS, HTML, Python, JSON and
  Markdown, and a project passes `--root`/`--tree`/`--doc` to be read by the same bans. A second
  ban list in a project is the failure the rule exists to prevent.
- **The reading is a document a person opens.** Every project gets
  `docs/prose/<project>/index.html` — the rule catalogue, the extractor counts, every drawn string
  with its budget and the rule it broke — and `docs/prose/index.html` links them. The documents live
  in `docs/`, so they publish with the landing page instead of dying in a chat.
- **The surface is the `prose` app package.** `app_package.APPS["prose"]` is kind `window`, entry
  `toast.html`, `?window=prose`, with `attach("prose")` in `toast.js`; the SpringBoard tile opens
  `/toast.html?window=prose`. `#prose-panel` carries the spinner and per-project bar and reads
  `/progress.json`; the probe reads that window through `/api/toast/window/audit` and
  `/api/toast/window/eval` name `prose`. No page beside the client, no bare iframe, no browser
  harness: a window supplied over bare http is a refusal (`window-not-secure`).
- **An icon frame signs only a proven launch.** `launch_proof()` reads the entry page and script from
  the bytes the payload signs and requires the window regions, the named panel and the script's own
  window mode; without it the package is refused `app-tile-unproven-launch` and the tile stays closed.
- **The driver owns the box's side.** The program asks the box what it has staged
  (`ls -1 /srv/ingest/family-prose ; ls -1 /srv/scratch/prose-staging` over `bridge.py run`), and
  stages a missing project by publishing a bundle at `GET /api/toast/prose/stage/<name>.tar.gz` for
  the box to pull. The corpus is written by the driver's own service: a
  `PermissionError` on `/opt/cua-driver/artifacts/corpus/corpus.jsonl` is `corpus-write-permission`,
  a `blocked` freshness row naming that act, not a pass and not this project's staleness.
- **Measured 2026-11-25.** 11 of 11 family projects documented and staged (12 staged on the box).
  The SpringBoard is read in the shell's window over TLS: `secure True`, no brand heading, no lane
  count and shortened identities, and dialin/settings/prose SIGNED with bridge refused
  `app-kind-foreign`. Copy that survives elsewhere is not rewritten: the per-rule counts are the
  sweep's work list.
- **The record.** `data/probes/2026-11-25-family-prose-program.md`,
  `data/probes/2026-11-25-window-surfaces-and-probe-authority.md` and
  `logs/authority/2026-11-25-family-prose-program.jsonl`.

- **Five constructions are refused, not budgeted.** `structure: brand-header` (a drawn `POPIT` or
  `SPRINGBOARD` heading), `structure: live-lanes` (`N live lanes`, `no live lanes`),
  `structure: mic-listening` (`mic listening`, `listening only`), `structure: family-surface`
  (`the family surface`) and `structure: hash-unshortened` (`blake3:` with 13 or more hex) are in the
  checker's `HARD_RULES`: they fail a project by name wherever they are drawn, and no
  `prose-baseline.json` can hold one. A drawn identity is `app@rev+blake3:` with at most twelve hex;
  the full digest stays in the element's `dataset`, not on the foot.
- **The home key is the bar's, on every view.** The SpringBoard draws one home control, in
  `data-region="bar"`; a per-view back key and a second `LIVE` badge are the same redundancy the lane
  bar was. The window still carries bar, status, body and foot (`#secure-pill` is the status).
- **The rule is read by the same checker in every project.** `tools/ui_prose.py` prints in UTF-8 and
  never grades `docs/prose`, so the receipts it writes cannot accuse it of the copy they quote.
