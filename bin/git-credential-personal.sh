#!/bin/sh
# git credential helper: supplies a personal GitHub PAT from the environment.
# Configured as the repo-local credential.helper for this dotfiles repo so the
# personal PAT is used instead of any machine/org-provided GitHub credential
# (e.g. a devspaces GitHub App token that lacks access to personal repos).
#
# Setup (per machine, run by install.sh or by hand):
#   git config credential.helper ""        # reset inherited helpers
#   git config --add credential.helper "$PWD/bin/git-credential-personal.sh"
# Then export PERSONAL_GITHUB_PAT=<token> in your environment.
[ "$1" = get ] || exit 0
[ -n "$PERSONAL_GITHUB_PAT" ] || exit 0
echo "username=zsalzbank"
echo "password=$PERSONAL_GITHUB_PAT"
