"""Import smoke tests for dk_data package.

Verifies that all top-level submodules can be imported without errors.
This catches broken imports, missing dependencies, and circular import issues.
"""

import importlib

import pytest


# Top-level submodules that should always be importable
CORE_MODULES = [
    "dk_data.core",
    "dk_data.database",
    "dk_data.models",
    "dk_data.models.data_platform",
    "dk_data.models.data_platform.base",
    "dk_data.models.bronze",
    "dk_data.models.silver",
    "dk_data.models.gold",
    "dk_data.models.application",
    "dk_data.ingestion",
    "dk_data.ingestion.fetchers",
    "dk_data.ingestion.fetchers.base",
    "dk_data.ingestion.utils",
    "dk_data.ingestion.utils.validators",
    "dk_data.observability",
]

# Modules that require optional dependencies or env config
OPTIONAL_MODULES = [
    "dk_data.api",
    "dk_data.api.routes",
    "dk_data.claude_sdk",
    "dk_data.services",
]

# Fetcher modules
FETCHER_MODULES = [
    "dk_data.ingestion.fetchers.cms_inpatient",
    "dk_data.ingestion.fetchers.cms_hospital_info",
    "dk_data.ingestion.fetchers.cms_cost_reports",
    "dk_data.ingestion.fetchers.hrsa",
    "dk_data.ingestion.fetchers.acc_tvc",
]


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_core_module_imports(module_name):
    """Core modules must import without errors."""
    mod = importlib.import_module(module_name)
    assert mod is not None


@pytest.mark.parametrize("module_name", FETCHER_MODULES)
def test_fetcher_module_imports(module_name):
    """Fetcher modules must import without errors."""
    mod = importlib.import_module(module_name)
    assert mod is not None


@pytest.mark.parametrize("module_name", OPTIONAL_MODULES)
def test_optional_module_imports(module_name):
    """Optional modules should import (warn if they fail due to missing deps)."""
    try:
        mod = importlib.import_module(module_name)
        assert mod is not None
    except ImportError as e:
        pytest.skip(f"Optional module {module_name} unavailable: {e}")
