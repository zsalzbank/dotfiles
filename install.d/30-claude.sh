# Claude Code setup: settings merge, personal CLAUDE.md, and always-on plugins.
# The settings merge runs first here so it is in place before 40-rtk.sh patches
# ~/.claude/settings.json with the rtk hook.

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

install_claude_settings
install_claude_personal
install_claude_plugins
