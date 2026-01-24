# ISSUE-019: Python Dependency Version Management

**Project**: dk-data-FE
**Category**: Dependencies
**Priority**: P2 - Medium
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

Python dependencies use minimum version constraints (e.g., `>=2.9.9`) without upper bounds or lock files. This creates risk of dependency drift between environments, untested dependency combinations, and potential breaking changes from upstream updates.

---

## Current State

### requirements.txt Analysis

```
sqlmesh>=0.90.0          # Minimum only
psycopg2-binary>=2.9.9   # Minimum only
pandas>=2.0.0            # Minimum only
anthropic>=0.40.0        # Minimum only
pydantic>=2.5.0          # Minimum only
requests>=2.31.0         # Minimum only
python-dotenv>=1.0.0     # Minimum only
beautifulsoup4>=4.12.0   # Minimum only
lxml>=5.0.0              # Minimum only
fastapi>=0.109.0         # Minimum only
uvicorn>=0.27.0          # Minimum only
kubernetes>=29.0.0       # Minimum only
pytest>=8.0.0            # Minimum only
pytest-postgresql>=6.0.0 # Minimum only
```

**Issues**:
1. No upper version bounds
2. No lock file (requirements.lock, poetry.lock)
3. No hash verification
4. Development dependencies mixed with production

---

## Risk Assessment

### Dependency Drift Scenarios

| Scenario | Likelihood | Impact |
|----------|------------|--------|
| Minor update breaks API | Medium | Medium |
| Major version incompatibility | Low | High |
| Security vulnerability in dep | Medium | High |
| Different versions in dev/prod | High | Medium |

### Known Risky Dependencies

| Package | Risk | Reason |
|---------|------|--------|
| `pydantic>=2.5.0` | High | Pydantic v1→v2 had breaking changes |
| `sqlmesh>=0.90.0` | Medium | Active development, API changes |
| `anthropic>=0.40.0` | Medium | SDK updates with API changes |
| `pandas>=2.0.0` | Medium | Pandas 2.0 had breaking changes |

---

## Current vs Ideal State

### Current

```
requirements.txt
     │
     ▼
pip install -r requirements.txt
     │
     ▼
Latest compatible versions installed
(may differ between machines/times)
```

### Ideal

```
pyproject.toml (source of truth)
     │
     ▼
uv lock / pip-compile
     │
     ▼
requirements.lock (pinned versions + hashes)
     │
     ▼
pip install -r requirements.lock
     │
     ▼
Identical versions everywhere
```

---

## Recommended Solutions

### Option A: pip-tools (Recommended for simplicity)

#### A.1 Split Requirements Files

```
# requirements/base.in (production dependencies)
sqlmesh>=0.90.0,<1.0.0
psycopg2-binary>=2.9.9,<3.0.0
pandas>=2.0.0,<3.0.0
anthropic>=0.40.0,<1.0.0
pydantic>=2.5.0,<3.0.0
requests>=2.31.0,<3.0.0
python-dotenv>=1.0.0,<2.0.0
beautifulsoup4>=4.12.0,<5.0.0
lxml>=5.0.0,<6.0.0
fastapi>=0.109.0,<1.0.0
uvicorn>=0.27.0,<1.0.0
kubernetes>=29.0.0,<30.0.0
```

```
# requirements/dev.in
-r base.in
pytest>=8.0.0
pytest-postgresql>=6.0.0
pytest-cov>=4.0.0
ruff>=0.1.0
mypy>=1.0.0
```

```
# requirements/batch.in (job-trigger specific)
-r base.in
# Additional deps for batch container
```

#### A.2 Generate Lock Files

```bash
# Install pip-tools
pip install pip-tools

# Generate locked requirements
pip-compile requirements/base.in -o requirements/base.txt --generate-hashes
pip-compile requirements/dev.in -o requirements/dev.txt --generate-hashes

# Update locked requirements
pip-compile --upgrade requirements/base.in -o requirements/base.txt --generate-hashes
```

#### A.3 Makefile Integration

```makefile
.PHONY: deps deps-upgrade deps-sync deps-check

deps:
	pip-compile requirements/base.in -o requirements/base.txt --generate-hashes
	pip-compile requirements/dev.in -o requirements/dev.txt --generate-hashes

deps-upgrade:
	pip-compile --upgrade requirements/base.in -o requirements/base.txt --generate-hashes
	pip-compile --upgrade requirements/dev.in -o requirements/dev.txt --generate-hashes

deps-sync:
	pip-sync requirements/dev.txt

deps-check:
	pip-compile --dry-run --upgrade requirements/base.in
```

