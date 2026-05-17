"""Regression guard: every TAVR fetch CronJob's source arg must be a
registered key in `dk_data.ingestion.main.SOURCES`.

Background: the TAVR Phase 0/1A/1B bundle (PRs #392/#395/#398/#399/
#400/#401) deployed six `cronjob-fetch-tavr-*.yaml` CronJobs, each of
which invokes `run_ingestion(<arg>)`. `run_ingestion` raises
``ValueError: Unknown source`` for any source not in `SOURCES`. If a
fetcher/loader is imported but never wired into `SOURCES` (the
hospital_profile gap that surfaced as an F401 lint error), the deployed
CronJob fails at runtime on every fire while CI stays green.

This test pins the k8s CronJob args to the Python source registry so
the drift cannot recur silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dk_data.ingestion.main import SOURCES

REPO_ROOT = Path(__file__).resolve().parents[2]
CRONJOB_DIR = REPO_ROOT / "k8s" / "apps" / "cronjobs" / "base"

_ARGS_RE = re.compile(r'args:\s*\[\s*"([^"]+)"\s*\]')


def _tavr_cronjob_sources() -> list[tuple[str, str]]:
    """Return (cronjob_filename, source_arg) for every TAVR fetch CronJob."""
    pairs: list[tuple[str, str]] = []
    for path in sorted(CRONJOB_DIR.glob("cronjob-fetch-tavr-*.yaml")):
        m = _ARGS_RE.search(path.read_text())
        assert m, f"{path.name}: could not parse `args: [\"...\"]`"
        pairs.append((path.name, m.group(1)))
    return pairs


def test_tavr_cronjobs_discovered():
    """Sanity: we actually found the TAVR CronJobs (guards the glob)."""
    pairs = _tavr_cronjob_sources()
    assert len(pairs) >= 6, f"expected >=6 TAVR CronJobs, found {pairs}"


@pytest.mark.parametrize(
    "cronjob,source", _tavr_cronjob_sources(), ids=lambda v: v
)
def test_tavr_cronjob_source_is_registered(cronjob: str, source: str):
    assert source in SOURCES, (
        f"{cronjob} fires run_ingestion('{source}') but '{source}' is not "
        f"a key in dk_data.ingestion.main.SOURCES — the CronJob will raise "
        f"ValueError('Unknown source: {source}') on every fire. "
        f"Wire the fetcher + loader into SOURCES."
    )
    entry = SOURCES[source]
    assert callable(entry.get("fetcher")), (
        f"SOURCES['{source}']['fetcher'] is not callable: {entry.get('fetcher')!r}"
    )
    assert callable(entry.get("loader")), (
        f"SOURCES['{source}']['loader'] is not callable: {entry.get('loader')!r}"
    )
