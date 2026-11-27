# Family source documentation and comment policy

**Status:** Proposed family-wide contract for TICKET-0009. This is a source-backed design record, not evidence that the enforcement tools or generated reference pages exist yet.

## 1. Purpose

A developer should be able to understand a family project from its external documentation, package contracts, schemas, tests and rendered evidence without reading thousands of lines of source to discover how it works.

Source files contain executable logic and machine-readable declarations. They are not the documentation surface. Explanatory comments, docstrings and AI-authored annotations are not an acceptable substitute for external documentation.

Every family project has a generated, navigable, rustdoc-shaped HTML reference linked from its landing page and available through the Popit client. The reference is separate from the prose/copy audit report:

- `docs/reference/<project>/` — code/API reference and architecture.
- `docs/prose/<project>/` — current family prose and drawn-string audit report.
- `docs/index.html` or the owning landing page — links both surfaces and identifies their source revision.

The Rustdoc comparison is about navigation, symbol coverage, source links, typed signatures and readable generated pages. It does not authorize Rustdoc comments or any other explanatory comment syntax in source files.

## 2. Source-comment rule

### 2.1 Prohibited

No newly authored explanatory source comments or docstrings in any language. This includes:

- natural-language comments before, after or inside a code block;
- comments that restate the next statement, function name, variable or obvious control flow;
- comments that narrate what the agent is doing or what a future reader should infer;
- AI-authored section banners, file headers, motivational phrases, toy summaries, TODO/FIXME/HACK/NOTE prose and "why this works" paragraphs;
- Python module, class and function docstrings used as documentation;
- Rust `//!`, `///` and block doc comments used as documentation;
- Go package and exported-symbol comments used as documentation;
- JavaScript/TypeScript JSDoc and TSDoc blocks;
- comments in HTML, CSS, shell, YAML, TOML, C/C++ or other supported source formats.

A comment is not made acceptable by being short, factual, helpful to an LLM, ignored by the UI prose checker, or placed in a function that is otherwise well-tested. A prose gate is not a licence to write a comment and wait for a later scan.

### 2.2 Narrow machine-syntax exceptions

Only comments that the compiler, interpreter, build system, formatter, linter, or license tooling consumes as a directive may remain. Examples include SPDX/license notices, shebangs, build constraints, embed/generate directives, formatter boundaries and exact linter/type-check suppressions.

These are not general exceptions. The driver must identify the parser-recognized directive and its consumer. A suppression also needs an external ticket or policy reference where the tool supports one. A natural-language explanation appended to a directive is prohibited.

The allowlist is versioned and finite. Unknown directives, unknown comment forms and unrecognized source languages refuse with a named code. There is no free-text "necessary comment" override.

Generated/vendor files are handled through an explicit provenance manifest and are not silently treated as project-authored source. A family driver may not add comments to generated output by hand.

### 2.3 Existing source comments

Existing comments are migration input, not permission to add more. The family driver inventories them by repository, file, language, line, category and digest.

For each meaningful comment:
1. determine whether it describes real behavior or merely repeats code;
2. move useful behavior, constraints, invariants, ownership, refusal semantics or examples into the correct external reference page;
3. remove the source comment through the CUA patch path;
4. verify the source and external page against the same commit and dependency pins.

Junk, duplicate narration and AI filler are deleted without being reproduced elsewhere. Historical reasoning belongs in the project history, ticket or probe, not in current API documentation.

A touched file may not acquire new explanatory comments while legacy comments are being migrated. A migration ticket tracks outstanding files and comment counts; it is not a waiver for new comments.

## 3. How the comment gate works

The gate runs before a source write is applied. It examines the proposed diff and the complete changed source file using a language-aware parser/tokenizer. It does not rely on regular expressions over raw text, because comment-looking sequences can appear inside strings, test fixtures, regular expressions and embedded documents.

Required parser coverage includes every source language admitted by the family project register. Current family inventories include Python, Rust, Go, JavaScript, MJS, TypeScript, TSX, HTML, CSS, JSON, TOML and YAML, with other languages registered as they appear. Embedded languages are parsed separately where applicable.

Refusal codes include:

- `source-comment-added` — a patch adds an explanatory comment or docstring;
- `source-comment-existing` — a changed file retains a comment that its migration ticket requires removing;
- `source-comment-directive-unknown` — a comment is not in the finite machine-directive allowlist;
- `source-language-uncovered` — no approved comment parser exists for the source language;
- `source-parser-failed` — the checker cannot determine the lexical structure safely.

