---
description: Cross-project agent-mesh coordinator — shared filesystem primitive for status, handoffs, and append-only decisions across DK repos. Routes intent to `dkify mesh ...` for all writes. Four modes: off / on-local / on-gh-default / on-gh-custom.
---

---
description: Cross-project agent-mesh coordinator. USE THIS when the user mentions the mesh, cross-project status, handoffs between DK repos, inter-project decisions, publishing status, "what are other projects doing", or resuming work that depends on another repo. Reads and writes a shared filesystem primitive (`~/.dk-mesh/` or a cloned git repo) so parallel Codex sessions across `dk-cli`, `dk-alchemy`, `dk-data-FE`, `dk-clusters`, etc. share a durable handshake. All mutations go through `dkify mesh ...` shell commands — you route intent, the CLI writes files.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding. The first token of `$ARGUMENTS` is the mode (`status`, `publish`, `handoff`, `respond`, `close`, `decision`, `check`, `init`, `enroll`, `sync`). The rest are mode-specific args. If `$ARGUMENTS` is empty, default to `status`.

## Principles

Read `.dk/memory/principles.md` and `.dk/memory/mesh.md` before acting. All mesh writes must honor the project's principles: **simple, complete, senior**. All mesh writes carry the dkify attribution trailer automatically (the CLI handles it; do not hand-author trailers).

## Overview

You are a **mesh participant**. Every DK repo with `mesh.mode != off` in its `.dk/config.yaml` reads and writes to a shared filesystem primitive that is either local (`~/.dk-mesh/`) or cloned from a git repo (default: `data-kinetic-projects/dk-mesh-coordinator`). The mesh answers:

- "What are sibling DK projects doing right now?"
- "Who am I blocking?"
- "Who is waiting on me?"
- "What cross-project decisions have been made that I should respect?"

You do **not** write mesh files by hand. Every mutation is a thin shell to `dkify mesh <mode> ...`. The CLI handles paths, timestamping, tag scoping, and the attribution trailer. Your job: pick the mode, gather free-form text via `AskUserQuestion` when needed, and invoke the command.

### Key concepts

| Term | Meaning |
|---|---|
| **mode** | `off` / `on-local` / `on-gh-default` / `on-gh-custom` — controls whether/where the mesh is stored. Set in `.dk/config.yaml:mesh.mode`. |
| **tag** | Path-prefix scope that isolates teams sharing a coordinator repo. Your project's tag is `.dk/config.yaml:mesh.tag`. |
| **status** | `projects/<tag>/<name>.md` — a living doc you publish when entering/exiting stages or changing blockers. |
| **handoff** | `handoffs/<tag>/open/*.md` — a directed request to another project. Appears in the target's next session. |
| **decision** | `decisions/<tag>/*.md` — append-only cross-project decisions. Never edit after create. |

## Prerequisites

1. Read `.dk/memory/principles.md` and `.dk/memory/mesh.md`.
2. Read `.dk/config.yaml` to learn the project's `mesh.mode`, `mesh.tag`, and `name`. If `mesh.mode` is `off`, tell the user to run `/dk.mesh init` (see the `init` section below) and stop — most modes require the mesh to be enabled first.
3. Do **not** run mesh commands if `mesh.mode == off`. Read-only commands (`status`, `check`) degrade gracefully; mutations refuse.

## Modes

### `status` (default)

Show the mesh digest relevant to this project.

```bash
dkify mesh status                    # this tag
dkify mesh status --tag all          # every tag in the coordinator repo
dkify mesh status --tag <other>      # inspect another team's tag
```

Read the output, summarize for the user in one paragraph, and flag:
- Peer projects with status older than `mesh.stale_days`.
- Open handoffs that name **this project** as the target.
- Anything in decisions that constrains the user's current work.

### `publish`

Rewrite `projects/<tag>/<name>.md` with this project's current state. Publish when:

1. Entering or exiting a stage (`/dk.stage exec` / `/dk.stage close`).
2. Opening or resolving a blocker on another project.
3. A cross-project decision is accepted.
4. The user explicitly asks for a status bump.

Gather free-form notes via `AskUserQuestion` if the user's message doesn't already include them. Keep notes under ~10 lines — the mesh is not a firehose.

```bash
dkify mesh publish \
  --notes "Auth contract v2 landed in PR #142. Blocking dk-data-FE on token refresh." \
  --active-spec ".dk/specs/042-auth-v2/" \
  --stage "Stage 3 of 042-auth-v2"
```

### `handoff <target> <topic>`

Open a directed request to another project. Use when this project cannot proceed without work in a sibling repo.

1. Identify the target (must be enrolled in the mesh under the same tag).
2. Draft a short body: what you need, why, definition of done, references (PR/spec/commit URLs).
3. Call:

```bash
dkify mesh handoff <target-project> "<topic-slug>" --body-file /tmp/handoff-body.md
```

Or `--body "inline body"` for short messages. The CLI stamps `**From**`, `**To**`, `**Opened**`, adds the Responses template, and appends the attribution trailer.

