# Popit Shell as the Secure Shell / Restore client and app layer

**Status:** design and source audit for TICKET-0010. This document records the intended ownership map and the implementation gaps found at the 2026-11-27 source baseline. It does not claim that the Developer Kit, its MCP capabilities, or the full client integration already exists.

## 1. Architectural correction

Popit Shell is the modern Windows desktop and OTA phone client/application implementation of Secure Shell and Restore. It is not a second package architecture and Restore is not an older implementation to replace Popit's current signed app store.

The system has one package/trust lineage with distinct owners:

1. **Secure Shell Restore** defines the operating-layer and package contracts: canonical identity, BLAKE3 content coverage, monotonic revisions, dependency pins, signing/admission separation, stream integrity, subordinate mount receipts, restore and witness.
2. **Secure Shell Axis on Debian** is the authority for CUA drivers: registration, capability declaration, attestation, exact-action tickets, expiry, receipts and learning records.
3. **Popit Shell** is the modern client/application layer: Windows desktop window client, OTA phone client, Settings package, mutable app subscriptions, Ed25519 app/system publisher, app catalogue/store projection, and the client surfaces that render and witness packages.
4. **The Popit Developer Kit** is the controlled MCP surface. It makes family project capabilities discoverable and requests work from Axis/CUA. It is not a shell, editor, package publisher or second renderer.

The Debian backend does not become the Windows window manager. It provides the authoritative package, security, ticket and event services. The client owns rendering, focus, input and observation. The phone client consumes the same signed package identities and launch policy over a secure origin.

## 2. Source ownership and current implementation

| Contract | Current owner/source | Current Popit implementation | Audit status |
|---|---|---|---|
| Canonical serialization and BLAKE3 package digest | Restore package contract; Popit's existing reader/writer is `dialin.py` | `PACKAGE_SCHEMA`, `canonical_json`, `package_digest`, `_kept` | Reuse the Popit implementation; do not add a parallel digest library |
| Settings package and mutable settings values | Popit | `settings_package.py` | Existing Ed25519 publisher, signed manifest/payload and subscription admission |
| Mutable app base | Popit | `app_base.py` | Signed mutation record embeds Settings identity/digest and the current control/project baseline |
| App identity, signature and catalogue | Popit | `app_package.py`, `docs/app-store.json`, `tools/app_store.py` | Existing BLAKE3 manifest digest and Ed25519 record signature; gaps below remain |
| Phone trust and caller envelopes | Popit | `envelope.py`, `ui/package.js`, `ui/phone.js` | One Ed25519 implementation and trust registry; TLS remains a separate transport trust |
| Windows desktop CUA | Popit | `cua.py`, `toast.py` | Desktop actions and receipts exist; not a complete project-development workforce |
| Debian Axis authorization | Secure Shell | `server/axis.mjs`, `server/axis-server.mjs`, `server/axis-driver.mjs` | Ticket/attestation architecture exists; current node driver only declares `witness` and `learning-apply` |
| Client window composition | Popit Settings/app package | `app_base.py`, `toast.py::app_page`, `ui/package.js` | The current renderer path still supplies the entire body from a shared multi-app page; not an isolated per-app body substrate yet |
| Family project baseline | Popit + family-wide policy | `app_base.PROJECT_SETUP`, `docs/family-development-policy.md`, `tools/gate.py` | Digest is carried in app base; it is not yet a complete executable CUA work protocol |
| MCP interface | Popit | `toast.py::Handler.mcp`, `/mcp` | Existing MCP endpoint lacks the typed family development catalogue and still exposes unrestricted `debian.command` |
| Code/API documentation | Popit Prose worker and family checker | `tools/prose_family.py`, `docs/prose/<project>/` | Current pages are copy-audit reports, not a navigable API reference; current `passed` badge can coexist with 741 hits |

## 3. Package identity and signing: keep the lineage, close the pin gap

### 3.1 What is already shared

Popit's `dialin.py` provides canonical sorted-key JSON, a package manifest/payload BLAKE3 digest, length framing, and the package schema identifier derived from the `secure-shell.package` family. `settings_package.py` and `app_package.py` use that implementation. The Popit app identity remains a `name@revision+blake3:<digest>` lineage with monotonic integer revisions.

The Popit app/system publisher uses `envelope.py` and its OpenSSL Ed25519 implementation. The Settings publisher key is reused by app packages, and the same trust registry is used for package/caller trust. This is the modern Popit client app-signing path; do not add a second app signer or new crypto runtime.

