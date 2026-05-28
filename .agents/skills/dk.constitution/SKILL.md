---
description: Establish project context, conventions, and quality standards.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Overview

You are establishing the **project constitution** — the foundational context document that all future dk commands will reference. This document captures the project's purpose, conventions, quality standards, and constraints. You also activate **principle tags** that enforce those standards.

## Process

1. If `.dk/memory/constitution.md` already exists, read it first and offer to update rather than overwrite.

2. Gather context about the project by reading:
   - `README.md`, `package.json`, or equivalent project metadata
   - Existing code structure (languages, frameworks, directory layout)
   - Any existing CI/CD configuration
   - Testing setup and conventions

3. Load `.dk/templates/constitution-template.md` for the constitution structure.

4. Ask the user about:
   - **Project goals**: What is this project? Who is it for?
   - **Quality standards**: Testing requirements, code review policy, documentation expectations
   - **Tech constraints**: Required frameworks, deployment targets, compatibility requirements
   - **Conventions**: Naming conventions, file organization, commit message format
   - **Non-negotiables**: Security requirements, performance targets, accessibility standards

5. Generate `.dk/memory/constitution.md` with these sections:

   ```markdown
   # Project Constitution

   ## Project Overview
   <Brief description, purpose, target users>

   ## Tech Stack
   <Languages, frameworks, databases, infrastructure>

   ## Quality Standards
   - Testing: <requirements>
   - Code Review: <policy>
   - Documentation: <expectations>

   ## Conventions
   - File Organization: <structure>
   - Naming: <conventions>
   - Git: <branch strategy, commit format>

   ## Constraints
   - <Security, performance, accessibility, compatibility>

   ## Non-Negotiables
   - <Hard requirements that must never be violated>
   ```

6. **Activate principle tags** based on the constitution:
   - Read `.dk/memory/tags.md`
   - Review the user's stated quality standards, constraints, and non-negotiables
   - For each non-negotiable that maps to an available tag, move it to Active Tags
   - Examples:
     - "No secrets in logs" → activate `[NOLOG]`
     - "All endpoints require authentication" → activate `[RBAC]`
     - "HIPAA compliance required" → activate `[HIPAA]`, `[NCMPL]`, `[AUDIT]`
     - "TypeScript strict mode" → activate `[TYPED]`
     - "All APIs versioned" → activate `[VERSN]`
     - "WCAG AA compliance" → activate `[A11Y]`
   - Add project-specific tags for non-negotiables not covered by available tags
   - Save `.dk/memory/tags.md`

7. Run `.dk/scripts/bash/update-agent-context.sh` to propagate the constitution and activated tags to all configured AI agent context files.

## Output

```
Constitution created:
  File: .dk/memory/constitution.md
  Tags activated: [TAG1] [TAG2] ... (<N> active)
  Context updated for: <agent list>
```

## Rules

- Be thorough but concise — the constitution should be scannable
- Capture decisions, not just preferences — include the "why" when possible
- Focus on information that helps AI agents make better decisions
- Do not include implementation details that will change frequently
- **Every non-negotiable should map to a tag** — if there's no tag for it, create one

