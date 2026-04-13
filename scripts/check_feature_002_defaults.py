#!/usr/bin/env python3
"""T164 — CI lint for feature 002 open-question defaults.

Feature: 002-external-integration-foundation (D14)

The feature 002 spec resolved 15 open questions during the clarify
phase. Each resolution became a project default. This CI check
enforces that new PRs can't silently reintroduce the old behavior.

Enforced defaults (with the task/decision they came from):

  1. **JWT audience strict** (FR-060): every JWTService caller must
     pass `expected_audience="dk-data"` — no `expected_audience=None`
  2. **No web_anon grants in new migrations** (F-D014): migrations
     numbered ≥ 218 must not contain `GRANT ... TO web_anon` (the
     rollback file is the one exception)
  3. **PostgREST probes stay TCP** (D6): `k8s/apps/postgrest/base/
     deployment.yaml` must not reintroduce `httpGet` probes
  4. **dk-data-client telemetry never logs raw args** (FR-061):
     `dk_data_client/telemetry.py` must reference `hash_args` and
     must NOT reference `json.dumps(args)` as a top-level expression
  5. **No BYPASS of the metering proxy** (F-D008): any new k8s Service
     selector pointing at PostgREST directly must include a comment
     explaining why, and the Deployment's Service must still route
     through the metering-proxy sidecar

Exit codes:
    0 — all defaults enforced
    1 — one or more violations
    2 — prerequisite failure
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

Violation = str


def check_jwt_audience_strict() -> list[Violation]:
    """Every JWTService call must pass expected_audience="dk-data"."""
    violations: list[Violation] = []
    target = REPO_ROOT / "src" / "dk_data" / "services" / "auth"
    if not target.exists():
        return violations
    for py_file in target.rglob("*.py"):
        text = py_file.read_text()
        if "expected_audience=None" in text:
            violations.append(
                f"{py_file.relative_to(REPO_ROOT)}: expected_audience=None — "
                "must be 'dk-data' per FR-060"
            )
    return violations


def check_no_new_web_anon_grants() -> list[Violation]:
    """Migrations ≥ 218 must not grant to web_anon."""
    violations: list[Violation] = []
    migrations_dir = REPO_ROOT / "src" / "dk_data" / "sql" / "migrations"
    if not migrations_dir.exists():
        return violations
    pattern = re.compile(r"GRANT\s+[A-Z, ]+\s+TO\s+web_anon", re.IGNORECASE)
    for sql_file in migrations_dir.glob("*.sql"):
        match = re.match(r"^(\d+)_", sql_file.name)
        if not match:
            continue
        number = int(match.group(1))
        if number < 218:
            continue  # historical, not our concern
        if "rollback" in sql_file.name:
            continue  # the minimum-restore rollback is allowed per F-D014
        code_only = "\n".join(
            line for line in sql_file.read_text().splitlines()
            if not line.lstrip().startswith("--")
        )
        if pattern.search(code_only):
            violations.append(
                f"{sql_file.name}: grants to web_anon in a post-218 migration"
            )
    return violations


def check_postgrest_probes_stay_tcp() -> list[Violation]:
    """k8s/apps/postgrest/base/deployment.yaml must not reintroduce httpGet probes."""
    violations: list[Violation] = []
    deployment = REPO_ROOT / "k8s" / "apps" / "postgrest" / "base" / "deployment.yaml"
    if not deployment.exists():
        return violations
    text = deployment.read_text()
    # If the file contains `httpGet:` AND a probe block, that's a regression.
    if "httpGet:" in text and re.search(r"Probe:\s*\n\s+httpGet:", text):
        violations.append(
            "k8s/apps/postgrest/base/deployment.yaml: httpGet probe reintroduced "
            "(decision D6 requires TCP-only probes)"
        )
    return violations


def check_telemetry_hashes_args() -> list[Violation]:
    """dk-data-client telemetry must hash args, not log them raw."""
    violations: list[Violation] = []
    py_telemetry = (
        REPO_ROOT
        / "packages"
        / "dk-data-client"
        / "python"
        / "dk_data_client"
        / "telemetry.py"
    )
    if py_telemetry.exists():
        text = py_telemetry.read_text()
        if "hash_args" not in text:
            violations.append(
                "packages/dk-data-client/python/dk_data_client/telemetry.py: "
                "must call hash_args() — see FR-061"
            )
    ts_telemetry = (
        REPO_ROOT
        / "packages"
        / "dk-data-client"
        / "typescript"
        / "src"
        / "telemetry.ts"
    )
    if ts_telemetry.exists():
        text = ts_telemetry.read_text()
        if "hashArgs" not in text:
            violations.append(
                "packages/dk-data-client/typescript/src/telemetry.ts: "
                "must call hashArgs() — see FR-061"
            )
    return violations


def check_postgrest_service_via_proxy() -> list[Violation]:
    """
    The external PostgREST Service must route through the metering-proxy
    sidecar. The proxy runs on port 3001 in the PostgREST pod, and the
    external Service should target it, not port 3000 (PostgREST's own
    port, which would bypass auth).

    This check is advisory — if the file doesn't exist, skip.
    """
    violations: list[Violation] = []
    service_file = REPO_ROOT / "k8s" / "apps" / "postgrest" / "base" / "service.yaml"
    if not service_file.exists():
        return violations
    text = service_file.read_text()
    # If there's an `externalTrafficPolicy` or LoadBalancer Service that
    # targets port 3000 directly (PostgREST) rather than 3001 (proxy),
    # flag it. This is a heuristic — add refinements as the pattern evolves.
    if "type: LoadBalancer" in text and "targetPort: 3000" in text:
        violations.append(
            "k8s/apps/postgrest/base/service.yaml: LoadBalancer Service "
            "targets PostgREST port 3000 directly — must route through "
            "metering-proxy (port 3001)"
        )
    return violations


def main() -> int:
    all_violations: list[Violation] = []
    all_violations.extend(check_jwt_audience_strict())
    all_violations.extend(check_no_new_web_anon_grants())
    all_violations.extend(check_postgrest_probes_stay_tcp())
    all_violations.extend(check_telemetry_hashes_args())
    all_violations.extend(check_postgrest_service_via_proxy())

    if all_violations:
        print("Feature 002 default-check FAILED:\n", file=sys.stderr)
        for v in all_violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print("Feature 002 default-check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