The signature record is separate from the BLAKE3 content digest. A valid digest says which bytes; the Ed25519 signature says which trusted publisher asserted the record. Neither by itself proves admission, successful mounting, or correct rendering.

### 3.2 Exact conformance gap found

At the inspected source revision:

- `settings_package.py` writes a root Settings manifest with `dependencies: []`, which is appropriate for the base package.
- `app_base.subscription()` embeds the current Settings package identity, digest, payload digest, Settings fields, controls baseline and project setup into the signed app payload.
- `app_package.py::publish()` nevertheless writes each app manifest with `dependencies: []`.
- Its identity string is `app-name@revision+blake3:digest`, with no pin-complete dependency suffix.

That means the app payload knows which Settings identity it mutates, but the package manifest and identity do not expose that dependency as a first-class Restore-style pin. The Developer Kit must refuse to create new packages with this omission. The existing Popit package reader/writer needs a ticketed migration that puts the Settings identity in the declared dependency set and produces the pin-complete identity, while preserving the current Popit schema/digest domain and existing Ed25519 authority.

The current Popit schema identifier is derived by `dialin.PACKAGE_SCHEMA`; the Restore reference implementation names its current reader domain `secure-shell.package/1`. These are not silently interchangeable byte-for-byte digest domains. The Popit mapping is an explicit modern client profile. A compatibility test must prove the declared relationship, and any change of schema/domain requires a ticket, new package revision and explicit migration. Never add an automatic fallback or a second reader.

### 3.3 Trust claims remain separate

The client/store flow must preserve this order, with each claim having its own record and refusal:

1. Canonical manifest, dependency closure and BLAKE3 content identity.
2. Ed25519 verification against the current, non-revoked publisher trust registry.
3. Admission for the target Windows/phone client and its capabilities.
4. Secure stream/chunk integrity and resumable transfer where used.
5. Client mount/adoption receipt tied to the exact admitted revision.
6. Client-side witness of the actual rendered/operational surface.

A TLS certificate or pinned HTTPS origin authenticates the transport endpoint. It does not replace the package signature. A package signature does not replace client measurement.

### 3.4 Settings admission is distinct from the current attach path

There are two related mechanisms with different semantics:

- `app_base.subscription()` builds the signed, mutated Settings-base record embedded in the app payload. This is the current app-package base/dependency description.
- `SettingsPackage.subscribe()` admits a signed window key and nonce into `subscriptions.json`, then returns the current Settings delivery.

The current `ui/package.js::attach()` calls `GET /api/toast/apps/<name>`; that route returns `AppPackages.document()`, which calls package verification and supplies the Settings theme. The inspected attach path does not call `SettingsPackage.subscribe()`. Therefore, do not claim that every app currently completes the signed subscriber-admission handshake. The package mutation and server-side subscriber registry are separate capabilities; the DevKit must bind them without creating a second Settings authority.

### 3.5 Popit and Restore signing authorities must be chained, not conflated

Restore's accepted plan names Debian as the signer of the canonical store/stream package. Popit's current app package records use the Settings publisher's Ed25519 key, verified against Popit's trust registry and consumed by the Windows/phone client. These are different authorities in the current sources.

The target system must retain Popit's current Ed25519 app/system signing path while explicitly binding it to the Debian Restore admission/stream chain. A Debian stream signature, Popit app publisher signature, transport TLS certificate and external agent call-envelope signature answer different questions. The DevKit must not assume they are interchangeable or silently collapse their key custody. The exact cross-authority certificate/attestation mapping must be expressed in a ticketed Restore/Popit contract and proven with positive and negative interoperability fixtures.

### 3.6 Current app-package documentation contains stale claims

The existing `docs/app-packages.md` historically describes the app identity as literal `secure-shell.package/1`, lists `surface` as a signable kind, and treats the Settings subscription as a fully admitted path. The source audit finds:
- the Popit package domain is generated by `dialin.PACKAGE_SCHEMA`, not shown byte-for-byte equal to Restore's literal domain;
- current signable kinds are `window` and `phone`;
- `ui/package.js` reads the app document, while the signed Settings subscriber registry method is not called by that path.

The doc now has a 2026-11-27 source-audit correction block. Historical sections should be reconciled in the owning app-docs ticket rather than treated as evidence of runtime behavior.


## 4. Popit app model: Settings is the only UI authority

