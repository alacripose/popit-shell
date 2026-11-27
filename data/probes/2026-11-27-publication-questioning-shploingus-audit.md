# 2026-11-27 — family questioning, public publication and Shploingus release audit

## Scope and evidence boundary

This is a read-only public-source audit prepared for Popit TICKET-0010. It examines public GitHub copies of Popit Shell, Secure Shell Restore, Hyperskill, Brass Meridian and Shploingus Clean. The user-provided publishing transcript is treated as an input reproduction, not as an independently observed local command trace.

No local drive, Windows client, Debian Axis, CUA driver, local Git object database, running game or physical/remote downstream client was accessed. No source was changed in the audited project repositories. No secret scan was run here, and no claim is made that Shploingus contains a secret.

## 1. Family questioning lineage

### Source pins

- Secure Shell Restore `docs/SECURE-SHELL-RESTORE@1.HYPERGRILL.md`: blob `ea1b002cdd7add6349ace729befa1bb96a2fc556`, format v2, dated 2026-11-04.
- Hyperskill public `SKILL.md`: version `0.1.0`, blob `dd9e1d34de64a3a1a41454f621d4fe7fb61b3219`; `source-records/hypergrilling.md`: blob `dfba8274792716d391d9639652b057e9cf96b123`, observed 2026-09-24.
- Brass Meridian `tools/questions-6.mjs`: blob `6129e6696a3be116b3995d78dfc4b2eedbace8fd`; `state/questions-6.0.jsonl`: blob `4e8de64149376d5daddbf9eac4163d357235f1d9`; `tools/reconcile-6.mjs`: blob `b2d2aeb5efaa930ed5581eba1e83b5150d6a369c`; `ledger/reconciliation/phase-06.jsonl`: blob `2d38d87b60787aad7e63b49f9356bceaafb02152`.
- Shploingus Clean `docs/HYPERGRILLING.md`: blob `c9806692f1606e6093980648ff49266793269c3b`, 2,636 lines, current file's last numbered round is Round 18 dated 2026-10-03.

### What each mechanism actually does

1. Shploingus retains its own dated project question/answer record, with follow-up passes and evidence traces. It is a project record, not the current family-wide evidence-search service.
2. Hyperskill 0.1.0 formalizes material decision types, append-only answers, child uncertainty packets, explicit per-invocation high agency and hard safety/privacy/evidence/authority boundaries. It is an incomplete description of later family implementations.
3. Restore HYPERGRILL v2 makes the CUA driver perform the expensive search first. It classifies questions as `code`, `spec`, `external`, `measure` and `owner`. The driver closes the first four with source evidence or measured experiments; only the owner class escalates.
4. Brass Meridian Questions 6.0 implements a concrete project question record and independent answer reconciliation. The generator has 100 pre-authored stable IDs in five rounds and outputs both Markdown and JSONL. A separate 100-row reconciliation record classifies 77 consistent, 9 contradictions and 14 taste decisions. The gate checks full answer coverage and valid evidence rows. This does not replace Restore's evidence-exhaustion loop: the questions generator has fixed rows and does not search the code, drives, stores or web itself.
5. The owner has now set the family-wide user-facing round limit to **at most ten material questions**. Brass Meridian's 20-per-round format is a project-history record, not the current family UI limit.

The Hyperskill documentation should explicitly link the later Restore v2 and Brass Meridian implementations. The DevKit must use the combined workflow: exhaustive CUA search first, then a canonical project interview record and answer-by-answer reconciliation for true owner-only residue.

## 2. Publication decision from the owner

The user's direct instruction (2026-11-27) establishes public publication as the standing family default. Family project agents must not choose private-first or ask the user to repeat public/private for each project. An explicit owner-approved exception must be present in the project decision record to change that default.

This does not authorize exposing secrets or unreviewed content. The safe sequence is: scan current tree and complete Git history; block on findings or missing scan; finish licensing/provenance/tests/performance/signing; then make the public push and signed release. A secret finding does not change the repository to private as a workaround.

The family distribution surfaces remain separate: public Git source; public release executable; Popit signed app package; Restore signed package stream; and actual downstream Windows/phone client access.

## 3. The supplied Shploingus publishing case and the current public project

### Repository and tag

- Repository: `alacripose/shploingus-clean`.
- GitHub repo is currently public; default branch is `main`.
- Current inspected `main` head: `c0a205d661e1fffe2cb1d9ffa0eb6f6977972724`.
- The current annotated `v0.1.0` tag object `b3900ae2a4e3fdfd76349129899ba9cff9bc6a2f` is unsigned and points to commit `b84331a1afe129dcebadfcbdc0ca18b833cf70c9`, not the inspected `main` head.
- The tag target rewrites 59 spectra input files and its message says it stores their bytes verbatim, but no successful workflow witness for that commit was found in the six currently listed runs.
- The public release API returns an empty list: there is no GitHub Release object.

### Current Actions evidence (2026-11-27)

The six latest runs are three `ci` and three `release` runs. All six concluded failure:
- release `46058627731` and CI `46058609707`, both on `c0a205d`;
- release `46058278651` and CI `46058273803`, both on `793ead9c5930709017c6debb94f0aa190898bbab`;
- release `46058100578` and CI `46058093026`, both on `43d39351b6c778cdc7c24ee2bc90b9961521d077`.

On the latest CI run the `Headless tests` step failed. On the latest release run the `Build the executable` step failed; package creation, GitHub Release creation and artifact upload were skipped.

