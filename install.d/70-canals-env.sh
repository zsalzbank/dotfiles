# Canals app env overrides (.env.local), read by services and `make auto`.

# Seed canals app env into the repo-root .env.local, which packages/config
# loadEnvVars() reads into process.env for every service and `make auto`. Done
# here (not in shell rc) because the boot chain that launches the services is
# non-interactive and never sources ~/.bash_profile. Runs before the per-repo
# start hook fires `make auto`. Idempotent: only appends a key it doesn't have.
install_canals_env_local() {
  local env_local="$HOME/repositories/canals/.env.local"
  [[ -d "$(dirname "$env_local")" ]] || { info "canals repo absent; skipping .env.local"; return 0; }
  local kv
  for kv in "NO_MATCHING=1"; do
    if ! grep -q "^${kv%%=*}=" "$env_local" 2>/dev/null; then
      printf '%s\n' "$kv" >> "$env_local"
      info "added ${kv%%=*} to $env_local"
    fi
  done
}

install_canals_env_local
