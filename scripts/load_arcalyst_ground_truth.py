#!/usr/bin/env python3
"""
Ground Truth pipeline for Arcalyst (rilonacept) + competitor discovery.

Adapts the CompetitorDiscoveryService logic from xenon-repo for standalone use.

Steps:
  1. Discover IL-1 class competitors via OpenFDA EPC search
  2. Load bioRxiv / medRxiv preprints for Arcalyst via Crossref
  3. Load real CMS data (Open Payments, Medicaid drug utilization)
  4. For each competitor: run the same full TOOL_REGISTRY + bulk source pipeline

Run with Doppler:
    doppler run -- python3 scripts/load_arcalyst_ground_truth.py
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx
import psycopg2
from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ── DB ───────────────────────────────────────────────────────────────────────
DB_DSN = (
    f"host={os.getenv('POSTGRES_HOST','localhost')} "
    f"port={os.getenv('POSTGRES_PORT','5433')} "
    f"dbname={os.getenv('POSTGRES_DB','dk_data')} "
    f"user={os.getenv('POSTGRES_USER','postgres')} "
    f"password={os.getenv('POSTGRES_PASSWORD','1wFs27wL6qwEG2TMtVpjwPzP')}"
)

OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "")
NCBI_API_KEY    = os.getenv("NCBI_API_KEY", "")

DRUG_NAME    = "Arcalyst"
GENERIC_NAME = "rilonacept"
CHEMBL_ID    = "CHEMBL157030"
RXNORM_CUI   = "763450"
KEGG_ID      = "D06635"
REGN_CIK     = "872589"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "dk-data-platform research@datakinetic.com",
}
TIMEOUT = 45.0

# ── Competitors discovered via xenon CompetitorDiscoveryService pattern ──────
# IL-1 pathway competitors for CAPS and Recurrent Pericarditis indications.
# Source: OpenFDA pharm_class_epc search + known clinical landscape.

COMPETITORS = [
    {
        "name": "canakinumab",
        "brand": "Ilaris",
        "company": "Novartis",
        "mechanism": "IL-1β monoclonal antibody",
        "indications": ["CAPS", "SJIA", "FMF", "HIDS/MKD", "TRAPS", "gout flares"],
        "phase": "Approved",
        "chembl": "CHEMBL1201823",
        "rxnorm": "1310149",
        "epc": "Interleukin-1 Beta Inhibitor [EPC]",
        "threat_notes": "Primary competitor in CAPS; broader indication set; SQ q8w dosing (Arcalyst q1w)",
    },
    {
        "name": "anakinra",
        "brand": "Kineret",
        "company": "Swedish Orphan Biovitrum (SOBI)",
        "mechanism": "Recombinant IL-1 receptor antagonist (IL-1Ra)",
        "indications": ["RA", "NOMID/CAPS", "SJIA", "FMF", "recurrent pericarditis"],
        "phase": "Approved",
        "chembl": "CHEMBL1201823",
        "rxnorm": "214555",
        "epc": "Interleukin-1 Receptor Antagonist [EPC]",
        "threat_notes": "Daily SQ dosing (disadvantage vs Arcalyst); approved for recurrent pericarditis 2021",
    },
    {
        "name": "colchicine",
        "brand": "Colcrys",
        "company": "Takeda (brand); multiple generics",
        "mechanism": "Anti-inflammatory (tubulin polymerization inhibitor)",
        "indications": ["pericarditis", "gout", "FMF"],
        "phase": "Approved",
        "chembl": "CHEMBL107",
        "rxnorm": "41493",
        "epc": "Tubulin Polymerization Inhibitor [EPC]",
        "threat_notes": "Standard of care for pericarditis; oral; low cost; primary competitor for pericarditis indication",
    },
]


# ── DB helpers ───────────────────────────────────────────────────────────────

def db_conn():
    return psycopg2.connect(DB_DSN)

def _req_id(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:64]

def _body_hash(body_str: str) -> str:
    return hashlib.sha256(body_str.encode()).hexdigest()

def std_insert(schema: str, table: str, url: str, body: dict,
               drug: str, status: int = 200, ms: int = 0) -> str:
    c = db_conn()
    try:
        rid = _req_id(f"{drug}:{table}:{datetime.now(timezone.utc).isoformat()}")
        body_str = json.dumps(body, default=str)
        bh = _body_hash(body_str)
        cur = c.cursor()
        # Detect whether response_time_ms column exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s AND column_name='response_time_ms'
        """, (schema, table))
        has_time = cur.fetchone() is not None
        if has_time:
            cur.execute(f"""
                INSERT INTO {schema}.{table}
                    (request_id, api_endpoint, response_status, response_body,
                     response_body_hash, response_size_bytes, response_time_ms, request_params)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (rid, url[:500], status, Json(body), bh, len(body_str), ms,
                  Json({"drug_name": drug})))
        else:
            cur.execute(f"""
                INSERT INTO {schema}.{table}
                    (request_id, api_endpoint, response_status, response_body,
                     response_body_hash, response_size_bytes, request_params)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (rid, url[:500], status, Json(body), bh, len(body_str),
                  Json({"drug_name": drug})))
        c.commit()
        return "inserted"
    except psycopg2.errors.UniqueViolation:
        c.rollback()
        return "exists"
    finally:
        c.close()


