"""Contract test — T064.

Verifies that the client-side schema fingerprint (baked in by
`scripts/generate-types.sh`) matches the fingerprint reported by a live
dk-data instance's `/rpc/server_info` endpoint.

This test is the teeth behind the "warn on mismatch" policy in
src/version.ts. It fails CI on any PR that modifies the dk-data
contract (PostgREST OpenAPI or FastAPI OpenAPI) without also
regenerating the client types.

The test fetches the live OpenAPI surfaces, computes the same
fingerprint the generate-types script would compute, and compares
against the baked-in value. Run manually:

    DK_DATA_INTEGRATION_URL=http://localhost:3001 \
    DK_DATA_INTEGRATION_KEY=dk_data_test_integration_key \
      pytest packages/dk-data-client/tests/contract/ -q

Skipped unless the integration env vars are set.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

try:
    import httpx
except ImportError:  # pragma: no cover
    pytest.skip("httpx required for contract tests", allow_module_level=True)


INTEGRATION_URL = os.environ.get("DK_DATA_INTEGRATION_URL")
INTEGRATION_KEY = os.environ.get("DK_DATA_INTEGRATION_KEY")

skipif_no_stack = pytest.mark.skipif(
    not (INTEGRATION_URL and INTEGRATION_KEY),
    reason="ephemeral dk-data-FE stack not available",
)


def _canonical_json(value: Any) -> str:
    """Match the sort order used by jq -S in generate-types.sh."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _compute_fingerprint(postgrest_spec: Any, fastapi_spec: Any) -> str:
    combined = {"postgrest": postgrest_spec, "fastapi": fastapi_spec}
    payload = _canonical_json(combined)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_baked_fingerprint() -> str:
    """Read the fingerprint baked into the client source.

    For the Python client, we look at `dk_data_client/_fingerprint.py`
    which the generate-types script writes. For the TypeScript client,
    we parse `typescript/src/version.ts`. The two must agree — that's
    how we ensure both language builds stayed in sync at type-gen time.
    """
    repo_root = Path(__file__).resolve().parents[2]

    py_fingerprint: str | None = None
    py_file = repo_root / "python" / "dk_data_client" / "_fingerprint.py"
    if py_file.exists():
        for line in py_file.read_text().splitlines():
            if line.startswith("CLIENT_SCHEMA_FINGERPRINT"):
                py_fingerprint = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

    ts_fingerprint: str | None = None
    ts_file = repo_root / "typescript" / "src" / "version.ts"
    if ts_file.exists():
        for line in ts_file.read_text().splitlines():
            if "CLIENT_SCHEMA_FINGERPRINT" in line and "=" in line:
                right = line.split("=", 1)[1].strip().rstrip(";").strip()
                ts_fingerprint = right.strip('"').strip("'")
                break

    assert (
        py_fingerprint is not None or ts_fingerprint is not None
    ), "neither the Python nor TypeScript fingerprint is present"
    if py_fingerprint and ts_fingerprint and py_fingerprint != ts_fingerprint:
        raise AssertionError(
            f"Python fingerprint ({py_fingerprint[:16]}...) and TypeScript "
            f"fingerprint ({ts_fingerprint[:16]}...) disagree — regenerate types."
        )
    return (py_fingerprint or ts_fingerprint) or ""


@skipif_no_stack
def test_client_fingerprint_matches_live_dk_data():
    """The baked fingerprint must match the fingerprint of the live OpenAPI.

    If this fails, the fix is:

        cd packages/dk-data-client
        DK_DATA_BASE_URL=$DK_DATA_INTEGRATION_URL \
          DK_DATA_API_KEY=$DK_DATA_INTEGRATION_KEY \
          ./scripts/generate-types.sh

    Then commit the updated fingerprint.
    """
    baked = _read_baked_fingerprint()
    if baked == "v0.1.0-placeholder":
        pytest.skip(
            "fingerprint is still the v0.1.0 placeholder — run scripts/generate-types.sh"
        )
    headers = {"Authorization": f"Bearer {INTEGRATION_KEY}"}
    with httpx.Client(timeout=10) as http:
        postgrest = http.get(f"{INTEGRATION_URL}/", headers=headers)
        fastapi = http.get(f"{INTEGRATION_URL}/openapi.json", headers=headers)
    postgrest.raise_for_status()
    fastapi.raise_for_status()
    computed = _compute_fingerprint(postgrest.json(), fastapi.json())
    assert computed == baked, (
        f"fingerprint drift: baked={baked[:16]}... live={computed[:16]}... "
        f"— regenerate client types"
    )


def test_client_fingerprint_is_present_offline():
    """Even without a live stack, there must be a fingerprint somewhere.

    This catches the "someone deleted _fingerprint.py and version.ts
    placeholder at the same time" scenario.
    """
    baked = _read_baked_fingerprint()
    assert baked, "no fingerprint found in client source"
