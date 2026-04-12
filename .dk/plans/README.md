# Ad-hoc Plans

This directory holds plans for work that isn't tied to a specific feature spec.
For spec-driven features, use `.dk/specs/<feature>/plan.md` instead.

## Convention

- File naming: `YYYY-MM-DD-<short-topic>.md`
- One plan per file; do not batch multiple unrelated tasks
- Mark items done as you execute; keep the file until the work ships
- Delete or archive after merge

## Usage

Create a plan before any task with 3+ steps. The `plan-before-edit` hook blocks
edits unless a plan file exists in an approved location (`.dk/plans/*.md`,
`.dk/specs/*/plan.md`, or `.claude/plans/`).
