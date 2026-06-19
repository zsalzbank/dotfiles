# ~/.bash_profile — managed by dotfiles repo
#
# This is just a loader. Real config lives in ~/.bashrc.d/*.sh (symlinked from
# the dotfiles repo). Drop a new NN-name.sh file in there to add a category;
# a gitignored ~/.bashrc.d/99-local.sh is the place for machine-specific bits.

if [[ -d ~/.bashrc.d ]]; then
  for _rc in ~/.bashrc.d/*.sh; do
    [[ -r "$_rc" ]] && source "$_rc"
  done
  unset _rc
fi
