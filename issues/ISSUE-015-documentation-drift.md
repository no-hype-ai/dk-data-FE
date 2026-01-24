# ISSUE-015: Documentation Drift Risk

**Project**: dk-data-FE
**Category**: Code Quality
**Priority**: P3 - Low
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

ARCHITECTURE.md (1305 lines) and README.md are comprehensive but manually maintained. As the codebase evolves, documentation drift is likely, leading to outdated information that can mislead developers and cause integration errors.

---

## Current Documentation State

| Document | Lines | Last Updated | Auto-Generated |
|----------|-------|--------------|----------------|
| ARCHITECTURE.md | 1305 | Unknown | No |
| README.md | 329 | Unknown | No |
| API OpenAPI spec | Auto | On deploy | Yes (PostgREST) |
| Code comments | Sparse | Variable | No |

---

## Drift Risk Areas

### High Risk: Configuration Examples

```markdown
# ARCHITECTURE.md
PGRST_JWT_SECRET=your-secret-key
```

**Risk**: If configuration changes, documentation examples become invalid.

### Medium Risk: Code Patterns

```markdown
# ARCHITECTURE.md - Fetcher Template
class {{ class_name }}Fetcher(BaseFetcher):
    SOURCE_NAME = "{{ name }}"
    BASE_URL = "{{ base_url }}"
```

**Risk**: If BaseFetcher interface changes, template becomes incorrect.

### Medium Risk: API Endpoints

```markdown
# README.md
curl http://localhost:3030/catalog
curl http://localhost:3030/jobs
```

**Risk**: Endpoints may change, status codes may differ from documentation.

### Low Risk: Architecture Diagrams

ASCII diagrams can become outdated as architecture evolves.

---

## Evidence of Existing Drift

### Potential Issues Found

1. **PostgREST version**:
   - docker-compose.yml: `postgrest/postgrest:v12.2.3`
   - kustomization.yaml: `newTag: v12.0.2`
   - Documentation may reference different version

2. **Port numbers**:
   - Multiple references to ports throughout docs
   - Easy to miss updating all instances

3. **Environment variables**:
   - Different defaults in docker-compose vs docs

---

## Recommended Solutions

### Phase 1: Documentation Verification

#### 1.1 Automated Doc Testing

```python
# scripts/verify_docs.py
"""Verify documentation examples work."""

import subprocess
import re
from pathlib import Path

def extract_bash_examples(filepath: Path) -> list:
    """Extract bash code blocks from markdown."""
    content = filepath.read_text()
    pattern = r'```bash\n(.*?)```'
    return re.findall(pattern, content, re.DOTALL)

def extract_curl_commands(examples: list) -> list:
    """Extract curl commands."""
    commands = []
    for example in examples:
        for line in example.split('\n'):
            if line.strip().startswith('curl'):
                commands.append(line.strip())
    return commands

def verify_endpoints():
    """Verify documented endpoints exist."""
    readme = Path('README.md')
    examples = extract_bash_examples(readme)
    curls = extract_curl_commands(examples)

    for cmd in curls:
        # Extract URL
        url_match = re.search(r'http://[^\s]+', cmd)
        if url_match:
            url = url_match.group()
            # Test endpoint exists (expect 200 or 401, not 404)
            result = subprocess.run(
                ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', url],
                capture_output=True, text=True
            )
            status = result.stdout
            if status == '404':
                print(f"FAIL: {url} returns 404")
            else:
                print(f"OK: {url} returns {status}")

if __name__ == '__main__':
    verify_endpoints()
```

### Phase 2: Living Documentation

#### 2.1 Generate API Docs from Code

```python
# scripts/generate_api_docs.py
"""Generate API documentation from FastAPI app."""

import json
from ingestion.batch.api import app

def generate_openapi_docs():
    """Export OpenAPI schema."""
    schema = app.openapi()

    # Write to docs
    with open('docs/api/openapi.json', 'w') as f:
        json.dump(schema, f, indent=2)

    # Generate markdown summary
    with open('docs/api/ENDPOINTS.md', 'w') as f:
        f.write("# API Endpoints\n\n")
        f.write("*Auto-generated from FastAPI OpenAPI schema*\n\n")

        for path, methods in schema.get('paths', {}).items():
            f.write(f"## `{path}`\n\n")
            for method, details in methods.items():
                f.write(f"### {method.upper()}\n\n")
                f.write(f"{details.get('summary', 'No description')}\n\n")
                if 'parameters' in details:
                    f.write("**Parameters:**\n")
                    for param in details['parameters']:
                        f.write(f"- `{param['name']}`: {param.get('description', '')}\n")
                f.write("\n")
```

