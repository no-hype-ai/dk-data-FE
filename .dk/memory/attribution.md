# Attribution

> Canonical rule for commit and PR authorship on this project. Every agent honors it.
> Edit freely — changes take effect immediately; no regeneration needed.

## TL;DR

When an agent creates a commit or PR:

- **Author identity** — `Dkify by Data Kinetic <dkify@datakinetic.com>`
- **Trailer block** — exactly these three lines at the bottom, nothing else:

  ```
  Buy the ticket. Take the ride.

  Co-Authored-By: Dkify <dkify@datakinetic.com>
  ```

## Rules

### 1. Author identity

Every `git commit` produced by an agent MUST pass `--author`:

```bash
git commit \
  --author="Dkify by Data Kinetic <dkify@datakinetic.com>" \
  -m "$(cat <<'EOF'
<subject line>

<body, if any>

Buy the ticket. Take the ride.

Co-Authored-By: Dkify <dkify@datakinetic.com>
EOF
)"
```

This keeps bot commits visually distinct from human commits in `git log` and in GitHub's author filter, while leaving the user's global git config untouched.

### 2. Trailer block

The final three lines of every commit message and every PR body MUST be:

```
Buy the ticket. Take the ride.

Co-Authored-By: Dkify <dkify@datakinetic.com>
```

The first line is editorial voice. The blank line separates it from the machine-readable trailer. The `Co-Authored-By:` line uses standard Git trailer syntax so GitHub surfaces the Dkify avatar on the commit / PR.

### 3. Banned phrases

Agents MUST NOT write any of these into commits or PR bodies:

- `Co-Authored-By: Claude ...`
- `Co-Authored-By: GPT ...`
- `Co-Authored-By: Gemini ...`
- `Co-Authored-By: Qwen ...`
- `Co-Authored-By: Codex ...`
- `Co-Authored-By: Copilot ...`
- `🤖 Generated with <any tool>`
- `Written by <any agent>`

If the harness tries to append one of these automatically, remove it before finalizing the commit / PR.

## Rationale

Dkify unifies multi-agent output under one identity. Review, audit, and attribution shouldn't care which specific agent produced a patch — only that the patch meets the project's bar.
