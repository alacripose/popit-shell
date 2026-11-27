# Family questioning, publication and project-release authority

**Status:** Proposed family-wide standard for TICKET-0010. The user instructions below are direct owner decisions from 2026-11-27. Repository findings are pinned in the related probe. This document describes required behavior; it does not claim runtime enforcement exists.

## 1. One authority path for material decisions

The DevKit must combine the family questioning lineage instead of implementing another agent's preferred interview format.

### 1.1 The lineage and each mechanism's actual role

| Lineage | What it contributes | What it does not replace |
|---|---|---|
| Shploingus project Hypergrilling ledger, beginning 2026-09-29 and continuing through Round 18 (2026-10-03) | Project-specific questions, owner answers in the owner's words, evidence traces, follow-up questions, open items and supersession. | It is not the later family-wide driver search loop. |
| Hyperskill 0.1.0 (2026-09-24) | Portable material-decision taxonomy; append-only decisions; user control; child uncertainty escalations; per-invocation high agency; safety/privacy/evidence boundaries. | It does not describe the later Restore v2 driver-deliberation and Brass Meridian's project record/reconciliation implementation. |
| Secure Shell Restore HYPERGRILL v2 (2026-11-04) | The family research-and-deliberation loop. A CUA driver exhausts code, documents, store/package sources, external references and bounded measurements before asking the owner. | It does not itself define the complete project-specific interview and reconciliation files for each app/game. |
| Brass Meridian Questions 6.0 (2026-11-19) | A concrete project question record: 100 stable IDs, five thematic rounds, phase labels, generated Markdown plus JSONL, then one reconciliation row per answer and a gate that verifies complete coverage. | Its 100 rows are pre-authored project questions. The generator does not itself exhaust project evidence or discover every open question. |
| The family owner's current instruction (2026-11-27) | Owner-facing question turns contain at most ten material questions, after the driver has exhausted searchable evidence. | Ten is a maximum, not a target. Never fill a round with questions the evidence already answers. |

The public Hyperskill document is therefore incomplete as a description of the current family workflow. It preserves an important protocol core, but omits the later Secure Shell Restore v2 driver deliberation and the Brass Meridian question/reconciliation implementation. This standard closes that lineage gap.

### 1.2 Driver-led evidence exhaustion

Every material task begins with a hypergrill by the authorized CUA driver. The model is a coordinator and may request that work; it is not the authority that declares a question answered.

Before asking the owner, the driver:
1. Reads the complete project `AGENTS.md`, authoritative records, decisions, current ticket, implementation plan and applicable package/client contract.
2. Reads the full relevant project implementation, tests, build/gate definitions, ledgers, failures, refusals, probes, release history and prior question records.
3. Searches the family project register and the full dependency closure, not only the current checkout.
4. Searches the authorized drive roots and project corpus through the registered driver search capability. It records roots included, exclusions, unreadable locations and incomplete sources. It does not use ad hoc `find`, `grep -r`, `rg` or shell listings where the family search/driver tools exist.
5. Searches current external specifications and upstream behavior where the question has an external fact component.
6. Runs bounded measurements or controlled experiments when a measurement can decide the question. The act must have its own Axis ticket, driver identity and receipt.
7. Reconciles every found claim to its owning authority and version. Conflicting evidence stays visible; it is not averaged or silently resolved by preference.

The search is not complete just because the first relevant line was found. The receipt names the sources, pins, excluded/unavailable sources, search boundary and whether the question is settled or remains open.

### 1.3 Who can close a question

Use the Restore v2 classes:

- `code`: driver closes by reading the authoritative implementation/tests.
- `spec`: driver derives from recorded owner decisions and the current contract.
- `external`: driver researches current external specifications and cites the source.
- `measure`: driver runs a bounded, reproducible experiment and records the output.
- `owner`: only the owner closes. Publication, public exposure exceptions, risk appetite, money, destructive writes, history rewrites, identity/trust policy, material product scope and taste belong here.

A driver may not escalate something it could have searched or measured. A child agent cannot prompt the owner directly; it returns an uncertainty packet to the coordinator. The coordinator consolidates duplicate questions and asks only the true owner-class residue.

