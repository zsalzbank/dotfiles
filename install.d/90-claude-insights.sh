# claude-weekly-insights: symlink the weekly-insights CLI onto PATH.
#
# ~/.local/bin is already on PATH (see bash/bashrc.d/00-env.sh, shared with rtk),
# so a symlink there makes `claude-weekly-insights` callable from any shell. The
# script runs Claude Code's built-in /insights over one ISO-week folder of the
# sessions the shutdown hook backs up to /mnt/personal/claude-sessions/.

install_claude_insights() {
  local src="$REPO_DIR/bin/claude-weekly-insights"
  local bindir="$HOME/.local/bin"
  local dest="$bindir/claude-weekly-insights"

  mkdir -p "$bindir"
  if [[ -L "$dest" ]]; then
    rm -f "$dest"
  elif [[ -e "$dest" ]]; then
    info "backing up existing $dest -> $dest.backup.$TIMESTAMP"
    mv "$dest" "$dest.backup.$TIMESTAMP"
  fi
  ln -s "$src" "$dest"
  info "linked $dest -> $src"
}

install_claude_insights
