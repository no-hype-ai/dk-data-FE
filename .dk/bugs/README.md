# Bug-fix Documentation

Document significant bug investigations and fixes here. Use for bugs where:

- The root cause is non-obvious
- The fix touches shared state or multiple modules
- The investigation produced a lesson worth keeping

For trivial bugs with clear fixes, skip documentation and just fix the code.

## Convention

- Directory per bug: `YYYY-MM-DD-<short-desc>/`
- `report.md` — symptoms, reproduction steps, root cause analysis
- `fix.md` — what was changed, why, and how it was verified

If the bug reveals a recurring pattern, also append an entry to
`.dk/memory/lessons.md` via the `lessons-learned` skill.