An unanswered owner question stays `open`. It blocks only dependent work. Safe independent investigation can continue. Silence, elapsed time, a suggested default, a model preference or a filled-in form is not consent. A later answer supersedes an earlier answer by a new append-only record; the earlier answer remains readable.

### 1.4 Owner-facing round format

The current owner instruction is at most **ten material questions per round**. One round has one coherent theme and presents neutral options or a concise free-form question. No option is marked “recommended” to steer the owner. No round is padded to ten.

Each question shows:
- stable ID and exact unresolved decision;
- why the decision is material and which work depends on it;
- what the family/project authorities already say;
- what the driver searched, measured or could not access;
- two to four neutral options with concrete effects where useful;
- the consequence of leaving it open.

Answers are recorded verbatim, with provenance source `user`. Mission text, model output, tool output and cited documents are never laundered into owner voice. After the answer, the driver updates the project record and reconciles it against the evidence; an answer that conflicts with existing authority is recorded as a contradiction or supersession, not silently edited to fit.

### 1.5 Brass Meridian-style records and reconciliation

Every material project interview uses a project-owned canonical source record. Stable question IDs and rows contain at least:
`id`, `round`, `phase`, `class`, `question`, `answer`, `source`, `evidence`, `ruling`, `depends_on` and state.

The project generates its navigable Markdown interview and machine-readable JSONL from the same canonical rows. It does not keep two independently editable copies.

Every answer receives one append-only reconciliation row with:
- question ID;
- verdict: `consistent`, `contradicts`, or `taste` (plus explicit `unresolved`/missing evidence state where no conclusion can be made);
- evidence source and immutable pin;
- actual claim about the implementation;
- effect/ruling;
- ticket and actor;
- evidence receipt digest.

A project gate verifies: unique/stable IDs, every canonical question has one state, every answer has one reconciliation row, each evidence locator resolves, verdict vocabulary is valid, and generated Markdown/JSONL agree with the canonical record. Missing question, missing reconciliation, missing evidence or stale output refuses. “100 questions generated” is not “100 decisions proved.”

Brass Meridian's exact 100-question static generator is a reference for file shape and coverage reconciliation, not a replacement for the dynamic source-exhaustion worker. Do not copy its answers into another project, and do not claim it searches automatically.

## 2. Publication is an owner decision with a standing family default

**Standing owner decision, 2026-11-27:** Family projects are intended for public publication. A project agent must not default to private-first, create a private repository as an unrequested staging step, or ask the owner to repeat the public/private decision for each family repo.

The DevKit treats public as the family default for Git repositories and public family project releases. It still verifies the current project's recorded identity and any explicit superseding owner exception. If the project register records a specific owner-approved private exception, that one project follows that exception; the agent may not invent one.

This policy does not weaken any security gate. Public visibility is not permission to publish secrets, private data, keys, credentials, local paths, unreviewed provenance or a package that has not passed its admission/signing checks.

### 2.1 Correct publication sequence

1. Identify the existing project, canonical root, repository, remote, branch, object format and worktree state through the CUA driver. Do not create a second repository when the existing project already has one.
2. Exhaust the project and family publication records, prior decisions, secrets findings, release history and dependent clients.
3. Run the approved secret scan over the full working tree and full Git history, including all branches/tags/refs, reachable and relevant unreachable objects as supported, submodules, LFS pointers/objects, generated assets, archives, CI artifacts and release payloads. Record the exact scan scope, scanner versions, result digests and exclusions. A current-tree-only scan is not a full-history scan.
4. If any secret is found or any required scan did not run, refuse the push/release. Preserve the exact finding and block publication. Do not change visibility to private as a workaround, and do not remove history or rewrite references without a separate owner-authorized recovery ticket.
5. Verify licensing, provenance, current family conventions, tests, performance gates, security review, documentation and the full project release acceptance.
6. Build the release artifact from the exact source commit; record BLAKE3 identity and the appropriate Ed25519 signature/attestation. Verify the signature with the target clients' trusted keys. Artifact provenance, source identity and publisher authorization are separate claims.
7. Publish the public Git repository and its public release, then publish/admit the signed package in the family app/package store where that project uses one. Both surfaces point to the same source revision and release manifest.
8. Verify from a clean external client context that source, release artifact, signature, dependencies and downstream client install/access actually work. A successful push is not a release witness.

