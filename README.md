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
│   ├── 35-claude-skills.sh # symlink claude/skills/* into ~/.claude/skills
│   ├── 40-rtk.sh           # install + verify pinned rtk, enable it, telemetry off
│   ├── 50-git-safe-directory.sh  # mark this repo a git safe.directory
│   ├── 60-git-credential.sh      # repo-local GitHub PAT credential helper
│   ├── 70-canals-env.sh    # seed canals .env.local overrides
│   ├── 80-devspaces-hooks.sh     # install workspace hooks to /mnt/personal/hooks
│   └── 90-claude-insights.sh     # symlink claude-weekly-insights onto PATH
├── bin/                    # helper scripts (git-credential-personal.sh, claude-weekly-insights)
├── claude/                 # settings.json + CLAUDE.personal.md installed by 30
│   └── skills/             # personal Claude skills, symlinked into ~/.claude/skills by 35
├── hooks/                  # devspaces workspace hooks (installed by 80)
│   ├── lib/hooklib.py            # payload parse + episode dedup + detached inject
│   ├── pr-status-changed/        # review-comments / merge-conflict / ci-failures (Python)
│   └── shutdown/                 # backup-sessions.py — back up Claude sessions at teardown
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

## Devspaces workspace hooks

`80-devspaces-hooks.sh` installs the Python hooks in `hooks/` onto the personal
volume (`/mnt/personal/hooks/`), where the devspaces in-pod agent discovers and
runs them. Each subdir of `hooks/` (other than `lib/`) is one hook *event*; the
installer walks them generically, so adding a new event family is just dropping
a new dir in `hooks/` — no change to `80-devspaces-hooks.sh`. All hooks are
invoked with the event JSON as `argv[1]` and install **disabled**.

### `pr-status-changed/` — react to a PR I opened changing

Fires when a PR I opened from a workspace changes. Each hook reacts to the
payload and **types a command into the running Claude session** by shelling out
to `devspaces agent send-message` (see below):

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

### `shutdown/` — back up Claude sessions at teardown

`backup-sessions.py` runs at pod teardown (stop *or* destroy), via the devspaces
`shutdown` hook event (see devspaces PR #399). Claude Code's session transcripts
under `~/.claude/projects/` are per-pod and vanish when the pod is torn down;
this copies every transcript into the durable personal share, bucketed by the
ISO week (UTC) of the session's last edit, so a weekly `claude insights` pass can
distill learnings across every workspace:

```
/mnt/personal/claude-sessions/<YYYY-Www>/<session-id>.jsonl
```

See the docstring in `hooks/shutdown/backup-sessions.py` for the full rules
(week bucketing, one-bucket-per-session pruning, why the session UUID is a
sufficient key). Enable it (its trigger runs on the way down, so there's nothing
to "see" until the next stop/destroy):

```sh
devspaces hooks enable backup-sessions.py     # or --global for every workspace
```

Test it offline against the real session data with:

```sh
python3 hooks/shutdown/backup-sessions.py '{"type":"shutdown","toStatus":"stopping"}'
```

> Requires a devspaces build that includes the `shutdown` hook event (PR #399).
> Until that ships, `devspaces hooks list` won't surface it — the file is
> installed and ready regardless.

## Weekly insights (`bin/claude-weekly-insights`)

The other half of the backup hook: analyze the consolidated sessions.
`90-claude-insights.sh` symlinks it to `~/.local/bin/` (already on PATH).
Passes are selectable with `--mode` (comma-separated, `all`, or `weekly`):

```sh
claude-weekly-insights                          # insights, last complete week
claude-weekly-insights --mode weekly            # friction + friction-review
claude-weekly-insights 2026-W30 --mode all      # every pass
claude-weekly-insights '2026-W32..2026-W35' --mode friction   # aggregate a range
claude-weekly-insights --list                   # which weeks exist, and which have real sessions
claude-weekly-insights 2026-W30 --open          # open each report in the File Viewer
```

Reports land in `/mnt/personal/claude-insights/`. The first three shell out to
`claude` and cost tokens; the fourth is local Python and costs seconds.

- **`insights`** → `<week>.html` — Claude Code's built-in `/insights` usage
  report. It only analyzes transcripts under its config dir's `projects/` tree
  and writes to `<config-dir>/usage-data/report.html`, so the script stages the
  week into a throwaway `CLAUDE_CONFIG_DIR` (auth is env-based —
  `ANTHROPIC_API_KEY` — so it survives the switch), runs `claude -p /insights`
  there, and harvests the HTML. Skips subagent (`agent-*`) and trivial sessions,
  so a subagent-only week yields an empty report (`--list` flags which weeks have
  interactive sessions).
- **`permissions`** → `<week>-permissions.md` — the built-in
  `fewer-permission-prompts` skill, pointed at the week and forced report-only
  (its argument overrides the hardcoded `~/.claude/projects` scan root and the
  settings.json write). A prioritized read-only allowlist derived from the week's
  actual Bash/MCP calls.
- **`skills`** → `<week>-skills.md` — mines the week for recurring, repeatable
  workflows and proposes new skills to create.
- **`friction`** → `<week>-friction.md` + `<week>-friction.json` — local, no
  model, seconds even over a month of transcripts. Counts where the week went
  wrong: interrupts (and commands re-run after being killed), corrective
  messages, AskUserQuestion stalls and how often they were rejected, refused tool
  calls, missing commands, hook errors and per-hook latency, context
  compactions, oversized tool results, files re-derived across many sessions,
  subagent cost-vs-return, and which skills actually ran. It also reports which
  skill and file were in play when a correction landed, completion claims the next
  message disputed, corrections repeated inside one session, questions asked in
  more than one session, conventions being re-explained ("like the others" —
  each cluster is a skill nobody wrote down), and hook injections counted
  *before* dedup so repeat firings on one PR stay visible. Read the **Alarms**
  block; the correction-pattern profile is a stable fingerprint week to week and
  says little on its own.

  Messages are read whole, with pasted output stripped at the first `>>`/`====`
  marker and numbered lists split into their individual items — the earlier
  length cap skipped 30% of messages, and slash-command bodies (which arrive as
  user text and read like emphatic instructions) were being counted as
  corrections. Any count taken before that is inflated and length-biased, so
  normalise by interactive session count and don't compare across the fix.
- **`friction-review`** → `<week>-friction-review.md` — the interpretation half,
  and the one worth reading weekly. Hands the model the complete `friction`
  corpus (not a file sample) plus `friction-ledger.md`, a running list of
  findings already reported, and asks only for what's new: failure modes the
  hand-written patterns can't name, corrections that violate a rule already in
  `CLAUDE.personal.md` (meaning that rule needs sharpening), and conventions
  being re-explained often enough to deserve a skill. The ledger is what stops a
  weekly cadence from reprinting the same themes.

Alarms are gated on the last week of available data, because a date-blind alarm
re-reports finished problems: six commands installed in the image kept alarming
for three weeks after the fix landed. Raw totals track how much got *captured*,
not how much went wrong — divide by interactive session count before comparing
weeks.

`-n/--dry-run` prints what each pass would run without spending tokens.

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
