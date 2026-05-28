# Mesh

> Cheat-sheet for cross-project agent-mesh coordination.
> Edit freely — changes take effect immediately; no regeneration needed.

## What

The mesh is a filesystem-backed primitive shared across all dkified DK projects. It lets a Claude session in one repo see what other repos are doing, open durable handoffs, and record cross-project decisions — without Slack, without human ferrying.

Every DK repo with `mesh.mode != off` in its `.dk/config.yaml` reads and writes to the same mesh directory (local or git-backed).

## Where

- **Default**: `~/.dk-mesh/` (override with `$DK_MESH_DIR`)
- **Default git-backed coordinator**: <https://github.com/data-kinetic-projects/dk-mesh-coordinator>

Layout (scoped by tag):

```
<mesh-root>/
├── README.md
├── mesh.yaml                           # registry of enrolled projects per tag
├── projects/<tag>/<name>.md            # one file per project
├── handoffs/<tag>/open/*.md
├── handoffs/<tag>/closed/*.md
└── decisions/<tag>/*.md                # append-only
```

## Who writes what

| Path | Writer | Readers |
|---|---|---|
| `projects/<tag>/<name>.md` | agents working in `<name>` | everyone |
| `handoffs/<tag>/open/*.md` | the originating project | everyone (esp. target) |
| `handoffs/<tag>/closed/*.md` | moved there by the closer | everyone |
| `decisions/<tag>/*.md` | the proposing project; append-only after creation | everyone |
| `mesh.yaml` | humans + `dkify mesh enroll` | everyone |

Single-writer-per-path. No locking. Readers are lock-free.

## Four modes

Set in `.dk/config.yaml:mesh.mode`:

| Mode | Behavior |
|---|---|
| `off` | Mesh disabled for this project. `mesh-status-brief.sh` exits 0 silently. |
| `on-local` | `~/.dk-mesh/` is a plain filesystem dir. No git sync. Solo single-machine only. |
| `on-gh-default` | `~/.dk-mesh/` is a clone of `data-kinetic-projects/dk-mesh-coordinator`. |
| `on-gh-custom` | `~/.dk-mesh/` is a clone of a user-supplied remote. |

Switch modes by re-running `dkify mesh init --mode <...>`.

## Tags

Every mesh path is scoped by `.dk/config.yaml:mesh.tag`. Teams sharing the same coordinator repo pick distinct tags so their files never collide (e.g., `tumeke`, `alchemy`, `default`).

- Your writes always go to your tag.
- `dkify mesh status --tag all` reads across tags.
- Cross-tag mutations are not supported (and are a v2 concern).

## When to publish

Publish on meaningful events, **not** every turn:

1. Entering or exiting a `/dk.stage` stage.
2. Opening or resolving a blocker on another project.
3. A cross-project decision is accepted.
4. The user explicitly asks for a bump.

Stale statuses (> `mesh.stale_days` days old; default 7) are flagged by `dkify mesh check`.

## Commands

The slash command is `/dk.mesh` (see `.claude/commands/dk.mesh.md`). Every mutation goes through the `dkify mesh` Typer CLI — `/dk.mesh` is a thin intent router, not a file-writer.

| Verb | Purpose |
|---|---|
| `dkify mesh init` | Initialize the host-level mesh dir. |
| `dkify mesh enroll` | Register this project + enable the SessionStart hook. |
| `dkify mesh status` | Digest of peer statuses and handoffs. |
| `dkify mesh publish` | Update this project's status file. |
| `dkify mesh handoff <to> <topic>` | Open a directed request. |
| `dkify mesh respond <file>` | Append a dated response to a handoff. |
| `dkify mesh close <file>` | Move a handoff to `closed/`. |
| `dkify mesh decision <title>` | Create an append-only decision. |
| `dkify mesh check` | Audit stale statuses + open handoffs involving us. |
| `dkify mesh prune` | Move old `closed/*.md` to `closed/stale/`. |
| `dkify mesh sync` | Pull + push (on-gh-* modes). |

All writes carry the dkify attribution trailer automatically.

## Session start

When `mesh.session_start_hook: true` (set by `dkify mesh enroll`), every Claude session starts with `bash .dk/scripts/bash/mesh-status-brief.sh` — a terse digest of peer state. If the mesh is off or missing, the hook exits 0 silently.

## On-gh-* sync etiquette

- Run `dkify mesh sync` before a long read session so the digest is current.
- Run `dkify mesh sync` after every burst of writes so peers on other machines see them.
- If `git pull --rebase` surfaces a conflict, **stop** and ask the user — never auto-resolve.
