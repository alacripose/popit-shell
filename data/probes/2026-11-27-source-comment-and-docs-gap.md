# 2026-11-27 — source comments, external reference docs and Freebuff authoring reproduction

## Scope and evidence status

This is a retained source-audit record for TICKET-0009. The Popit, Restore, Axis, Brass Meridian and Hero Retarget Workbench files listed below were inspected through their public GitHub source. The Freebuff sequence is the owner-provided transcript in the conversation.

This is not a Debian Axis/CUA driver receipt. No local file, process, Windows desk, Debian host or phone was operated in this audit. No CI run, live app witness, patch-probe execution or family ledger write is claimed.

## 1. The supplied Freebuff sequence

The transcript contains two scripts written into /tmp with cat/heredoc syntax. It then shows an edit to cua.py, direct Python compilation, a PID obtained by parsing netstat output, taskkill, a curl polling loop and a direct HTTP request to the Popit MCP endpoint.

The edit adds natural-language comments explaining Chromium's accessibility tree warm-up and increases the retry loop. The current Popit cua.py source contains the same explanation around _composer_element(), with an 18-attempt loop and a sleep between attempts.

Against the already documented family rules, the transcript demonstrates several missing preventive boundaries:

- Heredoc authoring was prohibited by the family. The submitted commands must have been rejected before execution.
- Source edits must be performed by an attested CUA driver under an Axis ticket, not by an agent editing a file directly.
- Explanatory source comments and docstrings have no approved authoring exception.
- Process lifecycle requires a registered supervisor identity, exact executable, PID, start time and owned process group. A PID copied from a port listing is insufficient.
- A command receipt must preserve the actual target process exit code. A trailing tail, echo or wrapper cannot replace it.
- A direct MCP HTTP request is not proof of a CUA action. The agent's active task must invoke a declared MCP capability and receive a driver/task receipt.

The user clarified the intended Freebuff composer behavior: the active agent explicitly invokes a read-only composer capability while it is working, to read new text without stopping its current task. It must not poll automatically, steal focus, type or submit.

## 2. Popit prose report status is conflated

Inspected current source:

- tools/prose_family.py — commit/source SHA e4936633b85b2c2a996a6cf8a7b5dadb767c49fc
- docs/prose/popit-shell/index.html — source SHA f3e75c08d677bd3bace05b62086d4ce5798daf0f

The committed Popit report displays 1,739 drawn strings, 741 hits, 104 files and a passed badge.

In tools/prose_family.py, inventory() records job.hits and the extracted copy findings. render_project() chooses its visible state from job.refusal rather than from the hit count. verify() checks that the generated document exists and carries expected markers, then settles the job with the existing refusal state.

Therefore the passed badge proves that the report-generation job did not carry a driver-stage refusal and that a page was written. It does not prove that the copy has zero unaccepted hits. The DevKit must report inventory completion, copy quality, reference coverage and reference freshness as separate states.

## 3. The current prose report is not the API reference

tools/prose_family.py creates docs/prose/<project>/index.html. The page lists source extractors, drawn strings, line numbers and copy-rule hits. It is a useful family copy-audit document, but it does not give the rustdoc-like module/API reference the family needs.

The family-development-policy.md says every project should have external visible HTML documents similar to rustdoc. It also says the rules are imported through one family checker rather than copied into each repository.

The new documentation contract separates:

- docs/prose/<project>/ — extracted user-facing copy, prose findings and copy-state receipt.
- docs/reference/<project>/ — navigable code/API reference generated from language structure, signatures, schemas, dependencies, routes, tools and separately authored external docs.
- docs/ — authored architecture, behavior, contract, lifecycle, authority and refusal explanations.

The reference must not be produced by copying source comments or guessing from function names. Public symbol coverage and documentation digests must be checked against the exact source commit and dependencies.

## 4. Current source comment coverage is incomplete

Hero Retarget Workbench tools/ui_prose.py SHA 9724c59aeed2b46b26a2469c441d18e27a9e9f80 says it uses Python AST and that comments and identifiers do not count. Its copy scan measures user-facing literals, not whether source comments are allowed.

Brass Meridian docs/PROSE.md SHA 79f3a7667b5fc3e5a1ec3a12b4bf78dca197aba9 says code comments are not scanned.

Popit's current cua.py SHA f9b66b46d67a3bf57da9434bf3834578f8b54194 contains explanatory comments/docstrings around the Chromium UI Automation reader. The supplied example aligns with the code around _composer_element(), including the retry explanation.

Popit docs/prose/popit-shell/index.html includes a comment-restates row with one finding. That is not evidence of a general language-aware source-comment prohibition or a pre-write refusal.

The portal-shell/tools/ui_prose.py family checker source was not retrievable through the connected public GitHub integration. Its full internal parser and rule coverage remain unverified. Do not assume it catches all source comments.

## 5. Skills and their distinct scope

Declauding source: https://github.com/oaustegard/claude-skills/tree/main/declauding — version 0.17.0 at the source inspected. Its own instructions cover prose authored for people and explicitly exclude code and quoted text.

Stop Slop source: https://github.com/hardikpandya/stop-slop — a prose editing/review skill, not a code parser or source-comment restriction.

Impeccable source: https://github.com/pbakaus/impeccable — frontend design critique and implementation guidance. It does not override the Popit Settings package as the sole design-system authority.

Consequently, skill use and source-comment enforcement are separate controls. Declauding and Stop Slop must be applied to external prose and user-facing copy. Impeccable applies to frontend/UI tasks. A language-aware pre-write gate separately rejects explanatory comments/docstrings.

## 6. Required implementation

1. Add language-aware tokenizers for every language admitted by the family project register. Parse the proposed diff before applying it.
2. Refuse explanatory comments/docstrings before any file bytes are written. Use a finite allowlist for exact machine directives and required license metadata only.
3. Treat an unsupported source language, parser failure, unknown directive or ambiguous comment as a named refusal.
4. Inventory legacy comments under tickets. Move useful behavior/contracts into external docs and remove the source comments through the CUA patch path. Delete empty narration.
5. Generate a rustdoc-shaped HTML API reference separately from the current prose/copy report.
6. Require complete public-symbol coverage and source/dependency digest parity.
7. Load the prose and UI skills from the managed skill registry and record versions, digests and actual task receipts.
8. Separate inventory_complete, copy_clean, copy_held, reference_current, reference_stale and driver_blocked in the report and UI.
9. Keep all writes, builds, commands, process lifecycle actions and client witnesses under Axis-ticketed CUA driver execution.

## Evidence boundary

Source audit: present. Owner transcript: provided. New family documentation standard: drafted in the ticket branch. Source-comment parser, external API reference generator, skill registry, DevKit UI and runtime refusal integration: not implemented. Debian Axis/CUA action receipt: absent. Windows/Qt client witness: absent. OTA phone witness: absent.