def simple_insert(schema: str, table: str, body: dict) -> str:
    c = db_conn()
    try:
        cur = c.cursor()
        cur.execute(f"INSERT INTO {schema}.{table} (response_status, response_body) VALUES (%s, %s)",
                    (200, Json(body)))
        c.commit()
        return "inserted"
    finally:
        c.close()


# ── Fetch helper ─────────────────────────────────────────────────────────────

async def fetch(client: httpx.AsyncClient, url: str,
                method: str = "GET", post_json: Any = None,
                extra_headers: Dict = None) -> Optional[Tuple[Any, int]]:
    hdrs = {**HEADERS, **(extra_headers or {})}
    t0 = time.monotonic()
    try:
        if method == "POST":
            r = await client.post(url, json=post_json, headers=hdrs, timeout=TIMEOUT)
        else:
            r = await client.get(url, headers=hdrs, timeout=TIMEOUT)
        r.raise_for_status()
        if "json" not in r.headers.get("content-type", ""):
            return None
        return r.json(), int((time.monotonic() - t0) * 1000)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 — COMPETITOR DISCOVERY
# Replicates xenon-repo CompetitorDiscoveryService.discoverCompetitorsFromOpenFDA
# ═══════════════════════════════════════════════════════════════════════════

async def discover_and_score_competitors(client: httpx.AsyncClient) -> List[Dict]:
    """
    Discover IL-1 competitors via OpenFDA EPC search, then score each on 7 dimensions.
    Mirrors xenon-repo CompetitorDiscoveryService scoring logic.
    """
    print("\n── COMPETITOR DISCOVERY ─────────────────────────────────────────")

    # Step 1: EPC-based discovery via OpenFDA
    print("  Querying OpenFDA for IL-1 class drugs...")
    epc_competitors = set()

    il1_epcs = [
        "Interleukin-1 Receptor Antagonist [EPC]",
        "Interleukin-1 Inhibitor [EPC]",
        "Interleukin-1 Beta Inhibitor [EPC]",
    ]
    for epc in il1_epcs:
        url = f"https://api.fda.gov/drug/label.json?search=openfda.pharm_class_epc:\"{quote(epc)}\"&limit=20"
        if OPENFDA_API_KEY:
            url += f"&api_key={OPENFDA_API_KEY}"
        res = await fetch(client, url)
        if res:
            data, _ = res
            for label in data.get("results", []):
                gname = (label.get("openfda", {}).get("generic_name") or [""])[0].lower()
                if gname and gname != GENERIC_NAME:
                    epc_competitors.add(gname)

    print(f"  OpenFDA EPC discovery found: {sorted(epc_competitors) or '(none — biologic EPC not indexed)'}")
    print(f"  Using known IL-1 competitor set: {[c['name'] for c in COMPETITORS]}")

    # Step 2: Score each competitor (xenon 7-dimension scoring)
    enriched = []
    for comp in COMPETITORS:
        name = comp["name"]
        drug_enc = quote(name)
        print(f"  Scoring {name}...")

        # Fetch label for scoring
        label_url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:{drug_enc}&limit=3"
        trials_url = (
            f"https://clinicaltrials.gov/api/v2/studies"
            f"?query.intr={quote(name)}&filter.overallStatus=RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION"
            f"&pageSize=20&format=json"
        )
        label_res = await fetch(client, label_url)
        trials_res = await fetch(client, trials_url)

        labels = label_res[0].get("results", []) if label_res else []
        trials = trials_res[0].get("studies", []) if trials_res else []

        # Compute 7-dimension scores (matches xenon CompetitorDiscoveryService.computeScores)
        phase_score = 10 if comp["phase"] == "Approved" else 7
        active_trials = len([
            t for t in trials
            if "recruit" in str(t.get("protocolSection", {}).get("statusModule", {}).get("overallStatus", "")).lower()
        ])
        has_boxed_warning = any(l.get("boxed_warning") or l.get("warnings") for l in labels)

        dosage_text = " ".join(
            str(l.get("dosage_and_administration", "")) for l in labels
        ).lower()
        if "once daily" in dosage_text or "daily" in dosage_text:
            dosing_score = 4
        elif "weekly" in dosage_text or "every 8 weeks" in dosage_text:
            dosing_score = 8
        elif "monthly" in dosage_text or "every 4 weeks" in dosage_text:
            dosing_score = 9
        else:
            dosing_score = 6

        scores = [
            {"dimension": "evidence",    "score": min(10, phase_score),     "justification": f"Approved drug"},
            {"dimension": "survival",    "score": 5,                        "justification": "No OS data (autoinflammatory indication)"},
            {"dimension": "safety",      "score": 4 if has_boxed_warning else 7, "justification": "Boxed warning" if has_boxed_warning else "No boxed warning"},
            {"dimension": "dosing",      "score": dosing_score,             "justification": f"Parsed from label text"},
            {"dimension": "mechanism",   "score": 8,                        "justification": comp["mechanism"]},
            {"dimension": "pipeline",    "score": min(10, 2 + active_trials * 1.5), "justification": f"{active_trials} active trials"},
            {"dimension": "regulatory",  "score": 8,                        "justification": "Approved product"},
        ]
        avg = sum(s["score"] for s in scores) / len(scores)
        threat_score = round(min(1.0, avg / 10), 2)

        enriched.append({
            **comp,
            "scores": scores,
            "threat_score": threat_score,
            "active_trials": active_trials,
            "label_found": len(labels) > 0,
        })
        print(f"    → threat_score={threat_score}, active_trials={active_trials}, label={'found' if labels else 'not found'}")

    return enriched


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 — BIORXIV / MEDRXIV via Crossref
# ═══════════════════════════════════════════════════════════════════════════

