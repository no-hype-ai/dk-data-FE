#!/usr/bin/env python3
"""
OpenAlex Scientific Publications Loader

Loads scientific publication data from OpenAlex API into PostgreSQL.
Focuses on pharmaceutical and biomedical research.

Tables populated:
- bronze.openalex: Scientific works with citations, authors, concepts

Data Source: https://openalex.org/
API Docs: https://docs.openalex.org/

Usage:
    # Load publications for known drugs
    python -m dk_data.data.load_openalex --mode drugs

    # Load by concept (e.g., "pharmacology")
    python -m dk_data.data.load_openalex --mode concept --concept C89423630

    # Load recent publications
    python -m dk_data.data.load_openalex --mode recent --days 30

    # Test with limit
    python -m dk_data.data.load_openalex --limit 100

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    OPENALEX_EMAIL (optional, for polite pool)
"""

import os
import sys
import asyncio
from datetime import datetime, timedelta
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

# OpenAlex API
OPENALEX_API_URL = "https://api.openalex.org"
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")


def ensure_tables(conn) -> None:
    """Create OpenAlex tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bronze.openalex (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                openalex_id TEXT UNIQUE NOT NULL,
                doi TEXT,
                title TEXT,
                publication_date DATE,
                publication_year INTEGER,
                type TEXT,
                open_access BOOLEAN DEFAULT FALSE,
                cited_by_count INTEGER DEFAULT 0,
                authors JSONB DEFAULT '[]',
                institutions JSONB DEFAULT '[]',
                concepts JSONB DEFAULT '[]',
                topics JSONB DEFAULT '[]',
                journal_name TEXT,
                journal_issn TEXT,
                volume TEXT,
                issue TEXT,
                first_page TEXT,
                last_page TEXT,
                abstract_inverted_index JSONB,
                referenced_works JSONB DEFAULT '[]',
                related_works JSONB DEFAULT '[]',
                raw_data JSONB,
                source_updated_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_to_silver BOOLEAN DEFAULT FALSE
            );

            CREATE INDEX IF NOT EXISTS idx_openalex_doi ON bronze.openalex(doi);
            CREATE INDEX IF NOT EXISTS idx_openalex_year ON bronze.openalex(publication_year);
            CREATE INDEX IF NOT EXISTS idx_openalex_cited ON bronze.openalex(cited_by_count);
            CREATE INDEX IF NOT EXISTS idx_openalex_concepts ON bronze.openalex USING GIN(concepts);
            CREATE INDEX IF NOT EXISTS idx_openalex_authors ON bronze.openalex USING GIN(authors);
            CREATE INDEX IF NOT EXISTS idx_openalex_processed ON bronze.openalex(processed_to_silver);
        """)
        conn.commit()
    logger.info("OpenAlex tables ensured")


