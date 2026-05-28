---
description: Convert tasks.md entries into GitHub issues.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Overview

You are a **project manager**. Your job is to convert the tasks in `tasks.md` into GitHub issues with proper labels, descriptions, and dependency links.

## Process

1. Run `.dk/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`.

2. Read `tasks.md` and parse all tasks with their IDs, descriptions, phases, and dependencies.

3. Determine the GitHub repo: run `git remote get-url origin` and parse `owner/repo`.

4. Create labels if they don't exist:
   ```bash
   gh label create "dk-task" --description "DK task" --color "0075ca" 2>/dev/null || true
   gh label create "dk-setup" --description "Setup phase" --color "e4e669" 2>/dev/null || true
   gh label create "dk-foundation" --description "Foundation phase" --color "d876e3" 2>/dev/null || true
   gh label create "dk-feature" --description "Feature phase" --color "0e8a16" 2>/dev/null || true
   gh label create "dk-polish" --description "Polish phase" --color "fbca04" 2>/dev/null || true
   ```

5. For each task, create a GitHub issue:
   ```bash
   gh issue create --title "T0XX: <task description>" \
     --label "dk-task,<phase-label>" \
     --body "$(cat <<'EOF'
   ## Task
   **ID**: T0XX
   **Phase**: <phase name>
   **Priority**: <P1/P2/P3>

   ## Description
   <full task description>

   ## Files
   - `<file paths from task>`

   ## Dependencies
   - Blocked by: <list of blocking task IDs>

   ## Acceptance Criteria
   <from linked user story/requirement>
   EOF
   )"
   ```

6. After creating all issues, print a mapping of task IDs to issue numbers.

## Rules

- Preserve task ordering and dependencies
- Include file paths in issue body for easy navigation
- Link dependent issues using "Blocked by #XX" in the body
- Do not create issues for already-completed tasks (`[x]`)

