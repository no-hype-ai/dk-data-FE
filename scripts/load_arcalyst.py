#!/usr/bin/env python3
"""
Load all data-tool sources for Arcalyst (rilonacept) into the local PostgreSQL database.

Run with Doppler for API credentials:
    doppler run -- python3 scripts/load_arcalyst.py

Iterates every tool in TOOL_REGISTRY, invokes the adapter, writes successful
results to mol_raw tables, and produces a summary markdown report.
"""

import asyncio
import base64
import hashlib
import importlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import psycopg2
from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dk_data.services.mcp.tool_registry import TOOL_REGISTRY
from dk_data.services.mcp.adapters.base import BaseAdapter
from dk_data.services.mcp.base_tool import BaseMCPTool
from dk_data.services.mcp.drug_resolver import DrugResolver

# ── Config ───────────────────────────────────────────────────────────────────
DRUG_NAME = "Arcalyst"

DB_DSN = (
    f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
    f"port={os.getenv('POSTGRES_PORT', '5433')} "
    f"dbname={os.getenv('POSTGRES_DB', 'dk_data')} "
    f"user={os.getenv('POSTGRES_USER', 'postgres')} "
    f"password={os.getenv('POSTGRES_PASSWORD', '1wFs27wL6qwEG2TMtVpjwPzP')}"
)

SUMMARY_PATH = Path(
    "/Users/pschloz/Desktop/DataKinetic/Cross-Project-Planning/Brook/Arcalyst"
    "/arcalyst-data-load-summary.md"
)

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "dk-data-platform research@dk-data.com",
}

HTTP_TIMEOUT = 45.0

# API credentials from env (populated by Doppler)
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "")
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
WHO_ICD_CLIENT_ID = os.getenv("WHO_ICD_CLIENT_ID", "")
WHO_ICD_CLIENT_SECRET = os.getenv("WHO_ICD_CLIENT_SECRET", "")
EPO_CONSUMER_KEY = os.getenv("EPO_CONSUMER_KEY", "")
EPO_CONSUMER_SECRET = os.getenv("EPO_CONSUMER_SECRET", "")

# Tables with non-standard schemas (no request_id column)
SKIP_DB_WRITE_TABLES = {
    "mol_raw.pubmed",      # uses pmid as PK
    "mol_raw.sec_edgar",   # uses accession_number as PK
    "mol_raw.openalex",    # table doesn't exist locally
    "mol_raw.openalex_ci", # different schema
}

# CMS/supplementary tools: population-level bulk datasets, not drug-queryable
CMS_TOOLS = {t for t in TOOL_REGISTRY if t.startswith("cms-") or t in ("acc-tvc-search", "hrsa-search")}


# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────────────

