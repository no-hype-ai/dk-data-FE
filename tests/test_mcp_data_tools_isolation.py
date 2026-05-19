"""Regression guard for the sys.modules landmine in test_mcp_data_tools.py.

`tests/test_mcp_data_tools.py` loads MCP source modules directly via a
custom importlib loader at *collection time* (module-level code). Before the
WS3 fix this left the canonical ``dk_data.services.mcp.*`` keys in
``sys.modules`` polluted:

- ``sys.modules["dk_data.services.mcp.adapters"]`` became an empty
  ``types.ModuleType`` stub (no ``__spec__``, no ``__file__``), and
- a fresh ``importlib.import_module(...)`` of a submodule returned the
  file-loaded copy instead of the canonical package module.

That split-brain made #421's CI red (a test patched a re-imported class
while the router held the canonical one) and would poison the ~26 new
``test_adapter_*.py`` files added in WS3 batches that are collected after
this file.

This test imports ``tests.test_mcp_data_tools`` (running its module-level
loader exactly as pytest collection would) and then asserts the canonical
``dk_data`` namespace is left pristine. It FAILS on origin/staging's
unfixed code and PASSES after the snapshot/restore wrapper is added.
"""

import importlib
import sys
import types
from pathlib import Path

# Canonical src root: the editable install adds the *main checkout* src to
# sys.path, so canonical module __file__ values resolve under <repo>/src.
_CANONICAL_SRC = Path(
    importlib.import_module("dk_data").__file__
).resolve().parent.parent


def _import_data_tools_module():
    """Import (and thus collect, at module level) the loader test file."""
    return importlib.import_module("tests.test_mcp_data_tools")


def test_adapters_package_not_left_as_empty_stub():
    """After collecting test_mcp_data_tools, the canonical adapters package
    key must be absent OR a *real* package (loaded from src/.../__init__.py),
    never an empty types.ModuleType stub with no loader/spec.
    """
    _import_data_tools_module()

    key = "dk_data.services.mcp.adapters"
    mod = sys.modules.get(key)

    if mod is None:
        # Absent is acceptable — nothing polluted.
        return

    spec = getattr(mod, "__spec__", None)
    file_attr = getattr(mod, "__file__", None)

    assert spec is not None, (
        f"{key} left in sys.modules as an empty stub (__spec__ is None) — "
        "test_mcp_data_tools collection polluted the canonical namespace"
    )
    assert file_attr is not None, (
        f"{key} left in sys.modules with no __file__ — empty stub pollution"
    )

    resolved = Path(file_attr).resolve()
    assert resolved == (
        _CANONICAL_SRC / "dk_data" / "services" / "mcp" / "adapters" / "__init__.py"
    ), (
        f"{key} __file__ ({resolved}) does not point at the canonical "
        f"package __init__.py under {_CANONICAL_SRC}"
    )


def test_fresh_import_of_submodule_is_canonical():
    """An import of an adapter submodule, performed AFTER
    test_mcp_data_tools has been collected, must resolve to the canonical
    module under the repo src/ path (the editable-install src), not the
    file-loaded copy the loader injected — and must keep a single class
    identity shared with the canonical package (the exact #421 split-brain).

    We deliberately do NOT pop the cached submodule first: popping and
    re-importing would re-execute the canonical file and create a *new*
    class object even with zero pollution, which is an artefact of the
    test, not a real split-brain. The true regression signal is whether
    the resident module (and its class) the codebase will actually use is
    the canonical one consistent with the canonical package.
    """
    _import_data_tools_module()

    submod_name = "dk_data.services.mcp.adapters.hta_decisions"

    # Importing the canonical package establishes/repairs the canonical
    # submodule binding the codebase relies on (mirrors what the router
    # does via `from dk_data.services.mcp.adapters import ...`).
    canonical_pkg = importlib.import_module("dk_data.services.mcp.adapters")

    # Parent must be a real package, never an empty stub.
    assert not (
        isinstance(canonical_pkg, types.ModuleType)
        and getattr(canonical_pkg, "__spec__", None) is None
    ), "adapters package is an empty stub after collection — pollution"
    pkg_file = getattr(canonical_pkg, "__file__", None)
    assert pkg_file is not None
    assert Path(pkg_file).resolve() == (
        _CANONICAL_SRC / "dk_data" / "services" / "mcp" / "adapters" / "__init__.py"
    ), f"adapters package resolved to {pkg_file}, not the canonical __init__.py"

    hta = importlib.import_module(submod_name)

    file_attr = getattr(hta, "__file__", None)
    assert file_attr is not None, (
        f"{submod_name} import has no __file__ — namespace poisoned"
    )
    resolved = Path(file_attr).resolve()
    assert resolved == (
        _CANONICAL_SRC
        / "dk_data"
        / "services"
        / "mcp"
        / "adapters"
        / "hta_decisions.py"
    ), (
        f"import of {submod_name} resolved to {resolved}, not the "
        f"canonical file under {_CANONICAL_SRC} — split-brain pollution"
    )

    # The class the codebase will use via the canonical package must be the
    # exact same object as the one on the resolved submodule. Before the
    # fix, the loader-injected copy made these two differ — that mismatch is
    # precisely what made #421's instance-vs-class patch miss.
    assert hta.HtaDecisionsTool is canonical_pkg.HtaDecisionsTool, (
        "HtaDecisionsTool identity differs between the resident submodule "
        "and the canonical package — the exact #421 split-brain"
    )