### 2.2 Visibility, Git format, release and package store are distinct

The GitHub repository's visibility, Git object format, source history, GitHub release assets, Popit signed app package, Restore package stream, and downstream client access each have separate state and evidence. Do not conflate them.

- Public/private visibility follows the standing owner decision above.
- Git object format is fixed when the repo is created. It is a material architecture choice, not a harmless publication toggle.
- A Git push does not produce a release executable or a signed Popit/Restore package.
- A GitHub release asset does not automatically become an admitted package in the family app store.
- A package signature does not prove the Windows/OTA client installed or rendered it.
- Downstream client availability is an acceptance item: the relevant family clients must be able to discover, authenticate, download, verify and open the intended public package.

### 2.3 SHA-256 Git repositories and GitHub

The owner-provided transcript shows a local repository whose push failed because the receiving GitHub service did not accept its SHA-256 object format. It then unilaterally proposed a fast-export history rewrite.

The DevKit must not jump directly to history conversion. Current Git documentation describes a SHA-256 repository configured with a SHA-1 compatibility object format; in that supported transition mode, Git can translate pushed objects for a SHA-1 server while retaining local SHA-256 object identities and a bidirectional mapping. This depends on the repository being correctly configured and the full relevant objects being present. The fact that this option exists does not prove it is available in the particular local checkout.

Current GitHub public discussion in November 2026 reports that GitHub hosts SHA-1 object-format repositories only; the discussion is unanswered and is community information, not a definitive official GitHub support statement. The driver's local probe must identify the actual Git version, `extensions.objectFormat`, `extensions.compatObjectFormat`, repository creation history, remotes, server-advertised capabilities and exact push error.

If compatibility is absent or cannot be safely enabled without altering history, the driver records the available hosting choices and the effects on commit IDs, signatures, tags, branches, PRs, CI, release links and existing clients. A history rewrite, a new SHA-1 mirror, or moving the canonical project to another forge is an `owner` decision. Before any authorized migration: preserve a verified original bundle and immutable ref/object inventory; prove all original refs and objects are present; record original and new digests/IDs; identify which signatures no longer verify; test a representative clone/fetch/push/CI/release path; and retain the original repository without destructive overwrite. There is no silent `fast-export` conversion.

The Git object hash is not the application's content hash. Do not replace the project's package digest, BLAKE3 integrity or Ed25519 signer with Git's repository object ID.

### 2.4 Remote HTTPS desk access reuses the signed Popit surface

A request for an external HTTPS connection to the desk does not authorize a second, hand-written website. The existing Popit family policy and client already define a remote desk surface:

- the phone/client origin is served over the existing Popit HTTPS listener and certificate;
- the remote desk is a separate HTTPS listener (currently documented as port 5222) behind the signed desk sign-in surface;
- the sign-in envelope is checked against the Popit Ed25519 trust registry, requires the named desk-access capability, spends a single-use nonce and creates a secure session;
- the tunnel helper forwards to that secure listener, not to the LAN read-only view, loopback API or an arbitrary development server;
- the remote page remains a signed Settings-derived Popit app/window. Its contour, four regions, controls, material, motion and DPI come from the shared Settings baseline.

The agent must first read the existing remote-access policy, the secure LAN phone probe and the HTTPS origin/driver ownership refusal. It then asks the existing CUA driver to expose and measure the approved path. It must not write a standalone HTML page, copy a local app into an unverified tunnel, expose a raw MCP/terminal surface, or claim that TLS alone makes the application secure.

The receipt must name the public HTTPS origin, tunnel and upstream listener identities, certificate SAN/fingerprint, signed app/package identity, Settings dependency, Ed25519 trust/admission result, capability and session result, CUA driver ticket/receipt, client-render witness and exact package digest. TLS endpoint authentication, application package signing, user admission and actual client rendering remain separate claims.

