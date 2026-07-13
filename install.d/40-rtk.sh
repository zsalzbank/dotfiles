# rtk (Rust Token Killer): install to ~/.local/bin, enable the global Claude
# Code rewrite hook, telemetry explicitly disabled.
#
# Ordering: runs after 30-claude.sh so `rtk init`'s patch to
# ~/.claude/settings.json layers on top of the already-merged base settings.

# rtk pin (known-good, audited). We install this EXACT release instead of a
# moving "latest", so every workspace runs identical, vetted bytes. Provenance:
#  - v0.43.0 SOURCE was read end-to-end (no network egress except opt-in, off).
#  - The tarball hash below also matches upstream's published checksums.txt.
#  - The binary hash was recorded from that verified artifact (2026-07-08).
# These hashes are the AUTHORITY: install re-verifies every copy against them
# and aborts on any mismatch — it never falls back to an unpinned build. To bump
# the version: download the new release, re-audit the source, then update the
# version + both hashes here. Linux x86_64 only (the platform these workspaces
# run); other targets are skipped rather than silently pulling an unpinned build.
RTK_VERSION="v0.43.0"
RTK_TARGET="x86_64-unknown-linux-musl"
RTK_TARBALL_SHA256="ff8a1e7766496e175291a85aeca1dc97c9ff6df33e51e5893d1fbc78fea2a609"
RTK_BIN_SHA256="f160611f3baee17fe4eb3a04c56a8bc3d15fec4274d8838016088d4776c6f628"

# sha256_of <file>: print the file's SHA-256 (Linux sha256sum or macOS shasum).
# Returns non-zero if neither tool exists.
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    return 1
  fi
}