#### 2.2 Generate Config Docs from Code

```python
# scripts/generate_config_docs.py
"""Generate configuration documentation from environment variables."""

import os
import re
from pathlib import Path

def extract_env_vars(filepath: Path) -> dict:
    """Extract environment variable usage from file."""
    content = filepath.read_text()

    # Pattern: os.getenv("VAR", "default") or os.environ.get("VAR")
    patterns = [
        r'os\.getenv\(["\'](\w+)["\'](?:,\s*["\']([^"\']*)["\'])?\)',
        r'os\.environ\.get\(["\'](\w+)["\'](?:,\s*["\']([^"\']*)["\'])?\)',
        r'\$\{(\w+):-([^}]*)\}',  # Docker compose pattern
    ]

    vars = {}
    for pattern in patterns:
        for match in re.finditer(pattern, content):
            var_name = match.group(1)
            default = match.group(2) if len(match.groups()) > 1 else None
            vars[var_name] = default

    return vars

def generate_env_docs():
    """Generate environment variable documentation."""
    all_vars = {}

    # Scan Python files
    for pyfile in Path('src/dk_data').rglob('*.py'):
        vars = extract_env_vars(pyfile)
        for var, default in vars.items():
            if var not in all_vars:
                all_vars[var] = {'default': default, 'files': []}
            all_vars[var]['files'].append(str(pyfile))

    # Scan docker-compose
    for yml in Path('src/dk_data').glob('docker-compose*.yml'):
        vars = extract_env_vars(yml)
        for var, default in vars.items():
            if var not in all_vars:
                all_vars[var] = {'default': default, 'files': []}
            all_vars[var]['files'].append(str(yml))

    # Write documentation
    with open('docs/CONFIGURATION.md', 'w') as f:
        f.write("# Configuration\n\n")
        f.write("*Auto-generated from codebase*\n\n")
        f.write("| Variable | Default | Used In |\n")
        f.write("|----------|---------|--------|\n")

        for var in sorted(all_vars.keys()):
            info = all_vars[var]
            default = info['default'] or 'None'
            files = ', '.join(Path(f).name for f in info['files'][:3])
            f.write(f"| `{var}` | `{default}` | {files} |\n")
```

### Phase 3: Documentation as Code

#### 3.1 Makefile Integration

```makefile
.PHONY: docs docs-verify docs-generate

docs: docs-generate docs-verify

docs-generate:
	@echo "Generating API documentation..."
	python scripts/generate_api_docs.py
	@echo "Generating configuration documentation..."
	python scripts/generate_config_docs.py

docs-verify:
	@echo "Verifying documentation..."
	python scripts/verify_docs.py
```

#### 3.2 Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: verify-docs
        name: Verify Documentation
        entry: python scripts/verify_docs.py
        language: python
        files: '\.(md|py|yml)$'
        pass_filenames: false
```

### Phase 4: Documentation Standards

#### 4.1 README Template

```markdown
# Project Name

![CI Status](badge)
![Coverage](badge)

## Quick Start

<!-- GENERATED:START:quickstart -->
{auto-generated from Makefile targets}
<!-- GENERATED:END -->

## API Endpoints

<!-- GENERATED:START:endpoints -->
{auto-generated from OpenAPI}
<!-- GENERATED:END -->

## Configuration

<!-- GENERATED:START:config -->
{auto-generated from environment variables}
<!-- GENERATED:END -->

## Manual Sections

### Architecture

{manually maintained}

### Development

{manually maintained}
```

---

## Documentation Checklist

- [ ] Create `scripts/verify_docs.py`
- [ ] Create `scripts/generate_api_docs.py`
- [ ] Create `scripts/generate_config_docs.py`
- [ ] Add `docs-verify` to Makefile
- [ ] Add pre-commit hook for doc verification
- [ ] Add CI step for documentation verification
- [ ] Mark auto-generated sections in README
- [ ] Create CONTRIBUTING.md with documentation guidelines
- [ ] Set up doc generation in release process

---

## Maintenance Guidelines

### What to Auto-Generate

- API endpoint list
- Environment variable reference
- Database schema (from introspection)
- Command reference (from Makefile)

### What to Manually Maintain

- Architecture explanations
- Design decisions
- Getting started guides
- Troubleshooting guides

---

## References

- [Docs as Code](https://www.writethedocs.org/guide/docs-as-code/)
- [OpenAPI Documentation](https://swagger.io/specification/)
- [pre-commit: Documentation](https://pre-commit.com/)
