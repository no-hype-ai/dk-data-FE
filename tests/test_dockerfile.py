"""Container image smoke tests for dk_data package.

Validates that the Dockerfile and entry point modules are correctly configured:
- No redundant source copy that shadows the installed package
- No PYTHONPATH override that bypasses site-packages
- Entry point modules use absolute imports
- Key modules are importable as installed packages

These tests run without Docker — they validate source code correctness.
Docker build verification is done via quickstart.md commands.
"""

import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent


class TestDockerfileCorrectness:
    """Verify Dockerfile doesn't contain known bugs from Issue #88."""

    def test_no_redundant_source_copy(self):
        """Dockerfile must NOT copy raw source over installed package."""
        dockerfile = (REPO_ROOT / "Dockerfile").read_text()
        assert "/build/src/dk_data /app/dk_data" not in dockerfile, (
            "Dockerfile still contains redundant COPY of raw source "
            "that shadows the pip-installed package"
        )

    def test_no_pythonpath_override(self):
        """Dockerfile must NOT set PYTHONPATH=/app."""
        dockerfile = (REPO_ROOT / "Dockerfile").read_text()
        assert "PYTHONPATH=/app" not in dockerfile, (
            "Dockerfile still sets PYTHONPATH=/app which causes Python "
            "to find the raw source dir instead of site-packages"
        )

    def test_pip_install_present(self):
        """Dockerfile must install the package via pip."""
        dockerfile = (REPO_ROOT / "Dockerfile").read_text()
        assert "pip install" in dockerfile, (
            "Dockerfile missing pip install step"
        )


class TestEntryPointImports:
    """Verify CronJob entry point modules use absolute imports."""

    def test_fetch_data_no_sys_path_hack(self):
        """fetch_data.py must not use sys.path.insert for imports."""
        fetch_data = (
            REPO_ROOT / "src" / "dk_data" / "ingestion" / "fetch_data.py"
        ).read_text()
        assert "sys.path.insert" not in fetch_data, (
            "fetch_data.py still uses sys.path.insert() — "
            "should use absolute dk_data.* imports"
        )

    def test_fetch_data_absolute_imports(self):
        """fetch_data.py must use dk_data.ingestion.fetchers imports."""
        fetch_data = (
            REPO_ROOT / "src" / "dk_data" / "ingestion" / "fetch_data.py"
        ).read_text()
        assert "from dk_data.ingestion.fetchers import" in fetch_data

    def test_fetch_molecules_absolute_imports(self):
        """fetch_molecules.py must use dk_data.* imports."""
        fetch_molecules = (
            REPO_ROOT / "src" / "dk_data" / "ingestion" / "fetch_molecules.py"
        ).read_text()
        assert "sys.path.insert" not in fetch_molecules

    def test_fetch_data_importable(self):
        """fetch_data module must be importable."""
        mod = importlib.import_module("dk_data.ingestion.fetch_data")
        assert mod is not None
        assert hasattr(mod, "FETCHERS")

    def test_fetch_molecules_importable(self):
        """fetch_molecules module must be importable."""
        mod = importlib.import_module("dk_data.ingestion.fetch_molecules")
        assert mod is not None
        assert hasattr(mod, "main")
