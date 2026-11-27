# Popit Shell — family development authority

This file is the working convention for `popit-shell`. It is not a second package specification and does not replace the family policy, Secure Shell Restore contracts, or the user's recorded decisions.

## 0. Authority and precedence

The project has four distinct owners. Do not merge them:

| Concern | Owner | Popit relationship |
|---|---|---|
| Package identity, canonical content, revisioning, dependency pins, admission, stream, mount and restore semantics | Secure Shell Restore | Normative package/trust architecture. Read `SECURE-SHELL-RESTORE@1.ARCHITECTURE.md` and its implementation plan. |
| Debian Axis, driver registration/attestation, tickets, capability checks and action receipts | Secure Shell / Debian Axis | Development authority and CUA dispatch. Popit is a client, not a replacement Axis. |
| Windows desktop and OTA phone clients, Settings subscriptions, app package signing and app-store projection | Popit Shell | The current modern client/application implementation of Secure Shell and Restore. Do not create a second app store, signer, package reader or UI framework. |
| Family conventions and cross-project capability evidence | Family project register and each project's `AGENTS.md`, failures, refusals, probes and ledgers | Read before work; reuse the owning capability and preserve its evidence. |

**Popit Shell is not a competing package architecture.** Its `dialin.py` canonical package functions, `settings_package.py`, `app_base.py`, `app_package.py`, signed app registry and phone client are the modern Popit implementation of the client/application side. Changes must preserve that lineage and explicitly map any Restore contract difference. Never import the older Restore implementation as a second writer or silently change Popit's digest domain.

The Windows Settings package and its Ed25519 publisher/trust registry are the current Popit UI/package authority. The Debian Axis remains the authorization authority for CUA development acts. A content digest is not a signature; a signature is not an admission verdict; an admission is not a mount receipt; a mount receipt is not a client witness.

Platform safety and legal constraints still apply. A project convention cannot override them.

## 1. Mandatory bootstrap — before planning or editing

1. Resolve the exact repository, worktree, branch and commit. Record the current commit and the relevant Restore, Axis and family project pins.
2. Read this file, `docs/family-development-policy.md`, the relevant ticket, the relevant Restore architecture/implementation documents, and the owning source files. Read the actual files; a search excerpt or previous chat summary is not a substitute.
3. Read the family failure/refusal register and matching project probes. Search by capability and dependency lineage, not only by current repository.
4. Identify the exact CUA driver, its declared capability, attestation state and Axis endpoint. A model name, task label or driver's presence is not proof of authorization.
5. Run the repository's existing incremental baseline for the changed component and dependency closure. Record the actual exit code and output digest.
6. Take one ticket and one branch. A ticket states the requirement before work and has decidable acceptance conditions. A diagnosis is not an implementation unit.
7. Request a ticket from Debian Axis for the exact driver, action and scope before any mutating act.

A missing source, unavailable driver, absent receipt or refusing gate is recorded as `absent` or `refused`; it is never guessed, waived, called pending, or represented as a pass.

## 2. Work authority: CUA drivers perform development

People and model agents may research, inspect, propose, plan and request work through the family Development Kit. They do not bypass the Debian Axis/CUA development path.

All repository mutations, source edits, app generation, builds, tests, signing, app-store publication, installation and client measurement are performed by an attested CUA driver using an Axis ticket for the exact action. MCP is a typed request/status surface; it is not a shell or a file-writing runtime.

The model must not:
- write or replace project files directly;
- create an app, package, manifest, icon, UI framework, theme, motion system or renderer by hand;
- use arbitrary shell, arbitrary root command, arbitrary executable or arbitrary filesystem path;
- sign, admit, mount, install, kill, restart or otherwise mutate the host directly;
- self-assign a driver identity or claim that an operation ran through CUA when no driver receipt exists.

A tool that accepts arbitrary commands or paths is not an acceptable substitute for a typed driver capability. No `debian.command` or alias for unrestricted root execution may be exposed to an agent.

## 3. Popit package and client rules

