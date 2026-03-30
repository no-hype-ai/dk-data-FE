#!/usr/bin/env python3
"""
USPTO PatentsView Patent Loader

Loads patent data from USPTO PatentsView API into PostgreSQL.
Note: PatentsView API requires registration for API key.

Tables populated:
- mol_bronze.uspto_patents: Patent data with drug/pharma focus

Data Source: https://patentsview.org/
API Registration: https://patentsview-support.atlassian.net/servicedesk/customer/portals

Usage:
    # Load patents for known drugs
    python -m dk_data.data.load_uspto_patents --mode drugs

    # Load by company/assignee
    python -m dk_data.data.load_uspto_patents --mode assignee --assignee "Pfizer"

    # Load recent pharma patents
    python -m dk_data.data.load_uspto_patents --mode recent --days 365

    # Test with limit
    python -m dk_data.data.load_uspto_patents --limit 100

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    PATENTSVIEW_API_KEY (required)
"""

import os
import sys
import asyncio
from datetime import datetime
from typing import List, Dict, Any
import argparse

import psycopg2
from psycopg2.extras import Json
from loguru import logger
from tqdm import tqdm
import aiohttp

# Database config
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# PatentsView API
PATENTSVIEW_API_URL = "https://search.patentsview.org/api/v1/patent/"
PATENTSVIEW_API_KEY = os.getenv("PATENTSVIEW_API_KEY")


def ensure_tables(conn) -> None:
    """Create USPTO patents tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mol_bronze.uspto_patents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                patent_number TEXT UNIQUE NOT NULL,
                title TEXT,
                abstract TEXT,
                grant_date DATE,
                application_date DATE,
                expiry_date DATE,
                patent_type TEXT DEFAULT 'utility',
                assignees JSONB DEFAULT '[]',
                inventors JSONB DEFAULT '[]',
                claims_count INTEGER,
                cpc_codes JSONB DEFAULT '[]',
                uspc_codes JSONB DEFAULT '[]',
                citations_count INTEGER DEFAULT 0,
                cited_by_count INTEGER DEFAULT 0,
                drug_name TEXT,
                active_substance TEXT,
                raw_data JSONB,
                source_updated_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_to_silver BOOLEAN DEFAULT FALSE
            );

            CREATE INDEX IF NOT EXISTS idx_uspto_grant_date ON mol_bronze.uspto_patents(grant_date);
            CREATE INDEX IF NOT EXISTS idx_uspto_assignee ON mol_bronze.uspto_patents USING GIN(assignees);
            CREATE INDEX IF NOT EXISTS idx_uspto_cpc ON mol_bronze.uspto_patents USING GIN(cpc_codes);
            CREATE INDEX IF NOT EXISTS idx_uspto_drug ON mol_bronze.uspto_patents(drug_name);
            CREATE INDEX IF NOT EXISTS idx_uspto_processed ON mol_bronze.uspto_patents(processed_to_silver);
        """)
        conn.commit()
    logger.info("USPTO patents tables ensured")


