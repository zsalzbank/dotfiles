# Devspaces workspace hooks: PR-status events that type into the running Claude
# session (see hooks/ in this repo and devspaces .claude/hooks.md).
#
# Copies the shared lib + per-event hooks (Python) onto the personal volume,
# where the in-pod `devspaces agent` dispatcher runs them. The actual injection
# is done by `devspaces workspaces send-message`, which the hooks shell out to.
# Installs them DISABLED — enable per workspace with `devspaces hooks enable`.

install_devspaces_hooks() {
  if [[ ! -d /mnt/personal ]]; then
    info "/mnt/personal not present; skipping devspaces hooks"
    return 0
  fi

  local hooks_root="/mnt/personal/hooks"
  local lib_src="$REPO_DIR/hooks/lib/hooklib.py"
  local lib_dest_dir="$hooks_root/lib"
  local event_src="$REPO_DIR/hooks/pr-status-changed"
  local event_dest="$hooks_root/pr-status-changed"

  # copy_hook_file <src> <dest> [+x]: install one file, backing up a differing
  # real file first (mirrors the repo's backup convention).
  copy_hook_file() {
    local src="$1" dest="$2" exec="${3:-}"
    if [[ -e "$dest" && ! -L "$dest" ]] && ! cmp -s "$src" "$dest"; then
      info "backing up existing $dest -> $dest.backup.$TIMESTAMP"
      mv "$dest" "$dest.backup.$TIMESTAMP"
    fi
    cp "$src" "$dest"
    [[ "$exec" == "+x" ]] && chmod +x "$dest"
  }

  # Drop any stale bash-era files from an earlier version of this feature so the
  # dispatcher doesn't run both.
  rm -f "$event_dest"/*.sh "$lib_dest_dir/claude-inject.sh" 2>/dev/null || true

  # Shared lib. Lives under hooks/lib (NOT an event dir), so the dispatcher and
  # `devspaces hooks list` — both keyed on the fixed event-type list — ignore it.
  # Imported (not exec'd), so no +x needed.
  mkdir -p "$lib_dest_dir"
  copy_hook_file "$lib_src" "$lib_dest_dir/hooklib.py"
  info "installed hook lib -> $lib_dest_dir/hooklib.py"

  # Per-event hooks (executable).
  mkdir -p "$event_dest"
  local f name
  for f in "$event_src"/*.py; do
    [[ -e "$f" ]] || continue
    name="$(basename "$f")"
    copy_hook_file "$f" "$event_dest/$name" +x
    info "installed hook $name -> $event_dest/$name"
  done

  info "devspaces hooks installed (disabled). Enable per workspace with:"
  info "  devspaces hooks enable ci-failures.py review-comments.py merge-conflict.py"
}

install_devspaces_hooks
