# Environment variables.

# Silence the macOS "bash is deprecated, switch to zsh" notice (no-op elsewhere).
export BASH_SILENCE_DEPRECATION_WARNING=1

export EDITOR=vim

# Nx
export NX_DAEMON=false
export NX_PARALLEL=8

# Claude Code
export CLAUDE_CODE_SCROLL_SPEED=8

# rtk (Rust Token Killer) — installed to ~/.local/bin by install.sh.
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# Hard telemetry opt-out. config.toml already sets consent_given=false; this env
# var is a belt-and-suspenders override checked before rtk makes any network call.
export RTK_TELEMETRY_DISABLED=1

# Persist rtk's savings/tracking DB on the durable, cross-workspace share so
# stats aggregate across all workspaces (the default ~/.local/share is per-
# workspace and wiped on rebuild). Priority 1 in rtk's DB-path resolution;
# mirrored in config.toml. rtk uses WAL + a 5s busy_timeout and treats tracking
# writes as best-effort, so concurrent workspaces are safe.
export RTK_DB_PATH="/mnt/personal/.rtk/data/history.db"