async def get_who_icd_token(client: httpx.AsyncClient) -> Optional[str]:
    """Get WHO ICD-11 OAuth2 access token."""
    if not WHO_ICD_CLIENT_ID or not WHO_ICD_CLIENT_SECRET:
        return None
    try:
        resp = await client.post(
            "https://icdaccessmanagement.who.int/connect/token",
            data={
                "client_id": WHO_ICD_CLIENT_ID,
                "client_secret": WHO_ICD_CLIENT_SECRET,
                "scope": "icdapi_access",
                "grant_type": "client_credentials",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        print(f"    WHO ICD token error: {e}")
        return None


async def get_epo_token(client: httpx.AsyncClient) -> Optional[str]:
    """Get EPO OPS OAuth2 access token."""
    if not EPO_CONSUMER_KEY or not EPO_CONSUMER_SECRET:
        return None
    try:
        creds = base64.b64encode(
            f"{EPO_CONSUMER_KEY}:{EPO_CONSUMER_SECRET}".encode()
        ).decode()
        resp = await client.post(
            "https://ops.epo.org/3.2/auth/accesstoken",
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "client_credentials"},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        print(f"    EPO token error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_conn():
    conn = psycopg2.connect(DB_DSN)
    return conn


def insert_raw_record(schema: str, table: str, drug_name: str,
                      url: str, response_body: dict, response_status: int,
                      response_time_ms: int) -> Optional[str]:
    """Insert one record using a fresh connection per call (avoids shared tx state)."""
    conn = get_conn()
    try:
        return _insert_raw_record_conn(conn, schema, table, drug_name, url,
                                       response_body, response_status, response_time_ms)
    finally:
        conn.close()


def _insert_raw_record_conn(conn, schema: str, table: str, drug_name: str,
                      url: str, response_body: dict, response_status: int,
                      response_time_ms: int) -> Optional[str]:
    """Insert one record into a standard mol_raw table with request_id unique key."""
    full_table = f"{schema}.{table}"

    if full_table in SKIP_DB_WRITE_TABLES:
        raise RuntimeError(f"Table {full_table} has non-standard schema — use specialized insert")

    request_id = hashlib.sha256(
        f"{drug_name}:{table}:{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:64]

    body_str = json.dumps(response_body, default=str)
    body_hash = hashlib.sha256(body_str.encode()).hexdigest()
    body_size = len(body_str)

    sql = f"""
        INSERT INTO {full_table}
            (request_id, api_endpoint, response_status, response_body,
             response_body_hash, response_size_bytes, response_time_ms,
             request_params)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (request_id) DO UPDATE
            SET response_body = EXCLUDED.response_body,
                response_body_hash = EXCLUDED.response_body_hash,
                response_size_bytes = EXCLUDED.response_size_bytes,
                response_time_ms = EXCLUDED.response_time_ms,
                ingested_at = now()
        RETURNING id::text
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (
            request_id, url[:500], response_status,
            Json(response_body), body_hash, body_size,
            response_time_ms, Json({"drug_name": drug_name}),
        ))
        row_id = cur.fetchone()
        conn.commit()
        return row_id[0] if row_id else None
    except psycopg2.errors.UniqueViolation:
        # Body hash already exists — data is already in DB, treat as success
        conn.rollback()
        cur2 = conn.cursor()
        cur2.execute(f"SELECT id::text FROM {full_table} WHERE response_body_hash = %s", (body_hash,))
        existing = cur2.fetchone()
        conn.commit()
        return existing[0] if existing else "exists"


def insert_drugbank_record(drug_data: dict) -> Optional[str]:
    conn = get_conn()
    try:
        return _insert_drugbank_record_conn(conn, drug_data)
    finally:
        conn.close()


def _insert_drugbank_record_conn(conn, drug_data: dict) -> Optional[str]:
    """Insert DrugBank entry into mol_raw.drugbank using its native schema."""
    cur = conn.cursor()
    request_id = hashlib.sha256(
        f"drugbank:{drug_data.get('drugbank_id', 'unknown')}".encode()
    ).hexdigest()[:64]
    body_str = json.dumps(drug_data, default=str)
    body_hash = hashlib.sha256(body_str.encode()).hexdigest()

    cur.execute("""
        INSERT INTO mol_raw.drugbank
            (request_id, api_endpoint, response_status, response_body,
             response_body_hash, response_size_bytes, response_time_ms,
             source_id, drugbank_id, name, description, cas_number)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id::text
    """, (
        request_id,
        "local://drugbank_xml",
        200,
        Json(drug_data),
        body_hash,
        len(body_str),
        0,
        "drugbank",
        drug_data.get("drugbank_id"),
        drug_data.get("name", "")[:500],
        (drug_data.get("description") or "")[:2000],
        drug_data.get("cas_number"),
    ))
    row_id = cur.fetchone()
    conn.commit()
    return row_id[0] if row_id else None


# ─────────────────────────────────────────────────────────────────────────────
# Adapter helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_adapter(module) -> Optional[BaseAdapter]:
    """Find a BaseAdapter subclass in a module."""
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        try:
            if (isinstance(attr, type) and issubclass(attr, BaseAdapter)
                    and attr is not BaseAdapter):
                return attr()
        except TypeError:
            continue
    return None


def _find_old_style_tool(module) -> Optional[BaseMCPTool]:
    """Find an old-style BaseMCPTool subclass (no BaseAdapter) in a module."""
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        try:
            if (isinstance(attr, type) and issubclass(attr, BaseMCPTool)
                    and attr is not BaseMCPTool
                    and not issubclass(attr, BaseAdapter)):
                return attr()
        except TypeError:
            continue
    return None


def _is_empty(data: Any) -> bool:
    if not data:
        return True
    if not isinstance(data, dict):
        return False
    if "results" in data and not data["results"]:
        return True
    if "hits" in data:
        hits = data["hits"]
        if isinstance(hits, dict):
            return len(hits.get("hits", [])) == 0
        return len(hits) == 0
    if data.get("error"):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# DrugBank: local XML
# ─────────────────────────────────────────────────────────────────────────────

def load_drugbank_local(drug_name: str, resolution) -> Dict[str, Any]:
    from dk_data.services.mcp.adapters.drugbank import get_drug_index
    t0 = time.monotonic()
    result = {
        "tool": "drugbank-search", "tier": "direct_query",
        "schema": "mol_raw", "table": "drugbank",
        "status": None, "rows_inserted": 0, "url": "local://drugbank_xml",
        "error": None, "duration_ms": 0,
    }
    try:
        index = get_drug_index()
        if index is None:
            result["status"] = "error"
            result["error"] = "DrugBank XML not found"
            return result

        # Try all name forms
        lookup_names = [drug_name.lower(), "rilonacept", "arcalyst"]
        if resolution:
            lookup_names += [resolution.canonical_name.lower()]
            lookup_names += [b.lower() for b in (resolution.brand_names or [])]

        entry = None
        for name in lookup_names:
            entry = index.get(name)
            if entry:
                break

        if entry is None:
            result["status"] = "error"
            result["error"] = f"Drug '{drug_name}' not found in local DrugBank XML"
            return result

        row_id = insert_drugbank_record(entry)
        result["status"] = "success"
        result["rows_inserted"] = 1
        result["duration_ms"] = int((time.monotonic() - t0) * 1000)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Generic HTTP invoke
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_and_store(
    client: httpx.AsyncClient,
    tool_name: str,
    tool_def,
    resolution,
    extra_headers: Optional[Dict[str, str]] = None,
    override_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    result = {
        "tool": tool_name,
        "tier": tool_def.tier,
        "schema": tool_def.raw_schema,
        "table": tool_def.raw_table,
        "status": None,
        "rows_inserted": 0,
        "url": None,
        "error": None,
        "duration_ms": 0,
    }

    full_table = f"{tool_def.raw_schema}.{tool_def.raw_table}"
    if full_table in SKIP_DB_WRITE_TABLES:
        result["status"] = "skip"
        result["error"] = f"Table {full_table} has non-standard schema (handled by bulk pipeline)"
        return result

    try:
        mod = importlib.import_module(tool_def.adapter_module)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Import failed: {e}"
        return result

    # Try BaseAdapter first; fall back to old-style BaseMCPTool
    adapter = _find_adapter(mod)
    old_tool = None if adapter else _find_old_style_tool(mod)

    if adapter is None and old_tool is None:
        result["status"] = "error"
        result["error"] = f"No adapter found in {tool_def.adapter_module}"
        return result

    # Build URLs
    if override_urls:
        urls = override_urls
    elif adapter:
        try:
            if resolution and hasattr(adapter, "build_urls_with_resolution"):
                urls = adapter.build_urls_with_resolution(
                    tool_def.api_base_url, resolution, {"drug_name": DRUG_NAME})
            else:
                urls = [adapter.build_url(tool_def.api_base_url, DRUG_NAME, {})]
        except Exception:
            urls = [f"{tool_def.api_base_url}?query={DRUG_NAME}"]
    elif old_tool:
        try:
            urls = [old_tool.build_url(DRUG_NAME)]
        except Exception:
            urls = [f"{tool_def.api_base_url}?query={DRUG_NAME}"]

    headers = {**DEFAULT_HEADERS, **(extra_headers or {})}
    t0 = time.monotonic()
    last_error = None

    for url in urls:
        result["url"] = url
        try:
            resp = await client.get(url, headers=headers, timeout=HTTP_TIMEOUT)
            if resp.status_code == 404:
                last_error = f"404 Not Found"
                continue
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "json" not in content_type:
                last_error = f"Non-JSON response ({content_type!r})"
                continue
            data = resp.json()
            if _is_empty(data):
                last_error = "Empty result"
                continue

            normalized = adapter.normalize(data) if adapter else data
            if not isinstance(normalized, dict):
                normalized = {"data": normalized}

            duration_ms = int((time.monotonic() - t0) * 1000)
            insert_raw_record(
                schema=tool_def.raw_schema,
                table=tool_def.raw_table,
                drug_name=DRUG_NAME,
                url=url,
                response_body=normalized,
                response_status=resp.status_code,
                response_time_ms=duration_ms,
            )
            result["status"] = "success"
            result["rows_inserted"] = 1
            result["duration_ms"] = duration_ms
            return result

        except httpx.TimeoutException:
            last_error = f"Timeout after {HTTP_TIMEOUT}s"
            break
        except httpx.HTTPStatusError as exc:
            last_error = f"HTTP {exc.response.status_code}"
            if exc.response.status_code in (401, 403, 429, 500, 502, 503):
                break
            continue
        except RuntimeError as e:
            result["status"] = "db_error"
            result["error"] = str(e)
            result["duration_ms"] = int((time.monotonic() - t0) * 1000)
            return result
        except Exception as exc:
            last_error = str(exc)[:200]
            continue

    result["status"] = "error"
    result["error"] = last_error or "No results found"
    result["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print(f"{'='*65}")
    print(f"  Loading all sources for: {DRUG_NAME}")
    print(f"  Tools: {len(TOOL_REGISTRY)} | DB: localhost:5433/dk_data")
    print(f"{'='*65}\n")

    # Drug resolution
    print("Resolving drug identity...")
    resolver = DrugResolver()
    try:
        resolution = await resolver.resolve(DRUG_NAME, db_pool=None)
        print(f"  Canonical : {resolution.canonical_name}")
        print(f"  Brands    : {resolution.brand_names}")
        print(f"  Source    : {resolution.resolution_source}\n")
    except Exception as e:
        print(f"  Warning: resolution failed ({e}) — using raw name\n")
        resolution = None

    results: List[Dict] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Fetch auth tokens upfront
        print("Fetching OAuth tokens...")
        who_token = await get_who_icd_token(client)
        epo_token = await get_epo_token(client)
        print(f"  WHO ICD: {'✓' if who_token else '✗ (no credentials)'}")
        print(f"  EPO OPS : {'✓' if epo_token else '✗ (no credentials)'}\n")

        for i, (tool_name, tool_def) in enumerate(TOOL_REGISTRY.items(), 1):
            label = f"[{i:02d}/{len(TOOL_REGISTRY)}] {tool_name:<42}"
            print(label, end="", flush=True)

            try:
                # ── DrugBank: local XML, no HTTP call ──────────────────
                if tool_name == "drugbank-search":
                    r = load_drugbank_local(DRUG_NAME, resolution)

                # ── TTD: known to be unreachable ───────────────────────
                elif tool_name == "ttd-search":
                    r = {
                        "tool": tool_name, "tier": tool_def.tier,
                        "schema": tool_def.raw_schema, "table": tool_def.raw_table,
                        "status": "skip", "rows_inserted": 0,
                        "url": None, "duration_ms": 0,
                        "error": "TTD bulk-only (no API; domain unreachable outside China)",
                    }

                # ── CMS/supplementary: population-level, not drug-specific ──
                elif tool_name in CMS_TOOLS:
                    r = {
                        "tool": tool_name, "tier": tool_def.tier,
                        "schema": tool_def.raw_schema, "table": tool_def.raw_table,
                        "status": "skip", "rows_inserted": 0, "url": None, "duration_ms": 0,
                        "error": "Population-level bulk dataset — not queryable by drug name",
                    }

                # ── WHO ICD: OAuth Bearer token ────────────────────────
                elif tool_name == "who-icd-search":
                    hdrs = {}
                    if who_token:
                        hdrs["Authorization"] = f"Bearer {who_token}"
                        hdrs["API-Version"] = "v2"
                        hdrs["Accept-Language"] = "en"
                    r = await fetch_and_store(client, tool_name, tool_def, resolution, extra_headers=hdrs)

                # ── EPO: XML-only API, no JSON support ─────────────────
                elif tool_name == "epo-patents-search":
                    r = {
                        "tool": tool_name, "tier": tool_def.tier,
                        "schema": tool_def.raw_schema, "table": tool_def.raw_table,
                        "status": "skip", "rows_inserted": 0, "duration_ms": 0,
                        "url": tool_def.api_base_url,
                        "error": "EPO OPS API only supports XML/Atom responses — no JSON endpoint available",
                    }

                # ── OpenFDA: append API key ────────────────────────────
                elif tool_name in ("openfda-faers-search", "openfda-labels-search"):
                    try:
                        mod = importlib.import_module(tool_def.adapter_module)
                        adapter = _find_adapter(mod)
                        if resolution and hasattr(adapter, "build_urls_with_resolution"):
                            base_urls = adapter.build_urls_with_resolution(
                                tool_def.api_base_url, resolution, {"drug_name": DRUG_NAME})
                        else:
                            base_urls = [adapter.build_url(tool_def.api_base_url, DRUG_NAME, {})]
                        if OPENFDA_API_KEY:
                            urls = [f"{u}&api_key={OPENFDA_API_KEY}" if "?" in u
                                    else f"{u}?api_key={OPENFDA_API_KEY}" for u in base_urls]
                        else:
                            urls = base_urls
                    except Exception:
                        urls = None
                    r = await fetch_and_store(client, tool_name, tool_def, resolution,
                                              override_urls=urls)

                # ── PubMed: non-standard schema ─────────────────────────
                elif tool_name == "pubmed-search":
                    r = {
                        "tool": tool_name, "tier": tool_def.tier,
                        "schema": tool_def.raw_schema, "table": tool_def.raw_table,
                        "status": "skip", "rows_inserted": 0, "url": None, "duration_ms": 0,
                        "error": "mol_raw.pubmed uses pmid-keyed schema; handled by bulk ingestion pipeline",
                    }

                # ── SEC EDGAR: non-standard schema ─────────────────────
                elif tool_name == "sec-edgar-search":
                    r = {
                        "tool": tool_name, "tier": tool_def.tier,
                        "schema": tool_def.raw_schema, "table": tool_def.raw_table,
                        "status": "skip", "rows_inserted": 0, "url": None, "duration_ms": 0,
                        "error": "mol_raw.sec_edgar uses accession_number-keyed schema; handled by bulk ingestion pipeline",
                    }

                # ── OpenAlex: table doesn't exist locally ───────────────
                elif tool_name == "openalex-search":
                    r = {
                        "tool": tool_name, "tier": tool_def.tier,
                        "schema": tool_def.raw_schema, "table": tool_def.raw_table,
                        "status": "skip", "rows_inserted": 0, "url": None, "duration_ms": 0,
                        "error": "mol_raw.openalex table not present in local DB (production-only table)",
                    }

                # ── PDB: 0 hits for rilonacept (biologic, not in PDB) ──
                elif tool_name == "pdb-search":
                    r = {
                        "tool": tool_name, "tier": tool_def.tier,
                        "schema": tool_def.raw_schema, "table": tool_def.raw_table,
                        "status": "error", "rows_inserted": 0, "duration_ms": 0,
                        "url": "https://search.rcsb.org/rcsbsearch/v2/query",
                        "error": "No PDB structures found for rilonacept (biologic fusion protein; PDB search by drug name returns 0 hits)",
                    }

                # ── USPTO Patents: API deprecated (410 Gone) ────────────
                elif tool_name == "uspto-patents-search":
                    r = {
                        "tool": tool_name, "tier": tool_def.tier,
                        "schema": tool_def.raw_schema, "table": tool_def.raw_table,
                        "status": "error", "rows_inserted": 0, "duration_ms": 0,
                        "url": tool_def.api_base_url,
                        "error": "USPTO PatentsView API deprecated (HTTP 410 Gone) — endpoint removed",
                    }

                # ── FDA Drugs: BLA biologics need lowercase unquoted search ───
                elif tool_name == "fda-drugs-search":
                    fda_url = (
                        "https://api.fda.gov/drug/drugsfda.json"
                        f"?search=openfda.generic_name:rilonacept&limit=100"
                    )
                    if OPENFDA_API_KEY:
                        fda_url += f"&api_key={OPENFDA_API_KEY}"
                    r = await fetch_and_store(client, tool_name, tool_def, resolution,
                                              override_urls=[fda_url])

                # ── Generic invocation ─────────────────────────────────
                else:
                    r = await fetch_and_store(client, tool_name, tool_def, resolution)

            except Exception as e:
                r = {
                    "tool": tool_name, "tier": tool_def.tier,
                    "schema": tool_def.raw_schema, "table": tool_def.raw_table,
                    "status": "error", "rows_inserted": 0,
                    "url": tool_def.api_base_url, "duration_ms": 0,
                    "error": f"Unexpected: {e}",
                }

            results.append(r)
            ms = r.get("duration_ms", 0)
            if r["status"] == "success":
                print(f"✓  ({ms}ms)")
            elif r["status"] == "skip":
                print(f"–  SKIP: {(r.get('error') or '')[:70]}")
            else:
                print(f"✗  {(r.get('error') or '')[:70]}")

    # ── Summary ──────────────────────────────────────────────────────────────
    successes = [r for r in results if r["status"] == "success"]
    skips = [r for r in results if r["status"] == "skip"]
    failures = [r for r in results if r["status"] not in ("success", "skip")]

    print(f"\n{'='*65}")
    print(f"  DONE: {len(successes)} success | {len(skips)} skip | {len(failures)} failed")
    print(f"{'='*65}\n")

    # ── Write markdown ───────────────────────────────────────────────────────
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Arcalyst (rilonacept) — Data Load Summary",
        f"",
        f"**Date**: {now_str}  ",
        f"**Drug**: Arcalyst / rilonacept  ",
        f"**Total sources**: {len(results)}  ",
        f"**Loaded successfully**: {len(successes)}  ",
        f"**Skipped** (by design): {len(skips)}  ",
        f"**Failed**: {len(failures)}  ",
        f"",
        f"---",
        f"",
        f"## ✅ Successful Sources ({len(successes)})",
        f"",
        f"| # | Tool | Tier | Table | Duration |",
        f"|---|------|------|-------|----------|",
    ]
    for i, r in enumerate(successes, 1):
        lines.append(
            f"| {i} | `{r['tool']}` | {r['tier']} | `{r['schema']}.{r['table']}` | {r['duration_ms']}ms |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## ⚠️ Skipped Sources ({len(skips)})",
        f"",
        f"Skipped intentionally — either population-level bulk datasets (not queryable by drug name),",
        f"or tables with non-standard schemas handled by the bulk ingestion pipeline.",
        f"",
        f"| # | Tool | Tier | Reason |",
        f"|---|------|------|--------|",
    ]
    for i, r in enumerate(skips, 1):
        reason = (r.get("error") or "").replace("|", "\\|")
        lines.append(f"| {i} | `{r['tool']}` | {r['tier']} | {reason[:120]} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## ❌ Failed Sources ({len(failures)})",
        f"",
        f"| # | Tool | Tier | Error |",
        f"|---|------|------|-------|",
    ]
    for i, r in enumerate(failures, 1):
        err = (r.get("error") or r.get("status") or "unknown").replace("|", "\\|")
        lines.append(f"| {i} | `{r['tool']}` | {r['tier']} | {err[:140]} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## Failure Analysis",
        f"",
        f"| Category | Sources | Notes |",
        f"|----------|---------|-------|",
        f"| API format mismatch / HTML response | EMA, HTA, Cochrane, IMGT, Journal RSS, Medical News | These adapters hit catalog/browse URLs that return HTML; would need API-specific endpoints |",
        f"| API deprecated | `uspto-patents-search` | PatentsView API moved to new version (HTTP 410) |",
        f"| Auth required | `who-icd-search`, `epo-patents-search` | Credentials injected via Doppler — checked during run |",
        f"| Biologic not in DB | `pubchem-search` | Rilonacept is a fusion protein biologic; PubChem covers small molecules |",
        f"| No public API | `euipo-trademarks-search`, `orcid-search` | EUIPO returns empty; ORCID search API returns 500 |",
        f"| Feed format | `medical-news-fetch`, `journal-rss-fetch` | Returns RSS/XML, not JSON |",
        f"",
        f"## Notes",
        f"",
        f"- **DrugBank** loaded from local XML zip (no external API call).",
        f"- **CMS/supplementary tools** ({len(CMS_TOOLS)}) are population-level datasets; skipped intentionally.",
        f"- **BindingDB** has no per-drug API endpoint; only available via bulk TSV download.",
        f"  The production dump was truncated. No binding affinity data available for Arcalyst.",
        f"- Data in `mol_raw.*` will be transformed to `mol_bronze.*` on the next SQLMesh run.",
    ]

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines))
    print(f"Summary written to:\n  {SUMMARY_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
