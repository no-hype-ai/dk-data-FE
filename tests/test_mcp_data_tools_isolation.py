"""Regression guard for the sys.modules landmine in test_mcp_data_tools.py.

``tests/test_mcp_data_tools.py`` loads MCP source modules directly via a
custom importlib loader at *collection time* (module-level code). Before the
WS3 fix this left the canonical ``dk_data.services.mcp.*`` keys in
``sys.modules`` polluted:

- ``sys.modules["dk_data.services.mcp.adapters"]`` became an empty
  ``types.ModuleType`` stub (no ``__spec__``, no ``__file__``), and
- a fresh ``importlib.import_module(...)`` of a submodule returned a
  file-loaded copy whose class objects differed from the canonical
  package's — a split-brain.

That split-brain made #421's CI red (a test patched a re-imported class
while the router held the canonical one) and would poison the ~26 new
``test_adapter_*.py`` files added in WS3 batches that are collected after
this file.

This test executes ``test_mcp_data_tools.py``'s module-level loader exactly
as pytest collection would — but loads it *by absolute file path under a
throwaway module name*, never via ``importlib.import_module("tests.…")``.
``tests/`` is NOT an importable package under CI's ``pytest tests/`` (no
``tests/__init__.py``; pytest collects by path/rootdir), so a
``tests``-package import passes only on dev machines and fails in CI. The
file-path probe is faithful to how collection actually runs the module.

The assertions are identity/anchor based (no hard-coded src path coupling):
they FAIL on origin/staging's unfixed code (empty-stub pollution /
class-identity split-brain) and PASS after the snapshot/restore wrapper.
"""

import importlib
import importlib.util
import sys
import types
from pathlib import Path

_PROBE_PATH = Path(__file__).parent / "test_mcp_data_tools.py"
_PROBE_MOD_NAME = "_isolation_probe_tmdt"

# Canonical adapters package __init__ path (suffix the loaded module's
# __file__ must end with). Anchored on the *package layout*, not on a
# resolved repo-src absolute path, so this is robust to where the editable
# install / worktree lives.
_ADAPTERS_INIT_SUFFIX = "/dk_data/services/mcp/adapters/__init__.py"


def _import_data_tools_module():
    """Run test_mcp_data_tools.py's module-level loader exactly as pytest
    collection would, WITHOUT depending on ``tests`` being an importable
    package.

    We load the file by absolute path via spec_from_file_location under a
    unique throwaway module name and exec it. exec_module runs the file's
    module-level ``_ensure_pkg``/``_load`` block and the WS3 snapshot/restore
    guard — the precise code path collection exercises — with zero
    ``tests``-package dependency (``tests/`` has no ``__init__.py`` and is
    not importable under CI's ``pytest tests/``).
    """
    sys.modules.pop(_PROBE_MOD_NAME, None)
    spec = importlib.util.spec_from_file_location(_PROBE_MOD_NAME, _PROBE_PATH)
    assert spec is not None and spec.loader is not None, (
        f"could not build import spec for probe at {_PROBE_PATH}"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_PROBE_MOD_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


def test_adapters_package_not_left_as_empty_stub():
    """After executing test_mcp_data_tools's loader, the canonical adapters
    package key must be absent OR a *real* package (loaded from the package
    ``__init__.py``), never an empty types.ModuleType stub with no
    loader/spec.
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

    resolved = Path(file_attr).resolve().as_posix()
    assert resolved.endswith(_ADAPTERS_INIT_SUFFIX), (
        f"{key} __file__ ({resolved}) does not point at the canonical "
        f"package __init__.py (expected to end with {_ADAPTERS_INIT_SUFFIX})"
    )


def test_fresh_import_of_submodule_is_canonical():
    """An import of an adapter submodule, performed AFTER
    test_mcp_data_tools's loader has run, must keep a single class identity
    shared with the canonical package — the exact #421 split-brain signal.

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
    assert pkg_file is not None, (
        "canonical adapters package has no __file__ — namespace poisoned"
    )
    assert Path(pkg_file).resolve().as_posix().endswith(
        _ADAPTERS_INIT_SUFFIX
    ), (
        f"adapters package resolved to {pkg_file}, not the canonical "
        f"package __init__.py (expected to end with {_ADAPTERS_INIT_SUFFIX})"
    )

    hta = importlib.import_module(submod_name)

    file_attr = getattr(hta, "__file__", None)
    assert file_attr is not None, (
        f"{submod_name} import has no __file__ — namespace poisoned"
    )

    # The class the codebase will use via the canonical package must be the
    # exact same object as the one on the freshly-imported submodule. Before
    # the fix, the loader-injected copy made these two differ — that
    # mismatch is precisely what made #421's instance-vs-class patch miss.
    # Identity, not src-path coupling, is the regression signal.
    assert hta.HtaDecisionsTool is canonical_pkg.HtaDecisionsTool, (
        "HtaDecisionsTool identity differs between the resident submodule "
        "and the canonical package — the exact #421 split-brain"
    )