A new remote surface or changed authentication scope is a material security/authority decision. The evidence sweep checks whether an existing signed surface already satisfies the request; only a genuinely unresolved owner decision is escalated. A failed page or certificate check blocks exposure—it does not permit the agent to invent a new page or weaken authentication.

## 3. Shploingus Clean — current public source and release audit

Repository: `alacripose/shploingus-clean`, `main`, current inspected head `c0a205d661e1fffe2cb1d9ffa0eb6f6977972724`. The GitHub repository is **public**. The current `v0.1.0` tag points to `b84331a1afe129dcebadfcbdc0ca18b833cf70c9` through an unsigned annotated tag object `b3900ae2a4e3fdfd76349129899ba9cff9bc6a2f`. That commit rewrites 59 spectra input files to preserve byte endings. It is not the current `main` head. The public release list is empty.

### 3.1 Live CI and release evidence

On 2026-11-27, the three most recent runs of both `ci` and `release` all failed. The latest `ci` run `46058609707` and `release` run `46058627731` both target `c0a205d`. In each latest job:
- CI fails in `Headless tests`; release fails in `Build the executable`.
- Later build/package/upload/release steps are skipped.
- `voxel-model/build.rs:153` refuses because the computed spectra digest `8561c7772a0b399d62490fdeef1e5ddf3c86c44f9da9a65589bda2299939617c` differs from recorded digest `88ed8ac7ae0f011105147e7e5b4a61c64112bd85a1cf0790b772f3cb0fc0289a`.

The owner-provided local transcript identifies the drive project path, but this session inspected the public GitHub copy only. Local object format and worktree divergence are not evaluated. The latest public tag commit says 59 spectra files were byte-normalized incorrectly by Git and rewrites their committed bytes; the current main-run logs nevertheless still show the mismatch at `c0a205d`. The tagged commit has not been shown by a successful CI/release run, and no signed release witness exists.

### 3.2 Other release blockers

- `crates/voxel-package/src/signing.rs` exposes the signing/verifying seam but supplies `NoSigningBackend`; the handoff explicitly states no signature has ever been produced or verified, no trust root exists, and no `voxel-envelope` backend is linked.
- The content identity in the workspace is SHA-256 (`sha2`); it is not the family's BLAKE3 package identity.
- `.github/workflows/ci.yml` runs only Windows CI, excludes `shploingus` and `voxel-client` from tests and only checks a release binary build. It does not invoke the `frame-cost` measurement, a regression threshold, a full-history secret scan or the family package signing/client witness.
- `.github/workflows/release.yml` builds a Windows executable and ZIP then tries to create a GitHub Release; it does not sign the output or emit an attested BLAKE3 package manifest.
- `crates/voxel-client/examples/frame-cost.rs` is a useful measured offscreen example: it warms up, runs frame batches, prints medians and FPS, and measures the same renderer/readback. It does not compare measurements with a committed baseline/threshold and is not called by CI. This is an instrument, not a performance regression gate.
- The project handoff itself lists alpha gates as incomplete and states that no signature, visible client run, alpha artifact, release claim or fresh independent review was verified.
- No full-history secret scan or GitHub Release asset was observed in the inspected current CI/release source and public release listing. This is an absent-public-evidence finding, not a claim that secrets exist.

### 3.3 Recovery is not "regenerate until green"

The materials digest refusal is an integrity gate doing its job. The correct recovery is to identify which bytes the digest was originally computed over, inspect the exact source/provenance and line endings, determine whether the source files or generated tables changed, and then regenerate only through the recorded materials-generator operation with before/after digest and output evidence. The `materials-regeneration` feature explicitly bypasses digest verification for that build so the generator can run; that path must be ticketed and tightly isolated, then every normal build must rerun with the feature disabled and the gate restored. Repeatedly changing file endings, regenerating tables or retagging without preserving the previous digests is not an acceptable recovery.

## 4. Required DevKit refusals for publication and questions

