# GitHub credential helper for the dotfiles repo (only when PERSONAL_GITHUB_PAT
# is set).

# Wire the repo-local GitHub credential helper so pushes from this dotfiles repo
# authenticate with a personal PAT over HTTPS, instead of any org/machine GitHub
# credential that can't reach personal repos. The token itself is never written
# to disk (the helper reads $PERSONAL_GITHUB_PAT at push time).
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

install_git_credential_helper
