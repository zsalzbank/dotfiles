# Shell profile + the modular ~/.bashrc.d config directory it loads.

# link <source> <target>: symlink source -> target, backing up any real target.
link() {
  local src="$1" dest="$2"
  if [[ -L "$dest" ]]; then
    rm -f "$dest"            # replace an old symlink (ours or otherwise)
  elif [[ -e "$dest" ]]; then
    info "backing up existing $dest -> $dest.backup.$TIMESTAMP"
    mv "$dest" "$dest.backup.$TIMESTAMP"
  fi
  ln -s "$src" "$dest"
  info "linked $dest -> $src"
}

link "$REPO_DIR/bash/.bash_profile" "$HOME/.bash_profile"
link "$REPO_DIR/bash/bashrc.d" "$HOME/.bashrc.d"

# Ensure interactive non-login shells (typical on Linux) load the profile too.
if [[ -f "$HOME/.bashrc" ]] && grep -q 'source ~/.bash_profile' "$HOME/.bashrc"; then
  : # already wired up
else
  printf '\n# Load login-shell config in interactive shells too (added by dotfiles).\n[[ -r ~/.bash_profile ]] && source ~/.bash_profile\n' >> "$HOME/.bashrc"
  info "wired ~/.bashrc to source ~/.bash_profile"
fi