async def search_patents(query: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Search PatentsView API."""
    if not PATENTSVIEW_API_KEY:
        logger.error("PATENTSVIEW_API_KEY not set. Register at: https://patentsview-support.atlassian.net/servicedesk/customer/portals")
        return []

    headers = {
        "X-Api-Key": PATENTSVIEW_API_KEY,
        "Content-Type": "application/json"
    }

    # Build query for pharma patents
    request_body = {
        "q": {"_text_any": {"patent_abstract": query}},
        "f": [
            "patent_number", "patent_title", "patent_abstract",
            "patent_date", "patent_type", "patent_num_claims",
            "assignees", "inventors", "cpcs", "uspcs",
            "citedby_patents", "cited_patents"
        ],
        "o": {"page": 1, "per_page": min(limit, 1000)},
        "s": [{"patent_date": "desc"}]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                PATENTSVIEW_API_URL,
                json=request_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 401:
                    logger.error("Invalid API key. Please check PATENTSVIEW_API_KEY")
                    return []
                if response.status != 200:
                    text = await response.text()
                    logger.warning(f"PatentsView API returned {response.status}: {text[:200]}")
                    return []

                data = await response.json()
                return data.get("patents", [])

    except Exception as e:
        logger.error(f"PatentsView API error: {e}")
        return []


def parse_patent(patent: Dict[str, Any], drug_name: str = None) -> Dict[str, Any]:
    """Parse patent data from API response."""
    # Parse dates
    grant_date = None
    if patent.get("patent_date"):
        try:
            grant_date = datetime.strptime(patent["patent_date"], "%Y-%m-%d").date()
        except Exception:
            pass

    # Calculate expiry (20 years from filing for utility patents)
    expiry_date = None
    if grant_date:
        expiry_date = grant_date.replace(year=grant_date.year + 20)

    # Parse assignees
    assignees = []
    for a in patent.get("assignees", []) or []:
        assignees.append({
            "name": a.get("assignee_organization") or a.get("assignee_first_name", ""),
            "type": a.get("assignee_type"),
            "location": a.get("assignee_city"),
        })

    # Parse inventors
    inventors = []
    for i in patent.get("inventors", []) or []:
        name = f"{i.get('inventor_first_name', '')} {i.get('inventor_last_name', '')}".strip()
        inventors.append({
            "name": name,
            "location": i.get("inventor_city"),
        })

    # Parse CPC codes
    cpc_codes = []
    for c in patent.get("cpcs", []) or []:
        cpc_codes.append(c.get("cpc_group_id", ""))

    # Parse USPC codes
    uspc_codes = []
    for u in patent.get("uspcs", []) or []:
        uspc_codes.append(u.get("uspc_mainclass_id", ""))

    return {
        "patent_number": patent.get("patent_number"),
        "title": patent.get("patent_title"),
        "abstract": patent.get("patent_abstract"),
        "grant_date": grant_date,
        "expiry_date": expiry_date,
        "patent_type": patent.get("patent_type", "utility"),
        "assignees": assignees,
        "inventors": inventors,
        "claims_count": patent.get("patent_num_claims"),
        "cpc_codes": cpc_codes,
        "uspc_codes": uspc_codes,
        "cited_by_count": len(patent.get("citedby_patents") or []),
        "citations_count": len(patent.get("cited_patents") or []),
        "drug_name": drug_name,
    }


def insert_patent(conn, patent: Dict[str, Any]) -> bool:
    """Insert patent into database."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mol_bronze.uspto_patents (
                    patent_number, title, abstract, grant_date, expiry_date,
                    patent_type, assignees, inventors, claims_count,
                    cpc_codes, uspc_codes, cited_by_count, citations_count,
                    drug_name, raw_data
                ) VALUES (
                    %(patent_number)s, %(title)s, %(abstract)s, %(grant_date)s, %(expiry_date)s,
                    %(patent_type)s, %(assignees)s, %(inventors)s, %(claims_count)s,
                    %(cpc_codes)s, %(uspc_codes)s, %(cited_by_count)s, %(citations_count)s,
                    %(drug_name)s, %(raw_data)s
                )
                ON CONFLICT (patent_number) DO UPDATE SET
                    cited_by_count = EXCLUDED.cited_by_count,
                    source_updated_at = NOW()
            """, {
                **patent,
                "assignees": Json(patent.get("assignees", [])),
                "inventors": Json(patent.get("inventors", [])),
                "cpc_codes": Json(patent.get("cpc_codes", [])),
                "uspc_codes": Json(patent.get("uspc_codes", [])),
                "raw_data": Json(patent),
            })
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"Error inserting patent {patent.get('patent_number')}: {e}")
        conn.rollback()
        return False


async def load_for_drugs(conn, limit: int = None) -> int:
    """Load patents for drugs in the database."""
    total_inserted = 0

    # Get drug names from mol_silver.molecules
    drug_names = []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT canonical_name
                FROM mol_silver.molecules
                WHERE canonical_name IS NOT NULL
                ORDER BY canonical_name
                LIMIT 200
            """)
            drug_names = [row[0] for row in cur.fetchall()]
    except Exception:
        pass

    if not drug_names:
        # Fallback to common pharma search terms
        drug_names = ["aspirin", "ibuprofen", "metformin", "atorvastatin"]

    logger.info(f"Searching patents for {len(drug_names)} drugs")

    for drug_name in tqdm(drug_names, desc="Loading drug patents"):
        try:
            patents = await search_patents(drug_name, limit=20)
            for patent in patents:
                parsed = parse_patent(patent, drug_name)
                if insert_patent(conn, parsed):
                    total_inserted += 1

            if limit and total_inserted >= limit:
                break

            await asyncio.sleep(0.5)  # Rate limiting

        except Exception as e:
            logger.warning(f"Error loading patents for {drug_name}: {e}")
            continue

    return total_inserted


async def load_by_assignee(conn, assignee: str, limit: int = 500) -> int:
    """Load patents by assignee/company."""
    patents = await search_patents(assignee, limit=limit)

    total_inserted = 0
    for patent in tqdm(patents, desc=f"Loading {assignee} patents"):
        parsed = parse_patent(patent)
        if insert_patent(conn, parsed):
            total_inserted += 1

    return total_inserted


async def load_recent_pharma(conn, days: int = 365, limit: int = 1000) -> int:
    """Load recent pharmaceutical patents."""
    # Pharma-related search terms
    pharma_terms = [
        "pharmaceutical composition",
        "therapeutic compound",
        "drug formulation",
        "antibody",
        "treatment of cancer",
        "method of treating",
    ]

    total_inserted = 0
    per_term = limit // len(pharma_terms)

    for term in pharma_terms:
        patents = await search_patents(term, limit=per_term)
        for patent in tqdm(patents, desc=f"Loading '{term[:20]}...' patents"):
            parsed = parse_patent(patent)
            if insert_patent(conn, parsed):
                total_inserted += 1

        await asyncio.sleep(1)

    return total_inserted


async def main():
    parser = argparse.ArgumentParser(description="Load USPTO patent data")
    parser.add_argument("--mode", choices=["drugs", "assignee", "recent"],
                        default="drugs", help="Loading mode")
    parser.add_argument("--assignee", type=str, help="Assignee name for assignee mode")
    parser.add_argument("--days", type=int, default=365, help="Days back for recent mode")
    parser.add_argument("--limit", type=int, help="Limit records to load")
    args = parser.parse_args()

    if not PATENTSVIEW_API_KEY:
        logger.error("PATENTSVIEW_API_KEY environment variable required")
        logger.error("Register at: https://patentsview-support.atlassian.net/servicedesk/customer/portals")
        sys.exit(1)

    logger.info(f"Starting USPTO patents loader in {args.mode} mode")

    conn = psycopg2.connect(**DB_CONFIG)
    ensure_tables(conn)

    try:
        if args.mode == "drugs":
            total = await load_for_drugs(conn, args.limit)

        elif args.mode == "assignee":
            if not args.assignee:
                logger.error("--assignee required for assignee mode")
                sys.exit(1)
            total = await load_by_assignee(conn, args.assignee, args.limit or 500)

        elif args.mode == "recent":
            total = await load_recent_pharma(conn, args.days, args.limit or 1000)

        logger.info(f"USPTO patents loading complete. Inserted {total} patents.")

    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