Every new Popit application must be created as a package mutation of the Settings application baseline and appear through the existing signed app catalogue. No app may introduce a private renderer, framework, theme, contour, chrome, button baseline, motion engine, style system or alternate app store.

The Settings package owns:
- The family window frame and the four structural regions: `bar`, `status`, `body`, `foot`.
- Contour geometry, chrome, responsive measurements and DPI behavior.
- Shared controls and their behavior/visual contract.
- Material, theme, palette, layout, motion and reduced-motion preferences.
- The publisher/trust identity to which apps subscribe.

An app contributes its typed functional body, data and declared behavior. It does not replace the window, author another visual system or copy Settings CSS/JavaScript into a private framework.

### 4.1 Current implementation gap

`app_base.py` has a real `popit.app-base/1` mutation record and the Popit package payload includes it. However, the current delivery path requires closer enforcement:

- The registered windows point at `toast.html`.
- `toast.html` contains DialIn, Settings, Prose, Archive and Evidence panels and their global handlers.
- `toast.py::app_page()` takes the Settings package head and substitutes the entire body from that shared page.
- `ui/toast.js` contains the separate per-mode controllers and boot paths.

That makes each signed app identity a mode of a shared multipurpose document, rather than an independently declared body module composed into the Settings-owned window. It is a partial subscription/rendering mechanism, not yet the isolated app factory the family requires.

The next app factory must compose exactly one app body into the Settings-owned four-region shell. The body and its declared modules must be the only app-specific assets; the family frame, controls, motion, layout, chrome and boot contract come from the subscribed Settings base. Home/close/navigation must deactivate the current body and all of its timers/resources before another body mounts. An app must never remain painted over SpringBoard after close.

### 4.2 Package publication gate

A signature must never be treated as an app-validity verdict. `app_package.py` currently records `ui_audit: pending` and can still sign/verify that package. `ui/phone.js` checks `verified` and launch proof, not a mandatory passing audit state. The publisher must be changed so no app becomes launchable, discoverable as verified or publishable in the store unless the exact current payload digest has:

- a passing UI audit from the actual client surface;
- a successful launch proof for the route the icon opens;
- the required package/dependency and project-baseline checks;
- a driver/task receipt for the mutation;
- the independent client witness required by the ticket.

A measurement of other bytes is not reusable. Re-signing does not turn a pending measurement into a pass.

## 5. Secure Shell Axis and the development workforce

The Debian Axis is the ticket authority. Each driver declares a bounded capability set and carries an expiring attestation. The Axis issues a ticket for one driver, one action and one scope. The driver requests the ticket before acting, and reports the result for a receipt. A missing, mismatched, expired or unauthorized ticket refuses before device mutation.

The current Secure Shell reference node driver exposes only `witness` and `learning-apply`. Its current implementation is not yet a general source-edit/build/test/project-development driver. Do not describe that functionality as present. The family DevKit work must add bounded project-development capabilities to the Axis and real driver implementations, with socket-level refusal tests.

The intended pipeline is:

`owner requirement → family/source discovery → project ticket → branch/work unit → Axis ticket → attested CUA driver act → postcondition → incremental verification → ledger/refusal row → commit/PR → signed Popit package → Windows/phone client witness`

The model/agent decomposes and requests. Axis authorizes. CUA drivers act. Popit clients render and witness. No component may promote itself to a higher authority.

## 6. MCP Developer Kit

### 6.1 App surface

The Developer Kit is a dedicated signed Popit `window` app in the existing app catalogue and SpringBoard. It is built from Settings, not a standalone web page. The page must show:

- project/source pins and dependency lineage;
- tickets, current unit, assigned driver and attestation;
- declared driver capabilities and Axis ticket state;
- incremental baseline and post-change check results;
- refusal/failure records and linked regression fixtures;
- app package identity, Settings dependency pin, signer/trust, admission and audit status;
- Windows/phone launch proof and client witness;
- explicit absent/blocked states rather than implied success.

It must not include a generic terminal, raw path editor, alternate theme editor, CSS/HTML authoring mode or package-signing button.

### 6.2 MCP verbs

The exact schemas are to be generated from the pinned Popit/Axis contract and checked in as a capability template. Initial logical operations:

