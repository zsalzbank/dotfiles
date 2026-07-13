#!/usr/bin/env bash
#
# install.sh — set up this machine from the dotfiles repo.
#
# Thin orchestrator. It defines the shared helpers/vars, then sources each
# feature module in install.d/ in filename order. To add a feature, drop a new
# NN-name.sh file in install.d/ (copy an existing one for the pattern) — no edit
# to this file needed. Modules run in the SAME shell, so they see `info`,
# `$REPO_DIR`, `$TIMESTAMP`, and `set -euo pipefail`, and any helper an earlier
# module defined. Ordering matters where noted (e.g. rtk after the Claude
# settings merge) — the numeric prefixes encode it.
#
# Safe to re-run (idempotent). Backs up any pre-existing real files it would
# replace to "<file>.backup.<timestamp>". Stores no secrets: the GitHub
# credential helper reads the PAT from $PERSONAL_GITHUB_PAT at push time.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"

# Shared by every feature module.
info() { printf '  %s\n' "$*"; }

echo "Installing dotfiles from $REPO_DIR"

for _module in "$REPO_DIR"/install.d/*.sh; do
  # shellcheck source=/dev/null
  source "$_module"
done
unset _module

echo "Done. Open a new shell or run: source ~/.bash_profile"