async def load_biorxiv_for_drug(client: httpx.AsyncClient, drug_name: str, generic: str) -> Dict:
    """
    Fetch bioRxiv and medRxiv preprints via Crossref API (indexes both servers).
    Crossref type:posted-content = preprints.
    """
    queries = [generic, drug_name]
    all_items = []

    for query in queries:
        url = (
            f"https://api.crossref.org/works?query={quote(query)}"
            f"&filter=type:posted-content&rows=50"
            f"&mailto=research@datakinetic.com"
            f"&select=DOI,title,author,abstract,posted,institution,group-title,URL"
        )
        t0 = time.monotonic()
        res = await fetch(client, url)
        if not res:
            continue
        data, ms = res
        items = data.get("message", {}).get("items", [])
        # Filter to only items actually mentioning the drug
        qlow = query.lower()
        for item in items:
            title_text = " ".join(item.get("title", [])).lower()
            abstract_text = (item.get("abstract") or "").lower()
            if qlow in title_text or qlow in abstract_text:
                # Avoid duplicates
                doi = item.get("DOI", "")
                if not any(x.get("DOI") == doi for x in all_items):
                    all_items.append(item)

    if not all_items:
        return {"status": "no_results", "rows": 0}

    body = {
        "drug": drug_name,
        "generic_name": generic,
        "query_date": datetime.now(timezone.utc).isoformat(),
        "source": "Crossref API — bioRxiv/medRxiv preprints (type:posted-content)",
        "total_found": len(all_items),
        "preprints": [
            {
                "doi": item.get("DOI", ""),
                "title": " ".join(item.get("title", [])),
                "authors": [
                    f"{a.get('given','')} {a.get('family','')}".strip()
                    for a in (item.get("author") or [])[:10]
                ],
                "abstract": (item.get("abstract") or "")[:1000],
                "posted_date": (item.get("posted", {}).get("date-parts") or [[None]])[0],
                "server": (item.get("institution", [{}])[0].get("name")
                           or item.get("group-title") or "preprint"),
                "url": item.get("URL", ""),
            }
            for item in all_items
        ],
    }
    url_logged = f"https://api.crossref.org/works?query={quote(generic)}&filter=type:posted-content"
    std_insert("mol_raw", "biorxiv", url_logged, body, drug=drug_name, ms=ms)
    return {"status": "success", "rows": len(all_items)}


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 — CMS DATA
# ═══════════════════════════════════════════════════════════════════════════

