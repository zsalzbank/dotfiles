---
name: erp-probe
description: Write, fix, or extend an ERP probe — a standalone bash script that hits a live Eclipse / P21 / Infor instance to settle a question the code can't answer. Use whenever the task involves creating or changing a probe, or when someone asks to "probe" an ERP, verify an org's ERP configuration or permissions, confirm what an ERP field or status actually does, or test an ERP call against sandbox or production before shipping a change. Also use when asked for a probe "like the others" or "like the existing ones" — this captures those conventions so they don't have to be re-explained.
---

# ERP probes

Write (or fix) a standalone ERP probe script that answers a question about a real
ERP instance, and hand it over ready to run.

A probe is a self-contained bash script that talks to a live ERP (Eclipse, P21,
Infor) to settle a question the code can't answer — what a field does, whether a
status is inert, whether an org is configured for a feature. It is the thing that
turns "I think" into "I checked".

## Where the conventions live

`~/repositories/canals` is the app; the probes live in
`/mnt/personal/planning/canals-inventory-network/` — ~78 of them, named
`<erp>_probe_<question>.sh` (`eclipse_probe_interim_status.sh`,
`p21_probe_price_override_authority.sh`, `infor_probe_create_product.sh`).

**Read the most recent probe for the same ERP before writing anything** and copy
its shape. Don't invent a new one; these are heavily converged and the user asks
for "like the others" every single time.

## Non-negotiables

- **Pick the credential convention from the audience, and say which you picked.**
  There are two, and getting it wrong bakes an org's credential into a file that
  leaves the building.

  *Internal probe I run myself* (`<erp>_probe_<question>.sh`, 44 of them) —
  ciphertext embedded in the target table:

  ```bash
  target_row() {   # host|user|encrypted-password|env
    case "$1" in
      kendall-sbx)  echo 'https://kg-dev-api.kendallgroup.com|CANALSAI|<enc>|sandbox' ;;
      kendall-prod) echo 'https://kg-api.kendallgroup.com|CANALSAI|<enc>|production' ;;
      *) return 1 ;;
    esac
  }
  ```

  Get the encrypted value from the org record via the read-only `postgres-*` MCP.
  Keep the `PLAINPASS_<inst>` override.

  *Anything handed to a customer, or run against an org whose keys I don't hold*
  (`<erp>_verify_customer_setup.sh`) — **no baked ciphertext at all.** Auth, host
  and proxy all arrive as flags: `--host`, `--user`, `--pass` or `--enc-pass`,
  `--canals-repo`. `p21_verify_customer_setup.sh:12` states the rule outright.

- **The decrypt helper must reject the CLI's own failure text.** `pnpm cli decrypt`
  writes `ELIFECYCLE Command failed` to **stdout**, so a bare `| tail -n1` captures
  that as the password and a missing `AUTOMATOR_API_KEY` then reports itself as an
  auth rejection from the ERP. Copy the guard verbatim:

  ```bash
  decrypt_value() {   # ciphertext  env
    local out status
    out=$( cd "$CANALS_REPO" && pnpm cli decrypt "$1" -e "$2" -r "$DECRYPT_REASON" 2>/dev/null )
    status=$?
    [[ $status -ne 0 ]] && return 1
    out=$(printf '%s' "$out" | tail -n1)
    [[ -z "$out" || "$out" == *ELIFECYCLE* || "$out" == *"Command failed"* ]] && return 1
    printf '%s' "$out"
  }
  ```

- **One paste-ready command, no assembly.** The user runs these on their **Mac**,
  not in the pod. End with the exact single line to run — real values, no
  placeholders, nothing to stitch together from two places:

  ```
  PROXY_SANDBOX=http://sandbox-pritunl:8888 CANALS_REPO=~/code/canals \
    bash ~/Downloads/<probe>.sh 2>&1 | tee /tmp/<probe>.log
  ```

- **Read-only by default; writes are opt-in behind `--apply`.** State the verdict on
  its own line in the header (`✅ READ-ONLY` or `WRITES`). A write-capable probe
  defaults to a dry run that prints the exact payload it *would* send, and only
  `--apply` actually sends it. Close with a banner naming precisely what gets
  created and on which targets (`⚠️ --apply: this CREATES …` vs
  `DRY RUN (no --apply): …`). Print created ids so they can be cancelled. Only write
  when I've asked to exercise a write path.

- **Never shrink the MANUAL / NOT CHECKED section.** Verify scripts end with a tail
  listing what could not be checked — no input, or the read it needed was
  unavailable. That section exists so a run can't look complete when things went
  unchecked. Don't trim it to make output tidier.

- **Both environments.** Support sandbox and production instances via the target
  table and `TARGETS`, with `PROXY_SANDBOX` / `PROXY_PRODUCTION` / `PROXY`.

- **It does the whole job itself.** No "now go click this in the UI", no manual
  step in the middle. If it needs a token, an order, a second line — the probe
  creates them.

- **macOS *and* Linux.** It runs on the user's laptop, so no GNU-only invocations
  without a BSD fallback:

  ```bash
  date -u -d "+${DAYS} days" +%Y-%m-%d 2>/dev/null || date -u -v+"${DAYS}"d +%Y-%m-%d
  ```

- **No hardcoded org identity in logic.** Instance rows are the one place specifics
  belong. Keep customer/branch/product as `<VAR>_<inst>` env-overridable defaults.

- `set -euo pipefail`, a `ccurl` wrapper with `--max-time` and the optional proxy,
  and HTTP status captured and printed for every call — a probe that hides a 400 is
  worse than no probe.

- **Never name a variable `COLUMNS`.** Bash owns it (terminal width) and clobbers it
  silently. Use `COLUMNS_OVERRIDE`.

## The header comment

Copy the existing shape: one line saying what question it answers, then **why it
exists** (the decision or bug that made the question matter, with PR numbers and
any live observation), then whether it writes, then `Env:` and `Usage:` blocks.
This is the one place verbose prose is wanted — it's what makes a probe re-runnable
in three weeks.

## Steps

- Pin down the question. One probe, one question — if there are three, say so and
  ask whether to write three.
- Read the newest probe for that ERP and reuse its helpers verbatim.
- Look up the instance's host/user/encrypted-password from the org record via the
  read-only `postgres-*` MCP for the right environment.
- Write the script into `/mnt/personal/planning/canals-inventory-network/`
  (durable — the pod is not).
- **Attach it** with the `add_attachment` MCP tool so it can be downloaded, then
  print the single run command.
- After the user pastes results back: record the findings in the relevant planning
  doc, and keep the probe's own commentary out of anything customer- or
  channel-facing.

## Constraints

- Don't run it against production yourself. These are handed over and run locally.
- Never print a decrypted password, and never echo the plaintext into the log.
- If the question can be answered from the DB or the code, say so instead of
  writing a probe.
