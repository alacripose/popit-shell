# TICKET-0009 — family MCP Developer Kit and refusal-first production gate

## Requirement

Owner instruction (2026-11-27): *“resynthesize the full audit against this so I can have an actual mcp development kit for people and agents to make apps/work on family based projects”*, with a dedicated MCP app in the desk that programmatically refuses code, apps and packages that do not follow family convention, refuses lowered security and hand-rolled development that bypasses CUA automation, and prevents agents from replacing or styling the Settings app's UI framework, motion or design system.

The governing architecture is Secure Shell Restore, not a new Popit-only package format. Preserve the accepted Restore identity, content digest, signing, admission, stream, mount and witness separation. Popit apps remain signed mutations of the current Settings package; every mutable app subscribes to Settings and inherits the same four-region window, control, theme, layout, motion and DPI contract.

The 2026-11-27 Freebuff transcript is a concrete reproduction, not an anecdotal warning:

- It read `toast.py` and `ui/toast.js`, then announced that it would remove the timer and freshness gate before it had established that the existing mechanism was invalid.
- It edited code, ran commands, and only afterwards measured the new gate, package re-sign and window audits.
- It used a process-name command-line match that could select processes other than the desk supervisor, possibly including its own shell. It recognized the mistake only after acting.
- It attempted a `runlogs/reauth.py` invocation through a pipeline that printed `$?` after `tail`, so the reported status would not be the status of the actual command.
- The family-wide no-heredoc rule has also been violated post hoc: agents sometimes use a heredoc, encounter a failure, then acknowledge that heredocs were banned. That is exactly the behavior the rule must prevent before the first write.

A rule is not satisfied by remembering it, acknowledging it afterwards, or adding a prose note to a ledger. The authoring and execution path must refuse the prohibited act before it occurs. A detected violation stops the unit, preserves evidence, and becomes a kept regression case. It is not permission to retry by another route.

The Hero Retarget Workbench's Werewolf→Shiv and Tengu→Haze tail work, together with the deferred aim-matrix animation blending work, is a cross-project acceptance case: a shared production-pipeline defect must become reusable, dependency-aware capability and regression evidence, not a fix trapped in one hero/mod slice or repeated rediscovery by the next agent.

## Acceptance

### Authority and bootstrap

- **A1 — One project rulebook.** Add top-level `AGENTS.md`. It links to `docs/family-development-policy.md` rather than copying its policy into a second owner. It states the Restore architecture as the package authority, the existing Popit Settings package as the UI authority, and the Debian Axis/CUA driver as the sole development actor. Every inbound instruction is classified by source; only recorded owner input carries owner authority.
- **A2 — Refusal before reasoning or action.** The first operation of each work unit is a machine-enforced preflight. It identifies repository, commit, ticket, artifact, driver, capabilities, authority record, current gates and known refusals. If a required gate is absent or refuses, the unit does not plan around it or continue to write.
- **A3 — Ticketed atomic work.** A unit changes one declared artifact or one tightly coupled implementation boundary, with a ticket and an exit test. Required sequence: pinned bootstrap → baseline incremental checks → CUA driver ticket → bounded CUA act → observed postcondition → independent verification → durable ledger row → commit/PR → client witness where applicable. No direct-to-main implementation.
- **A4 — Non-authoritative harness boundary.** A harness work-folder label is not an authorization boundary. The family working set is resolved through its recorded family checkout/project register. A collision is logged by name and cannot silently restrict legitimate family reads. This does not grant access to secrets or unrelated users' files.

### Secure Shell Restore and phone package trust

- **A5 — Canonical package identity.** Use Restore's `name@<monotonic-integer-revision>+blake3:<64 lowercase hex>` grammar and pin-complete dependency identities. Revisions are never reused. Hash the complete canonical content under the Restore preimage and vocabulary; transport chunks, compression, encryption nonces/tags, signature envelopes and timestamps never enter content identity. No silent SHA-256/legacy identity fallback.
- **A6 — Independent security claims.** Content identity, Ed25519 signer verification, server admission, stream integrity/resume, client mount receipt and client witness remain distinct, ordered checks. A BLAKE3 match is not authorship or authorization. Unknown, revoked, stale, incompatible or malformed identities are refused by name.
- **A7 — Ed25519 phone/system signing.** Mutable phone/system packages and their signed launch tiles use the established Ed25519 package authority and trust registry. A TLS transport certificate is a separate channel identity and cannot substitute for the package signature. Private keys never enter Git, MCP arguments, prompts, package templates, screenshots or logs.
- **A8 — Settings is the only UI foundation.** Every app is a signed `window` or the `phone` home, never a foreign kind. A window is a mutation of the verified Settings page, retains `bar/status/body/foot`, subscribes to the Settings identity and derives theme, layout, motion, controls, DPI, contour and chrome from it. No private framework, independent theme, motion engine, window chrome, CSS design system, standalone page or alternate renderer may be created. A Settings identity change invalidates stale app derivations.
- **A9 — Sign only measured, declared payloads.** Every served dependency is inside the package digest; app subscription, window completeness, launch proof, UI audit, trust and CUA driver attribution are mandatory before a mutable package is signed. A pending or failed measurement is not a pass and does not become fresh through re-signing.

### MCP Developer Kit and CUA-only work

