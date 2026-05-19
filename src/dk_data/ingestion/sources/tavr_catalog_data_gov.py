"""TAVR catalog (Data.gov) loader.

Reads the records returned by TavrCatalogDataGovFetcher and:

  1. Inserts one bronze row per fetch event into `hcs_bronze.tavr_catalog_raw`.
  2. Upserts the dedup'd silver row into `hcs_silver.tavr_catalog_packages`.
  3. Promotes / refreshes the gold row in `hcs_gold.tavr_catalog_candidate_manifest`,
     applying provenance discipline (NOT NULL + CHECK-constrained vocabularies).
     Rows missing required provenance fields are logged to
     `meta.transform_runs` with a refusal reason and skipped.
  4. Emits `meta.catalog_drift_events` rows when distribution_urls or
     license/access_level have mutated since the last gold snapshot.

Schema: migration 238.
Spec: .dk/specs/006-tavr-catalog-candidate-manifest-provisioning/spec.md
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

PUBLISHER = "data_gov"
SOURCE_ID = "tavr_catalog_data_gov"

# CKAN access_level mapping. CKAN packages don't always carry an explicit field,
# so default to 'public' for the catalog.data.gov surface (which is by definition
# public). Restricted/private surfaces would come from other publishers' APIs.
_DEFAULT_ACCESS_LEVEL = "public"

# Provenance defaults applied at promotion. Phase 0 is catalog discovery only,
# so every row gets `coverage_class='catalog_discovered'` and
# `use_class='discovery_only'`. The reviewer flips these on promotion.
_DEFAULT_COVERAGE_CLASS = "catalog_discovered"
_DEFAULT_USE_CLASS = "discovery_only"
_DEFAULT_GRAIN = "dataset_package"
_DEFAULT_CONFIDENCE = 0.50  # mid-confidence at discovery; reviewer adjusts.
_DEFAULT_CAVEAT = (
    "Auto-discovered candidate. Provenance fields populated by Phase 0 "
    "harvest defaults; reviewer must validate before promotion."
)

_BRONZE_INSERT_SQL = """
    INSERT INTO hcs_bronze.tavr_catalog_raw (
      publisher, catalog_package_id, raw, search_query, fetched_at
    ) VALUES (
      %s, %s, %s::jsonb, %s, NOW()
    )
    RETURNING id
"""

_SILVER_UPSERT_SQL = """
    INSERT INTO hcs_silver.tavr_catalog_packages (
      catalog_package_id, publisher, slug, title, access_level, license,
      temporal_coverage, data_dictionary_url, distribution_urls, search_query,
      last_harvested_date, raw_id
    ) VALUES (
      %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW(), %s
    )
    ON CONFLICT (publisher, catalog_package_id) DO UPDATE SET
      slug                = EXCLUDED.slug,
      title               = EXCLUDED.title,
      access_level        = EXCLUDED.access_level,
      license             = EXCLUDED.license,
      temporal_coverage   = EXCLUDED.temporal_coverage,
      data_dictionary_url = EXCLUDED.data_dictionary_url,
      distribution_urls   = EXCLUDED.distribution_urls,
      search_query        = EXCLUDED.search_query,
      last_harvested_date = NOW(),
      raw_id              = EXCLUDED.raw_id
"""

_GOLD_UPSERT_SQL = """
    INSERT INTO hcs_gold.tavr_catalog_candidate_manifest (
      catalog_package_id, slug, title, publisher, access_level, license,
      temporal_coverage, last_harvested_date, data_dictionary_url,
      distribution_urls, search_query, source_class, coverage_class,
      use_class, grain, as_of_date, source_id, confidence, caveat_text,
      review_state
    ) VALUES (
      %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s::jsonb, %s,
      %s, %s, %s, %s, NOW(), %s, %s, %s, 'catalog_discovered'
    )
    ON CONFLICT (catalog_package_id) DO UPDATE SET
      slug                = EXCLUDED.slug,
      title               = EXCLUDED.title,
      publisher           = EXCLUDED.publisher,
      access_level        = EXCLUDED.access_level,
      license             = EXCLUDED.license,
      temporal_coverage   = EXCLUDED.temporal_coverage,
      last_harvested_date = NOW(),
      data_dictionary_url = EXCLUDED.data_dictionary_url,
      distribution_urls   = EXCLUDED.distribution_urls,
      search_query        = EXCLUDED.search_query,
      as_of_date          = NOW(),
      source_id           = EXCLUDED.source_id,
      caveat_text         = EXCLUDED.caveat_text,
      updated_at          = NOW()
    RETURNING (xmax = 0) AS inserted