| Operation | Kind | Authority | Effect |
|---|---|---|---|
| `devkit.project.describe` | read | Popit/Axis read scope | Return registered project identity, pinned sources, status and dependencies |
| `devkit.ticket.read` | read | Axis ticket scope | Read a ticket and its acceptance conditions |
| `devkit.driver.list` | read | Axis registry | Return driver capabilities, attestation and current work |
| `devkit.work.request` | write request | Axis | Submit bounded intent; Axis creates/returns the exact work ticket |
| `devkit.work.status` | read | Axis receipt scope | Read work state, outputs, refusal and postcondition |
| `devkit.evidence.read` | read | Project evidence scope | Read selected receipt/refusal/probe records, bounded |
| `devkit.package.inspect` | read | Popit package registry | Read identity, dependency pins, signer, admission, audit and witness state |
| `devkit.template.request` | write request | Axis/store | Request a pinned, capability-scoped generated agent template |
| `devkit.freebuff.composer.read` | read | Windows CUA driver | Read the active Freebuff agent's composer on explicit agent invocation |

Every tool schema requires `additionalProperties: false`, required fields, bounded lengths/arrays, enums, semantic validation, idempotency, bounded output and typed refusals. No caller-supplied command, executable, arbitrary path, shell fragment, key or capability grant is accepted.

MCP never writes source, creates the package, runs arbitrary commands, signs, admits, mounts or installs. A write-like MCP operation creates a structured request to Axis; the attested CUA driver performs the actual work under its ticket.

### 6.3 Freebuff composer read

The composer read is explicitly agent-initiated. There is no shell startup poll, four-second poll, freshness gate or automatic capture presented as an agent read.

The active Freebuff agent invokes the MCP capability while its mission is running. The driver reads the accessible composer text, separately identifies the placeholder, returns the text and a receipt, and leaves focus, keyboard and submit state unchanged. If UI Automation cannot produce text, the operation returns a named refusal with the available non-text evidence; it must not claim that a screenshot digest is a text read. No automatic polling is permitted.

### 6.4 Hard refusals

The DevKit and underlying gate must refuse, before an act:

- non-CUA source/file/app/package writes;
- raw root shell, arbitrary command or executable execution;
- arbitrary host path or process-name-based lifecycle action;
- heredoc-based code/data/record authoring;
- app packages without Settings dependency/subscription, four-region shell, declared assets, shared controls and passing client audit;
- locally authored UI framework, chrome, motion, palette, contour or button system;
- unsigned, untrusted, revoked, stale, dependency-incomplete or tampered package;
- launchable packages with pending audit or missing client witness;
- CI/prose/secrets/family checks that did not actually run;
- a repeated refusal that has no new ticketed recovery and regression fixture.
- an explanatory source comment/docstring, unrecognized comment directive or source language with no comment parser;
- a changed public API with no current external reference entry;
- a prose/copy report that labels unaccepted hits as clean or conflates inventory completion with quality;
- external prose saved without the mandatory skill and review receipts.

A refusal stops the current work unit. It is not a warning followed by a less constrained workaround.

## 7. Documentation, comments and skills are separate controls

The project needs three separate, enforced capabilities. They must not be collapsed into the current prose scanner.

### 7.1 No explanatory prose in source

No AI-authored explanatory comments or docstrings. That includes ordinary line/block comments, Python docstrings, Rustdoc, JSDoc/TSDoc, Go package/symbol comments, HTML/CSS comments and shell/YAML/TOML comments. A short comment, a factual comment, a helpful comment, or a comment the prose scanner ignores is still not an accepted documentation surface.

Only parser-recognized machine directives and required license metadata survive, through a finite allowlist. An unexplained suppression or unknown directive is refused. TODO/FIXME/HACK prose becomes a ticket or external record, not a code annotation.

The pre-write CUA editor/patch path parses the proposed diff using language-aware tokenizers. A prohibited comment is refused before the file changes. The CI/source scan is a second check. A language without a supported parser is refused until the driver adds and tests that parser. No generic regex-only parser, no skip flag and no baseline waiver.

Existing comments are migrated under tickets. The driver reads their intent, writes useful behavior/contracts into external documentation, and then removes the comment. Repeated narration and AI filler are deleted. A touched file cannot gain comments while the legacy migration is still open.

### 7.2 External reference pages replace source comments

The current Popit prose worker already renders `docs/prose/<project>/index.html`, but this page is a copy-quality report: it lists source files, extracted strings, word budgets and prose hits. It is not the rustdoc-shaped API documentation the family requires.

The new reference system is separate:

