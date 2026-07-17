# dotfiles

Personal shell configuration, portable across Linux and macOS.

## Install

```sh
git clone <repo-url> ~/code/dotfiles
cd ~/code/dotfiles
./install.sh
```

Then open a new shell (or `source ~/.bash_profile`).

`install.sh` is idempotent — re-run it any time. It backs up any real files it
would replace to `<file>.backup.<timestamp>`.

## Layout

```
dotfiles/
├── install.sh              # thin orchestrator — sources install.d/*.sh in order
├── install.d/              # one file per install feature (see "Install steps")
│   ├── 10-shell.sh         # symlink bash profile + ~/.bashrc.d, wire ~/.bashrc
│   ├── 20-git-scripts.sh   # fetch git-prompt.sh / git-completion.bash
│   ├── 30-claude.sh        # Claude settings merge, personal CLAUDE.md, plugins
│   ├── 40-rtk.sh           # install + verify pinned rtk, enable it, telemetry off
│   ├── 50-git-safe-directory.sh  # mark this repo a git safe.directory
│   ├── 60-git-credential.sh      # repo-local GitHub PAT credential helper
│   ├── 70-canals-env.sh    # seed canals .env.local overrides
│   └── 80-devspaces-hooks.sh     # install PR-status hooks to /mnt/personal/hooks
├── bin/                    # helper scripts (e.g. git-credential-personal.sh)
├── claude/                 # settings.json + CLAUDE.personal.md installed by 30
├── hooks/                  # devspaces pr-status-changed hooks (installed by 80)
│   ├── lib/hooklib.py            # payload parse + episode dedup + detached inject
│   └── pr-status-changed/        # review-comments / merge-conflict / ci-failures (Python)
└── bash/
    ├── .bash_profile       # loader — sources everything in ~/.bashrc.d/*.sh
    └── bashrc.d/
        ├── 00-env.sh       # EDITOR, NX_*, rtk env (RTK_DB_PATH, telemetry off)
        ├── 10-prompt.sh    # git-aware PS1 prompt
        ├── 20-git.sh       # git tab-completion
        └── 30-functions.sh # shell functions (nb, ...)
```

## How it loads

`install.sh` symlinks:

- `bash/.bash_profile` → `~/.bash_profile`
- `bash/bashrc.d/`     → `~/.bashrc.d/`

`~/.bash_profile` then sources every `~/.bashrc.d/*.sh` in order. macOS terminals
run login shells and read `~/.bash_profile` directly; most Linux terminals run
interactive non-login shells, so the installer also appends a line to `~/.bashrc`
that sources `~/.bash_profile`.

## Adding config

Drop a new `NN-name.sh` file in `bash/bashrc.d/` (the numeric prefix sets load
order) and re-run `install.sh` if the directory symlink isn't in place yet.

For machine-specific settings that shouldn't be committed, create
`~/.bashrc.d/99-local.sh` — it loads last and is gitignored.

## Install steps

`install.sh` is a thin loader: it defines the shared helpers (`info`,
`$REPO_DIR`, `$TIMESTAMP`) and then sources every `install.d/*.sh` in filename
order. Each module owns one feature and both defines and runs its own logic.
Add a step by dropping a new `NN-name.sh` in `install.d/` — no edit to
`install.sh` needed. Modules run in the same shell under `set -euo pipefail`, so
they share those helpers; the numeric prefix encodes order where it matters
(e.g. `40-rtk.sh` runs after `30-claude.sh` so rtk's hook layers on top of the
merged Claude settings).

## Git helper scripts

`10-prompt.sh` and `20-git.sh` rely on git's `git-prompt.sh` and
`git-completion.bash`. `install.sh` installs them to `~/.git-prompt.sh` and
`~/.git-completion.bash` by copying from a system location if one exists
(common Linux paths, macOS Command Line Tools / Xcode), otherwise downloading
the latest version from the upstream git repository.

## Claude Code settings

`install.sh` merges `claude/settings.json` from this repo into the machine's
`~/.claude/settings.json`: it creates the file if absent, or deep-merges into it
(repo values win on conflicts, existing settings preserved) using `jq`. If `jq`
isn't installed it's installed via `apt-get` (Ubuntu). Currently this disables
Claude's commit/PR attribution.

## Devspaces PR-status hooks

`80-devspaces-hooks.sh` installs the Python hooks in `hooks/` onto the personal
volume (`/mnt/personal/hooks/`), where the devspaces in-pod agent runs them when
a PR I opened from a workspace changes (a `pr-status-changed` event). Each hook
reacts to the payload and **types a command into the running Claude session** by
shelling out to `devspaces agent send-message` (see below):

| Hook                 | Fires when                          | Injects                                              |
| -------------------- | ----------------------------------- | --------------------------------------------------- |
| `review-comments.py` | PR gains unresolved review comments | `/plan-from-pr-comments`                            |
| `merge-conflict.py`  | PR develops a merge conflict        | `/merge-master`                                     |
| `ci-failures.py`     | checks rollup goes `failure`        | run `plan-from-ci-failures` in a background subagent |

`hooklib.py` parses the event, dedups with per-episode marker files (the
dispatcher delivers at-least-once and re-fires on every rollup change), and
launches `devspaces agent send-message --wait-idle "<text>"` **detached**,
so the hook returns under the agent's 60s timeout while the CLI does the waiting
and typing.

The `devspaces agent send-message` command (in the devspaces CLI) owns the
injection: it resolves the `zmx` session, and with `--wait-idle` injects
immediately if Claude is busy (Claude queues it) or waits until the screen has
been idle (`--idle-secs`, default 30s — i.e. the user paused) otherwise, then
bracketed-pastes + submits. Only the `cli` frontend has a TUI; on web/bot it
no-ops. **Requires a devspaces build that includes `send-message`.**

Hooks install **disabled**. Enable them per workspace:

```sh
devspaces hooks list
devspaces hooks enable ci-failures.py review-comments.py merge-conflict.py
```

Test a hook offline with `DEVSPACES_HOOK_DRYRUN=1 python3 hooks/pr-status-changed/ci-failures.py "$(cat payload.json)"`
(prints what it would inject instead of sending).

## rtk (Rust Token Killer)

`install.d/40-rtk.sh` installs a **pinned, hash-verified** rtk binary (never a
moving "latest"; the version + SHA-256s are the authority and every copy is
re-verified), caches it on `/mnt/personal/.rtk/`, enables the global Claude Code
rewrite hook, and disables telemetry (config + `RTK_TELEMETRY_DISABLED=1` in
`00-env.sh`). rtk's savings DB is relocated to `/mnt/personal/.rtk/data/` (via
`RTK_DB_PATH` + config) so `rtk gain` aggregates across all pods.

`rtk session` and `rtk discover` read Claude Code's transcripts under
`~/.claude/projects`, which are per-pod — so they only ever reflect the current
pod's sessions.

## Secrets

This repo manages **no** secrets. Keep API keys and other private values in a
file outside the repo (e.g. `~/.bashrc.d/99-local.sh`, which is gitignored).