- `dialin.py` is the current Popit canonical serialization and BLAKE3 package digest implementation. Reuse it. Do not add a competing digest helper or silently substitute SHA-256.
- Preserve monotonic integer revisions, the `name@revision+blake3:<hash>` lineage, canonical manifest/payload coverage and declared schema vocabulary. Dependency identities must be explicit and pin-complete wherever Restore requires them. A Popit-specific schema/domain difference must be named, versioned and tested; never silently claim byte-for-byte Restore compatibility.
- `envelope.py` is the existing Ed25519 signing/verification implementation. `settings_package.py` and `app_package.py` use the Popit publisher key and shared trust registry. Preserve key custody, revocation and trust checks. Private keys never enter source, prompt text, screenshots, package payloads, MCP arguments or logs.
- `settings_package.py` is the sole Settings authority. `app_base.py` is the current subscription and shared-control baseline. `app_package.py` is the current signed app registry/package publisher. Extend these; do not create another store or signing path.
- The Windows desk and OTA phone client must consume the same signed app identities and launch decisions. HTTPS/secure-origin and certificate pinning are transport requirements; transport trust does not replace Ed25519 package trust.
- A window may only be a Settings-derived mutation. The Settings package owns the window frame, four regions (`bar`, `status`, `body`, `foot`), contour, chrome, shared controls, palette, layout, material, motion and DPI. An app may contribute its declared body/functionality; it may not author another framework or visual system.
- A Settings revision invalidates every subscriber built against the previous identity. Stale subscriptions refuse until rebuilt and measured.
- Pending UI measurement is not a passing audit. A package must not be launchable or listed as verified unless its exact signed payload digest has a passing client-side measurement, a valid launch proof and the required integration evidence.
- A screenshot, source selector, JSON self-report or launch URL alone is not a client witness. The real Qt/Windows client or OTA phone client must observe the exact package under test.

Known gaps are not permissions. At the 2026-11-27 baseline, `app_package.py` wrote empty manifest dependencies even though its signed mutated app-base payload embedded the Settings identity; the visible identity omitted the pin-complete dependency suffix. The manifest also used a Popit-derived `dialin.PACKAGE_SCHEMA` digest domain rather than the literal Restore reference module's domain. These are explicit conformance/migration work items, not a reason to add a second package reader.

## 4. Refusal-first authoring and command safety

A refusal is a precondition that stops the act, not a note to acknowledge after violating the rule.

### 4.1 No heredocs

No heredoc for code, data, configuration or records in any project: not `<<'PY'`, `<<EOF`, `python - <<`, `cat > file <<`, or equivalent nested/quoted forms.

Use the project's approved editor/patch capability for code and `tools/record_row.py` or its owning project recorder for records. Keep patch probes; never delete, overwrite or rewrite a historical probe or refusal row.

The gate must inspect the actual command/operation before dispatch. A static scan of committed scripts is supplemental; it cannot prevent a terminal heredoc sent at runtime. If the command channel cannot reject heredoc syntax before execution, that channel is not an authorized code-authoring interface.

On a violation: refuse before execution, stop the current unit, preserve the exact attempted operation and refusal, and add a kept regression case. Do not run a second command to work around the refused act.

### 4.2 Process and service lifecycle

Never select a process by substring, command-line grep, broad executable name or an assumed port owner.

A lifecycle act requires:
- a registered supervisor identity;
- exact PID and executable identity;
- process start time and owned child/process-group relationship;
- a second validation immediately before the action;
- a ticket for that exact stop/start/restart action;
- a measured API/port/window postcondition afterwards.

Ambiguous ownership is refused without terminating anything. The current desk must not be killed to make a probe convenient.

### 4.3 Command and receipt integrity

The exit code must be the target process's exit code, not a later `tail`, `echo $?`, shell wrapper, background process or pipeline status. Commands are bounded and idempotent where possible. Each act returns the command identity, actual exit status, bounded output/digest and independently observed postcondition.

A failure is never hidden by continuing to re-sign packages, refresh the app store or execute later steps.

## 5. Evidence, failures and cross-project memory

Every unit has:
- ticket and pinned source revisions;
- authority/source classification;
- driver identity, attestation and Axis ticket;
- baseline and post-change incremental check results;
- exact artifact digests and dependency closure;
- retained patch probe;
- failure/refusal row, including unsuccessful attempts;
- commit/PR reference;
- client witness when the unit claims a user-visible result.

Failure rows are append-only. Include the action, named refusal, command and actual exit, observed pre/post state, affected dependencies, recovery and regression test. A model/driver cannot erase, rewrite, self-adjudicate or convert a refusal into success.

Search the family evidence register before implementation. A failure in a shared capability is recorded against every affected consumer through the owning family's mechanism. A passing slice does not close a cross-stack ticket while dependent slices remain untested.

The Hero Retarget Workbench Werewolf→Shiv and Tengu→Haze tail work, plus aim-matrix animation blending, are examples of the required transfer: inspect and test the complete source → skeleton/slots → mapping/weights → animation tracks → aim matrices → blending → export → stage → compile → install → in-game witness chain. Do not repeat a local patch while the shared pipeline remains broken.

## 6. MCP Development Kit contract

