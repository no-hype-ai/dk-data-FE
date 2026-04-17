#!/usr/bin/env python3
"""
Pipeline loader for Goflikicept (RPH-104) — competitor to Arcalyst (rilonacept).

Goflikicept is a recombinant fusion protein (IL-1 trap) developed by RSLS/Bioxcel.
Also known as RPH-104. Being studied for recurrent pericarditis and other IL-1-mediated
conditions.

Run with Doppler:
    doppler run -- python3 scripts/load_goflikicept.py
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

DRUG_NAME    = "Goflikicept"
GENERIC_NAME = "goflikicept"
ALT_NAME     = "RPH-104"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "dk-data-platform research@datakinetic.com",
}
TIMEOUT = 45.0

RESULTS: List[Dict] = []


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


# ── Logging helper ────────────────────────────────────────────────────────────

def log_result(drug: str, source: str, status: str, error: str = "", rows: int = 0, ms: int = 0):
    RESULTS.append({"drug": drug, "source": source, "status": status,
                    "error": error, "rows": rows, "ms": ms})
    icon = "✓" if status == "success" else ("–" if status == "skip" else "✗")
    detail = f"{ms}ms" if status == "success" else f"{error[:60]}"
    print(f"    {icon} {drug:<20} {source:<28} {detail}")


# ── ChEMBL discovery ──────────────────────────────────────────────────────────

async def discover_chembl_id(client: httpx.AsyncClient) -> Optional[str]:
    """Search ChEMBL for goflikicept / RPH-104 and return the ChEMBL ID if found."""
    search_terms = [GENERIC_NAME, ALT_NAME, "goflikicept"]
    for term in search_terms:
        # Try pref_name exact match first
        url = f"https://www.ebi.ac.uk/chembl/api/data/molecule?pref_name__iexact={quote(term)}&format=json"
        res = await fetch(client, url)
        if res:
            data, _ = res
            mols = data.get("molecules", [])
            if mols:
                chembl_id = mols[0].get("molecule_chembl_id")
                print(f"  ChEMBL: found by pref_name '{term}' → {chembl_id}")
                return chembl_id

        # Try free-text search
        url2 = f"https://www.ebi.ac.uk/chembl/api/data/molecule?q={quote(term)}&format=json"
        res2 = await fetch(client, url2)
        if res2:
            data2, _ = res2
            mols2 = data2.get("molecules", [])
            for mol in mols2:
                pref = (mol.get("pref_name") or "").lower()
                syns = [s.get("molecule_synonym", "").lower() for s in (mol.get("molecule_synonyms") or [])]
                if term.lower() in pref or term.lower() in syns:
                    chembl_id = mol.get("molecule_chembl_id")
                    print(f"  ChEMBL: found via search '{term}' → {chembl_id} (pref_name={mol.get('pref_name')})")
                    return chembl_id

    print("  ChEMBL: no match found for goflikicept / RPH-104")
    return None


# ── Source loaders (adapted from load_arcalyst_ground_truth.py) ───────────────

async def load_clinicaltrials(client, drug_name, generic):
    # Search by generic name AND by RPH-104 alias
    all_studies = []
    seen_ncts = set()

    for term in [generic, ALT_NAME]:
        url = f"https://clinicaltrials.gov/api/v2/studies?query.intr={quote(term)}&pageSize=100&format=json"
        t0 = time.monotonic()
        res = await fetch(client, url)
        if not res:
            continue
        data, ms = res
        studies = data.get("studies", [])
        for s in studies:
            nct = s.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "")
            if nct and nct not in seen_ncts:
                seen_ncts.add(nct)
                all_studies.append(s)

    if not all_studies:
        log_result(drug_name, "clinicaltrials", "error", "no studies found"); return

    # Also try brand/alias search
    url_alias = f"https://clinicaltrials.gov/api/v2/studies?query.intr={quote(ALT_NAME)}&pageSize=100&format=json"
    merged_data = {"studies": all_studies, "totalCount": len(all_studies),
                   "_search_terms": [generic, ALT_NAME]}
    url_logged = f"https://clinicaltrials.gov/api/v2/studies?query.intr={quote(generic)}&pageSize=100&format=json"
    std_insert("mol_raw", "clinicaltrials", url_logged, merged_data, drug=drug_name, ms=500)
    log_result(drug_name, "clinicaltrials", "success", rows=len(all_studies), ms=500)


async def load_openfda_labels(client, drug_name, generic):
    # Goflikicept is not FDA-approved — try both name variants
    for term in [generic, ALT_NAME]:
        url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:{quote(term)}&limit=10"
        if OPENFDA_API_KEY:
            url += f"&api_key={OPENFDA_API_KEY}"
        res = await fetch(client, url)
        if res:
            data, ms = res
            if data.get("results"):
                std_insert("mol_raw", "openfda_labels", url, data, drug=drug_name, ms=ms)
                log_result(drug_name, "openfda_labels", "success", rows=len(data["results"]), ms=ms)
                return
    log_result(drug_name, "openfda_labels", "error", "no FDA label (not approved)")


async def load_openfda_faers(client, drug_name, generic):
    for term in [generic, ALT_NAME]:
        url = f"https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:{quote(term)}&limit=100"
        if OPENFDA_API_KEY:
            url += f"&api_key={OPENFDA_API_KEY}"
        res = await fetch(client, url)
        if res:
            data, ms = res
            if data.get("results"):
                std_insert("mol_raw", "openfda_faers", url, data, drug=drug_name, ms=ms)
                log_result(drug_name, "openfda_faers", "success", rows=len(data["results"]), ms=ms)
                return
    log_result(drug_name, "openfda_faers", "error", "no FAERS data (not approved)")


async def load_chembl(client, drug_name, generic, chembl_id=None):
    if chembl_id:
        url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/{chembl_id}?format=json"
        res = await fetch(client, url)
        if res:
            data, ms = res
            std_insert("mol_raw", "chembl", url, data, drug=drug_name, ms=ms)
            log_result(drug_name, "chembl", "success", rows=1, ms=ms)
            return

    # No known ChEMBL ID — try search
    for term in [generic, ALT_NAME]:
        url = f"https://www.ebi.ac.uk/chembl/api/data/molecule?pref_name__iexact={quote(term)}&format=json"
        res = await fetch(client, url)
        if res:
            data, ms = res
            if data.get("molecules"):
                std_insert("mol_raw", "chembl", url, data, drug=drug_name, ms=ms)
                log_result(drug_name, "chembl", "success", rows=len(data["molecules"]), ms=ms)
                return

        url2 = f"https://www.ebi.ac.uk/chembl/api/data/molecule?q={quote(term)}&format=json"
        res2 = await fetch(client, url2)
        if res2:
            data2, ms2 = res2
            if data2.get("molecules"):
                # Check if any match our drug
                for mol in data2["molecules"]:
                    pref = (mol.get("pref_name") or "").lower()
                    syns = [s.get("molecule_synonym", "").lower() for s in (mol.get("molecule_synonyms") or [])]
                    if term.lower() in pref or term.lower() in syns:
                        std_insert("mol_raw", "chembl", url2, data2, drug=drug_name, ms=ms2)
                        log_result(drug_name, "chembl", "success", rows=1, ms=ms2)
                        return

    log_result(drug_name, "chembl", "error", "no ChEMBL entry found")


async def load_uniprot(client, drug_name, generic):
    for term in [generic, ALT_NAME, "IL-1 trap"]:
        url = f"https://rest.uniprot.org/uniprotkb/search?query={quote(term)}&format=json&size=25"
        res = await fetch(client, url)
        if res:
            data, ms = res
            results = data.get("results", [])
            if results:
                std_insert("mol_raw", "uniprot", url, data, drug=drug_name, ms=ms)
                log_result(drug_name, "uniprot", "success", rows=len(results), ms=ms)
                return
    log_result(drug_name, "uniprot", "error", "no results")


async def load_dailymed(client, drug_name, generic):
    for term in [generic, ALT_NAME]:
        url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_name={quote(term)}&pagesize=20"
        res = await fetch(client, url)
        if res:
            data, ms = res
            spls = data.get("data", [])
            if spls:
                std_insert("mol_raw", "dailymed", url, data, drug=drug_name, ms=ms)
                log_result(drug_name, "dailymed", "success", rows=len(spls), ms=ms)
                return
    log_result(drug_name, "dailymed", "error", "no DailyMed entry (not approved)")


async def load_orange_book(client, drug_name, generic):
    for term in [generic, ALT_NAME]:
        url = f"https://api.fda.gov/drug/drugsfda.json?search=openfda.generic_name:{quote(term)}&limit=10"
        if OPENFDA_API_KEY:
            url += f"&api_key={OPENFDA_API_KEY}"
        res = await fetch(client, url)
        if res:
            data, ms = res
            if data.get("results"):
                std_insert("mol_raw", "orange_book", url, data, drug=drug_name, ms=ms)
                log_result(drug_name, "orange_book", "success", rows=len(data["results"]), ms=ms)
                return
    log_result(drug_name, "orange_book", "error", "no Orange Book entry (not approved)")


async def load_pubmed(client, drug_name, generic):
    # Search both generic name and RPH-104 alias
    all_pmids = []
    for term in [generic, ALT_NAME]:
        esearch = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={quote(term)}&retmode=json&retmax=100&sort=relevance"
        )
        if NCBI_API_KEY:
            esearch += f"&api_key={NCBI_API_KEY}"
        res = await fetch(client, esearch)
        if res:
            data, _ = res
            ids = data.get("esearchresult", {}).get("idlist", [])
            for pid in ids:
                if pid not in all_pmids:
                    all_pmids.append(pid)

    if not all_pmids:
        log_result(drug_name, "pubmed", "error", "no PMIDs found"); return

    ids_str = ",".join(all_pmids[:100])
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
        for pmid in all_pmids[:100]:
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
            except Exception as e:
                c.rollback()
        c.commit()
        log_result(drug_name, "pubmed", "success", rows=inserted, ms=ms)
    except Exception as e:
        log_result(drug_name, "pubmed", "error", str(e)[:60])
    finally:
        c.close()


async def load_europepmc(client, drug_name, generic):
    all_results = []
    for term in [generic, ALT_NAME]:
        url = (
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/search"
            f"?query={quote(term)}&format=json&resultType=core&pageSize=100&sort=CITED+desc"
        )
        res = await fetch(client, url)
        if res:
            data, ms = res
            results = data.get("resultList", {}).get("result", [])
            all_results.extend(results)

    if not all_results:
        log_result(drug_name, "europepmc", "error", "no results"); return

    simple_insert("mol_raw", "europepmc", {"drug": drug_name, "query": generic,
                                            "alt_name": ALT_NAME,
                                            "data": {"resultList": {"result": all_results}},
                                            "count": len(all_results)})
    log_result(drug_name, "europepmc", "success", rows=len(all_results), ms=ms)


async def load_nih_reporter(client, drug_name, generic):
    all_results = []
    for term in [generic, ALT_NAME]:
        url = "https://api.reporter.nih.gov/v2/projects/search"
        payload = {
            "criteria": {"advanced_text_search": {"operator": "and", "search_field": "all",
                                                   "search_text": term}},
            "include_fields": ["ProjectNum","ProjectTitle","AbstractText","Organization",
                               "FiscalYear","AwardAmount","PrincipalInvestigators"],
            "offset": 0, "limit": 100,
        }
        res = await fetch(client, url, method="POST", post_json=payload)
        if res:
            data, ms = res
            results = data.get("results", [])
            all_results.extend(results)

    if not all_results:
        log_result(drug_name, "nih_reporter", "error", "no results"); return
    simple_insert("mol_raw", "nih_reporter", {"drug": drug_name, "data": {"results": all_results}})
    log_result(drug_name, "nih_reporter", "success", rows=len(all_results), ms=ms)


async def load_rxnorm_drug(client, drug_name, generic):
    for term in [generic, ALT_NAME]:
        search_url = f"https://rxnav.nlm.nih.gov/REST/rxcui.json?name={quote(term)}&search=1"
        res = await fetch(client, search_url)
        if res:
            data, _ = res
            idGroup = data.get("idGroup", {})
            rxnorm_cuis = idGroup.get("rxnormId", [])
            if rxnorm_cuis:
                cui = rxnorm_cuis[0]
                url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{cui}/allrelated.json"
                res2 = await fetch(client, url)
                if res2:
                    data2, ms = res2
                    body = {"drug": drug_name, "search_term": term, "cui": cui, "allrelated": data2}
                    std_insert("mol_raw", "rxnorm", url, body, drug=drug_name, ms=ms)
                    log_result(drug_name, "rxnorm", "success", rows=1, ms=ms)
                    return
    log_result(drug_name, "rxnorm", "error", "no RxNorm CUI (not approved)")


async def load_biorxiv_drug(client, drug_name, generic):
    all_items = []
    for query in [generic, ALT_NAME]:
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
        qlow = query.lower()
        for item in items:
            title_text = " ".join(item.get("title", [])).lower()
            abstract_text = (item.get("abstract") or "").lower()
            if qlow in title_text or qlow in abstract_text:
                doi = item.get("DOI", "")
                if not any(x.get("DOI") == doi for x in all_items):
                    all_items.append(item)

    if not all_items:
        log_result(drug_name, "biorxiv", "error", "no preprints found"); return

    body = {
        "drug": drug_name,
        "generic_name": generic,
        "alt_name": ALT_NAME,
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
    log_result(drug_name, "biorxiv", "success", rows=len(all_items), ms=ms)


async def load_openalex(client, drug_name, generic):
    all_works = []
    seen_ids = set()

    for term in [generic, ALT_NAME]:
        url = (
            f"https://api.openalex.org/works?search={quote(term)}"
            f"&per-page=100&sort=cited_by_count:desc&mailto=research@datakinetic.com"
        )
        res = await fetch(client, url)
        if res:
            data, ms = res
            works = data.get("results", [])
            for w in works:
                wid = w.get("id", "")
                if wid not in seen_ids:
                    seen_ids.add(wid)
                    all_works.append(w)

    if not all_works:
        log_result(drug_name, "openalex_ci", "error", "no results"); return

    c = db_conn()
    inserted = 0
    try:
        cur = c.cursor()
        for w in all_works:
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
    for term in [generic, ALT_NAME]:
        url = f"https://api.pharmgkb.org/v1/data/drug?name={quote(term)}&view=max"
        res = await fetch(client, url)
        if res:
            data, ms = res
            if data.get("data"):
                std_insert("mol_raw", "pharmgkb", url, data, drug=drug_name, ms=ms)
                log_result(drug_name, "pharmgkb", "success", rows=1, ms=ms)
                return
    log_result(drug_name, "pharmgkb", "error", "no PharmGKB entry")


async def load_drug_pipeline(
    client: httpx.AsyncClient,
    drug_name: str,
    generic: str,
    chembl_id: Optional[str] = None,
):
    """Run the full source pipeline for goflikicept."""
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
    print(f"  Pipeline Loader: Goflikicept (RPH-104)")
    print(f"  Competitor to Arcalyst (rilonacept) — IL-1 trap, recurrent pericarditis")
    print(f"  DB: localhost:5433/dk_data")
    print(f"{'='*70}")

    async with httpx.AsyncClient(follow_redirects=True) as client:

        # Step 1: Discover ChEMBL ID
        print("\n── CHEMBL DISCOVERY ─────────────────────────────────────────────")
        chembl_id = await discover_chembl_id(client)
        if chembl_id:
            print(f"  → Will use ChEMBL ID: {chembl_id}")
        else:
            print("  → Proceeding without ChEMBL ID (will attempt search during pipeline)")

        # Step 2: Run full pipeline
        print(f"\n── FULL SOURCE PIPELINE: {DRUG_NAME} / {GENERIC_NAME} / {ALT_NAME} ──")
        await load_drug_pipeline(client, DRUG_NAME, GENERIC_NAME, chembl_id)

    # Summary
    ok   = [r for r in RESULTS if r["status"] == "success"]
    err  = [r for r in RESULTS if r["status"] == "error"]
    skip = [r for r in RESULTS if r["status"] == "skip"]

    print(f"\n{'='*70}")
    print(f"  DONE: {len(ok)} success | {len(skip)} skip | {len(err)} error")
    print(f"{'='*70}")

    if ok:
        print("\n  Successful loads:")
        for r in ok:
            print(f"  ✓ {r['source']:<28} rows={r['rows']} ms={r['ms']}")

    if err:
        print("\n  Errors (expected for unapproved drugs):")
        for r in err:
            print(f"  ✗ {r['source']:<28} {r['error']}")

    # Write summary JSON
    summary = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "drug": DRUG_NAME,
        "generic": GENERIC_NAME,
        "alt_name": ALT_NAME,
        "results": RESULTS,
        "totals": {"success": len(ok), "error": len(err), "skip": len(skip)},
    }
    out_path = Path(__file__).parent.parent / "goflikicept_load_results.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n  Results written to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
