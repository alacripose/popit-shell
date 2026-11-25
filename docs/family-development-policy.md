# Family development policy — the bridge, the drivers, and the ledgers

**Owner instruction, verbatim:** *"from now on all development in the family projects must be done
honestly using the bridge with the debian machine over dialin with their local model, managing the cua
drivers for their side of projects, while the projects here run through the windows client for logging
failures and ledgers properly in the programs"*.

## The split

| side | what runs there | what it is for |
|---|---|---|
| `cua-driver` (the family Debian box; its address is `runlogs/toast/debian-host.txt`, a local fact and not a repository constant) | the family's local model, the CUA drivers, the tools that need Steam/Proton | the work and the judgement: projects and code are managed on that side, not watched through a window here |
| this machine (Windows) | the client programs | running the project, and logging its failures and ledger rows in the programs themselves |

A development pass is not two habits. It is one loop: the bridge carries the project state to the
Debian side, the local model and the drivers do the work there, the result comes back, and the Windows
program writes the row that says what was measured. A row written by hand after the fact is not the
program logging its own failure and is not what this policy asks for.

## The channel and its surface

- `tools/bridge.py` (this shell) and `F:\Documents\mc3-client13\tools\bridge.py` read the host from
  `POPIT_DEBIAN_HOST` / `POPIT_DEBIAN_USER` or `runlogs/toast/debian-host.txt` / `debian-user.txt`, and
  reach the box through WSL's Debian distro with `/root/m0/id_ed25519`. `sh -s` on stdin, never
  `sh -c` argv: `wsl.exe` joins its arguments into one command line and the quoting is lost.
- Dialin is where the bridge is used: `dialin` hosts the `bridge` surface the same way it hosts the
  IDE, and the shell's own bridge pages (`bridge.py`, `mind_bridge.py`, `axis_bridge.py`) speak to the
  same box.

## The bridge app package

The bridge is a real package, not a page:

```
app-bridge@1+blake3:a481bdbba69c43b8a90c561ca8487ce64144c048c4fa82a77b79b341ebad4493
```

It is signed by the settings publisher key, verified against `runlogs/toast/envelope-trust.json`,
declares `kind: window` with the four furniture regions (`bar`, `status`, `body`, `foot`), derives
`theme`, `layout`, `motion` and `dpi` from the settings package, and carries **no stylesheet of its
own** — the look, the buttons, the chrome and the motion are the package's (`contour-theme.css`,
`toast.css`, `package.js`). Its springboard tile is signed with it: `ui/phone.js` lists `bridge` in
`APP_SURFACE`, so the launcher shows a tile only while that identity verifies.

## The failure sweep

`tools/family_failures.py scan` reads every ledger surface in the family projects
(`ledger/*.jsonl`, `logs/*.jsonl`, `logs/authority/*.jsonl`, `runlogs/**/*.jsonl`, `data/*.jsonl`) and
the hypergrilling documents under `Documents\.superpowers\hypergrilling`, and groups the failures by
their named refusal. `serve`/`probe` publish and check the Popit page over loopback.

Measured 2026-11-25: **168 rows · 49 codes · 4 projects**, every row traceable to a file and a line in
`runlogs/family-failures.json` and `docs/family-failures.md`. The largest groups are
`fail:gate` ×51 (deadlock-model-forge), `refused` ×14 and `blocked` ×11 from the hypergrilling docs,
`fail:compile` ×4, `fail:blender` ×3.

**What it does not claim.** Rows are counted, not adjudicated: the sweep says how often a name repeats
and where, not whether each instance was correct. A `fail:gate` row is the project gate refusing a
state, and the reading of whether that refusal was right is the gate's own record.
