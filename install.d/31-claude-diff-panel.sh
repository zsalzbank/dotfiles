# Keep the Claude Code diff panel from auto-opening.
#
# `diffSidebarOpen` lives in ~/.claude.json (the global config), not in
# settings.json — it is absent from the settings-overridable key list, so the
# settings merge in 30-claude.sh cannot carry it. Unset, the panel auto-opens at
# >=144 columns; false disables the auto-open path entirely while leaving /diff
# working as a manual toggle.

install_claude_diff_panel_off() {
  local dest="$HOME/.claude.json"

  if ! ensure_jq; then
    info "jq unavailable; cannot set diffSidebarOpen in $dest"
    return 0
  fi

  if [[ ! -f "$dest" ]]; then
    echo '{"diffSidebarOpen":false}' > "$dest"
    info "created $dest with diffSidebarOpen=false"
    return 0
  fi

  if [[ "$(jq -r '.diffSidebarOpen // empty' "$dest")" == "false" ]]; then
    info "diffSidebarOpen already false in $dest"
    return 0
  fi

  local tmp; tmp="$(mktemp)"
  jq '.diffSidebarOpen = false' "$dest" > "$tmp" && mv "$tmp" "$dest"
  info "set diffSidebarOpen=false in $dest"
}

install_claude_diff_panel_off