# rtk is a CLI proxy that compresses dev-command output before it reaches the
# model, cutting token usage.
#
# Supply-chain hardening — acquisition order (each path re-verifies the hash):
#   1. ~/.local/bin/rtk already matches the pinned hash        -> done
#   2. durable cache /mnt/personal/.rtk/<ver>/rtk matches      -> copy it
#   3. download the pinned release tarball, verify tarball AND
#      binary hashes, then seed the cache                      -> copy it
# Any mismatch aborts the rtk setup (we refuse to install unverified bytes) but
# never aborts the whole dotfiles run. ~/.local/bin is wiped on rebuild;
# /mnt/personal persists, so after the first download future workspaces install
# straight from cache.
install_rtk() {
  local rtk_bin="$HOME/.local/bin/rtk"
  local rtk_config_dir="$HOME/.config/rtk"
  local rtk_config="$rtk_config_dir/config.toml"
  local cache_dir="/mnt/personal/.rtk/$RTK_VERSION"
  local cache_bin="$cache_dir/rtk"
  local tmp=""

  # Only linux x86_64 is pinned. Refuse to silently pull an unpinned build.
  if [[ "$(uname -s)" != "Linux" || ! "$(uname -m)" =~ ^(x86_64|amd64)$ ]]; then
    info "rtk: no pinned build for $(uname -s)/$(uname -m); skipping"
    return 0
  fi
  if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then
    info "rtk: no sha256 tool available; refusing to install unverified binary"
    return 0
  fi

  # 1) Already installed and matching the pin? Nothing to do.
  if [[ -x "$rtk_bin" && "$(sha256_of "$rtk_bin")" == "$RTK_BIN_SHA256" ]]; then
    info "rtk $RTK_VERSION already installed and hash-verified"
  else
    local verified=""
    # 2) Durable verified cache in /mnt/personal (survives rebuilds).
    if [[ -f "$cache_bin" && "$(sha256_of "$cache_bin")" == "$RTK_BIN_SHA256" ]]; then
      verified="$cache_bin"
      info "rtk: using cached hash-verified binary ($cache_bin)"
    else
      # 3) Download the PINNED release (exact version URL, not "latest").
      tmp="$(mktemp -d)"
      local url="https://github.com/rtk-ai/rtk/releases/download/${RTK_VERSION}/rtk-${RTK_TARGET}.tar.gz"
      info "rtk: downloading pinned $RTK_VERSION ($RTK_TARGET)"
      if ! curl -fsSL "$url" -o "$tmp/rtk.tar.gz"; then
        info "rtk: download failed (network/egress?); skipping rtk setup"
        rm -rf "$tmp"; return 0
      fi
      if [[ "$(sha256_of "$tmp/rtk.tar.gz")" != "$RTK_TARBALL_SHA256" ]]; then
        info "rtk: TARBALL HASH MISMATCH — refusing to install (expected $RTK_TARBALL_SHA256)"
        rm -rf "$tmp"; return 0
      fi
      # Reject absolute / traversal paths before extracting (CWE-22).
      if tar -tzf "$tmp/rtk.tar.gz" | grep -qE '^/|(^|/)\.\.(/|$)'; then
        info "rtk: archive contains unsafe paths; refusing to extract"
        rm -rf "$tmp"; return 0
      fi
      if ! tar -xzf "$tmp/rtk.tar.gz" -C "$tmp"; then
        info "rtk: extraction failed; skipping rtk setup"
        rm -rf "$tmp"; return 0
      fi
      if [[ "$(sha256_of "$tmp/rtk")" != "$RTK_BIN_SHA256" ]]; then
        info "rtk: BINARY HASH MISMATCH — refusing to install (expected $RTK_BIN_SHA256)"
        rm -rf "$tmp"; return 0
      fi
      # Seed the durable cache so future workspaces skip the download entirely.
      if mkdir -p "$cache_dir" 2>/dev/null && cp "$tmp/rtk" "$cache_bin" 2>/dev/null; then
        chmod +x "$cache_bin"
        printf '%s  rtk\n' "$RTK_BIN_SHA256" > "$cache_dir/rtk.sha256" 2>/dev/null || true
        info "rtk: cached hash-verified binary -> $cache_bin"
      fi
      verified="$tmp/rtk"
    fi

    mkdir -p "$HOME/.local/bin"
    cp "$verified" "$rtk_bin"
    chmod +x "$rtk_bin"
    [[ -n "$tmp" ]] && rm -rf "$tmp"

    # Paranoia: re-verify the exact bytes we just installed.
    if [[ "$(sha256_of "$rtk_bin")" != "$RTK_BIN_SHA256" ]]; then
      info "rtk: installed copy failed hash check; removing it"
      rm -f "$rtk_bin"; return 0
    fi
    info "rtk $RTK_VERSION installed and hash-verified"
  fi

  # Write rtk config, only when absent so we never clobber user edits:
  #  - telemetry OFF, explicitly — written before `rtk init` so the (non-
  #    interactive) init sees consent already declined and never prompts. The
  #    RTK_TELEMETRY_DISABLED=1 env var (00-env.sh) is the hard override anyway.
  #  - tracking DB relocated onto the durable, cross-workspace share so savings
  #    stats aggregate across all workspaces instead of living in the per-
  #    workspace ~/.local/share (wiped on rebuild). Mirrors RTK_DB_PATH in
  #    00-env.sh. The FULL [tracking] table is required — a partial one fails to
  #    deserialize and would break config load. rtk uses WAL + a 5s busy_timeout
  #    and best-effort writes, so concurrent workspaces are safe.
  if [[ ! -f "$rtk_config" ]]; then
    mkdir -p "$rtk_config_dir" "/mnt/personal/.rtk/data"
    cat > "$rtk_config" <<'TOML'
[telemetry]
enabled = false
consent_given = false

[tracking]
enabled = true
history_days = 90
database_path = "/mnt/personal/.rtk/data/history.db"
TOML
    info "wrote rtk config (telemetry off, shared tracking DB) -> $rtk_config"
  fi

  # Enable globally: a PreToolUse hook that transparently rewrites commands
  # through rtk for every Claude Code project. --auto-patch edits
  # ~/.claude/settings.json without prompting (it backs the file up first).
  if "$rtk_bin" init -g --auto-patch >/dev/null 2>&1; then
    info "enabled rtk globally (Claude Code rewrite hook installed)"
  else
    info "rtk init failed; binary installed but global hook not enabled"
  fi
}

install_rtk
