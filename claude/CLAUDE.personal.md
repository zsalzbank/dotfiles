# Personal instructions

> **Editing these instructions:** the source of truth is this file at `/mnt/personal/dotfiles/claude/CLAUDE.personal.md`. The `install.sh` in this dotfiles repo `cp`s it to `/mnt/personal/CLAUDE.personal.md` on every workspace start, so any edit to that generated copy is overwritten. When I ask you to change my personal instructions / dotfiles config, edit THIS file (and the generated copy too if the change should take effect in the current session).

- Never make a PR or commit unless explicitly asked to. Exception: you may commit and push minor changes to an existing PR when fixing a CI problem.
- Never commit or push on your own. After making fixes or changes, wait for me to explicitly tell you to commit/push — this applies to everything, including skills like `plan-from-pr-comments` and `plan-from-ci-failures` that might otherwise do it automatically.
- Never post a comment to any third-party service (GitHub, Notion, Figma, etc.) unless I specifically ask you to.
- Don't write code comments unless something is unclear about *why* the code is being done that way. Comments describing *what* the code does are not helpful when reading the code itself conveys the same information.
- When making a pull request, link back to the devspaces workspace that created it. Add this line to the PR body: `[open devspace](https://devspaces.int.canals.ai/workspaces/$DEVSPACES_WORKSPACE_NAME)` — substitute the value of the `$DEVSPACES_WORKSPACE_NAME` env var (e.g. `jolly-beaver-47uk`) in the URL. If `$DEVSPACES_WORKSPACE_NAME` is unset (not in a devspaces workspace), skip this.
- When creating a new devspaces workspace, first run `devspaces ws list` to see the existing workspaces and their groups. If one of the existing groups clearly fits the new workspace, file it there with `devspaces ws create --group <name>`. Do **not** invent or create a new group — if you can't confidently match an existing group, omit `--group` entirely and let it be ungrouped.