Both latest logs show `crates/voxel-model/build.rs:153` refusing:
- computed spectra-source digest: `8561c7772a0b399d62490fdeef1e5ddf3c86c44f9da9a65589bda2299939617c`;
- recorded spectra digest: `88ed8ac7ae0f011105147e7e5b4a61c64112bd85a1cf0790b772f3cb0fc0289a`.

The mismatch is the observed failure. The public logs do not prove the original cause. The `.gitattributes` change on `main` is an attempted line-ending fix but a subsequent run on `c0a205d` still refused. The later tag commit's byte-exact rewrite has not been shown to pass CI or release.

The same tag name `v0.1.0` was used by release runs against three different commit SHAs. The current tag points to a fourth inspected commit SHA. This is a release-provenance warning and must be reconciled before another tag/release; the audit cannot determine intent from those runs alone.

## 4. Security, API documentation and family identity

- `crates/voxel-package/src/signing.rs` defines `Signer`/`Verifier` and `NoSigningBackend`. `docs/HANDOFF.md` explicitly says no signature has ever been generated or verified, no trust root exists, and no `voxel-envelope` backend is linked. This is not the family's BLAKE3/Ed25519 package system.
- The Shploingus workspace names `sha2` as its sole content identity; the package implementation is SHA-256-based. Its Git object IDs are SHA-1 on GitHub. Neither is a BLAKE3 package digest or an Ed25519 publisher signature.
- The current Shploingus root Cargo manifest, Rust API code, and performance example contain large amounts of explanatory comments and Rustdoc. The project-vendored Rust skills explicitly ask for `///` documentation and `// SAFETY:` comments. These are direct conflicts with the current family rule that source comments/docstrings are not the documentation surface. The skill must be adapted to an external API/safety contract, not followed literally.
- This is a Rust game project with its own documented `voxel-ui` in-game design system. That is distinct from a Popit desk application. The Popit Settings-only rule governs its Popit window/client shell and embedded app surfaces; it does not by itself prohibit a project's own domain-specific in-game UI where that UI is authorized by the project record.
- `docs/HANDOFF.md` says it was updated 2026-10-02 and describes itself as derived, not authority. The project's `docs/HYPERGRILLING.md` was last extended through Round 18 dated 2026-10-03, while the append-only `docs/LEDGER.md` contains a later C-193 entry. The old handoff points to older C-84–C-100 ranges. The DevKit must treat this as a stale summary and read the current authoritative ledger/hypergrill record before planning.

## 5. Performance gate evidence

`crates/voxel-client/examples/frame-cost.rs` is a substantial, useful instrument. It warms up the renderer, times frame render plus readback, measures 120 frames per batch, compares medians across batches and prints FPS at 1280×720 and quarter-resolution. It also measures far terrain and LOD bands.

However:
- it is an example, not an enforced gate;
- the current CI workflow does not invoke `frame-cost`;
- it does not compare against a committed machine/profile baseline or a declared regression threshold;
- there is no Criterion dependency or workspace `benches/` target in the inspected Cargo manifest/tree;
- the `shploingus` and `voxel-client` test targets are excluded from the headless test command.

Therefore performance measurement exists, but the CI performance regression prevention requested by the family is not established by the current workflow.

## 6. Current project gate shape

The current `.github/workflows/ci.yml` runs Windows headless tests excluding `shploingus` and `voxel-client`, then builds `shploingus`. The current release workflow builds a Windows executable, packages it into a ZIP and attempts to create a GitHub Release. Neither workflow source invokes a full-history secret scanner, BLAKE3 release manifest, Ed25519 signer, Popit/Restore admission, performance threshold gate or downstream client witness.

This is an absence-of-source-evidence finding. GitHub account-level secret scanning settings were not inspected, and this audit did not run a secret scan.

## 7. Git object format — corrected technical interpretation

The local user's transcript says that the local repository push failed because the receiving server rejected a SHA-256 repository. Git's current hash-transition documentation describes `extensions.objectFormat=sha256` with `extensions.compatObjectFormat=sha1`, a bidirectional object-ID mapping, and conversion of pushes to a SHA-1 server when compatibility is configured. This must be checked against the actual local repository and Git version. It is not evidence that the user's existing local repository already has a compatible mapping or that GitHub accepts a native SHA-256 repository.

GitHub Community Discussion #212994, opened 2026-11-13, is unanswered; community replies report SHA-1-only repository hosting. This is not an official GitHub support statement.

The agent's proposed fast-export rewrite was premature. A driver must inspect the local object-format and compatibility config, server advertisement and exact push error; test the non-destructive compatibility path in a clone; then escalate any history rewrite or forge choice to the owner. Any authorized rewrite preserves a verified original bundle and old-to-new ref/object map, and records signature/tag/PR/CI fallout. Git object format remains separate from BLAKE3 package identity.

## 8. Required work and limits

The DevKit should create a project-local Axis-ticketed Shploingus recovery campaign covering:
- local worktree versus GitHub source comparison and object-format/compatibility diagnosis;
- materials source provenance, exact bytes, line-ending semantics and digest repair;
- complete current/history secret scan;
- family Rust-skill adaptation and external API/safety reference docs;
- actual BLAKE3/Ed25519 package backend and Restore/Popit trust binding;
- full client tests and a visible client witness;
- measured performance baseline and regression threshold on declared hardware profiles;
- CI, release, immutable signed tags, signed BLAKE3 release manifest and executable;
- downstream Popit/Restore client discovery, verification and installation.

The public repo is online; the current build/release state is not a successful public release. The local drive checkout and current live game runtime remain uninspected. No repair, CUA action, secret scan, package signature, CI rerun, performance test or client install was performed by this probe.
