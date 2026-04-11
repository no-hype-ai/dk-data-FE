# /Users/pschloz/Desktop/DataKinetic/dk-data-FE

This project uses [dk](https://github.com/tumeke-stealth/tumeke-tools) for spec-driven development.

## DK Commands

Available commands (invoke as slash commands in your AI tool):

- `/dk.constitution` — Establish project context and conventions
- `/dk.specify` — Generate feature specification from a brief
- `/dk.clarify` — Resolve ambiguities in specifications
- `/dk.plan` — Create technical implementation plan
- `/dk.tasks` — Generate dependency-ordered task breakdown
- `/dk.implement` — Execute implementation tasks
- `/dk.analyze` — Cross-artifact consistency audit
- `/dk.checklist` — Pre-merge verification checklist
- `/dk.taskstoissues` — Convert tasks to GitHub issues
- `/dk.auto` — Autonomous pipeline (specify -> plan -> tasks -> analyze)
- `/dk.debug` — End-to-end app audit with Chrome DevTools
- `/dk.swarm` — Parallel implementation via git worktrees

## Project Structure

- `.dk/` — DK configuration and artifacts
- `.dk/config.yaml` — Project configuration
- `.dk/memory/` — Persistent project memory (constitution, etc.)
- `.dk/specs/` — Feature specifications and plans
- `.dk/scripts/` — Helper scripts

## Principles

This project honors `.dk/memory/principles.md` — read it before starting any task.
The bar is: **simple, complete, senior**. Plan before code (3+ steps), verify before done.

## AI Agents

Configured for: claude