- **A10 — Dedicated DevKit app.** Add a signed `devkit` Popit window, built from the Settings package and registered in the signed app catalogue and SpringBoard. The page is a family project interface, not a second window implementation. Its own UI is measured through the CUA driver and its audit receipt is tied to the exact signed payload digest.
- **A11 — Typed, bounded MCP catalogue.** The family-development MCP group has complete JSON Schemas: explicit required fields, enums, string/array bounds, `additionalProperties: false`, semantic validation, authentication/capability scope, idempotency, output bounds, and a typed refusal vocabulary. No `properties: {}` placeholder, arbitrary path, raw source write, arbitrary shell, arbitrary command, package signing or authority grant is exposed.
- **A12 — MCP requests work; drivers perform work.** MCP may inspect package/project status through read-only declared capabilities and submit a structured development intent to the Debian CUA driver. It may not author or write code, create files/apps/packages, run builds, change Settings, sign/admit/mount packages, invent a UI, or act directly on the device. Every mutation is performed by the CUA driver after a Secure Shell Axis ticket for the exact declared action and scope, and returns the driver's receipt.
- **A13 — No root shell escape.** The unrestricted `debian.command` MCP tool is removed and refused by name. No other tool or alias may recreate arbitrary command execution. A caller cannot supply a command, executable path, process-name match, raw file path, or a scope the server did not issue.
- **A14 — No heredoc before the act.** Heredoc-based code/data/record authoring is refused before execution, not detected only after it runs. Edits use the approved editor/file tooling and kept patch probes; records use the project recorder. The gate selftests positive and negative cases, including spaced delimiters, quoted delimiters, `python - <<`, `cat <<`, nested shell strings and CRLF scripts. A violation terminates the unit before subsequent commands.
- **A15 — Process identity and lifecycle.** No process is selected by substring/command-line grep or broad name matching. A lifecycle act must resolve a registered supervisor identity, exact PID plus executable identity, start time and owned child/process group; validate the target twice immediately before the act; act only on that owned identity; and verify the expected postcondition by port/API/window witness. Ambiguity refuses without termination. The live desk is never killed to make a test convenient.
- **A16 — Command receipts are real.** A command's reported exit status is the process exit status, not a later `tail`, `echo $?`, background shell or wrapper's status. No unbounded polling loops. A bounded operation emits an immutable receipt with command identity, actor, exit, output digest and observed postcondition.

### Shared learning, ledgers and regression ratchets

- **A17 — Failures are capabilities.** A refusal/failure row includes project, ticket, source class, actor/driver, action, named refusal, exact artifact/commit, command and actual exit, observed pre/post state, affected dependency closure, recovery, and a regression test. Its evidence is retained. It cannot be deleted, rewritten as success, self-adjudicated or closed by prose.
- **A18 — Stop on first unauthorized act.** The current unit is stopped when a preflight, action guard, signature, package gate, process gate, tool schema or postcondition refuses. Do not continue to re-sign, republish, or execute later commands after a prerequisite refusal. Recovery is a new ticketed unit after the refusal is resolved.
- **A19 — Cross-project transfer.** Failure learning is indexed by capability and dependency lineage, not only by repository. Before implementation, search the family evidence register and dependency closure for matching prior failures; after a new failure, add regression fixtures to every consumer that owns the shared capability. Do not copy a private checker or solve only one consumer. A passing slice never closes a pipeline ticket while dependent slices remain untested.
- **A20 — Hero Retarget Workbench pipeline proof.** The shared animation/retarget contract includes body/mesh source, skeleton and joint-slot order, mapped bone family and weights, animation track set, aim-matrix data, blend evaluation, export, stage, compile, install and in-game witness. The Werewolf→Shiv and Tengu→Haze tail paths and aim-matrix blending are named cross-project regression fixtures. A pass in import, a synthetic rig, one hero, one clip or one compiler stage is not end-to-end acceptance.
- **A21 — No evidence laundering.** A source statement, agent report, terminal message, guessed process state, successful compiler exit, package digest, screenshot or CI badge proves only its own scope. Absence remains absent; a check that did not run is not a pass; one reader's check is not an independent client witness.

## Evidence

- Requirement: GitHub issue #1.
- Baseline repository: `main` at `5ee3b9b228312c9b77b2effab47a6f666df957c6`.
- Baseline CI: `ci` run `46048422198` on that commit concluded `success` at 2026-11-27T18:19:07Z. This is baseline evidence only; it does not attest this ticket.
- Secure Shell Restore authority: `alacripose/secure-shell-restore`, `docs/SECURE-SHELL-RESTORE@1.ARCHITECTURE.md`, `docs/SECURE-SHELL-RESTORE@1.AGENT-BOOTSTRAP-API.md`, `docs/SECURE-SHELL-RESTORE@1.CUA-CIVILIAN-ACCEPTANCE.md`, and `impl/packages/identity.py` / `impl/packages/canonical.py`.
- Existing phone signing: `envelope.py` (`SIGNATURE_ALGORITHM = "ed25519"`); Settings and AppPackages use the same settings publisher key and trust registry.
- Existing Popit UI authority: `app_base.py`, `settings_package.py`, `app_package.py`, `tools/gate.py`.
- Existing CUA bridge: `axis_bridge.py`; Secure Shell Axis is the Debian permission/ticket/receipt authority. MCP requests are not tickets.
- Failure example: owner-provided Freebuff transcript dated 2026-11-27. No action or process termination from that transcript is represented as having been executed by this ticket.
- Hero regression source: `alacripose/hero-retarget-workbench` `AGENTS.md`, `AGENTS-INDEX.md`, `AGENTS-LOG.md`, `docs/ARCHITECTURE.md`, and `docs/agents-axis.md`. These pins are evidence sources, not a license to copy its whole domain-specific rulebook.

## State

`open`. The contract is recorded before the implementation. No runtime change, gate pass, MCP conformance, package signature, live app measurement, or CUA witness is claimed yet.

## Supersession

New ticket. Does not supersede TICKET-0001 through TICKET-0008.