async def load_cms_open_payments_real(client: httpx.AsyncClient, drug_name: str, generic: str) -> Dict:
    """
    Load CMS Open Payments via the correct DKAN API endpoints.
    Searches across multiple year datasets and payment types.
    """
    # CMS DKAN API — discovered via openpaymentsdata.cms.gov
    # The API requires a resource identifier; these are the 2021-2023 general payments
    dataset_searches = [
        # General payments 2023
        "https://openpaymentsdata.cms.gov/api/1/datastore/query?conditions[0][property]=covered_drug_device_biological_name&conditions[0][value]={drug}&conditions[0][operator]==&limit=500",
        "https://openpaymentsdata.cms.gov/api/1/datastore/query?conditions[0][property]=name_of_drug_or_biological_or_device_or_medical_supply_1&conditions[0][value]={drug}&conditions[0][operator]==&limit=500",
    ]

    for drug_variant in [drug_name.upper(), generic.upper()]:
        for url_template in dataset_searches:
            url = url_template.format(drug=drug_variant)
            res = await fetch(client, url)
            if res:
                data, ms = res
                results = data.get("results", [])
                if results:
                    body = {
                        "drug": drug_name,
                        "generic_name": generic,
                        "query_drug": drug_variant,
                        "results": results,
                        "count": len(results),
                    }
                    std_insert("mol_raw", "cms_open_payments", url, body, drug=drug_name, ms=ms)
                    return {"status": "success", "rows": len(results)}

    return {"status": "no_results", "rows": 0}


async def load_cms_part_d_real(client: httpx.AsyncClient, drug_name: str, generic: str) -> Dict:
    """
    Load CMS Part D spending data. Arcalyst is Part B (physician-administered),
    but query Part D as well in case any formulation is captured.
    Dataset: Medicare Part D Spending by Drug (CMS data portal)
    """
    # Try multiple possible dataset IDs for Part D drug spending
    dataset_ids = [
        "e2c5-9e4n",   # From cms_medicare_client.py DATASET_PART_D_SPENDING
        "0b8e6f28-9458-4532-9b85-f39d2a4da3e9",  # tried before
    ]
    base = "https://data.cms.gov/data-api/v1/dataset"

    for did in dataset_ids:
        for drug_variant in [drug_name.upper(), generic.upper(), drug_name, generic]:
            url = f"{base}/{did}/data?search={quote(drug_variant)}&limit=100"
            res = await fetch(client, url)
            if res:
                data, ms = res
                if isinstance(data, list) and data:
                    # Filter rows that actually mention our drug
                    relevant = [
                        r for r in data
                        if (drug_variant.upper() in str(r.get("Brnd_Name", "")).upper() or
                            drug_variant.upper() in str(r.get("Gnrc_Name", "")).upper() or
                            generic.upper() in str(r.get("Gnrc_Name", "")).upper())
                    ]
                    if relevant:
                        body = {"drug": drug_name, "generic_name": generic,
                                "dataset_id": did, "results": relevant}
                        std_insert("mol_raw", "cms_medicare", url, body, drug=drug_name, ms=ms)
                        return {"status": "success", "rows": len(relevant)}

    return {"status": "no_results", "rows": 0}


async def load_medicaid_drug_utilization(client: httpx.AsyncClient, drug_name: str, generic: str) -> Dict:
    """
    Load Medicaid State Drug Utilization data (SDUD) for the drug.
    Dataset: tau9-gfwr — Medicaid Drug Utilization
    """
    base = "https://data.cms.gov/data-api/v1/dataset"
    for drug_variant in [drug_name, generic]:
        url = f"{base}/tau9-gfwr/data?search={quote(drug_variant)}&limit=100"
        res = await fetch(client, url)
        if res:
            data, ms = res
            if isinstance(data, list) and data:
                relevant = [
                    r for r in data
                    if (drug_variant.lower() in str(r.get("product_name", "")).lower() or
                        drug_variant.lower() in str(r.get("labeler_name", "")).lower())
                ]
                if relevant:
                    body = {"drug": drug_name, "generic": generic,
                            "source": "Medicaid SDUD", "results": relevant}
                    std_insert("mol_raw", "cms_medicare", url, body, drug=drug_name, ms=ms)
                    return {"status": "success", "rows": len(relevant)}
    return {"status": "no_results", "rows": 0}


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 — FULL SOURCE PIPELINE FOR A DRUG
# Adapted from load_arcalyst.py for any drug name
# ═══════════════════════════════════════════════════════════════════════════