### Option B: Poetry (More comprehensive)

#### B.1 pyproject.toml

```toml
[tool.poetry]
name = "dk-data-fe"
version = "1.0.0"
description = "TAVR Data Infrastructure Platform"
authors = ["DataKinetic <dev@datakinetic.com>"]
readme = "README.md"
packages = [{include = "dk_data", from = "src"}]

[tool.poetry.dependencies]
python = "^3.11"
sqlmesh = "^0.90.0"
psycopg2-binary = "^2.9.9"
pandas = "^2.0.0"
anthropic = "^0.40.0"
pydantic = "^2.5.0"
requests = "^2.31.0"
python-dotenv = "^1.0.0"
beautifulsoup4 = "^4.12.0"
lxml = "^5.0.0"
fastapi = "^0.109.0"
uvicorn = "^0.27.0"
kubernetes = "^29.0.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0.0"
pytest-postgresql = "^6.0.0"
pytest-cov = "^4.0.0"
ruff = "^0.1.0"
mypy = "^1.0.0"

[tool.poetry.group.batch.dependencies]
# Specific to batch container

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

#### B.2 Poetry Commands

```bash
# Install dependencies
poetry install

# Update lock file
poetry lock

# Update specific package
poetry update pandas

# Export to requirements.txt (for Docker)
poetry export -f requirements.txt -o requirements.txt --without-hashes
```

### Option C: uv (Modern, fast)

#### C.1 Using uv

```bash
# Install uv
pip install uv

# Create lock file
uv pip compile requirements/base.in -o requirements/base.txt

# Install from lock file
uv pip sync requirements/base.txt

# Update all dependencies
uv pip compile --upgrade requirements/base.in -o requirements/base.txt
```

---

## Version Constraint Strategy

### Constraint Types

| Constraint | Example | When to Use |
|------------|---------|-------------|
| `==` | `==2.9.9` | Production lock files |
| `>=,<` | `>=2.9,<3.0` | Source files, SemVer |
| `~=` | `~=2.9.9` | Compatible release |
| `^` | `^2.9.9` | Poetry caret (SemVer) |

### Recommended Constraints by Package Type

| Type | Constraint | Example |
|------|------------|---------|
| Core framework | Minor bounds | `>=2.0,<2.2` |
| Stable library | Major bounds | `>=2.0,<3.0` |
| Active development | Minor bounds | `>=0.90,<0.95` |
| Security-critical | Exact + hash | `==2.9.9 --hash=sha256:...` |

---

## Docker Integration

### Dockerfile Best Practices

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install locked dependencies first (caching)
COPY requirements/base.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
```

### Multi-Stage Build

```dockerfile
# Build stage - install dependencies
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements/base.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r base.txt

# Runtime stage - lean image
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*
COPY src/ ./src/
```

---

## CI/CD Integration

### Dependency Verification

```yaml
# .github/workflows/deps.yml
name: Dependency Check

on:
  pull_request:
    paths:
      - 'requirements/**'
      - 'pyproject.toml'

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install pip-tools
        run: pip install pip-tools

      - name: Verify lock file is up to date
        run: |
          pip-compile requirements/base.in -o requirements/base.txt.new
          diff requirements/base.txt requirements/base.txt.new

      - name: Check for security vulnerabilities
        run: |
          pip install safety
          safety check -r requirements/base.txt
```

---

## Security Scanning

### Dependabot Configuration

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      python-deps:
        patterns:
          - "*"
    ignore:
      - dependency-name: "*"
        update-types: ["version-update:semver-major"]
```

### Manual Vulnerability Check

```bash
# Using safety
pip install safety
safety check -r requirements/base.txt

# Using pip-audit
pip install pip-audit
pip-audit -r requirements/base.txt
```

---

## Implementation Checklist

- [ ] Choose dependency management approach (pip-tools recommended)
- [ ] Split requirements into base.in and dev.in
- [ ] Add upper version bounds to all dependencies
- [ ] Generate lock files with hashes
- [ ] Update Dockerfile to use lock files
- [ ] Add Makefile targets for dependency management
- [ ] Configure Dependabot for automated updates
- [ ] Add CI check for lock file freshness
- [ ] Document dependency update process
- [ ] Schedule quarterly dependency audit

---

## References

- [pip-tools Documentation](https://pip-tools.readthedocs.io/)
- [Poetry Documentation](https://python-poetry.org/docs/)
- [uv Documentation](https://github.com/astral-sh/uv)
- [Python Dependency Management](https://packaging.python.org/en/latest/discussions/install-requires-vs-requirements/)
- [Safety: Vulnerability Scanner](https://pyup.io/safety/)
