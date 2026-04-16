#!/usr/bin/env python3
"""
One-shot rewrite: stamp a `dk-data-fe-` UID prefix on every dashboard JSON in
`grafana/dashboards/`, set `__metadata.folder = applications`, and move each
file to `grafana/dashboards/applications/dk-data-fe-<basename>.json`.

Output structure matches the dk-alchemy canonical form: each JSON is a two-key
object `{ "__metadata": {...}, "dashboard": {...} }`, so the existing
`sync-all.sh` / `import-dashboard.sh` helpers can parse folder + inner
dashboard identically to how they handle dk-alchemy dashboards.

Invoked once by this PR (PR-09); not part of CI. Idempotent.
"""

from __future__ import annotations

import json
import pathlib
import sys


REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "grafana" / "dashboards"
DST = SRC / "applications"
FOLDER = "applications"


RENAMES = {
    # source basename (no .json) -> target basename (no .json) == new uid
    "cms-pipeline-health": "dk-data-fe-cms-pipeline-health",
    "dk-data-platform-status": "dk-data-fe-platform-status",
    "dk-data-pipeline-sources": "dk-data-fe-pipeline-sources",
    "dk-data-transformations": "dk-data-fe-transformations",
    "dk-data-api-services": "dk-data-fe-api-services",
    "dk-data-adapter-telemetry": "dk-data-fe-adapter-telemetry",
}


def normalize(doc: dict, target_uid: str) -> dict:
    """
    Return `{ "__metadata": {"folder": "applications"}, "dashboard": {...} }`.

    Handles three incoming shapes:
      1. Unwrapped: top-level dashboard fields, no __metadata.
      2. Half-wrapped (observed in-repo): __metadata sibling to dashboard
         fields (no nested .dashboard key) — flatten and re-wrap.
      3. Fully wrapped (dk-alchemy canonical): __metadata + dashboard keys.
    """
    if "dashboard" in doc and isinstance(doc["dashboard"], dict):
        inner = doc["dashboard"]
    else:
        # strip wrapper metadata if present and treat remainder as the dashboard
        inner = {k: v for k, v in doc.items() if k != "__metadata"}

    inner["uid"] = target_uid
    return {
        "__metadata": {"folder": FOLDER},
        "dashboard": inner,
    }


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src_stem, dst_stem in RENAMES.items():
        src_path = SRC / f"{src_stem}.json"
        dst_path = DST / f"{dst_stem}.json"
        if not src_path.exists() and dst_path.exists():
            print(f"[skip]  already moved: {dst_path.relative_to(REPO)}")
            continue
        if not src_path.exists():
            print(f"[warn]  missing: {src_path.relative_to(REPO)}")
            continue
        data = json.loads(src_path.read_text())
        wrapped = normalize(data, dst_stem)
        dst_path.write_text(json.dumps(wrapped, indent=2) + "\n")
        src_path.unlink()
        moved += 1
        print(f"[move]  {src_path.relative_to(REPO)} -> {dst_path.relative_to(REPO)}")
    print(f"\nMoved {moved} dashboard(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