The gate must intercept every authoring route: editor write, patch application, code generation, formatting, generated files and any permitted command capability. A post-write CI check is a second line of defence, not the primary control.

A refusal leaves the target bytes unchanged, records the attempted operation and returns its code, subject and reason. The driver stops the current work unit. It does not retry through a terminal, heredoc, temporary file, alternate editor or direct Git operation.

## 4. External code/API reference

The reference is produced from two inputs:

1. **Machine-derived structure:** language parsers, exported symbol tables, types/signatures, schemas, package manifests, dependency identities, entry points, route/tool registries, test identifiers and measured build artifacts.
2. **External explanations:** Markdown or another declared documentation source under the project's `docs/` tree. These pages explain purpose, behavior, contracts, invariants, authority, state, effects, failure modes, dependencies and examples. They do not duplicate source comments.

The renderer publishes navigable HTML. Each page includes:
- repository, commit, package identity and source/dependency digests;
- project and module map;
- public functions, types, classes, routes, MCP tools and schemas;
- parameter and result types, state changes and side effects;
- authority and capability requirements;
- named refusals and recovery behavior;
- persistent data and lifecycle effects;
- links to relevant tests, fixtures, tickets and evidence;
- links to the exact source symbols and versioned dependencies.

The page is a reference for how to use and reason about the project, not a concatenation of comments or source files. It should let a new contributor locate the owner of a behavior and its tests before they need to inspect implementation lines.

Every exported/public entry point must resolve to a documented reference entry. Internal modules must appear in the module map with their owning responsibility and dependency relationships. Missing public-symbol coverage, stale source digests, broken links or an unregistered language/parser are refusals.

The reference generator does not invent descriptions from symbol names. A symbol whose behavior cannot be established from its declaration, contract, implementation and tests is marked undocumented and assigned to the CUA driver. An agent's guess is not documentation.

## 5. Prose and design skills

These skills have separate jobs. They do not replace the source-comment gate.

| Skill | Required use | Boundary |
|---|---|---|
| `declauding` | Load for external docs, README files, tickets, issue/PR text, changelogs, reports and other prose authored for people. Apply its factual-preservation and register workflow before publication. | Its own scope excludes code and quoted text. Never use it to justify explanatory source comments. |
| `stop-slop` | Load when drafting or reviewing prose and user-facing copy. Apply its directness, specificity, rhythm and anti-pattern checks. | Prose quality pass; it is not a parser, API-doc generator or source-comment detector. |
| `impeccable` | Load for frontend design, redesign, critique, audit, polish, accessibility, responsive behavior, motion and design-system work. | Settings remains the only Popit visual authority. Impeccable improves a Settings-derived client; it does not authorize a private theme, motion system, contour, component library or renderer. Not used for backend-only work. |

The source pins inspected for this audit are:
- Declauding 0.17.0, `oaustegard/claude-skills/declauding/SKILL.md`, source blob `9750e65daa294478158e06daa0d04875966e4746`.
- Stop Slop, `hardikpandya/stop-slop/SKILL.md`, source blob `83f2032fde406e97492ec48ee05ebe46f6403109`. Its current SKILL.md does not declare a version; pin the source revision instead of inventing one.
- Impeccable 4.11.1, `pbakaus/impeccable/plugin/skills/impeccable/SKILL.md`, source blob `3b8f11f8499e7c1412a930d0ebadb2429d3e4df9`.

The family skill registry records source URL, version/revision, content digest, compatibility, installation path and the invocation receipt for each task. Drivers load the skills from the managed family skill directory, currently `<home>/.agents/skills/`, or the registered agent-specific path. A missing, stale or unverifiable required skill is named before the relevant prose/UI task starts.

For Impeccable, the driver loads the project's actual design context before design work. The current skill's setup requires its context command, the task's relevant playbook and its craft-floor guidance immediately before a UI edit. It also requires review of the rendered result at the sizes where the interface ships. The Popit implementation must reconcile that process with the owner's Settings authority: project context and design critique are inputs to the Settings-derived app, not permission to replace its tokens, motion, contour or controls.

For documentation work, the driver records:
- the loaded Declauding and Stop Slop versions/digests;
- the draft/source and final prose digests;
- the deterministic lint result;
- the independent structural/newcomer review result where required by the skill;
- a factual-preservation diff for names, numbers, dates, quotations, claims and links.

For frontend work, record the Impeccable version/digest, the loaded project/design context, relevant playbook/craft-floor receipts, and the resulting UI audit/visual witness. Do not paste skill prompts, verbose skill checklists or skill commentary into source code.

