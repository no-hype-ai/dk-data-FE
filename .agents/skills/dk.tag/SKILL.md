---
description: Manage principle tags — add, remove, list, or activate constraint tags that enforce project standards.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Overview

You are a **principle tag manager**. Your job is to manage the project's constraint tags in `.dk/memory/tags.md`. Tags are token-efficient shorthand for technical constraints — one tag replaces paragraphs of instruction.

**Rule**: If you can't write a grep or a test for it, it's not a tag — it's a guideline. Guidelines go in the constitution.

## Commands

Parse `$ARGUMENTS` to determine the action:

### `add [TAG] "Principle" "Enforcement"`

1. Read `.dk/memory/tags.md`
2. Validate tag format: 3-6 chars, UPPERCASE, alphanumeric, wrapped in brackets
3. Check for duplicates — reject if tag already exists
4. Add to the **Active Tags** table
5. Suggest a CI enforcement approach if none provided
6. Save the file
7. Run `.dk/scripts/bash/update-agent-context.sh`

### `remove [TAG]`

1. Read `.dk/memory/tags.md`
2. Find the tag in Active Tags
3. Move it back to Available Tags (don't delete — it might be reactivated)
4. Save the file
5. Run `.dk/scripts/bash/update-agent-context.sh`

### `activate [TAG]`

1. Read `.dk/memory/tags.md`
2. Find the tag in Available Tags
3. Move it to Active Tags
4. Save the file
5. Run `.dk/scripts/bash/update-agent-context.sh`

### `list`

1. Read `.dk/memory/tags.md`
2. Print a summary:
   ```
   Active Tags:
     [TYPED] Strict typing — no `any`
     [AUDIT] All mutations emit audit event

   Available Tags: 18 tags across 5 categories
   ```

### No arguments (interactive)

1. Read `.dk/memory/tags.md`
2. Scan the project to understand the tech stack:
   - Read `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, etc.
   - Check for TypeScript (`tsconfig.json`), frameworks, auth providers, databases
3. **Recommend** which Available Tags should be activated based on the stack:
   - TypeScript project → suggest `[TYPED]`
   - Has API routes → suggest `[VERSN]`, `[ZVAL]`
   - Has auth → suggest `[RBAC]`
   - Uses LLMs → suggest `[STRM]`, `[TOKN]`
   - Multi-tenant → suggest `[SEGMN]`
   - Healthcare/regulated → suggest `[HIPAA]`, `[NCMPL]`, `[AUDIT]`
4. Present recommendations and let the user confirm which to activate
5. For each activated tag, move from Available to Active
6. Save and update context

## Rules

- Tag names are UPPERCASE, 3-6 chars, alphanumeric only
- One constraint per tag — never compound meanings
- Every tag must have both a principle (what) and enforcement (how to test)
- Active tags are project commitments — only activate what you'll enforce
- After any change, always run `update-agent-context.sh` to propagate

