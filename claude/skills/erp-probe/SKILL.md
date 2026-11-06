---
name: erp-probe
description: Write, fix, or extend an ERP probe — a script that goes through the Canals ERP proxy (Chrome console script, or the local ERP bridge for sandbox) to settle a question about a live Eclipse / P21 / Infor instance that the code can't answer. Use whenever the task involves creating or changing a probe, or when someone asks to "probe" an ERP, verify an org's ERP configuration or permissions, confirm what an ERP field or status actually does, or test an ERP call against sandbox or production before shipping a change. Also use when asked for a probe "like the others" or "like the existing ones" — this captures those conventions so they don't have to be re-explained.
---

# ERP probes

Write (or fix) a probe that answers a question about a real ERP instance, and hand
it over ready to run. A probe is the thing that turns "I think" into "I checked".

Every probe reaches the ERP **through the Canals ERP proxy**
(`/erp-proxy/{orgId}/{erpType}/<path>`). The proxy owns the real ERP credentials
and its permission checks stay authoritative.

## Retired: do not write these

- **No decrypting an org's ERP secret and using it locally.** That is no longer
  supported. No `pnpm cli decrypt`, no `decrypt_value`, no `target_row()` with baked
  ciphertext, no `PLAINPASS_<inst>`, no `--enc-pass`, no `CANALS_REPO` for decrypting.
- **No Pritunl.** No `PROXY_SANDBOX=http://sandbox-pritunl:8888` or any
  `PROXY_*` tunnel variable. Don't hit an ERP host directly.
- The old `<erp>_probe_<question>.sh` scripts that do this are legacy. Don't copy
  their auth. Their *questions* and header prose are still good reference.

## Pick the transport (say which you picked, and why)

| Target | Transport | Notes |
| --- | --- | --- |
| Production, or any org | **Chrome console script** | The only option for production. |
| Sandbox | Chrome console script, **or** the local ERP bridge | The bridge is **sandbox only**. |

Default to the console script. Use the bridge only when the question needs the real
client code path (Eclipse/P21 client logic, native readers, a local integration run)
instead of hand-built HTTP calls, and only against sandbox.

Start from `console-probe-template.js` in this skill's directory
(`/mnt/personal/dotfiles/claude/skills/erp-probe/`). It already has the origin guard,
adjustable pacing, 429 handling, status logging, NOT CHECKED output and results
download, so you only fill in `targets` and the questions. You don't need to read
other probes to write one.

Save the probe wherever the work lives (the task's planning directory, or next to the
code under investigation). There is no required location. Name it
`<erp>_probe_<topic>_erp_proxy.js`.

## Chrome console script

The user opens a tab on the right origin in the Chrome profile logged into Canals
(not impersonating), pastes the script into the console, and sends the downloaded
results back so you can read them.

What the template gives you, and what to keep when you change it:

- One async IIFE. First line guards the origin and throws a clear instruction:
  `https://api.canals.ai` for production, `https://sandbox.api.canals.ai` for
  sandbox. Tell the user which `/ping` page to open.
- Requests go to `${location.origin}/erp-proxy/${orgId}/${erpType}/${path}` with
  `credentials: 'same-origin'`, `Accept: application/json`, and
  `signal: AbortSignal.timeout(60000)`.
- **Pacing:** `window.probePauseMs = 500` by default, read before every request so
  the user can change it mid-run. Give them the console command
  (`window.probePauseMs = 1000`) in the final log line.
- **429:** use the server's actual delay (`retry-after` header, else
  `data.data.retryAfterSeconds`). Record a shared `cooldownUntil` and wait for it
  before any later request. No 30-second floor, no invented exponential backoff.
  If no usable delay comes back, throw and stop. A changed `probePauseMs` never
  shortens a cooldown.
- Print the HTTP status of every call. Never hide a 4xx/5xx. `console.table` a
  summary at the end.
- **Results go back through a download:** build a `Blob` of
  `{at, summary, results}`, trigger an `<a download>`, revoke the URL after 10 s.
  Say the filename in the header and the last log line. The user attaches that file
  (or pastes the summary) back to you.
- Read-only: GET, or POST only for read-style calls (for example an
  `EclipseSubroutine` `ACTION READ`). Anything that writes is opt-in (see below).
- Parameterise orgs, branches and ids in a `targets` array at the top. No
  customer-specific logic below it.
- The script does the whole job. No "now click this in the UI" step.
- Do not log tokens, cookies, or the Canals key.

Hand-over: attach the `.js` file with the `add_attachment` MCP tool, then give the
user the steps in one short block: open `<origin>/ping`, open DevTools console,
paste the file contents, wait for the download, send it back.

## Local ERP bridge (sandbox only)

For when the probe should exercise a real integration client locally. The bridge is
a loopback HTTP relay to the sandbox proxy. Design and usage:
`/mnt/personal/planning/inv-opt-syncs/local-erp-proxy-bridge-plan-20261029.md`
(branch `codex/local-erp-bridge` in the canals repo, `scripts/local_erp_bridge/`).

- ERP base URL becomes `http://erp-bridge.test:18765/erp-proxy/{orgId}/{erpType}`.
  It binds only to `127.0.0.1`. Hardcoded to `https://sandbox.api.canals.ai`. There
  is no production or staging mode, so never offer it for production.
