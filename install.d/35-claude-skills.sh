# Personal Claude skills: symlink every skill dir under claude/skills/ into
# ~/.claude/skills/.
#
# Symlinks rather than copies, and re-linked on every workspace start, because
# ~/.claude is wiped on rebuild while /mnt/personal survives — so the skill body
# has to live in the repo and only the pointer gets recreated. (This is why the
# image's guidance warns against shipping skills as a build COPY into ~/.claude:
# that seeds once at workspace creation and then never refreshes.)
#
# Generic on purpose: drop a new dir under claude/skills/ and it's picked up with
# no change here. `91-gh-triage.sh` also links its own skill; `ln -sfn` to the
# same target makes that harmless.

install_claude_skills() {
  local src_root="$REPO_DIR/claude/skills"
  local dest_root="$HOME/.claude/skills"

  if [[ ! -d "$src_root" ]]; then
    info "no claude/skills/ in the repo; skipping personal skills"
    return 0
  fi

  mkdir -p "$dest_root"

  local dir name dest
  for dir in "$src_root"/*/; do
    [[ -d "$dir" ]] || continue
    name="$(basename "$dir")"
    dest="$dest_root/$name"
    if [[ ! -f "$dir/SKILL.md" ]]; then
      info "skipping $name (no SKILL.md)"
      continue
    fi
    # A real directory here would be someone's own skill of the same name —
    # back it up rather than clobbering it.
    if [[ -e "$dest" && ! -L "$dest" ]]; then
      info "backing up existing $dest -> $dest.backup.$TIMESTAMP"
      mv "$dest" "$dest.backup.$TIMESTAMP"
    fi
    ln -sfn "${dir%/}" "$dest"
    info "linked $dest -> ${dir%/}"
  done
}

install_claude_skills
