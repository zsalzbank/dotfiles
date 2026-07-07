#!/usr/bin/env bash
#
# install.sh — symlink dotfiles into $HOME and fetch the git helper scripts.
#
# Safe to re-run (idempotent). Backs up any pre-existing real files it would
# replace to "<file>.backup.<timestamp>". Stores no secrets: the GitHub
# credential helper reads the PAT from $PERSONAL_GITHUB_PAT at push time.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"

# Upstream sources for the latest git helper scripts (used as a fallback).
GIT_PROMPT_URL="https://raw.githubusercontent.com/git/git/master/contrib/completion/git-prompt.sh"
GIT_COMPLETION_URL="https://raw.githubusercontent.com/git/git/master/contrib/completion/git-completion.bash"

info() { printf '  %s\n' "$*"; }

# link <source> <target>: symlink source -> target, backing up any real target.
link() {
  local src="$1" dest="$2"
  if [[ -L "$dest" ]]; then
    rm -f "$dest"            # replace an old symlink (ours or otherwise)
  elif [[ -e "$dest" ]]; then
    info "backing up existing $dest -> $dest.backup.$TIMESTAMP"
    mv "$dest" "$dest.backup.$TIMESTAMP"
  fi
  ln -s "$src" "$dest"
  info "linked $dest -> $src"
}