- External authoring sources live in project `docs/` files.
- Language parsers derive symbol maps, signatures, module boundaries, public API entries, dependencies, routes, tools and schemas.
- The reference renderer publishes navigable HTML under `docs/reference/<project>/`.
- Landing pages and the Popit Prose/DevKit surfaces link both the reference and the separate copy-audit report.
- Every public symbol and MCP/app capability has a reference entry. Each page is pinned to the exact source commit and dependency set.
- Descriptions cover behavior, typed inputs/results, side effects, state, invariants, security/authority, named refusals, lifecycle and tests.

The tool may use source code, test evidence and schemas to derive structure. It must not generate prose by copying source comments or guessing from function names. Unproven behavior remains marked undocumented and becomes a driver work item.

### 7.3 The existing prose report must stop confusing completion with cleanliness

The committed Popit report at `docs/prose/popit-shell/index.html` records 1,739 drawn strings and 741 hits, yet displays a `passed` badge.

The source explains this mismatch: `inventory()` records the number of hits, while `render_project()` derives its status from `job.refusal`; `verify()` checks that a generated document exists and has expected markers. A successful report-generation workflow can therefore be labelled `passed` even when the page contains hundreds of hits. The badge does not mean the prose is clean.

The UI and receipt must distinguish at least:
- `inventory_complete` — the checker read the declared sources;
- `copy_clean` — zero unaccepted copy hits;
- `copy_held` — one or more unaccepted hits remain;
- `reference_current` — external API docs cover the current public symbols and match the source digest;
- `reference_stale` — documentation no longer matches the source/dependency pins;
- `driver_blocked` — a driver operation could not be performed.

A nonzero unaccepted hit count cannot render as `copy_clean`. The word `passed` cannot be used to mean only that a page was generated.

The current report contains a `comment-restates` rule row. That one rule does not establish a complete comment detector or a pre-write prohibition. The Popit `cua.py` file contains the Chromium/UI Automation explanatory comments and docstrings from the supplied example; they remain in source. The Brass Meridian `docs/PROSE.md` says code comments are not scanned, and the Workbench Python prose tool states that comments/identifiers do not count and parses source with `ast`. The precise implementation of `portal-shell/tools/ui_prose.py` was not available in the inspected public GitHub repositories, so its full coverage remains unverified.

### 7.4 Mandatory prose and design skills

The two prose skills and the UI-design skill have distinct scopes:

| Skill | Required scope |
|---|---|
| Declauding | External technical prose: docs, README, tickets, PR/issue text, reports and release notes. Preserve source claims and remove model-shaped constructions. Its own instructions exclude code and quoted text. |
| Stop Slop | External prose and user-facing copy. Check directness, specificity, sentence rhythm and predictable AI writing patterns. |
| Impeccable | Popit/frontend design, UX review, accessibility, layout, typography, responsive behavior, motion and design-system documentation. Settings remains the only visual authority. |

These skills do not replace the comment parser or generate API documentation. The source comment ban is enforced by a separate language-aware tool.

The family skill registry records the skill source, version/revision, digest, installation path, compatibility and actual task invocation. Drivers load the skills from the managed family skill location. A missing or stale skill is a named preflight refusal for the prose/UI task. External prose records the skill receipts, lint result, factual-preservation diff and required independent review. UI work records its Impeccable revision and actual client measurement.

### 7.5 Freebuff example as a held reproduction

The owner-provided transcript shows the failure mode directly:

- two source probes were created through heredocs in `/tmp`;
- the agent used hand-run Python scripts instead of a declared CUA driver capability and work receipt;
- source comments were added to `cua.py` to narrate Chromium's accessibility behavior;
- the code change increased retry count and timeout values, then restarted the desk using a PID derived from `netstat`;
- the result was probed through direct local HTTP calls rather than a visible Axis/CUA receipt.

The transcript is owner-provided evidence, not an independently witnessed runtime test. The new DevKit must refuse these paths before the write or lifecycle act, and provide the missing driver capability as a ticketed implementation task rather than silently allowing an agent to improvise.

## 8. Family learning: prevent recurrence, not just log it

Failure records are useful only when they change what the next agent is allowed to do. The DevKit preflight must query family failures by capability and dependency closure before it issues a work request. The post-failure path must add a regression to the owning shared capability and expose it to every consuming project.

