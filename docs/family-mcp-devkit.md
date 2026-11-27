# Popit Shell as the Secure Shell / Restore client and app layer

**Status:** design and source audit for TICKET-0009. This document records the intended ownership map and the implementation gaps found at the 2026-11-27 source baseline. It does not claim that the Developer Kit, its MCP capabilities, or the full client integration already exists.

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

A refusal stops the current work unit. It is not a warning followed by a less constrained workaround.

## 7. Family learning: prevent recurrence, not just log it

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

## 8. Security and release gate matrix

| Gate | Positive case | Negative case |
|---|---|---|
| Restore identity | canonical Popit package, revision and BLAKE3 digest recompute | malformed name/revision/hash, missing dependency pin, unordered or duplicate deps |
| Ed25519 | current trusted Settings publisher verifies | altered payload, unknown/revoked key, malformed signature |
| Settings base | app mutation references current Settings identity and control baseline | stale identity, changed controls baseline, private theme/motion |
| App composition | app body is composed into Settings four-region window | app provides its own bar/status/footer, alternate frame or hidden sibling app panels |
| Dependency closure | every loaded file is declared and signed | undeclared module, image, manifest, worker or stylesheet |
| Client audit | exact package digest is measured in Qt/Windows and OTA phone surfaces | pending audit, stale digest, overlap, failed launch or no client witness |
| Axis | attested driver receives one ticket for declared action, then acts and returns receipt | unticketed, expired, wrong-action, wrong-scope, un-attested driver |
| Authoring | patch operation is performed by ticketed CUA driver | direct MCP write or heredoc command refused before execution |
| Process safety | exact registered supervisor and owned process group are verified | ambiguous PID/command-line match refuses without termination |
| Prose/secrets | actual shared family check ran, current and historical secret scans report | `[n/a]`, skipped checker, missing family checkout, history not scanned |
| Landing evidence | each app screenshot is tied to package digest, client and audit receipt | placeholder/stock screenshot, unreferenced screenshot, build-only claim |
| Cross-project learning | matching prior failure is loaded and full dependency chain is tested | repeated issue in a different consumer without regression transfer |

## 9. Migration sequence

1. **Authority and mapping** — record this ownership map, update `AGENTS.md`, identify Popit/Restore schema differences and the existing Axis capabilities.
2. **Refusal boundary** — replace arbitrary `debian.command` in MCP with typed Axis requests; enforce pre-action no-heredoc and exact process identity.
3. **Package conformance** — add explicit Settings dependency pins to app manifests and identity strings; make audit/launch/client witness hard preconditions to store verification.
4. **App composition** — separate app body modules from the shared multipurpose `toast.html`, compose them into a Settings-owned shell, and centralize activation/deactivation.
5. **MCP DevKit** — generate the typed API manifest/template from the Axis capability registry; register and build the signed DevKit app through the same app factory.
6. **Cross-project ratchets** — ingest the family failure register, add shared regression fixtures and incremental dependency-closure tests.
7. **Client witness** — verify the Developer Kit and every registered app in the actual Windows/Qt desk and OTA phone client; publish screenshots and receipts only when tied to the measured package digest.

Each stage is its own ticketed work unit. Later stages cannot be represented as complete because earlier documentation or static checks passed.

## 10. Source references

- Secure Shell Restore architecture: `alacripose/secure-shell-restore/docs/SECURE-SHELL-RESTORE@1.ARCHITECTURE.md`
- Restore decisions/milestones: `alacripose/secure-shell-restore/docs/SECURE-SHELL-RESTORE@1.IMPLEMENTATION-PLAN.md`
- Restore MCP/agent template contract: `alacripose/secure-shell-restore/docs/SECURE-SHELL-RESTORE@1.AGENT-BOOTSTRAP-API.md`
- Restore canonical identity/manifest: `alacripose/secure-shell-restore/impl/packages/identity.py`, `impl/packages/canonical.py`
- Secure Shell Axis: `alacripose/secure-shell/server/axis.mjs`, `server/axis-server.mjs`, `server/axis-driver.mjs`
- Popit identity/signing: `dialin.py`, `envelope.py`, `settings_package.py`, `app_base.py`, `app_package.py`
- Popit client/store: `toast.py`, `ui/package.js`, `ui/phone.js`, `tools/app_store.py`
- Hero Retarget conventions and evidence: `alacripose/hero-retarget-workbench/AGENTS.md`, `AGENTS-INDEX.md`, `AGENTS-LOG.md`, `docs/ARCHITECTURE.md`

