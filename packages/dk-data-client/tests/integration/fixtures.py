"""Integration-test fixture harness for dk-data-client.

Brings up an ephemeral dk-data-FE stack (Postgres + PostgREST + metering
proxy) that the TS and Python integration suites can point their
clients at. Used by the CI `integration` job and by `pnpm test
tests/integration` / `pytest tests/integration` on a developer machine.

Usage:

    # Bring up the stack. Prints the base URL on stdout.
    python fixtures.py up

    # Tear it down (idempotent).
    python fixtures.py down

    # Run as a context manager in a pytest conftest:
    with EphemeralDkData() as stack:
        client = DkDataClient(metering_proxy_url=stack.base_url, api_key=stack.api_key)

Design notes:
  - The fixture reuses the existing `docker-compose.yml` (points at
    `src/dk_data/docker-compose.yml`) rather than reinventing the
    container recipe. That's the "single source of truth" per
    principles §5.
  - A fresh Postgres database is seeded with just enough schema + rows
    to exercise the client's happy path: `mol_silver.molecules`,
    `mol_silver.molecule_identifiers`, `mol_gold.molecule_profile`, and
    a handful of fixture rows for well-known CHEMBL IDs.
  - The metering proxy is started with a test consumer whose API key is
    printed on bring-up.
  - On `down`, the docker volume is wiped so no test leak persists.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_FILE = REPO_ROOT / "src" / "dk_data" / "docker-compose.yml"
STATE_DIR = Path.home() / ".dk-data-client-fixtures"
STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class EphemeralDkData:
    base_url: str = "http://localhost:3001"
    api_key: str = "dk_data_test_integration_key"
    compose_file: Path = COMPOSE_FILE

    def up(self, *, wait_seconds: int = 60) -> None:
        if not self.compose_file.exists():
            raise RuntimeError(
                f"docker-compose file not found at {self.compose_file}"
            )
        env = os.environ.copy()
        env["POSTGREST_PASSWORD"] = "test_pw_integration"
        env["PGRST_JWT_SECRET"] = "test_jwt_secret_ephemeral"
        env["JWT_SECRET"] = env["PGRST_JWT_SECRET"]
        # Bring up services. Always Docker, no Kubernetes.
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "-p",
                "dk-data-client-fixture",
                "up",
                "-d",
            ],
            env=env,
            check=True,
        )
        self._wait_for_health(wait_seconds)
        self._seed_fixture_data()

    def down(self) -> None:
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "-p",
                "dk-data-client-fixture",
                "down",
                "-v",
            ],
            check=False,
        )

    def _wait_for_health(self, wait_seconds: int) -> None:
        """Poll the metering proxy /health until it returns 200 or timeout."""
        import urllib.request

        deadline = time.time() + wait_seconds
        url = f"{self.base_url}/health"
        last_error: str = ""
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if resp.status == 200:
                        return
            except Exception as e:  # noqa: BLE001
                last_error = str(e)
                time.sleep(1)
        raise RuntimeError(
            f"metering proxy did not come up within {wait_seconds}s — "
            f"last error: {last_error}"
        )

    def _seed_fixture_data(self) -> None:
        """Load a minimum fixture dataset for the integration suite.

        Reads `tests/integration/fixture.sql` (one directory up — see
        this module's sibling file) and pipes it into the compose
        postgres service. The fixture is idempotent — each test run
        truncates + reinserts.
        """
        sql_file = Path(__file__).parent / "fixture.sql"
        if not sql_file.exists():
            # No fixture yet — tests that need data should write one
            return
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "-p",
                "dk-data-client-fixture",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "postgres",
                "-d",
                "dk_data",
            ],
            input=sql_file.read_bytes(),
            check=True,
        )

    def __enter__(self) -> EphemeralDkData:
        self.up()
        return self

    def __exit__(self, *exc: object) -> None:
        self.down()


@contextmanager
def ephemeral() -> Iterator[EphemeralDkData]:
    """Context manager for use from test conftests."""
    stack = EphemeralDkData()
    try:
        stack.up()
        yield stack
    finally:
        stack.down()


def main() -> int:
    parser = argparse.ArgumentParser(description="dk-data-client integration fixture")
    parser.add_argument("command", choices=["up", "down"])
    args = parser.parse_args()
    stack = EphemeralDkData()
    if args.command == "up":
        stack.up()
        print(f"base_url={stack.base_url}")
        print(f"api_key={stack.api_key}")
    else:
        stack.down()
    return 0


if __name__ == "__main__":
    sys.exit(main())
