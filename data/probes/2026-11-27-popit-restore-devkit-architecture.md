# 2026-11-27 — Popit / Restore / Axis / Developer Kit source probe

## Scope and method

Read-only source inventory against the following public repository revisions:

| Source | Pin |
|---|---|
| `popit-shell` baseline | `5ee3b9b228312c9b77b2effab47a6f666df957c6` |
| `secure-shell-restore` | current `main` at inspection |
| `secure-shell` | current `main` at inspection |
| `hero-retarget-workbench` | current `main` at inspection |

This probe records source facts only. It did not run the Windows Qt desk, Debian Axis, an OTA phone client, CI, package signing or CUA automation. It does not claim a runtime witness.

## Findings

1. **Relationship corrected:** Popit Shell is the modern client/application implementation of Secure Shell and Restore for Windows desktop and OTA phone clients. Restore remains the package/trust/stream/restore architecture; Axis on Debian remains the authorization and CUA driver authority. Popit's app signer/store is retained as its modern client-app layer, not replaced by a second Restore writer.
2. **One existing Popit digest implementation:** `dialin.py` exposes canonical JSON and `package_digest` with BLAKE3, length-framed manifest and payload. Settings and app packages already call it. No new package digest implementation is to be introduced.
3. **Schema-domain distinction:** Popit `dialin.PACKAGE_SCHEMA` is derived from the `secure-shell.package` family declaration; Restore's reference module defines the literal `secure-shell.package/1` domain. They share the canonical package lineage but are not proven byte-for-byte interchangeable. Preserve the Popit domain; write explicit compatibility tests and do not auto-convert.
4. **Pin gap:** `app_base.subscription()` embeds the Settings identity in the signed app payload. However `app_package.py::publish()` writes app manifest `dependencies: []` and formats the visible identity without a dependency suffix. This is not pin-complete under Restore R-A. The app package needs an explicit Settings dependency and canonical pin-complete identity.
5. **Ed25519 is already shared:** `envelope.py` implements Ed25519 signing and verification. Settings and AppPackages use the Settings publisher key and the same trust registry. Preserve this single Popit app/system publisher path; private keys remain outside Git and logs.
6. **Settings base is present but not yet a full app factory:** `app_base.py` signs a mutable Settings subscription and current controls/project digests. However `toast.py::app_page()` copies the whole body from the shared `toast.html`; that file contains several app panels and `toast.js` contains their mode controllers. This is not independently composed app bodies in the shared Settings-owned window.
7. **Pending audit can still appear verified:** `AppPackages.publish()` may set `ui_audit: pending`; `verify()` returns `verified: true` without requiring a passing audit, and the phone tile path checks verified/launch proof. Store verification must require an exact-digest passing audit and client witness before a package is launchable.
8. **MCP has an unrestricted escape hatch:** `toast.py::Handler.mcp()` registers `debian.command` as a root command string. There is no typed family development tool group. That must be replaced by Axis-ticketed, bounded capabilities; no arbitrary command/path/file-write verb may remain.
9. **Axis driver capability gap:** current Secure Shell `server/axis-driver.mjs` declares `witness` and `learning-apply`. The Axis has ticket/attestation/receipt structure, but general project source editing, build and app development are not implemented by this reference node driver. Do not claim them present; add ticketed bounded capabilities and tests.
10. **Freebuff composer read must be agent-owned:** the previous timer-based probe was not an agent read. The DevKit operation must be invoked by the active Freebuff agent, return actual UI Automation text separately from placeholder, preserve focus, never type/submit, and have no polling loop.
11. **Cross-project regression transfer:** Workbench `AGENTS.md` and `AGENTS-LOG.md` record no-heredoc enforcement, retained patch probes, installed-client verification, fused hero graph structure and the Werewolf→Shiv/Tengu→Haze plus aim-matrix pipeline scope. These are family examples for capability-level failure reuse, not text to duplicate as an independent domain rulebook.

## Immediate gates / refusals

- Do not publish a new app with empty Settings dependency pins.
- Do not publish a new app by copying the multipurpose `toast.html` body.
- Do not accept pending UI audit as launchable.
- Do not expose `debian.command` or an alias for arbitrary root execution.
- Do not authorize direct MCP writes, heredocs, arbitrary process matching or app signing.
- Do not claim a CUA act, Axis ticket, client witness or Freebuff text read without the matching receipt.

## Evidence state

- Source inspected: present.
- New architecture map: created in `docs/family-mcp-devkit.md`.
- Project rules: created in top-level `AGENTS.md`.
- Runtime implementation: not performed by this probe.
- Tests/CI: not run by this probe.
- Windows/Qt, Debian Axis and phone witnesses: absent.