RESULTS: List[Dict] = []

def log_result(drug: str, source: str, status: str, error: str = "", rows: int = 0, ms: int = 0):
    RESULTS.append({"drug": drug, "source": source, "status": status,
                    "error": error, "rows": rows, "ms": ms})
    icon = "✓" if status == "success" else ("–" if status == "skip" else "✗")
    detail = f"{ms}ms" if status == "success" else f"{error[:60]}"
    print(f"    {icon} {drug:<16} {source:<28} {detail}")


async def load_clinicaltrials(client, drug_name, generic):
    url = f"https://clinicaltrials.gov/api/v2/studies?query.intr={quote(generic)}&pageSize=100&format=json"
    t0 = time.monotonic()
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "clinicaltrials", "error", "fetch failed"); return
    data, ms = res
    studies = data.get("studies", [])
    if not studies:
        log_result(drug_name, "clinicaltrials", "error", "no studies"); return
    std_insert("mol_raw", "clinicaltrials", url, data, drug=drug_name, ms=ms)
    log_result(drug_name, "clinicaltrials", "success", rows=len(studies), ms=ms)


async def load_openfda_labels(client, drug_name, generic):
    url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:{quote(generic)}&limit=10"
    if OPENFDA_API_KEY:
        url += f"&api_key={OPENFDA_API_KEY}"
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "openfda_labels", "error", "fetch failed"); return
    data, ms = res
    if not data.get("results"):
        log_result(drug_name, "openfda_labels", "error", "no results"); return
    std_insert("mol_raw", "openfda_labels", url, data, drug=drug_name, ms=ms)
    log_result(drug_name, "openfda_labels", "success", rows=len(data["results"]), ms=ms)


async def load_openfda_faers(client, drug_name, generic):
    url = f"https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:{quote(generic)}&limit=100"
    if OPENFDA_API_KEY:
        url += f"&api_key={OPENFDA_API_KEY}"
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "openfda_faers", "error", "fetch failed"); return
    data, ms = res
    if not data.get("results"):
        log_result(drug_name, "openfda_faers", "error", "no results"); return
    std_insert("mol_raw", "openfda_faers", url, data, drug=drug_name, ms=ms)
    log_result(drug_name, "openfda_faers", "success", rows=len(data["results"]), ms=ms)


async def load_chembl(client, drug_name, generic, chembl_id=None):
    search_term = chembl_id if chembl_id else generic
    url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/{search_term}?format=json" if chembl_id else \
          f"https://www.ebi.ac.uk/chembl/api/data/molecule?pref_name__iexact={quote(generic)}&format=json"
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "chembl", "error", "fetch failed"); return
    data, ms = res
    if not data:
        log_result(drug_name, "chembl", "error", "no data"); return
    std_insert("mol_raw", "chembl", url, data, drug=drug_name, ms=ms)
    log_result(drug_name, "chembl", "success", rows=1, ms=ms)


async def load_uniprot(client, drug_name, generic):
    url = f"https://rest.uniprot.org/uniprotkb/search?query={quote(generic)}&format=json&size=25"
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "uniprot", "error", "fetch failed"); return
    data, ms = res
    results = data.get("results", [])
    if not results:
        log_result(drug_name, "uniprot", "error", "no results"); return
    std_insert("mol_raw", "uniprot", url, data, drug=drug_name, ms=ms)
    log_result(drug_name, "uniprot", "success", rows=len(results), ms=ms)


async def load_dailymed(client, drug_name, generic):
    url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_name={quote(generic)}&pagesize=20"
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "dailymed", "error", "fetch failed"); return
    data, ms = res
    spls = data.get("data", [])
    if not spls:
        log_result(drug_name, "dailymed", "error", "no results"); return
    std_insert("mol_raw", "dailymed", url, data, drug=drug_name, ms=ms)
    log_result(drug_name, "dailymed", "success", rows=len(spls), ms=ms)