async def fetch_works(query_params: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch works from OpenAlex API."""
    works = []
    page = 1
    per_page = min(100, limit)

    headers = {}
    if OPENALEX_EMAIL:
        headers["mailto"] = OPENALEX_EMAIL

    async with aiohttp.ClientSession() as session:
        while len(works) < limit:
            params = {
                **query_params,
                "page": page,
                "per_page": per_page,
            }

            try:
                async with session.get(
                    f"{OPENALEX_API_URL}/works",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"OpenAlex API returned {response.status}")
                        break

                    data = await response.json()
                    results = data.get("results", [])

                    if not results:
                        break

                    works.extend(results)
                    page += 1

                    if len(results) < per_page:
                        break

                    await asyncio.sleep(0.1)  # Rate limiting

            except Exception as e:
                logger.error(f"OpenAlex API error: {e}")
                break

    return works[:limit]


def parse_work(work: Dict[str, Any]) -> Dict[str, Any]:
    """Parse OpenAlex work into database format."""
    # Parse authors
    authors = []
    for authorship in work.get("authorships", []):
        author = authorship.get("author", {})
        authors.append({
            "id": author.get("id"),
            "name": author.get("display_name"),
            "orcid": author.get("orcid"),
            "position": authorship.get("author_position"),
        })

    # Parse institutions
    institutions = []
    for authorship in work.get("authorships", []):
        for inst in authorship.get("institutions", []):
            if inst.get("id") not in [i.get("id") for i in institutions]:
                institutions.append({
                    "id": inst.get("id"),
                    "name": inst.get("display_name"),
                    "country": inst.get("country_code"),
                    "type": inst.get("type"),
                })

    # Parse concepts
    concepts = []
    for concept in work.get("concepts", []):
        concepts.append({
            "id": concept.get("id"),
            "name": concept.get("display_name"),
            "level": concept.get("level"),
            "score": concept.get("score"),
        })

    # Parse topics
    topics = []
    for topic in work.get("topics", []):
        topics.append({
            "id": topic.get("id"),
            "name": topic.get("display_name"),
            "score": topic.get("score"),
        })

    # Parse publication date
    pub_date = None
    if work.get("publication_date"):
        try:
            pub_date = datetime.strptime(work["publication_date"], "%Y-%m-%d").date()
        except Exception:
            pass

    # Parse journal info
    primary_location = work.get("primary_location", {}) or {}
    source = primary_location.get("source", {}) or {}

    return {
        "openalex_id": work.get("id"),
        "doi": work.get("doi"),
        "title": work.get("title"),
        "publication_date": pub_date,
        "publication_year": work.get("publication_year"),
        "type": work.get("type"),
        "open_access": work.get("open_access", {}).get("is_oa", False),
        "cited_by_count": work.get("cited_by_count", 0),
        "authors": authors,
        "institutions": institutions,
        "concepts": concepts,
        "topics": topics,
        "journal_name": source.get("display_name"),
        "journal_issn": source.get("issn_l"),
        "volume": work.get("biblio", {}).get("volume"),
        "issue": work.get("biblio", {}).get("issue"),
        "first_page": work.get("biblio", {}).get("first_page"),
        "last_page": work.get("biblio", {}).get("last_page"),
        "abstract_inverted_index": work.get("abstract_inverted_index"),
        "referenced_works": work.get("referenced_works", []),
        "related_works": work.get("related_works", []),
    }


def insert_work(conn, work: Dict[str, Any]) -> bool:
    """Insert work into database."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bronze.openalex (
                    openalex_id, doi, title, publication_date, publication_year,
                    type, open_access, cited_by_count, authors, institutions,
                    concepts, topics, journal_name, journal_issn, volume, issue,
                    first_page, last_page, abstract_inverted_index,
                    referenced_works, related_works, raw_data
                ) VALUES (
                    %(openalex_id)s, %(doi)s, %(title)s, %(publication_date)s, %(publication_year)s,
                    %(type)s, %(open_access)s, %(cited_by_count)s, %(authors)s, %(institutions)s,
                    %(concepts)s, %(topics)s, %(journal_name)s, %(journal_issn)s, %(volume)s, %(issue)s,
                    %(first_page)s, %(last_page)s, %(abstract_inverted_index)s,
                    %(referenced_works)s, %(related_works)s, %(raw_data)s
                )
                ON CONFLICT (openalex_id) DO UPDATE SET
                    cited_by_count = EXCLUDED.cited_by_count,
                    source_updated_at = NOW()
            """, {
                **work,
                "authors": Json(work.get("authors", [])),
                "institutions": Json(work.get("institutions", [])),
                "concepts": Json(work.get("concepts", [])),
                "topics": Json(work.get("topics", [])),
                "abstract_inverted_index": Json(work.get("abstract_inverted_index")),
                "referenced_works": Json(work.get("referenced_works", [])),
                "related_works": Json(work.get("related_works", [])),
                "raw_data": Json(work),
            })
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"Error inserting work {work.get('openalex_id')}: {e}")
        conn.rollback()
        return False


async def load_for_drugs(conn, limit: int = None) -> int:
    """Load publications for drugs in the database."""
    total_inserted = 0

    # Get drug names from silver.molecules if exists
    drug_names = []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT canonical_name
                FROM silver.molecules
                WHERE canonical_name IS NOT NULL
                ORDER BY canonical_name
                LIMIT 100
            """)
            drug_names = [row[0] for row in cur.fetchall()]
    except Exception:
        pass

    if not drug_names:
        # Fallback to common pharma search terms
        drug_names = ["aspirin", "ibuprofen", "metformin", "atorvastatin", "omeprazole"]

    logger.info(f"Searching publications for {len(drug_names)} drugs")

    for drug_name in tqdm(drug_names, desc="Loading drug publications"):
        try:
            works = await fetch_works(
                {"filter": f"title.search:{drug_name}"},
                limit=20
            )
            for work in works:
                parsed = parse_work(work)
                if insert_work(conn, parsed):
                    total_inserted += 1

            if limit and total_inserted >= limit:
                break

            await asyncio.sleep(0.2)

        except Exception as e:
            logger.warning(f"Error loading publications for {drug_name}: {e}")
            continue

    return total_inserted


async def load_by_concept(conn, concept_id: str, limit: int = 500) -> int:
    """Load publications by concept ID."""
    works = await fetch_works(
        {"filter": f"concepts.id:{concept_id}"},
        limit=limit
    )

    total_inserted = 0
    for work in tqdm(works, desc="Loading concept publications"):
        parsed = parse_work(work)
        if insert_work(conn, parsed):
            total_inserted += 1

    return total_inserted


async def load_recent(conn, days: int = 30, limit: int = 1000) -> int:
    """Load recent pharmaceutical publications."""
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Pharma concepts
    pharma_concepts = [
        "C89423630",  # Pharmacology
        "C71924100",  # Medicine
        "C126322002", # Clinical trial
    ]

    total_inserted = 0
    per_concept = limit // len(pharma_concepts)

    for concept in pharma_concepts:
        works = await fetch_works(
            {"filter": f"concepts.id:{concept},from_publication_date:{from_date}"},
            limit=per_concept
        )

        for work in tqdm(works, desc=f"Loading concept {concept}"):
            parsed = parse_work(work)
            if insert_work(conn, parsed):
                total_inserted += 1

        await asyncio.sleep(0.5)

    return total_inserted


async def main():
    parser = argparse.ArgumentParser(description="Load OpenAlex publication data")
    parser.add_argument("--mode", choices=["drugs", "concept", "recent"],
                        default="drugs", help="Loading mode")
    parser.add_argument("--concept", type=str, help="OpenAlex concept ID for concept mode")
    parser.add_argument("--days", type=int, default=30, help="Days back for recent mode")
    parser.add_argument("--limit", type=int, help="Limit records to load")
    args = parser.parse_args()

    logger.info(f"Starting OpenAlex loader in {args.mode} mode")

    conn = psycopg2.connect(**DB_CONFIG)
    ensure_tables(conn)

    try:
        if args.mode == "drugs":
            total = await load_for_drugs(conn, args.limit)

        elif args.mode == "concept":
            if not args.concept:
                logger.error("--concept required for concept mode")
                sys.exit(1)
            total = await load_by_concept(conn, args.concept, args.limit or 500)

        elif args.mode == "recent":
            total = await load_recent(conn, args.days, args.limit or 1000)

        logger.info(f"OpenAlex loading complete. Inserted {total} publications.")

    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