The Hero Retarget Workbench is an explicit acceptance example. Werewolf→Shiv and Tengu→Haze tail work and the aim-matrix blending omission must become shared pipeline regression fixtures. The pipeline is not complete at a successful import or one local compile. It must cover:
- source body/mesh and skeleton;
- joint/slot ordering and bone mapping/weights;
- animation tracks and clip bindings;
- aim matrices and blending;
- export, staging and compiled outputs;
- installed addon/game build;
- in-game witness.

A local workaround that leaves the shared capability broken is refused. A passing slice cannot close a parent ticket while a later stage remains untested.

## 9. Evidence-exhausted questioning and publication

The Developer Kit must implement the current family decision path, not merely use an LLM prompt saying "ask if uncertain."

### 9.1 The later questioning system is missing from the Hyperskill summary

The family lineage is now recorded in `docs/family-questioning-and-publication.md`:
- Shploingus keeps a long, project-owned append-only `docs/HYPERGRILLING.md` ledger, with its own rounds and evidence traces.
- Hyperskill 0.1.0 supplies the portable material-decision taxonomy, append-only user decisions, child escalation and explicit per-invocation authority.
- Secure Shell Restore HYPERGRILL v2 moves the expensive question work to the CUA driver: exhaust code, documents, store/package corpus, external sources and bounded experiments; resolve `code`, `spec`, `external` and `measure`; escalate only the `owner` residue.
- Brass Meridian's Questions 6.0 supplies the later concrete project record and reconciliation shape: 100 stable question IDs in five themed rounds, canonical source rows, generated Markdown/JSONL, one reconciliation row per answer and a gate that checks complete coverage. Its static generator is not a dynamic evidence-search engine.
- The owner's current rule is at most ten material questions per user-facing round. This supersedes Brass Meridian's 20-question round size as a family-wide presentation limit.

The DevKit composes the driver search engine with the project question record/reconciliation system. It must not copy Brass Meridian's project questions or fabricated answers into other projects.

### 9.2 Runtime behavior

Every task begins with hypergrill preflight. The driver searches the full current project/family dependency closure, ledgers, refusals, tickets, source docs, tests and authorized drive roots through the registered driver search tools. It uses current external sources and bounded experiments where those can settle a question.

It classifies each uncertainty into `code`, `spec`, `external`, `measure` or `owner`. Machine-resolvable questions are closed with evidence receipts before any owner prompt. Child workers return uncertainty packets to the coordinator; they do not prompt the owner directly.

The owner sees only material `owner` questions that remain after the sweep, in a coherent group of no more than ten. Each has a stable ID, source evidence, dependency/blocking information and neutral options. A missing answer remains open; work that depends on it does not proceed. Safe independent work may continue. The answer is recorded verbatim with `user` provenance and gets a separate evidence-backed reconciliation row. Contradictions and supersessions are explicit and append-only.

### 9.3 Public-first family publication

The user's standing family decision is public publication. Git repositories and public project releases default to public; agents must not introduce a private-first staging phase or ask the same public/private question repeatedly. An explicit owner-approved exception is recorded per project and is the only override.

Public by default does not reduce the security gate. Before any public push or release, an attested driver must perform and record a complete current/history secret scan, including refs, branches, tags, submodules, LFS and release payloads. Findings or missing scan coverage block publication. They do not trigger a private-visibility workaround. Publication and release work then checks license/provenance, required gates, BLAKE3 package identity, Ed25519 trust, client admission, artifact signature, and downstream client access.

GitHub repository visibility, Git history, executable release, Popit app-store package, Restore package stream and Windows/phone client witness are separate deliverables. One does not prove the others.

### 9.4 SHA-256 Git object format is not the package digest

The Freebuff transcript's automatic fast-export rewrite is not an acceptable first response. Git's hash-transition documentation describes the `compatObjectFormat=sha1` compatibility mode and bidirectional SHA-256/SHA-1 object-name mappings; when configured and supported, Git can translate pushes to a SHA-1 server without an immediate whole-history rewrite. The actual local checkout must be inspected before deciding whether it has that compatibility mapping. GitHub community discussion #212994 (opened 2026-11-13, unanswered) reports SHA-1-only hosting, but is not an official GitHub statement.

The driver must inspect local repository format, Git version, compatibility format, remote object-format capability and exact server error. If no compatible non-destructive path is available, the decision to rewrite history, mirror the project or change forge is escalated to the owner. Preserve the original bundle/ref inventory and map old-to-new commit identities; enumerate signature, tag, branch, PR, CI and release fallout before any authorized migration. Git object IDs do not replace BLAKE3 package identities or Ed25519 signatures.

