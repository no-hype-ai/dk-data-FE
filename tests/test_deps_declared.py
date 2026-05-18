"""Declared-dependency tests for dk_data.

Guards against fragile transitive resolution: modules that import a package
unconditionally at module top must have that package declared in
`[project].dependencies` in pyproject.toml.

These tests run without any services — they only parse pyproject.toml.
"""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _declared_dependency_names() -> set[str]:
    """Return normalized distribution names from [project].dependencies."""
    data = tomllib.loads(PYPROJECT.read_text())
    deps = data["project"]["dependencies"]
    names = set()
    for entry in deps:
        # Distribution name is the leading run of name characters before any
        # version spec / extras / marker (e.g. "openpyxl>=3.1,<4.0").
        match = re.match(r"^\s*([A-Za-z0-9._-]+)", entry)
        if match:
            # PEP 503 normalization: lowercase, runs of [-_.] -> "-".
            names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return names


def test_openpyxl_is_declared():
    """openpyxl is imported unconditionally by ema_epar; declare it explicitly."""
    assert "openpyxl" in _declared_dependency_names()
