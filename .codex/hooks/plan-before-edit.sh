#!/usr/bin/env bash
set -euo pipefail

# Consume stdin (tool input JSON) to avoid broken pipe
cat > /dev/null

# Check for plan files in common locations
plan_found=false

# .dk/specs/*/plan.md — feature-driven spec plans
for f in .dk/specs/*/plan.md; do
  [ -f "$f" ] && plan_found=true && break
done

# .dk/plans/*.md — ad-hoc plans (excluding the README)
if [ "$plan_found" != true ]; then
  for f in .dk/plans/*.md; do
    [ -f "$f" ] && [ "$(basename "$f")" != "README.md" ] && plan_found=true && break
  done
fi

# .dk/bugs/*/report.md — bug-fix investigations (carve-out)
if [ "$plan_found" != true ]; then
  for f in .dk/bugs/*/report.md; do
    [ -f "$f" ] && plan_found=true && break
  done
fi

# .claude/plans/ — Claude Code plan mode files
if [ "$plan_found" != true ] && [ -d ".claude/plans" ] && [ "$(ls -A .claude/plans/ 2>/dev/null)" ]; then
  plan_found=true
fi

# todo.md / TODO.md at project root — lightweight fallback
if [ "$plan_found" != true ] && { [ -f "todo.md" ] || [ -f "TODO.md" ]; }; then
  plan_found=true
fi

# *.plan.md at project root — ad-hoc fallback
if [ "$plan_found" != true ]; then
  for f in *.plan.md; do
    [ -f "$f" ] && plan_found=true && break
  done
fi

if [ "$plan_found" = true ]; then
  exit 0
fi

echo "BLOCKED: No plan file found. Write a plan before editing code." >&2
echo "Preferred locations (under .dk/, keeps root clean):" >&2
echo "  .dk/specs/<feature>/plan.md    (feature work)" >&2
echo "  .dk/plans/<topic>.md           (ad-hoc work)" >&2
echo "  .dk/bugs/<desc>/report.md      (bug investigations)" >&2
echo "Also accepted: .claude/plans/*, todo.md, *.plan.md" >&2
exit 1
