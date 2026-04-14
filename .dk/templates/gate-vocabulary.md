# Gate Vocabulary

Closed vocabulary for emoji, deferral reasons, and exit-gate types used
in `stage-status.md`. The skill enforces this vocabulary — don't invent
new tags without adding them here first, or cold-resume sessions will
fail to interpret the file.

## Stage / task emoji

| Emoji | State | Meaning |
|---|---|---|
| ✅ | closed | Stage merged OR task complete + verified |
| ⏳ | pending / in progress | Next up OR currently executing |
| ⏸ | deferred | Explicitly moved out of current stage with a reason + natural reschedule |
| ⛔ | blocked | Cannot proceed until an external condition is met (hardware, procurement, regulatory) |

**Rules**:
- Never combine emoji (no `⏳⏸`). A task is in exactly one state.
- Never use any emoji not in this list. No custom flags.
- `⏸` (deferred) is user-intentional; `⛔` (blocked) is externally imposed.
  The distinction matters for rollback reasoning — deferred work is a
  choice, blocked work is a constraint.

## Deferral reason tags

Every `defer` call must use exactly one of these as the prefix of the
reason text. The skill rejects free-form tags.

| Tag | Meaning | Example |
|---|---|---|
| `hardware-block:` | Waiting on procurement, racking, or physical infra | "hardware-block: scarecrow host not yet racked in the lab" |
| `operator-sign-off:` | Needs a human decision on blast radius, maintenance window, or regulatory approval | "operator-sign-off: Doppler token scope decision per D012" |
| `dependent-task:` | Blocked by another task in a later stage | "dependent-task: T136 LiteLLM cutover needs T132 DB created first" |
| `scope-split:` | Moved to a different feature entirely | "scope-split: this becomes feature/002 — see issue #620" |
| `risk-defer:` | Intentionally delayed to reduce blast radius of the current stage | "risk-defer: bundle this with the next maintenance window instead of mid-sprint" |

**Rules**:
- The tag is mandatory. No deferral without one.
- The tag is followed by a colon and a space, then free-form reason text.
- Reason text must be specific enough that someone reading it 3 weeks
  later knows what was blocking and what unblocks it.
- `operator-sign-off:` deferrals also require a `verification/<TID>.md`
  stub. The skill writes it automatically.

## Exit gate types

Each stage has exactly one `exit-gate-type`. The skill enforces this
at `close` time.

| Type | Meaning | Close-time check |
|---|---|---|
| `runtime-green` | Feature works end-to-end in prod with real config | "Are all tests green AND is the PR merged AND is the feature reachable end-to-end in the target env?" |
| `code-only-safe` | Code ships safely behind a documented fallback (e.g. 503 on missing credentials) | "Is the code safe to ship with the documented fallback AND is the PR merged AND is the follow-up task tracked?" |

**Choosing the type**:

- Default to `runtime-green`. It's stricter, and most stages can meet it.
- Only use `code-only-safe` when:
  1. The code has a documented fallback path (503, feature flag off,
     graceful degradation) that cannot harm users.
  2. Unit tests pass in isolation — the fallback doesn't bypass testing.
  3. The follow-up enablement task is tracked separately (typically
     as a deferred `operator-sign-off:` task or a task in a later stage).
  4. You can explain to a reviewer why shipping code before config is
     safer than waiting.

**The T043 pattern** (feature/001): Stage 5 shipped the provisioning
router with every endpoint returning 503 `provisioning_not_configured`
until T043 wired the Doppler token and CNPG RBAC. The code was safe
because:
- Missing clients → 503 fallback, not crash.
- Integration tests mocked the clients.
- T043 was deferred with `operator-sign-off:` and tracked in
  `verification/T043.md`.
- The "code lands, config follows" order was deliberate — it let us
  review the code without the blast-radius decision blocking the merge.

## Pipeline state values

`Pipeline state:` in the stage-status.md header is exactly one of:

| Value | Meaning |
|---|---|
| `init` | `stage-status.md` just written by `/dk.stage init`, no stages executed yet |
| `in-progress` | At least one stage is `⏳` |
| `closing` | Current stage's tasks are all `✅`/`⏸`, waiting on user confirmation to run `/dk.stage close` |
| `done` | All stages are `✅`, feature ready to merge/close |

## File paths the skill mutates

| Path | Mutated by | Notes |
|---|---|---|
| `FEATURE_DIR/stage-status.md` | `init`, `close`, `defer`, `replan` | Primary state file |
| `FEATURE_DIR/tasks.md` | `close` (tick `[x]`), `defer` (annotate `[ ] ⏸ — reason`) | In-place edit |
| `FEATURE_DIR/verification/<TID>.md` | `defer` with `operator-sign-off:` | New stub file, one per sign-off |
| `.dk/memory/decisions.md` | `close` only, append-only | Never rewrites prior entries |

## File paths the skill never touches

| Path | Why |
|---|---|
| `FEATURE_DIR/spec.md` | Immutable output from `/dk.specify` |
| `FEATURE_DIR/plan.md` | Immutable output from `/dk.plan` |
| `FEATURE_DIR/research.md` | Immutable output from `/dk.plan` |
| `FEATURE_DIR/data-model.md` | Immutable output from `/dk.plan` |
| `FEATURE_DIR/contracts/` | Immutable output from `/dk.plan` |
| Source code | `/dk.implement` and `/dk.swarm` handle that |