### `respond <handoff-file>`

Append a dated response to an existing handoff. Use when another project has opened a handoff targeting us. Always respond — even a one-line "picked up, eta EOD" signals to the originator that we are engaged.

```bash
dkify mesh respond ~/.dk-mesh/handoffs/<tag>/open/<file>.md \
  --message "Picked up. Shipping behind a feature flag by EOD — will ping when merged."
```

### `close <handoff-file>`

Move a handoff from `open/` to `closed/` with a reason. Use only when the Definition of Done is met — not as a way to silence an old request.

```bash
dkify mesh close ~/.dk-mesh/handoffs/<tag>/open/<file>.md \
  --reason "Auth contract v2 shipped in PR #142; dk-data-FE token-refresh flow verified end-to-end."
```

### `decision <title>`

Create an **append-only** cross-project decision. Use sparingly — only for choices that span repos and will constrain future work. The file is written once and never edited after.

1. Discuss with the user first (via `AskUserQuestion` if unclear) to capture: context, the choice, consequences.
2. Call:

```bash
dkify mesh decision "shared auth token v2" \
  --projects dk-cli,dk-alchemy,dk-data-FE \
  --body-file /tmp/decision-body.md
```

Then publish a status update referencing the decision so peers see it.

### `check`

Run a non-fatal audit of the mesh from this project's perspective.

```bash
dkify mesh check
```

Surfaces stale peer statuses and open handoffs where this project is the target. Report the output to the user verbatim, then prioritize: handoffs targeting us take precedence over our own follow-ups.

### `init [--mode <mode>] [--remote <url>]`

One-time host-level setup. Use only when the user is setting up the mesh for the first time or switching modes.

```bash
dkify mesh init --mode on-gh-default          # clones data-kinetic-projects/dk-mesh-coordinator
dkify mesh init --mode on-gh-custom --remote git@github.com:team/mesh.git
dkify mesh init --mode on-local               # no git sync; single-machine only
```

If the user is unsure which mode to pick, default to `on-gh-default` — it clones the canonical coordinator repo and works across machines. Ask via `AskUserQuestion` if mode is ambiguous.

### `enroll`

Enroll this project in the mesh registry and flip `mesh.session_start_hook: true` so future sessions see a mesh digest at startup.

```bash
dkify mesh enroll
```

Run this **once per project**, after `dkify mesh init` has created the shared mesh. The command upserts the project into `mesh.yaml`, sets the SessionStart hook in `.Codex/settings.json` (nested-hooks schema preserved), and writes `mesh.session_start_hook: true` back to `.dk/config.yaml`.

### `sync`

For `on-gh-*` modes only. Pulls remote changes, commits any local writes, and pushes. Run when:

1. After every mutation burst (batch of publishes/handoffs in one session), to make your writes visible to other machines.
2. Before a long-running read (so the digest is current).

```bash
dkify mesh sync
```

On-local mode is a no-op. The command surfaces merge conflicts rather than auto-resolving — stop and ask the user if you hit one.

## Tag discipline

Every mesh path is scoped by `mesh.tag`. Never cross tags without an explicit reason:

- Don't publish under `--tag <other>` — you only own your own tag.
- Don't open handoffs into another tag — targets must live under the same tag as the sender.
- `status --tag all` is fine for read; mutations with `--tag` flags are not supported.

If the user wants cross-tag coordination, that is a v2 feature — tell them and stop.

## Cadence

Publish on **meaningful events**, not every turn. A good heuristic:

- Stage entry (`/dk.stage exec` starts) → publish.
- Stage exit (`/dk.stage close`) → publish with the shipped summary.
- Opening a handoff → publish (so peers see why we're asking).
- Closing a handoff → publish.
- Receiving a decision that affects us → publish to acknowledge.
- Otherwise: don't.

## Safety rules

1. **Never hand-author mesh files.** Every mutation is `dkify mesh ...`. The CLI is the source of truth for format, timestamping, and the attribution trailer.
2. **Never close someone else's handoff.** Only the originator or the target closes a handoff, and the target closes only when the Definition of Done is met.
3. **Decisions are append-only.** If a decision turns out to be wrong, create a new one whose `**Status**` is `accepted` and whose body begins with "Supersedes `<path>`." Do not edit the old file.
4. **Respect tag isolation.** You write your tag only.
5. **Sync before long reads in on-gh-* modes.** Otherwise the digest is stale.
6. **Attribution is automatic.** If you see `Co-Authored-By: Codex` (or GPT/Gemini/etc.) anywhere in mesh content, strip it — dkify uses a unified Dkify identity. The CLI already does this correctly.

## On failure

- `mesh.mode` is off and user wants to publish/handoff → tell the user, suggest `/dk.mesh init` + `/dk.mesh enroll`, stop.
- Mesh dir missing → suggest `dkify mesh init`, stop.
- Git conflict on `sync` → surface the files, ask the user how to resolve, do not auto-rebase past a conflict.
- Decision file already exists at today's slug → ask the user for a more specific title, retry.

