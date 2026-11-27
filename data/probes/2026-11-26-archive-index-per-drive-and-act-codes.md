# The archive index lied in four ways, and each one is now measured

Date: 2026-11-26. The owner's report was *"the popit shell audit and evidence apps are still refusal
shaped and non functional"*. Read against the app's own records, that was four defects, not a taste
problem.

## 1. One directory budget for every drive

`MAX_DIRECTORIES = 6000` was one counter shared by the whole walk. Measured on the running desk,
`GET /api/toast/session` reported:

```
"index": {"state": "ready", "directories": 6060, "projects": 8, "truncated": true,
          "roots": ["C:\\","D:\\","E:\\","F:\\","H:\\","J:\\"]}
```

Six drives, 6060 directories, eight projects — the budget was spent inside `C:\` and every later
drive was never walked. The index was not "refusal shaped"; it was eight rows long on a machine with
359 project roots under `C:\Users` alone.

**Now:** one budget and one deadline per drive (`MAX_DIRECTORIES = 400000`, `WALK_SECONDS = 300`),
and `roots_detail` reports each drive's directories, projects, seconds, `truncated`, `timed_out` and
the refusal that stopped it. Measured rescan: `C:\` 24392 dirs / 24.8 s, `D:\` 94444 / 98.8 s,
`F:\` 21667 / 300.3 s (timed out, named), `H:\` 529, `J:\` 41, `E:\` 3 — 141,076 directories in
424 s, `truncated: false`.

## 2. An act code was logged as a refusal

`ledger()` set `result = "refused" if code else "recorded"`, so `archive-index-started` — an act the
walk writes about itself — was recorded as a refusal, and `tools/family_failures.py` counted the
app's own index start against the project. Three such rows sat in `runlogs/session-archive/ledger.jsonl`
(07:26:45, 07:27:46, 07:28:08) with `"result": "refused"`.

**Now:** `ACT_CODES = {"archive-index-started", "archive-index-done"}` are `recorded`; a real refusal
code still writes `refused`. The walk also writes `archive-index-done` with its seconds, projects,
directories, truncation and root count, so a finished pass is visible rather than inferred, and
`archive-index-failed` if the walk dies.

## 3. A file cap stopped the bytes

```python
if files > MAX_FILES_PER_PROJECT:   # 20000
    budget["truncated"] = True
    continue                        # ← the stat had already run; the byte was thrown away
```

`C:\Users` read **17.12 GB with 294,164 files** in the index while the independent walk measured
**197.79 GB**. The cap bounds the count, not the size; the size is in hand from the stat that was
just done.

**Now:** the byte is always added, the cap only sets `file_capped`, and `truncated` is reserved for a
directory budget or a deadline. `C:\Users` also reports `nested_projects: 359` — the projects under
it, which a top-level row previously reported as zero.

## 4. Junction points were read as folders

`C:\Users\<account>\Templates`, `Start Menu` and `SendTo` are reparse points; walking them produced six
`PermissionError` rows on the surface for trees that are the same bytes under a second name.

**Now:** a reparse point is skipped in the project walk and in the drive-root loop
(`FILE_ATTRIBUTE_REPARSE_POINT`). The remaining errors are genuine protected system folders
(`C:\Documents and Settings`, `WindowsApps\Deleted`, `D:\found.000`, `H:\Config.Msi`).

## 5. `python -m session_archive rescan` exited before the walk

The CLI called `ensure_index(force=True)`, which starts a daemon thread and answers `indexing`; the
short-lived process then exited and the walk it announced wrote nothing. The CLI now runs `_build()`
itself, writes the index, appends `archive-index-done` and prints the per-drive summary.

## Measured

- `python tools/session_archive_probe.py --fixture` → **10 passed, 0 failed, 0 blocked**.
- `python -m session_archive rescan` → 141,076 directories over six drives in 424 s, per-drive
  `roots_detail`, no false `truncated`, no reparse `PermissionError`.
- `node --check ui/toast.js` → ok; the window's status line now reads
  `N projects · walk cut short` when a drive was cut, and the note line names
  `<drive>:<refusal>` per cut drive (`index.cut()`), so a bounded walk is stated on the surface
  instead of being hidden behind a project count.

## What this does not decide

The index is a map, not a licence: it does not delete, move or claim anything. Space decisions
belong to the drive ledger (`deadlock-model-forge/tools/drive_ledger.py`), which requires a digest
at the destination before a source is removed, and refuses WSL data by name.