async def load_orange_book(client, drug_name, generic):
    url = f"https://api.fda.gov/drug/drugsfda.json?search=openfda.generic_name:{quote(generic)}&limit=10"
    if OPENFDA_API_KEY:
        url += f"&api_key={OPENFDA_API_KEY}"
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "orange_book", "error", "fetch failed"); return
    data, ms = res
    if not data.get("results"):
        log_result(drug_name, "orange_book", "error", "no results"); return
    std_insert("mol_raw", "orange_book", url, data, drug=drug_name, ms=ms)
    log_result(drug_name, "orange_book", "success", rows=len(data["results"]), ms=ms)


async def load_pubmed(client, drug_name, generic):
    esearch = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&term={quote(generic)}&retmode=json&retmax=100&sort=relevance"
    )
    if NCBI_API_KEY:
        esearch += f"&api_key={NCBI_API_KEY}"
    res = await fetch(client, esearch)
    if not res:
        log_result(drug_name, "pubmed", "error", "esearch failed"); return
    data, _ = res
    ids = data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        log_result(drug_name, "pubmed", "error", "no PMIDs"); return

    ids_str = ",".join(ids[:100])
    esum = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        f"?db=pubmed&id={ids_str}&retmode=json"
    )
    if NCBI_API_KEY:
        esum += f"&api_key={NCBI_API_KEY}"
    res2 = await fetch(client, esum)
    if not res2:
        log_result(drug_name, "pubmed", "error", "esummary failed"); return
    summary_data, ms = res2

    articles = summary_data.get("result", {})
    inserted = 0
    c = db_conn()
    try:
        cur = c.cursor()
        for pmid in ids[:100]:
            art = articles.get(pmid, {})
            if not art or pmid == "uids":
                continue
            pub_date = None
            pub_str = art.get("pubdate", "")
            if pub_str:
                try:
                    pub_date = date(int(pub_str.split()[0]), 1, 1)
                except Exception:
                    pass
            doi = next((e.get("value","") for e in art.get("elocationid",[])
                        if isinstance(e, dict) and e.get("eidtype")=="doi"), "")
            authors = [{"name": a.get("name",""), "authtype": a.get("authtype","")}
                       for a in art.get("authors", [])]
            try:
                cur.execute("""
                    INSERT INTO mol_raw.pubmed
                        (pmid, title, abstract, authors, journal, publication_date, doi, _loaded_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT (pmid) DO NOTHING
                """, (pmid[:20], art.get("title",""), None, Json(authors),
                      (art.get("fulljournalname","") or "")[:500],
                      pub_date, (doi or "")[:100] or None))
                inserted += 1
            except Exception:
                c.rollback()
        c.commit()
        log_result(drug_name, "pubmed", "success", rows=inserted, ms=ms)
    except Exception as e:
        log_result(drug_name, "pubmed", "error", str(e)[:60])
    finally:
        c.close()


async def load_europepmc(client, drug_name, generic):
    url = (
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query={quote(generic)}&format=json&resultType=core&pageSize=100&sort=CITED+desc"
    )
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "europepmc", "error", "fetch failed"); return
    data, ms = res
    results = data.get("resultList", {}).get("result", [])
    if not results:
        log_result(drug_name, "europepmc", "error", "no results"); return
    simple_insert("mol_raw", "europepmc", {"drug": drug_name, "query": generic,
                                            "data": data, "count": len(results)})
    log_result(drug_name, "europepmc", "success", rows=len(results), ms=ms)


async def load_nih_reporter(client, drug_name, generic):
    url = "https://api.reporter.nih.gov/v2/projects/search"
    payload = {
        "criteria": {"advanced_text_search": {"operator": "and", "search_field": "all",
                                               "search_text": generic}},
        "include_fields": ["ProjectNum","ProjectTitle","AbstractText","Organization",
                           "FiscalYear","AwardAmount","PrincipalInvestigators"],
        "offset": 0, "limit": 100,
    }
    res = await fetch(client, url, method="POST", post_json=payload)
    if not res:
        log_result(drug_name, "nih_reporter", "error", "fetch failed"); return
    data, ms = res
    if not data.get("results"):
        log_result(drug_name, "nih_reporter", "error", "no results"); return
    simple_insert("mol_raw", "nih_reporter", {"drug": drug_name, "data": data})
    log_result(drug_name, "nih_reporter", "success", rows=len(data["results"]), ms=ms)