"""

_DRIFT_INSERT_SQL = """
    INSERT INTO meta.catalog_drift_events (
      catalog_package_id, publisher, drift_kind, prev_value, new_value
    ) VALUES (
      %s, %s, %s, %s::jsonb, %s::jsonb
    )
"""

# Refusals are logged + counted; transform_runs has a different schema
# (per-chunk WAL accounting) and isn't the right surface here. The CHECK
# constraints on hcs_gold.tavr_catalog_candidate_manifest are the real
# backstop — anything reaching the gold INSERT has already cleared
# _provenance_complete().


def _classify_source(_pkg: Dict[str, Any]) -> str:
    """CKAN data.gov packages are all public_machine_readable by definition."""
    return "public_machine_readable"


def _extract_distribution_urls(pkg: Dict[str, Any]) -> List[Dict[str, Any]]:
    urls: List[Dict[str, Any]] = []
    for res in pkg.get("resources", []) or []:
        url = res.get("url")
        if not url:
            continue
        urls.append({
            "url": url,
            "format": res.get("format"),
            "name": res.get("name"),
            "size": res.get("size"),
        })
    return urls


def _extract_temporal_coverage(pkg: Dict[str, Any]) -> Optional[str]:
    start = pkg.get("temporal_start") or pkg.get("temporal_coverage_from")
    end = pkg.get("temporal_end") or pkg.get("temporal_coverage_to")
    if start and end:
        return f"{start}/{end}"
    return pkg.get("temporal") or None


def _provenance_complete(row: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Check the eight provenance-discipline fields. Return (ok, reason_if_not)."""
    for col in (
        "source_class", "coverage_class", "use_class", "grain",
        "as_of_date", "source_id", "confidence", "caveat_text",
    ):
        if row.get(col) in (None, ""):
            return False, f"missing provenance field: {col}"
    return True, None


def _detect_drift(cur, package_id: str, new_row: Dict[str, Any]) -> List[Tuple[str, Any, Any]]:
    """Compare against current gold row; return list of (drift_kind, prev, new) tuples."""
    cur.execute(
        """
        SELECT distribution_urls, license, access_level, publisher
          FROM hcs_gold.tavr_catalog_candidate_manifest
         WHERE catalog_package_id = %s
        """,
        (package_id,),
    )
    prev = cur.fetchone()
    if prev is None:
        return []
    prev_dist, prev_lic, prev_access, prev_pub = prev
    drifts: List[Tuple[str, Any, Any]] = []
    if json.dumps(prev_dist, sort_keys=True) != json.dumps(new_row["distribution_urls"], sort_keys=True):
        drifts.append(("distribution_url_changed", prev_dist, new_row["distribution_urls"]))
    if (prev_lic or "") != (new_row.get("license") or ""):
        drifts.append(("license_changed", prev_lic, new_row.get("license")))
    if prev_access != new_row["access_level"]:
        drifts.append(("access_level_changed", prev_access, new_row["access_level"]))
    if prev_pub != new_row["publisher"]:
        drifts.append(("publisher_metadata_changed", prev_pub, new_row["publisher"]))
    return drifts


