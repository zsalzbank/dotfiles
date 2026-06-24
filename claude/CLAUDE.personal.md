# Personal instructions

- Never make a PR or commit unless explicitly asked to. Exception: you may commit and push minor changes to an existing PR when fixing a CI problem.
- Never commit or push on your own. After making fixes or changes, wait for me to explicitly tell you to commit/push — this applies to everything, including skills like `plan-from-pr-comments` and `plan-from-ci-failures` that might otherwise do it automatically.
- Never post a comment to any third-party service (GitHub, Notion, Figma, etc.) unless I specifically ask you to.
- Don't write code comments unless something is unclear about *why* the code is being done that way. Comments describing *what* the code does are not helpful when reading the code itself conveys the same information.
- When making a pull request, link back to the devspaces workspace that created it. Add this line to the PR body: `Created from devspaces workspace [open devspace](https://devspaces.int.canals.ai/workspaces/$DEVSPACES_WORKSPACE_NAME)` — substitute the value of the `$DEVSPACES_WORKSPACE_NAME` env var (e.g. `jolly-beaver-47uk`) in the URL. If `$DEVSPACES_WORKSPACE_NAME` is unset (not in a devspaces workspace), skip this.
