# Git helper scripts (prompt + completion): prefer a system copy, else download
# the latest from upstream. Candidate paths cover common Linux locations and
# macOS (CommandLineTools / Xcode).

GIT_PROMPT_URL="https://raw.githubusercontent.com/git/git/master/contrib/completion/git-prompt.sh"
GIT_COMPLETION_URL="https://raw.githubusercontent.com/git/git/master/contrib/completion/git-completion.bash"

# install_git_script <target> <upstream-url> <candidate-path>...
# Copy the first existing candidate to <target>; otherwise download upstream.
install_git_script() {
  local dest="$1" url="$2"; shift 2
  if [[ -e "$dest" && ! -L "$dest" ]]; then
    info "backing up existing $dest -> $dest.backup.$TIMESTAMP"
    mv "$dest" "$dest.backup.$TIMESTAMP"
  fi
  local candidate
  for candidate in "$@"; do
    if [[ -r "$candidate" ]]; then
      cp "$candidate" "$dest"
      info "installed $(basename "$dest") from $candidate"
      return 0
    fi
  done
  info "no system copy of $(basename "$dest") found; downloading latest from upstream"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$dest"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$dest" "$url"
  else
    echo "ERROR: need curl or wget to download $(basename "$dest")" >&2
    return 1
  fi
  info "installed $(basename "$dest") from $url"
}

install_git_script "$HOME/.git-prompt.sh" "$GIT_PROMPT_URL" \
  /usr/share/git-core/contrib/completion/git-prompt.sh \
  /usr/share/bash-completion/completions/git-prompt.sh \
  /etc/bash_completion.d/git-prompt.sh \
  /Library/Developer/CommandLineTools/usr/share/git-core/git-prompt.sh \
  /Applications/Xcode.app/Contents/Developer/usr/share/git-core/git-prompt.sh

install_git_script "$HOME/.git-completion.bash" "$GIT_COMPLETION_URL" \
  /usr/share/git-core/contrib/completion/git-completion.bash \
  /usr/share/bash-completion/completions/git \
  /etc/bash_completion.d/git \
  /Library/Developer/CommandLineTools/usr/share/git-core/git-completion.bash \
  /Applications/Xcode.app/Contents/Developer/usr/share/git-core/git-completion.bash
