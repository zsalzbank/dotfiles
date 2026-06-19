# Shell functions and aliases.

# nb <name>: create a new branch off the latest origin/master.
nb() {
  git fetch origin && git checkout -b "$1" origin/master
}
