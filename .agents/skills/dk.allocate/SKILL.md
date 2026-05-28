---
description: Auto-allocate `[model:alias]` markers across an unmarked tasks.md by classifying each row (kind/complexity/risk) against the configurable rule table. Idempotent; never overwrites existing markers.
---

## User Input

```text
{{ARGS}}
```

You **MUST** consider the user input before proceeding (if not empty).

## Principles

Read `.dk/memory/principles.md` before acting. Honor `simple, complete, senior`. Allocator output must obey `[CHEAP]` (cost-first defaults) and `[FAMLY]` (reviewer-different-family) downstream.

## Overview

You are an **allocator driver**. Your job is to invoke `dkify distributor allocate` so unmarked rows in a `tasks.md` get filled in with sensible model markers. You do not edit tasks.md directly; the dispatcher's classifier does.

## Prerequisites

- `.dk/distributor.yaml` must exist with an `allocator:` block.
- The distributor venv must be bootstrapped (see `dk.distribute`).

## Process

1. Verify dkd is reachable:
   ```sh
   dkify distributor status
   ```

2. Inspect what would be written (no file writes):
   ```sh
   dkify distributor allocate --feature <name> --dry-run
   ```
   Or pass an explicit tasks file: `--tasks .dk/specs/<feature>/tasks.md`.

3. Apply (idempotent — re-running is a no-op for already-marked rows):
   ```sh
   dkify distributor allocate --feature <name>
   ```

4. Inspect the resulting tasks.md and confirm the markers match the heuristic table in `.dk/distributor.yaml > allocator.rules`.

5. To overwrite existing markers (rare, intentional re-allocation), edit the file and remove the markers manually, then re-run allocate.

## Hard rules

- **Existing `[model:...]` markers are sacred.** The allocator never overwrites them.
- **Tasks below `allocator.min_description_chars` (default 8) are refused** — too short to classify; needs a human marker.
- **Tasks below `allocator.fallback_chars` (default 20) without a kind verb route to `routes.default`** — cheaper than guessing.
- **Classification is deterministic.** Re-running produces a byte-identical result.

## Reference

- Rule table: `.dk/distributor.yaml > allocator.rules`
- Defaults: `allocator.min_description_chars`, `allocator.fallback_chars`
- Cross-references the same registry as `dkify distributor run` and `dkify distributor route`

