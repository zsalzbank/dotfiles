# Devspaces workspace hooks: copy the shared lib + every per-event hook onto the
# personal volume (/mnt/personal/hooks/), where the in-pod `devspaces agent`
# runtime discovers and runs them. Two hook families live here:
#
#   pr-status-changed/*  react to a PR I opened changing (CI, review comments,
#                        merge conflict) by typing a command into the running
#                        Claude session (via `devspaces agent send-message`).
#   shutdown/*           run at pod teardown (stop/destroy) — e.g. back up
#                        Claude sessions to /mnt/personal before the pod goes away.
#
# Installs them all DISABLED — enable per workspace with `devspaces hooks enable`
# (add `--global` to enable for every workspace). Each hook dir under hooks/ maps
# to one devspaces hook event; hooks/lib/ is shared code, not an event.

install_devspaces_hooks() {
  if [[ ! -d /mnt/personal ]]; then
    info "/mnt/personal not present; skipping devspaces hooks"
    return 0
  fi

  local hooks_root="/mnt/personal/hooks"

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
  rm -f "$hooks_root/pr-status-changed"/*.sh "$hooks_root/lib/claude-inject.sh" 2>/dev/null || true

  # Shared lib. Lives under hooks/lib (NOT an event dir), so the dispatcher and
  # `devspaces hooks list` — both keyed on the fixed event-type list — ignore it.
  # Imported (not exec'd), so no +x needed.
  local lib_dest_dir="$hooks_root/lib"
  mkdir -p "$lib_dest_dir"
  local f name
  for f in "$REPO_DIR"/hooks/lib/*; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f")"
    copy_hook_file "$f" "$lib_dest_dir/$name"
    info "installed hook lib -> $lib_dest_dir/$name"
  done

  # Per-event hooks (executable). Iterate every event dir under hooks/ (all but
  # lib/) so a new event family needs no change here — just drop its dir in.
  local event_dir event dest
  for event_dir in "$REPO_DIR"/hooks/*/; do
    event="$(basename "$event_dir")"
    [[ "$event" == "lib" ]] && continue
    dest="$hooks_root/$event"
    mkdir -p "$dest"
    for f in "$event_dir"*; do
      [[ -f "$f" ]] || continue
      name="$(basename "$f")"
      copy_hook_file "$f" "$dest/$name" +x
      info "installed hook $event/$name -> $dest/$name"
    done
  done

  info "devspaces hooks installed (disabled). Enable per workspace with e.g.:"
  info "  devspaces hooks enable ci-failures.py review-comments.py merge-conflict.py"
  info "  devspaces hooks enable backup-sessions.py   # shutdown: back up sessions"
}

install_devspaces_hooks
