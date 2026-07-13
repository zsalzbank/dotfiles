# Mark the dotfiles repo as a git safe.directory (dubious-ownership fix).

# It lives on the /mnt/personal share owned by nobody:nogroup, so without this
# git refuses operations here with a "dubious ownership" error. ~/.gitconfig is
# wiped on rebuild, so re-apply each run. Idempotent: --add is a no-op when the
# entry already exists.
mark_dotfiles_safe_directory() {
  git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$REPO_DIR" && {
    info "safe.directory already includes $REPO_DIR"
    return 0
  }
  git config --global --add safe.directory "$REPO_DIR"
  info "marked $REPO_DIR as a git safe.directory"
}

mark_dotfiles_safe_directory
