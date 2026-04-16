#!/usr/bin/env python3
"""
Emit stub JSON dashboards for the 6 dashboards called out in plan.md §J.3.
Each stub is a single-panel placeholder with a prominent TODO note pointing at
the plan section that owns the full content.

Run once; idempotent (overwrite).
"""

from __future__ import annotations

import json
import pathlib


REPO = pathlib.Path(__file__).resolve().parent.parent
DST = REPO / "grafana" / "dashboards" / "applications"
FOLDER = "applications"


# uid -> (title, plan-section, description / first-panel-hint)
STUBS = {
    "dk-data-fe-hydration": (
        "dk-data Hydration (stub)",
        "plan.md §J.3, §B.3",
        "Per-source hydration run status from meta.transform_runs. "
        "TODO: fill in panels for step state, row_count vs expected, p50/p95 duration, "
        "failures in last 24h.",
    ),
    "dk-data-fe-hydration-backlog": (
        "dk-data Hydration Backlog (stub)",
        "plan.md §J.3, §C.3",
        "Rows from meta.hydration_backlog with failure signature, last_error, quarantine "
        "reason. TODO: wire queries once migration lands.",
    ),
    "dk-data-fe-wal-pressure": (
        "dk-data WAL Pressure (stub)",
        "plan.md §J.3, §C.2",
        "meta.wal_pressure timeline + pause events + budget consumption. "
        "TODO: land meta.wal_pressure view first (C.2), then build panels.",
    ),
    "dk-data-fe-seaweedfs-artifacts": (
        "dk-data SeaweedFS Artifacts (stub)",
        "plan.md §J.3, §C.4",
        "meta.artifact_provenance freshness, download bytes/min, size-mismatch events. "
        "TODO: depends on C.4 pipeline + C.1 SeaweedFS cutover.",
    ),
    "dk-data-fe-resource-budget": (
        "dk-data Resource Budget (stub)",
        "plan.md §J.3, §D.3",
        "meta.resource_budget utilization: WAL headroom, PgBouncer slots, concurrent "
        "restores. TODO: depends on D.3 admission-control migration.",
    ),
    "dk-data-fe-source-registry": (
        "dk-data Source Registry (stub)",
        "plan.md §J.3, §D.2, §F",
        "Source count by tier/domain/status (stub/fetcher_ready/live), onboarding "
        "velocity. TODO: depends on meta.source_registry migration.",
    ),
}


def stub_dashboard(uid: str, title: str, plan_ref: str, description: str) -> dict:
    """Construct a minimal, valid-Grafana-schema stub dashboard.

    The panel is intentionally a `text` panel (no datasource required) so the
    stub parses cleanly through the validator without needing prometheus/loki
    UIDs stubbed out. The description makes it obvious in Grafana that the
    dashboard is a placeholder.
    """
    body = (
        f"## TODO — placeholder stub\n\n"
        f"**Plan section:** {plan_ref}\n\n"
        f"{description}\n\n"
        f"This dashboard will be fleshed out in a follow-up PR once the upstream "
        f"migrations / views referenced above land. The UID is locked in now so "
        f"links from runbooks and alerts resolve as soon as content ships."
    )
    return {
        "__metadata": {"folder": FOLDER},
        "dashboard": {
            "uid": uid,
            "title": title,
            "description": f"Stub — see {plan_ref}",
            "tags": ["dk-data-fe", "stub"],
            "schemaVersion": 39,
            "editable": True,
            "refresh": "",
            "time": {"from": "now-6h", "to": "now"},
            "timepicker": {},
            "timezone": "",
            "templating": {"list": []},
            "annotations": {"list": []},
            "panels": [
                {
                    "id": 1,
                    "type": "text",
                    "title": "TODO",
                    "gridPos": {"h": 8, "w": 24, "x": 0, "y": 0},
                    "options": {
                        "mode": "markdown",
                        "content": body,
                    },
                }
            ],
        },
    }


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    written = 0
    for uid, (title, plan_ref, description) in STUBS.items():
        path = DST / f"{uid}.json"
        doc = stub_dashboard(uid, title, plan_ref, description)
        path.write_text(json.dumps(doc, indent=2) + "\n")
        written += 1
        print(f"[stub] {path.relative_to(REPO)}")
    print(f"\nWrote {written} stub dashboard(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