UI strings still live in their appropriate source/data files as executable content, but they are extracted as copy, reviewed through the prose skills and the shared family copy checker, and inserted by the CUA driver. They are not comments or API documentation.

## 6. Distinguish the existing prose report from code documentation

The current `tools/prose_family.py` is a family inventory and prose-report generator. It imports the shared checker, inventories project files, counts drawn strings and emits `docs/prose/<project>/index.html`. That is useful, but it is not a complete code/API reference generator.

The current external page for Popit reports 1,739 drawn strings and 741 hits while its badge says `passed`. In the current worker:
- `inventory()` stores the hit count;
- `render_project()` derives the badge from `job.refusal`, not the hit count;
- `verify()` verifies that the generated page exists and has the expected markers.

Therefore the page's `passed` badge does not mean zero prose hits. It describes the generation workflow's recorded refusal state. The client must show independent states such as `inventory complete`, `copy clean`, `copy held`, `docs current` and `driver blocked`. A page with nonzero unaccepted hits cannot show `copy clean`.

The existing family policy and Brass Meridian's `docs/PROSE.md` say code comments are not part of the ordinary copy scan. The Workbench's `tools/ui_prose.py` explicitly uses Python AST and says comments and identifiers do not count; its Python docstrings are also excluded. Popit's current `cua.py` contains explanatory Chromium/UI Automation comments and docstrings, including the retry explanation that appears in the owner-provided Freebuff example.

The Popit prose report includes a `comment-restates` row, but that single reported category does not establish a complete language-aware prohibition or a pre-write refusal. The family checker implementation at `portal-shell/tools/ui_prose.py` was not available in the inspected public GitHub repositories, so its exact internal rule coverage remains unverified.

The code/API reference therefore has to be a separate deliverable, and the new comment gate has to act before file writes. Neither can be delegated to the existing copy scan.

## 7. Required DevKit workflow

1. Resolve the project and commit through the family project register and CUA driver, not an ad hoc shell search.
2. Load this standard, the project rules, Restore/Axis contracts, matching family failure records and the project's existing external docs.
3. Identify the source language and an installed parser. Unknown or unsupported syntax refuses before authoring.
4. Build the work unit and reference-page update plan. The page must document the changed public contract and cite its tests.
5. Request the exact Axis ticket and driver capability.
6. Have the driver author source changes through the approved patch path. The source-comment parser rejects comments before bytes are written.
7. Have the driver update external docs and run Declauding/Stop Slop for prose. Use Impeccable when the task changes UI.
8. Generate the HTML reference and separate prose/copy report. Link both from the Popit landing page and Developer Kit.
9. Verify public-symbol coverage, source/doc digest parity, stale/broken links, comment-token diff, prose results, build/tests and client witness.
10. Record the actual driver receipt, failed checks and retained patch probe. Commit only after all required gates hold.

No prose baseline, comment allowlist entry, or skip flag may be added just to let a current patch through. A policy change requires a separate owner decision and ticket; a work-unit failure is not grounds to lower the gate.

## 8. Acceptance fixtures

The owning gate must prove at least:

| Fixture | Expected result |
|---|---|
| Python module/function/class docstring added | refuse `source-comment-added` |
| Python inline or full-line explanatory comment | refuse `source-comment-added` |
| Rust `///`, `//!` or block documentation added | refuse `source-comment-added` |
| Go exported-symbol/package comment added | refuse `source-comment-added` |
| JS/TS JSDoc or ordinary explanatory line/block comment added | refuse `source-comment-added` |
| HTML/CSS comment added | refuse `source-comment-added` |
| Shell/YAML/TOML explanatory comment added | refuse `source-comment-added` |
| A string literal containing `//`, `#`, `/*` or `<!--` | do not classify it as a comment |
| License/build/linter directive in the exact registered form | admit only the declared machine directive |
| Unknown comment directive or unsupported source extension | refuse by name |
| A patch adds explanatory text to source and updates no external docs | refuse before writing |
| A changed public API has no external reference entry | refuse the work unit/release gate |
| Reference page source digest differs from the current commit | docs stale; do not show current |
| A prose report has hits but no critical copy-policy refusal | report `copy held`, not `copy clean` |
| A prose page was generated but external-skill receipts are missing | docs remain unverified |
| Heredoc or arbitrary temporary source authoring is attempted | refuse before command execution |

## 9. Evidence and limits

Source findings are recorded in `data/probes/2026-11-27-source-comment-and-docs-gap.md`. The new gate, language parsers, external reference pages, skill loader, updated Popit UI and CUA receipts remain implementation work. No current CI result, client witness or successful driver operation is claimed by this document.

