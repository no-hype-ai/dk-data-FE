---
description: Multi-model task dispatcher — invokes `dkify distributor run` to route tasks.md rows to LLM sub-agents (NVIDIA / OpenAI / OpenRouter) with verification gates (lint/type/test) + LLM-as-judge reviewer + auto-commit on green. Honors `[model:alias]` markers; falls back to route table.
---

## User Input

```text
{{ARGS}}
```

You **MUST** consider the user input before proceeding (if not empty).

## Principles

Read `.dk/memory/principles.md` and `.dk/memory/distributor.md` before acting. All output must honor the project's principles: **simple, complete, senior**. The dispatcher's commit identity and trailer block are non-negotiable.

## Overview

You are a **dispatcher driver**. Your job is to invoke `dkd` so individual `tasks.md` rows are executed by the routed model with full verification (gates + LLM-as-judge reviewer) and auto-commit on green. You do **not** edit code yourself; the model named by each task's `[model:<alias>]` marker (or by route fallback) does.

## Prerequisites

- `.dk/distributor.yaml` must exist (run `dkify upgrade --distributor=on` if not).
- The distributor venv must be bootstrapped: `bash .dk/scripts/bash/distributor-bootstrap.sh`.
- Provider env vars must be set in `.env.local` (at minimum `NVIDIA_API_KEY` or `OPENROUTER_API_KEY`).

## Process

1. Verify `dkd` is reachable:
   ```sh
   dkify distributor status
   ```
   If venv is not bootstrapped, run the bootstrap script first.

2. Inspect routing without API calls (sanity check):
   ```sh
   dkify distributor route --task <task_id_or_description>
   ```

3. Probe provider catalogs (optional, recommended on first run):
   ```sh
   dkify distributor sync-models
   ```

4. Dispatch:
   - **Single task**: `dkify distributor run --task <task_id>` — auto-commits on green gate + approved review.
   - **Whole feature**: `dkify distributor run --feature <name>` — walks tasks.md, fans `[P]` waves out into ephemeral worktrees, fast-forward-merges back under a serialization lock, halts cleanly on first failure.
   - Add `--dry-run` to preview routing without API calls or file writes.

5. Aggregate telemetry into a leaderboard:
   ```sh
   dkify distributor report
   ```

## Hard rules (enforced by `dkd`, but call them out)

- The dispatcher **never** pushes to a remote (`[NOPSH]`).
- Commit messages **never** contain a model alias / id (`[NOMDL]`).
- Reviewer's `family:*` tag must differ from the implementer's (`[FAMLY]`); pass `--allow-self-review` only for benchmark cases.
- Working tree must be clean before `dkd run` (override with `--allow-dirty` rarely).
- Auto-commit uses `Dkify by Data Kinetic <dkify@datakinetic.com>` author + the canonical trailer block.

## When to invoke `dkd` vs. doing the work yourself

Use `dkd` when:
- The task has a `[model:<alias>]` marker — the human author has explicitly chosen the implementer.
- A feature has many independent `[P]` tasks and price/throughput matter.
- You want the gate + reviewer pass to be enforced automatically.

Do the work in-session when:
- The task is meta about `dkd` itself.
- The change is one or two lines and routing overhead would dwarf the work.
- API keys are unavailable.

## Reference

- CLI subcommands: `dkify distributor --help`
- Model registry: `.dk/distributor.yaml`
- Telemetry: `.dk/telemetry/runs/<run_id>.json`
- Active tags: see `.dk/memory/tags.md` "Distributor preset" block.

