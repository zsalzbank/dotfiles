#!/usr/bin/env bash
#
# install.sh — symlink dotfiles into $HOME and fetch the git helper scripts.
#
# Safe to re-run (idempotent). Backs up any pre-existing real files it would
# replace to "<file>.backup.<timestamp>". Manages no secrets.

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

echo "Done. Open a new shell or run: source ~/.bash_profile"