async def load_rxnorm_drug(client, drug_name, generic):
    # Search RxNorm by name to get CUI, then fetch full data
    search_url = f"https://rxnav.nlm.nih.gov/REST/rxcui.json?name={quote(generic)}&search=1"
    res = await fetch(client, search_url)
    if not res:
        log_result(drug_name, "rxnorm", "error", "name lookup failed"); return
    data, _ = res
    idGroup = data.get("idGroup", {})
    rxnorm_cuis = idGroup.get("rxnormId", [])
    if not rxnorm_cuis:
        log_result(drug_name, "rxnorm", "error", "no CUI found"); return
    cui = rxnorm_cuis[0]
    url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{cui}/allrelated.json"
    res2 = await fetch(client, url)
    if not res2:
        log_result(drug_name, "rxnorm", "error", "allrelated fetch failed"); return
    data2, ms = res2
    body = {"drug": drug_name, "cui": cui, "allrelated": data2}
    std_insert("mol_raw", "rxnorm", url, body, drug=drug_name, ms=ms)
    log_result(drug_name, "rxnorm", "success", rows=1, ms=ms)


async def load_biorxiv_drug(client, drug_name, generic):
    result = await load_biorxiv_for_drug(client, drug_name, generic)
    if result["status"] == "success":
        log_result(drug_name, "biorxiv", "success", rows=result["rows"])
    else:
        log_result(drug_name, "biorxiv", "error", "no preprints found")


async def load_openalex(client, drug_name, generic):
    url = (
        f"https://api.openalex.org/works?search={quote(generic)}"
        f"&per-page=100&sort=cited_by_count:desc&mailto=research@datakinetic.com"
    )
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "openalex_ci", "error", "fetch failed"); return
    data, ms = res
    works = data.get("results", [])
    if not works:
        log_result(drug_name, "openalex_ci", "error", "no results"); return

    c = db_conn()
    inserted = 0
    try:
        cur = c.cursor()
        for w in works:
            work_id = w.get("id", "").replace("https://openalex.org/", "")
            doi = (w.get("doi") or "").replace("https://doi.org/", "")[:100]
            pub_date_str = w.get("publication_date")
            pub_date = None
            if pub_date_str:
                try:
                    pub_date = date.fromisoformat(pub_date_str)
                except Exception:
                    pass
            try:
                cur.execute("""
                    INSERT INTO mol_raw.openalex_ci
                        (work_id, doi, title, abstract, publication_date,
                         cited_by_count, concepts, authorships, primary_location, open_access)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (work_id) DO NOTHING
                """, (work_id[:50], doi or None,
                      w.get("title",""), (w.get("abstract","") or "")[:5000],
                      pub_date, w.get("cited_by_count", 0),
                      Json(w.get("concepts",[])), Json(w.get("authorships",[])),
                      Json(w.get("primary_location",{})), Json(w.get("open_access",{}))))
                inserted += 1
            except Exception:
                c.rollback()
        c.commit()
        log_result(drug_name, "openalex_ci", "success", rows=inserted, ms=ms)
    except Exception as e:
        log_result(drug_name, "openalex_ci", "error", str(e)[:60])
    finally:
        c.close()


async def load_pharmgkb(client, drug_name, generic):
    url = f"https://api.pharmgkb.org/v1/data/drug?name={quote(generic)}&view=max"
    res = await fetch(client, url)
    if not res:
        log_result(drug_name, "pharmgkb", "error", "fetch failed"); return
    data, ms = res
    if not data.get("data"):
        log_result(drug_name, "pharmgkb", "error", "no data"); return
    std_insert("mol_raw", "pharmgkb", url, data, drug=drug_name, ms=ms)
    log_result(drug_name, "pharmgkb", "success", rows=1, ms=ms)