Before any publication act, the DevKit must know:
- source project and authority;
- current canonical root and repository/remotes;
- public/private owner rule and any recorded per-project exception;
- Git object format and compatibility mapping;
- current and historical secret scan receipts;
- license/provenance/third-party obligations;
- current family gates and dependency closure;
- public release and app-store package identities;
- artifact BLAKE3 digest and Ed25519 signer/trust path;
- target Windows/phone clients and their witness requirements;
- current material questions, their classes and dependencies.

The DevKit refuses:
- private-first creation when the family public default applies;
- any publication when current/history scan is missing, stale, incomplete or has findings;
- unapproved history rewrite or destructive tag movement;
- a release generated from a different source SHA than the approved ticket and signed package manifest;
- unsigned, untrusted or dependency-incomplete family packages;
- failed CI, failed performance thresholds, incomplete external docs, unresolved required owner decision or missing client witness;
- describing a tag, successful push or build artifact as a published release when GitHub has no release and no asset;
- asking the owner a question that current family/project evidence already answers.

## 5. Required Shploingus remediation ticket

Shploingus Clean must have a project-local CUA/Axis ticket for a full recovery audit, not an improvised one-line fix. Its work units must cover:
1. local-vs-GitHub source comparison and repository object-format diagnosis;
2. materials source bytes, provenance, digest and generator recovery;
3. full current and historical secret scan;
4. Rust skill conflict (Rustdoc/safety comments versus family external-document policy);
5. package signing backend and BLAKE3/Ed25519 integration boundary;
6. complete native-client test and actual visible-client witness;
7. reproducible frame-time/performance baseline plus a CI regression threshold for supported hardware profiles;
8. project docs/reference generation and public API coverage;
9. CI/release workflow and immutable tag policy;
10. signed public release and downstream Popit/Restore client access.

A successful build only closes the build work unit. It does not close the release, performance, security, documentation, signature or client witness units.

## 6. Evidence and limits

- Secure Shell Restore HYPERGRILL v2: `alacripose/secure-shell-restore/docs/SECURE-SHELL-RESTORE@1.HYPERGRILL.md`, format v2, source blob `ea1b002cdd7add6349ace729befa1bb96a2fc556`.
- Hyperskill: `alacripose/hyperskill/SKILL.md`, version 0.1.0, blob `dd9e1d34de64a3a1a41454f621d4fe7fb61b3219`; `source-records/hypergrilling.md`, blob `dfba8274792716d391d9639652b057e9cf96b123`.
- Brass Meridian: `tools/questions-6.mjs` blob `6129e6696a3be116b3995d78dfc4b2eedbace8fd`; `state/questions-6.0.jsonl` blob `4e8de64149376d5daddbf9eac4163d357235f1d9`; `tools/reconcile-6.mjs` blob `b2d2aeb5efaa930ed5581eba1e83b5150d6a369c`; `ledger/reconciliation/phase-06.jsonl` blob `2d38d87b60787aad7e63b49f9356bceaafb02152`.
- Shploingus: `docs/HYPERGRILLING.md` blob `c9806692f1606e6093980648ff49266793269c3b`; `docs/HANDOFF.md` blob `619ae628d52d7c953f683c43b46098b1dfd47e89`; `AGENTS.md` blob `8c78a64ca5b4aa899ce382e444a6728811ed531e`; current `main` head `c0a205d661e1fffe2cb1d9ffa0eb6f6977972724`.
- Git SHA-256 transition: https://git-scm.com/docs/hash-function-transition — current documentation describes `compatObjectFormat=sha1` and bidirectional mappings; this is a compatibility mode requiring actual repo configuration, not a guarantee that a particular local checkout is already configured.
- GitHub SHA-256 support: https://github.com/orgs/community/discussions/212994 — opened 2026-11-13 and unanswered; community replies report SHA-1-only hosting. This is not an official GitHub product statement.
- User-provided publication transcript: source evidence of the proposed private-first visibility choice and unapproved Git history rewrite; not an independently witnessed local command/result transcript.
- Public Shploingus current release: repo visibility public; no GitHub Release object; latest tag is annotated and unsigned; latest CI/release workflows failed as stated. The local drive checkout and current runtime game were not accessed by this audit.