### 9.5 Current Shploingus publication audit

The public repository is `alacripose/shploingus-clean`. On the inspected source:
- `main` is public, at `c0a205d661e1fffe2cb1d9ffa0eb6f6977972724`.
- `v0.1.0` is an unsigned annotated tag pointing to `b84331a1afe129dcebadfcbdc0ca18b833cf70c9`, not the current main head.
- The latest three CI runs and latest three release runs on 2026-11-27 failed. The latest logs show `voxel-model/build.rs:153` refusing because the computed spectra-source digest `8561c777…` does not match the recorded `88ed8ac7…`.
- The failed release job stopped at executable build; packaging and GitHub Release creation were skipped. The public release listing is empty.
- The tagged commit rewrites 59 spectra source files and says it restores byte-exact inputs; it has no demonstrated passing CI/release witness yet.
- `voxel-package/src/signing.rs` exposes a signing interface but uses `NoSigningBackend`; project handoff says no signature has been generated or verified and no trust root/backend exists.
- Workspace identity is SHA-256, not family BLAKE3 package identity.
- Current CI excludes the `shploingus` and `voxel-client` test targets, and does not run `frame-cost`, a performance regression threshold or a full-history secret scan. The `frame-cost` example measures medians and FPS but prints results; it is not itself a regression gate.
- The release workflow builds a Windows executable/ZIP and attempts a GitHub Release, but has no Ed25519 package signature, BLAKE3 release manifest or downstream client witness.

This is a public-source audit, not a local-drive or running-game witness. The user's local checkout at `C:\Users\ala\Documents\shploingus-clean\` was not accessible from this session. The project's own handoff lists multiple alpha gates incomplete, so the public repository must not be described as a completed release.

### 9.6 Project remediation instead of repeated local patches

The DevKit must route Shploingus recovery into a project-local, Axis-ticketed CUA work plan covering repository/object-format comparison, materials input provenance and digest repair, full-history secret scan, Rust skill-policy conflict, BLAKE3/Ed25519 package backend, complete client tests, measured performance baseline/threshold, external API docs, signed tag/release and downstream Popit/Restore client access.

No one should regenerate the materials table by enabling the bypass feature and then declare the gate fixed. The recovery first determines the source bytes the recorded digest is meant to represent, records current and expected digests, and runs the generator only in its explicitly ticketed regeneration path. The normal build must then run with regeneration disabled and demonstrate that the gate is restored.

## 10. Security and release gate matrix

| Gate | Positive case | Negative case |
|---|---|---|
| Restore identity | canonical Popit package, revision and BLAKE3 digest recompute | malformed name/revision/hash, missing dependency pin, unordered or duplicate deps |
| Ed25519 | current trusted Settings publisher verifies | altered payload, unknown/revoked key, malformed signature |
| Settings base | app mutation references current Settings identity and control baseline | stale identity, changed controls baseline, private theme/motion |
| App composition | app body is composed into Settings four-region window | app provides its own bar/status/footer, alternate frame or hidden sibling app panels |
| Dependency closure | every loaded file is declared and signed | undeclared module, image, manifest, worker or stylesheet |
| Client audit | exact package digest is measured in Qt/Windows and OTA phone surfaces | pending audit, stale digest, overlap, failed launch or no client witness |
| Axis | attested driver receives one ticket for declared action, then acts and returns receipt | unticketed, expired, wrong-action, wrong-scope, un-attested driver |
| Authoring | patch operation is performed by ticketed CUA driver; no explanatory source comments | direct MCP write, heredoc, added comment or unknown comment syntax refused before writing |
| Process safety | exact registered supervisor and owned process group are verified | ambiguous PID/command-line match refuses without termination |
| Prose/secrets | actual shared family check ran, current and historical secret scans report | `[n/a]`, skipped checker, missing family checkout, history not scanned |
| External docs | current public API symbols link to reference pages pinned to the source digest | missing symbol, stale HTML, comment-only documentation or invented API behavior |
| Source comments | changed source contains no new natural-language comment/docstring tokens | explanatory comment/docstring, unknown directive or unparsed language refuses before write |
| Skill receipts | external prose has Declauding/Stop Slop evidence and UI work has Impeccable evidence | missing/stale skill, unreviewed prose or frontend work without the required design pass |
| Copy state | copy gate distinguishes clean, held, inventory-complete and blocked | 741 hits displayed as a generic `passed` state |
| Questions | Restore driver search closes machine-resolvable classes; owner receives only evidence-backed questions in 10-question maximum rounds | machine-answerable question asked of owner, missing source ignored, guessed default or silent closure |
| Publication | public-first repo/release has full-history secret receipt, package signing and client access witness | private-first default, partial secret scan, unpublished executable or unverified package claimed as release |
| Git object format | local format/compat map and server capability are measured before a publication plan | history rewritten automatically, tags/commits silently invalidated, object hash confused with BLAKE3 package digest |
| Release provenance | signed tag/release manifest ties exact source SHA, BLAKE3 payload, Ed25519 signer, build and client witness | unsigned/moved tag, artifact from another commit, or failed/skipped release described as published |
| Performance | baseline and explicit regression thresholds run in CI for declared profiles | benchmark prints FPS but no comparator/threshold or gate skips the client target |
| Landing evidence | each app screenshot is tied to package digest, client and audit receipt | placeholder/stock screenshot, unreferenced screenshot, build-only claim |
| Cross-project learning | matching prior failure is loaded and full dependency chain is tested | repeated issue in a different consumer without regression transfer |