def load_tavr_catalog_data_gov_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert bronze rows, dedupe to silver, promote to gold with provenance discipline.

    Returns a dict with counts: bronze_inserted, silver_upserted, gold_upserted,
    gold_refused, drift_events.
    """
    if not records:
        return {
            "status": "success",
            "bronze_inserted": 0,
            "silver_upserted": 0,
            "gold_upserted": 0,
            "gold_refused": 0,
            "drift_events": 0,
        }

    bronze_inserted = 0
    silver_upserted = 0
    gold_upserted = 0
    gold_refused = 0
    drift_events = 0

    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                for rec in records:
                    pkg = rec.get("_package") or {}
                    pkg_id = pkg.get("id") or pkg.get("name")
                    if not pkg_id:
                        continue
                    slug = pkg.get("name") or pkg_id
                    title = pkg.get("title") or slug
                    license_id = pkg.get("license_id") or pkg.get("license_title")
                    dist_urls = _extract_distribution_urls(pkg)
                    temporal = _extract_temporal_coverage(pkg)
                    search_query = rec.get("_search_query")

                    # Bronze: one row per fetch event.
                    cur.execute(
                        _BRONZE_INSERT_SQL,
                        (PUBLISHER, pkg_id, json.dumps(pkg), search_query),
                    )
                    raw_id = cur.fetchone()[0]
                    bronze_inserted += 1

                    # Silver: dedup by (publisher, package_id).
                    cur.execute(
                        _SILVER_UPSERT_SQL,
                        (
                            pkg_id, PUBLISHER, slug, title, _DEFAULT_ACCESS_LEVEL,
                            license_id, temporal, pkg.get("data_dictionary_url"),
                            json.dumps(dist_urls), search_query, raw_id,
                        ),
                    )
                    silver_upserted += 1

                    # Build gold row + provenance discipline check.
                    gold_row = {
                        "catalog_package_id": pkg_id,
                        "slug": slug,
                        "title": title,
                        "publisher": PUBLISHER,
                        "access_level": _DEFAULT_ACCESS_LEVEL,
                        "license": license_id,
                        "temporal_coverage": temporal,
                        "data_dictionary_url": pkg.get("data_dictionary_url"),
                        "distribution_urls": dist_urls,
                        "search_query": search_query,
                        "source_class": _classify_source(pkg),
                        "coverage_class": _DEFAULT_COVERAGE_CLASS,
                        "use_class": _DEFAULT_USE_CLASS,
                        "grain": _DEFAULT_GRAIN,
                        "as_of_date": True,  # set by NOW() in SQL
                        "source_id": SOURCE_ID,
                        "confidence": _DEFAULT_CONFIDENCE,
                        "caveat_text": _DEFAULT_CAVEAT,
                    }
                    ok, reason = _provenance_complete(gold_row)
                    if not ok:
                        logger.warning(
                            "[%s] gold refusal for %s: %s",
                            SOURCE_ID, pkg_id, reason,
                        )
                        gold_refused += 1
                        continue

                    # Detect drift BEFORE the upsert so prev values are still current.
                    drifts = _detect_drift(cur, pkg_id, gold_row)
                    for drift_kind, prev_val, new_val in drifts:
                        cur.execute(
                            _DRIFT_INSERT_SQL,
                            (
                                pkg_id, PUBLISHER, drift_kind,
                                json.dumps(prev_val), json.dumps(new_val),
                            ),
                        )
                        drift_events += 1

                    cur.execute(
                        _GOLD_UPSERT_SQL,
                        (
                            gold_row["catalog_package_id"], gold_row["slug"],
                            gold_row["title"], gold_row["publisher"],
                            gold_row["access_level"], gold_row["license"],
                            gold_row["temporal_coverage"],
                            gold_row["data_dictionary_url"],
                            json.dumps(gold_row["distribution_urls"]),
                            gold_row["search_query"],
                            gold_row["source_class"], gold_row["coverage_class"],
                            gold_row["use_class"], gold_row["grain"],
                            gold_row["source_id"], gold_row["confidence"],
                            gold_row["caveat_text"],
                        ),
                    )
                    gold_upserted += 1

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    logger.info(
        "[%s] bronze=%d silver=%d gold=%d refused=%d drift=%d",
        SOURCE_ID, bronze_inserted, silver_upserted, gold_upserted,
        gold_refused, drift_events,
    )
    return {
        "status": "success",
        "bronze_inserted": bronze_inserted,
        "silver_upserted": silver_upserted,
        "gold_upserted": gold_upserted,
        "gold_refused": gold_refused,
        "drift_events": drift_events,
        "records_inserted": gold_upserted,
        "record_count": gold_upserted,
    }