The dedicated Popit DevKit app and its MCP server must be generated from the Settings package and the existing Popit application catalogue. Its tools are capability-scoped and fully typed: required fields, bounded strings/arrays, enums, `additionalProperties: false`, idempotency, bounded outputs, authentication scope and named refusals.

Permitted MCP roles:
- inspect project/package/ticket/driver/gate status through bounded read-only methods;
- request a project plan or work item by typed intent;
- submit that intent to the Debian Axis/CUA workforce;
- read progress, refusals, receipts and client witnesses;
- request a scoped generated tool template from the authority.

Forbidden MCP roles:
- raw source writing, arbitrary command execution, raw path access, unrestricted root shell;
- app/template creation or package assembly by the MCP process;
- changing Settings, shared components, themes or motion;
- signing, admission, mount or install;
- claiming CUA action without the Axis ticket and driver receipt.

The agent decides when to call a capability such as reading the Freebuff composer. Popit must not poll that UI on a timer and label a screenshot as an agent read. The result must contain the readable composer text (and distinguish placeholder from draft), be read-only, not steal focus, not type or submit, and return a receipt tied to the requesting agent and its active task.

## 7. External documentation and source-comment refusal

The family documentation contract is `docs/family-documentation-standard.md`. It is mandatory for every language and every family project.

- **No explanatory source comments or docstrings.** Do not add natural-language comments, Python docstrings, Rustdoc/TSDoc/JSDoc, section banners, TODO/FIXME/HACK prose or comments that restate code. This applies to all source blocks and all agent-authored code. The narrow machine-directive/license allowlist in the documentation standard is the only exception.
- **Refuse before writing.** The CUA editor/patch path must parse the proposed diff and changed files before applying bytes. A new explanatory comment is `source-comment-added`; unknown directives and unsupported language syntax refuse by name. A CI scan after the write is supplemental, not permission to write first.
- **Document outside the source.** Use external documentation under `docs/`, with generated rustdoc-shaped HTML under `docs/reference/<project>/`. Public APIs, types, routes, app surfaces and MCP tools need reference entries tied to the exact source commit and dependencies. The existing `docs/prose/<project>/` is the copy-audit report, not the complete API reference.
- **Keep copy and reference states separate.** A generated page existing is not a clean prose result; a reference page existing is not proof its source digest is current. Report inventory completion, copy cleanliness, reference coverage and freshness as separate facts. A report with unaccepted hits cannot be labelled copy-clean.
- **Load the required skills for their actual scope.** Declauding and Stop Slop are mandatory for external technical prose and user-facing copy. Impeccable is mandatory for Popit/frontend design work. These skills do not authorize explanatory source comments or replace the parser gate. Record loaded versions/digests and the review receipts.
- **Migrate legacy comments with a ticket.** Read meaningful source comments as migration input, move useful contracts into external docs, remove the comment through the CUA patch path, and keep the patch probe. Delete empty narration without reproducing it. No new comments may be added while legacy cleanup is open.

The complete parser coverage, allowlist, reference-page contents, skill handling, positive/negative fixtures and refusal names are in the documentation standard. There is no `--skip-comments`, prose-baseline waiver or development-only exception.

## 8. Work-unit completion

A unit closes only when its ticket's acceptance is met by evidence. Compile success is not package validity; package validity is not launch proof; launch proof is not a client witness; CI success is not a skipped family check; absence of a refusal is not evidence that an act occurred.

A refused, unrun, unmeasured, unavailable or unwitnessed condition stays open and is named accurately.

## 9. Governing sources

- `docs/family-development-policy.md` — family project setup and gates.
- `docs/family-mcp-devkit.md` — Popit/Restore ownership map and MCP DevKit architecture.
- `docs/family-documentation-standard.md` — external API/reference docs, no-source-comment policy, language-aware pre-write refusal and prose-skill requirements.
- Secure Shell Restore: `alacripose/secure-shell-restore/docs/SECURE-SHELL-RESTORE@1.ARCHITECTURE.md`, `...IMPLEMENTATION-PLAN.md`, `...AGENT-BOOTSTRAP-API.md`, `...CUA-CIVILIAN-ACCEPTANCE.md`.
- Secure Shell Axis: `alacripose/secure-shell/server/axis.mjs`, `server/axis-server.mjs`, `server/axis-driver.mjs`, and the associated tests.
- Hero Retarget Workbench: its `AGENTS.md`, `AGENTS-INDEX.md`, `AGENTS-LOG.md`, project ledger and retained probes.

The links above identify authorities; they do not claim every proposed DevKit capability is already implemented.