## 11. Migration sequence

1. **Authority, question lineage and mapping** — record Restore v2, Hyperskill, Brass Meridian's question/reconciliation shape, project Hypergrill and Popit/Restore/Axis ownership in one current standard.
2. **Refusal boundary** — replace arbitrary `debian.command` in MCP with typed Axis requests; enforce pre-action no-heredoc and exact process identity.
3. **Evidence-exhaustion and owner decision engine** — implement driver-led searches, material decision classification, question records, 10-question owner rounds, append-only answers and per-answer reconciliation.
4. **Source-comment and documentation gate** — build language-aware pre-write comment refusal, external API reference generator, skill compatibility/receipts and honest copy-state model.
5. **Publication authority and gates** — enforce public-first by default, full-history secret scan, tag/history safeguards, exact source-to-artifact provenance and downstream client access.
6. **Package conformance** — add explicit Settings dependency pins to app manifests and identity strings; make audit/launch/client witness hard preconditions to store verification.
7. **App composition** — separate app body modules from the shared multipurpose `toast.html`, compose them into a Settings-owned shell, and centralize activation/deactivation.
8. **MCP DevKit** — generate the typed API manifest/template from the Axis capability registry; register and build the signed DevKit app through the same app factory.
9. **Cross-project ratchets** — ingest the family failure register, add shared regression fixtures and incremental dependency-closure tests, including performance thresholds and release gates.
10. **Client witness** — verify the Developer Kit and every registered app in the actual Windows/Qt desk and OTA phone client; publish screenshots and receipts only when tied to the measured package digest.

Each stage is its own ticketed work unit. Later stages cannot be represented as complete because earlier documentation or static checks passed.

## 12. Source references

- Secure Shell Restore architecture: `alacripose/secure-shell-restore/docs/SECURE-SHELL-RESTORE@1.ARCHITECTURE.md`
- Restore decisions/milestones: `alacripose/secure-shell-restore/docs/SECURE-SHELL-RESTORE@1.IMPLEMENTATION-PLAN.md`
- Restore MCP/agent template contract: `alacripose/secure-shell-restore/docs/SECURE-SHELL-RESTORE@1.AGENT-BOOTSTRAP-API.md`
- Restore canonical identity/manifest: `alacripose/secure-shell-restore/impl/packages/identity.py`, `impl/packages/canonical.py`
- Secure Shell Axis: `alacripose/secure-shell/server/axis.mjs`, `server/axis-server.mjs`, `server/axis-driver.mjs`
- Popit identity/signing: `dialin.py`, `envelope.py`, `settings_package.py`, `app_base.py`, `app_package.py`
- Popit client/store: `toast.py`, `ui/package.js`, `ui/phone.js`, `tools/app_store.py`
- Family documentation and source-comment standard: `docs/family-documentation-standard.md`
- Retained source-comment/prose/Freebuff audit: `data/probes/2026-11-27-source-comment-and-docs-gap.md`
- Hero Retarget conventions and evidence: `alacripose/hero-retarget-workbench/AGENTS.md`, `AGENTS-INDEX.md`, `AGENTS-LOG.md`, `docs/ARCHITECTURE.md`
- Family questioning/publication policy: `docs/family-questioning-and-publication.md`.
- Shploingus Clean public-source and release audit: `data/probes/2026-11-27-publication-questioning-shploingus-audit.md`.

