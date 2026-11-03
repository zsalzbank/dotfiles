update_skills_repo() {
  local repo="/home/canals/repositories/skills"
  local branch status

  if [[ ! -e "$repo/.git" ]]; then
    info "skills repo not present; skipping update"
    return 0
  fi
  if ! branch="$(git -C "$repo" symbolic-ref --quiet --short HEAD)" || [[ "$branch" != master ]]; then
    info "skills repo is not on master; skipping update"
    return 0
  fi
  if ! status="$(git -C "$repo" status --porcelain --untracked-files=all --ignore-submodules=none)"; then
    info "could not check skills repo status; skipping update"
    return 0
  fi
  if [[ -n "$status" ]]; then
    info "skills repo has local changes; skipping update"
    return 0
  fi
  if ! GIT_TERMINAL_PROMPT=0 timeout 60s git -C "$repo" pull --ff-only --no-rebase --no-autostash origin master; then
    info "could not fast-forward skills repo; continuing with existing skills"
    return 0
  fi
  info "updated skills repo"

  if command -v codex >/dev/null 2>&1; then
    # Codex caches local plugins, including when the version stays the same.
    if timeout 30s codex plugin add canals@canals-skills; then
      info "refreshed Codex skills plugin"
    else
      info "could not refresh Codex skills plugin; continuing"
    fi
  fi
}

update_skills_repo
