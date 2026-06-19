# Git-aware prompt: green cwd, ":<branch>", bold prompt char.
# git-prompt.sh is installed to ~/.git-prompt.sh by install.sh.

[[ -r ~/.git-prompt.sh ]] && source ~/.git-prompt.sh
PROMPT_COMMAND='PS1_CMD1=$(__git_ps1 ":%s")'; PS1='\[\e[92m\]\w\[\e[0m\]${PS1_CMD1}\[\e[1m\]\\$\[\e[0m\] '