- It needs `CANALS_API_KEY` (an existing user-bound key, from the env or a private
  prompt). Never paste the key into chat or bake it into a file. ERP credentials
  are synthetic: login calls get fixed fake responses, and the real ERP auth stays
  in the proxy.
- Start it on the Mac from the canals repo root:
  `pnpm --filter @canals/scripts exec tsx local_erp_bridge/bridge.ts`
- Local callers run with `NO_PROXY=erp-bridge.test,127.0.0.1,localhost` so the
  loopback traffic is not sent to an HTTP proxy.
- The bridge paces itself (one in-flight request per org, 500 ms spacing), relays
  429 unchanged and holds the org until `Retry-After` expires. It never retries.
  Don't add retries of your own on top, especially for writes.
- A client with a hardcoded auth host, or SQL/ODBC/TCP access, can't go through it.
  Say so rather than promising URL-only compatibility.
- Live compatibility per client is unproven. State that in the hand-over, and
  record what actually worked.

A bridge probe is a script or test command that the user runs on their Mac with the
one-line start command above. Give the exact full command, as `bash ./script.sh`
where it is a shell script.

## Non-negotiables (all transports)

- **Read-only by default; writes are opt-in.** State the verdict on its own line in
  the header (`✅ READ-ONLY` or `WRITES`). A write-capable probe defaults to a dry
  run that prints the exact payload it would send, and only sends it behind an
  explicit flag (`window.probeApply = true` in the console, `--apply` in a shell
  script). Close with a banner naming exactly what gets created and on which
  targets, and print created ids so they can be cancelled. Only write when asked to
  exercise a write path. The bridge never writes to production because it can't
  reach it.
- **Never shrink the NOT CHECKED section.** The probe ends by listing what it could
  not check (no input, read denied, 401/403, record absent). A run must not look
  complete when things went unchecked. Missing records and denied reads are
  "unknown", never zero.
- **Don't run it against production yourself.** Production probes are handed over
  and run by the user in their own browser session.
- **No hardcoded org identity in logic.** Orgs, branches and products are
  data at the top of the file, overridable.
- **Never name a variable `COLUMNS`** in shell scripts (bash owns it). Use
  `COLUMNS_OVERRIDE`.
- Shell scripts that remain (bridge helpers): `set -euo pipefail`, status printed
  for every call, macOS and Linux compatible (BSD `date` fallback).
- **No placeholders in what you hand the user.** Real org ids, real values.

## The header comment

One line saying what question it answers, then **why it exists** (the decision or
bug that made the question matter, with PR numbers and any live observation), then
the read-only/writes verdict, then usage and the output filename. This is the one
place verbose prose is wanted: it is what makes a probe re-runnable in three weeks.
No narrating of how the probe was verified, no dates or cross-references to docs.

## Steps

1. List every question the task raises. Cover as many as possible in **one** probe
   run (a section per question, all targets and controls in the same script) so the
   user pastes once and sends back one file. Don't split into several probes, and
   don't ask which to write. The user should not be a manual proxy for your
   follow-up queries. Anticipate the next call you would make (neighbouring
   endpoints, control records, the other branches or orgs) and include it now.
2. If the DB or the code can answer a question, answer it yourself and leave it out
   of the probe.
3. Pick the transport from the table above and say which.
4. Copy `console-probe-template.js` and fill it in.
5. Write it somewhere durable (the pod is not), e.g. the work's planning directory.
6. Attach it with `add_attachment`, and give the hand-over steps for that transport.
7. When the user sends results back: read them, state what they show and what they
   don't, and record the findings in the relevant planning doc in the same turn.
   Keep the probe's own commentary out of anything customer- or channel-facing.
8. Update this skill (see below) with anything from this probe that a future probe
   would need.

## Keep this skill current

This skill lives in the user's personal dotfiles
(`/mnt/personal/dotfiles/claude/skills/erp-probe/`, symlinked from
`~/.claude/skills/erp-probe`). Edit it directly whenever a probe teaches something
reusable. Don't ask first, and don't wait to be told. Tell the user in your reply
what you changed.

Worth recording:

- A correction from the user about how probes should work. Update the rule it
  contradicts, and don't just add a new line beside it.
- Proxy behaviour seen in a real run: which endpoints the proxy rejects or
  classifies differently, error shapes, how a 429 actually arrived, and auth or
  permission failures and what fixed them.
- ERP endpoint facts a probe confirmed: the working path and query shape,
  pagination limits, ids that need special encoding, fields that come back as a
  different type than the code assumes. Group them under a per-ERP heading in an
  `## ERP notes` section at the end of this file.
- Bridge compatibility per client: what worked through it, and what needed an
  auth-host override or couldn't go through at all.
- A helper you had to write that the next probe will want. Put it in
  `console-probe-template.js` instead of describing it here.

Not worth recording: org-specific ids, customer names, one-off results, or anything
that belongs in a planning doc. Keep tenant names out of the skill. Edit with the
Edit tool, keep it terse, and remove or fix anything that turned out to be wrong.
Don't commit or push the dotfiles repo unless the user asks.
