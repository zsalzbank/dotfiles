# gh-triage: symlink the notification cleanup CLI.

install_gh_triage() {
  local bindir="$HOME/.local/bin"
  mkdir -p "$bindir"

  local dest="$bindir/gh-triage"
  if [[ -L "$dest" ]]; then
    rm -f "$dest"
  elif [[ -e "$dest" ]]; then
    info "backing up existing $dest -> $dest.backup.$TIMESTAMP"
    mv "$dest" "$dest.backup.$TIMESTAMP"
  fi
  ln -s "$REPO_DIR/bin/gh-triage" "$dest"
  info "linked $dest"

  if [[ -z "${GITHUB_NOTIFICATIONS_PAT:-}" ]]; then
    info "note: GITHUB_NOTIFICATIONS_PAT unset; gh-triage needs a classic PAT with the notifications scope"
  fi
}

install_gh_triage
