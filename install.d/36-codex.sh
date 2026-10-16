install_codex_settings() {
  local python=python3
  if ! "$python" -c 'import tomlkit' >/dev/null 2>&1; then
    local venv="${XDG_DATA_HOME:-$HOME/.local/share}/dotfiles-codex/venv"
    python="$venv/bin/python"
    if command -v uv >/dev/null 2>&1; then
      if [[ ! -x "$python" ]]; then
        uv venv "$venv"
      fi
      if ! "$python" -c 'import tomlkit' >/dev/null 2>&1; then
        uv pip install --quiet --python "$python" 'tomlkit==0.13.3'
      fi
    else
      if ! "$python" -m pip --version >/dev/null 2>&1; then
        python3 -m venv "$venv"
      fi
      if ! "$python" -c 'import tomlkit' >/dev/null 2>&1; then
        "$python" -m pip install --quiet 'tomlkit==0.13.3'
      fi
    fi
  fi
  local dest="${CODEX_HOME:-$HOME/.codex}/config.toml"
  "$python" "$REPO_DIR/bin/merge-codex-config.py" \
    "$REPO_DIR/codex/config.toml" "$dest" "$TIMESTAMP"
  info "merged Codex settings into $dest"
}

install_codex_settings