# Ensure jq is available, installing it via apt-get (Ubuntu) if not.
# Returns success only if jq is callable afterward. Call it as an `if` condition
# so a failed install attempt doesn't abort the script (set -e is suppressed for
# functions invoked in a condition).
ensure_jq() {
  if command -v jq >/dev/null 2>&1; then return 0; fi
  info "jq not found; installing via apt-get"
  local sudo=""
  if [[ "$(id -u)" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then sudo="sudo"; fi
  if command -v apt-get >/dev/null 2>&1; then
    $sudo apt-get update -y && $sudo apt-get install -y jq
  else
    info "apt-get not found; please install jq manually"
  fi
  command -v jq >/dev/null 2>&1
}

# Merge the repo's Claude settings into the machine's ~/.claude/settings.json,
# creating it if absent and deep-merging (repo wins on conflicts) if present.
install_claude_settings() {
  local repo_settings="$REPO_DIR/claude/settings.json"
  local dest_dir="$HOME/.claude" dest="$HOME/.claude/settings.json"
  mkdir -p "$dest_dir"
  if [[ ! -f "$dest" ]]; then
    cp "$repo_settings" "$dest"
    info "created $dest"
    return 0
  fi
  if ensure_jq; then
    cp "$dest" "$dest.backup.$TIMESTAMP"
    local tmp; tmp="$(mktemp)"
    jq -s '.[0] * .[1]' "$dest" "$repo_settings" > "$tmp" && mv "$tmp" "$dest"
    info "merged Claude settings into $dest (backup: $dest.backup.$TIMESTAMP)"
  else
    info "jq unavailable; cannot safely merge $dest. Add this manually:"
    cat "$repo_settings"
  fi
}

# Install the Claude Code plugins I always want available. Plugins live under
# ~/.claude, which is wiped on every workspace rebuild, so reinstall them here.
# Idempotent: `claude plugin install` is a no-op when already installed. Skips
# entirely when the claude CLI isn't on PATH, and never aborts the script.
install_claude_plugins() {
  if ! command -v claude >/dev/null 2>&1; then
    info "claude CLI not found; skipping plugin install"
    return 0
  fi
  local plugin
  for plugin in figma@claude-plugins-official slack@claude-plugins-official; do
    if claude plugin install "$plugin" --scope user >/dev/null 2>&1; then
      info "installed Claude plugin $plugin"
    else
      info "could not install Claude plugin $plugin (network or marketplace unavailable?)"
    fi
  done
}

# Wire the repo-local GitHub credential helper so pushes from this dotfiles repo
# authenticate with a personal PAT over HTTPS, instead of any org/machine GitHub
# credential that can't reach personal repos. Only runs when $PERSONAL_GITHUB_PAT
# is set; the token itself is never written to disk.
install_git_credential_helper() {
  if [[ -z "${PERSONAL_GITHUB_PAT:-}" ]]; then
    info "PERSONAL_GITHUB_PAT not set; skipping GitHub credential helper setup"
    return 0
  fi
  local helper="$REPO_DIR/bin/git-credential-personal.sh"
  chmod +x "$helper"
  # SSH can't traverse an HTTP-only proxy and won't use a credential helper, so
  # rewrite an ssh origin to HTTPS.
  local origin
  origin="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null || true)"
  if [[ "$origin" == git@github.com:* ]]; then
    git -C "$REPO_DIR" remote set-url origin "https://github.com/${origin#git@github.com:}"
    info "rewrote origin to HTTPS: $(git -C "$REPO_DIR" remote get-url origin)"
  fi
  # Reset inherited helpers (the empty value must come first so it clears helpers
  # from earlier config files), then add ours.
  git -C "$REPO_DIR" config --unset-all credential.helper 2>/dev/null || true
  git -C "$REPO_DIR" config --add credential.helper ""
  git -C "$REPO_DIR" config --add credential.helper "$helper"
  info "configured repo-local GitHub credential helper -> $helper"
}

# Mark the dotfiles repo as a git safe.directory. It lives on the /mnt/personal
# share owned by nobody:nogroup, so without this git refuses operations here with
# a "dubious ownership" error. ~/.gitconfig is wiped on rebuild, so re-apply each
# run. Idempotent: --add is a no-op when the entry already exists.
mark_dotfiles_safe_directory() {
  git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$REPO_DIR" && {
    info "safe.directory already includes $REPO_DIR"
    return 0
  }
  git config --global --add safe.directory "$REPO_DIR"
  info "marked $REPO_DIR as a git safe.directory"
}

# Copy the personal CLAUDE.md into the durable per-user share so it's @imported
# by the workspace's org CLAUDE.md. Only runs when /mnt/personal is mounted.
install_claude_personal() {
  local src="$REPO_DIR/claude/CLAUDE.personal.md"
  local dest="/mnt/personal/CLAUDE.personal.md"
  if [[ ! -d /mnt/personal ]]; then
    info "/mnt/personal not present; skipping CLAUDE.personal.md"
    return 0
  fi
  cp "$src" "$dest"
  info "installed $dest"
}

# Seed canals app env into the repo-root .env.local, which packages/config
# loadEnvVars() reads into process.env for every service and `make auto`. Done
# here (not in shell rc) because the boot chain that launches the services is
# non-interactive and never sources ~/.bash_profile. Runs before the per-repo
# start hook fires `make auto`. Idempotent: only appends a key it doesn't have.
install_canals_env_local() {
  local env_local="$HOME/repositories/canals/.env.local"
  [[ -d "$(dirname "$env_local")" ]] || { info "canals repo absent; skipping .env.local"; return 0; }
  local kv
  for kv in "NO_MATCHING=1"; do
    if ! grep -q "^${kv%%=*}=" "$env_local" 2>/dev/null; then
      printf '%s\n' "$kv" >> "$env_local"
      info "added ${kv%%=*} to $env_local"
    fi
  done
}

# install_git_script <target> <upstream-url> <candidate-path>...
# Copy the first existing candidate to <target>; otherwise download upstream.
install_git_script() {
  local dest="$1" url="$2"; shift 2
  if [[ -e "$dest" && ! -L "$dest" ]]; then
    info "backing up existing $dest -> $dest.backup.$TIMESTAMP"
    mv "$dest" "$dest.backup.$TIMESTAMP"
  fi
  local candidate
  for candidate in "$@"; do
    if [[ -r "$candidate" ]]; then
      cp "$candidate" "$dest"
      info "installed $(basename "$dest") from $candidate"
      return 0
    fi
  done
  info "no system copy of $(basename "$dest") found; downloading latest from upstream"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$dest"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$dest" "$url"
  else
    echo "ERROR: need curl or wget to download $(basename "$dest")" >&2
    return 1
  fi
  info "installed $(basename "$dest") from $url"
}

echo "Installing dotfiles from $REPO_DIR"

# 1) Shell profile + the modular config directory it loads.
link "$REPO_DIR/bash/.bash_profile" "$HOME/.bash_profile"
link "$REPO_DIR/bash/bashrc.d" "$HOME/.bashrc.d"

# Ensure interactive non-login shells (typical on Linux) load the profile too.
if [[ -f "$HOME/.bashrc" ]] && grep -q 'source ~/.bash_profile' "$HOME/.bashrc"; then
  : # already wired up
else
  printf '\n# Load login-shell config in interactive shells too (added by dotfiles).\n[[ -r ~/.bash_profile ]] && source ~/.bash_profile\n' >> "$HOME/.bashrc"
  info "wired ~/.bashrc to source ~/.bash_profile"
fi

# 2) Git helper scripts: prefer a system copy, else the latest from upstream.
#    Candidate paths cover common Linux locations and macOS (CLT / Xcode).
install_git_script "$HOME/.git-prompt.sh" "$GIT_PROMPT_URL" \
  /usr/share/git-core/contrib/completion/git-prompt.sh \
  /usr/share/bash-completion/completions/git-prompt.sh \
  /etc/bash_completion.d/git-prompt.sh \
  /Library/Developer/CommandLineTools/usr/share/git-core/git-prompt.sh \
  /Applications/Xcode.app/Contents/Developer/usr/share/git-core/git-prompt.sh

install_git_script "$HOME/.git-completion.bash" "$GIT_COMPLETION_URL" \
  /usr/share/git-core/contrib/completion/git-completion.bash \
  /usr/share/bash-completion/completions/git \
  /etc/bash_completion.d/git \
  /Library/Developer/CommandLineTools/usr/share/git-core/git-completion.bash \
  /Applications/Xcode.app/Contents/Developer/usr/share/git-core/git-completion.bash

# 3) Claude Code settings (e.g. disable commit/PR attribution).
install_claude_settings

# 4) Personal CLAUDE.md into the durable per-user share.
install_claude_personal

# 4b) Claude Code plugins (figma, slack) — only when the claude CLI is present.
install_claude_plugins

# 4c) Mark the dotfiles repo as a git safe.directory (dubious-ownership fix).
mark_dotfiles_safe_directory

# 5) GitHub credential helper (only when PERSONAL_GITHUB_PAT is set).
install_git_credential_helper

# 6) Canals app env overrides (.env.local), read by services and `make auto`.
install_canals_env_local

echo "Done. Open a new shell or run: source ~/.bash_profile"
