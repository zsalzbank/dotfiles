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
├── install.sh              # symlinks config into $HOME; fetches git helper scripts
└── bash/
    ├── .bash_profile       # loader — sources everything in ~/.bashrc.d/*.sh
    └── bashrc.d/
        ├── 00-env.sh       # EDITOR, NX_*, BASH_SILENCE_DEPRECATION_WARNING
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

## Secrets

This repo manages **no** secrets. Keep API keys and other private values in a
file outside the repo (e.g. `~/.bashrc.d/99-local.sh`, which is gitignored).