async def load_drug_pipeline(
    client: httpx.AsyncClient,
    drug_name: str,
    generic: str,
    chembl_id: Optional[str] = None,
):
    """Run the full source pipeline for a single drug (competitor or target)."""
    sem = asyncio.Semaphore(6)

    async def run(coro):
        async with sem:
            try:
                await coro
            except Exception as e:
                print(f"    !! unhandled: {e}")

    tasks = [
        load_clinicaltrials(client, drug_name, generic),
        load_openfda_labels(client, drug_name, generic),
        load_openfda_faers(client, drug_name, generic),
        load_chembl(client, drug_name, generic, chembl_id),
        load_uniprot(client, drug_name, generic),
        load_dailymed(client, drug_name, generic),
        load_orange_book(client, drug_name, generic),
        load_pubmed(client, drug_name, generic),
        load_europepmc(client, drug_name, generic),
        load_nih_reporter(client, drug_name, generic),
        load_rxnorm_drug(client, drug_name, generic),
        load_biorxiv_drug(client, drug_name, generic),
        load_openalex(client, drug_name, generic),
        load_pharmgkb(client, drug_name, generic),
    ]
    await asyncio.gather(*[run(t) for t in tasks])


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    print(f"\n{'='*70}")
    print(f"  Ground Truth Pipeline: Arcalyst (rilonacept) + Competitors")
    print(f"  DB: localhost:5433/dk_data")
    print(f"{'='*70}")

    async with httpx.AsyncClient(follow_redirects=True) as client:

        # ── Step 1: Competitor Discovery ─────────────────────────────────
        competitors = await discover_and_score_competitors(client)

        # Store competitor discovery results in DB
        comp_body = {
            "drug": DRUG_NAME,
            "generic": GENERIC_NAME,
            "indication": "CAPS / Recurrent Pericarditis",
            "discovery_method": "OpenFDA EPC + known IL-1 clinical landscape",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "competitors": competitors,
        }
        std_insert("mol_raw", "websearch", "competitor_discovery://arcalyst",
                   comp_body, drug=DRUG_NAME)
        print(f"\n  ✓ Competitor discovery complete: {len(competitors)} competitors scored")

        # ── Step 2: bioRxiv for Arcalyst ─────────────────────────────────
        print("\n── BIORXIV / MEDRXIV ───────────────────────────────────────────")
        result = await load_biorxiv_for_drug(client, DRUG_NAME, GENERIC_NAME)
        print(f"  {'✓' if result['status']=='success' else '✗'} arcalyst biorxiv: {result['rows']} preprints")

        # ── Step 3: CMS Data ─────────────────────────────────────────────
        print("\n── CMS DATA ────────────────────────────────────────────────────")

        r = await load_cms_open_payments_real(client, DRUG_NAME, GENERIC_NAME)
        print(f"  {'✓' if r['status']=='success' else '✗'} cms_open_payments: {r['rows']} rows")

        r = await load_cms_part_d_real(client, DRUG_NAME, GENERIC_NAME)
        print(f"  {'✓' if r['status']=='success' else '✗'} cms_part_d: {r['rows']} rows")

        r = await load_medicaid_drug_utilization(client, DRUG_NAME, GENERIC_NAME)
        print(f"  {'✓' if r['status']=='success' else '✗'} medicaid_sdud: {r['rows']} rows")

        # ── Step 4: Full pipeline for Arcalyst (extend what was already loaded) ─
        print("\n── ARCALYST EXTENDED SOURCES ───────────────────────────────────")
        await load_drug_pipeline(client, DRUG_NAME, GENERIC_NAME, CHEMBL_ID)

        # ── Step 5: Full pipeline for each competitor ─────────────────────
        print("\n── COMPETITOR DATA LOADING ─────────────────────────────────────")
        for comp in competitors:
            cname = comp["name"]
            cbrand = comp["brand"]
            cchembl = comp.get("chembl")
            print(f"\n  [{cbrand} / {cname}]")
            await load_drug_pipeline(client, cbrand, cname, cchembl)

    # ── Final summary ──────────────────────────────────────────────────
    ok   = [r for r in RESULTS if r["status"] == "success"]
    err  = [r for r in RESULTS if r["status"] == "error"]
    skip = [r for r in RESULTS if r["status"] == "skip"]

    print(f"\n{'='*70}")
    print(f"  DONE: {len(ok)} success | {len(skip)} skip | {len(err)} error")
    print(f"{'='*70}")

    if err:
        print("\n  Errors:")
        for r in err:
            print(f"  ✗ [{r['drug']}] {r['source']}: {r['error']}")

    # Write summary
    summary = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "arcalyst": DRUG_NAME,
        "competitors_discovered": [c["name"] for c in competitors],
        "competitor_scores": {c["name"]: c["threat_score"] for c in competitors},
        "results": RESULTS,
        "totals": {"success": len(ok), "error": len(err), "skip": len(skip)},
    }
    out_path = Path("/Users/pschloz/Desktop/DataKinetic/Cross-Project-Planning/Brook/Arcalyst/ground_truth_pipeline_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n  Results: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
