#!/usr/bin/env python3
"""
Load ClinicalTrials.gov data into PostgreSQL.

Uses the ClinicalTrials.gov API v2 to fetch trial data.

Tables populated:
- bronze.clinicaltrials: Clinical trial records

Usage:
    python -m dk_data.data.load_clinicaltrials
    python -m dk_data.data.load_clinicaltrials --query "cancer drug"
    python -m dk_data.data.load_clinicaltrials --condition "diabetes"
    python -m dk_data.data.load_clinicaltrials --limit 1000

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import time
from typing import Optional, List, Dict, Any

import requests
import psycopg2
from psycopg2.extras import execute_values, Json
from loguru import logger
from tqdm import tqdm

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

CTGOV_API_BASE = "https://clinicaltrials.gov/api/v2"
RATE_LIMIT_DELAY = 0.1
PAGE_SIZE = 100


def ensure_tables(conn):
    """Ensure ClinicalTrials.gov tables exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.clinicaltrials (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            nct_id VARCHAR(20) UNIQUE NOT NULL,
            org_study_id VARCHAR(100),
            brief_title TEXT,
            official_title TEXT,
            acronym VARCHAR(50),
            overall_status VARCHAR(50),
            phase VARCHAR(50),
            study_type VARCHAR(50),
            enrollment INTEGER,
            enrollment_type VARCHAR(20),
            start_date DATE,
            completion_date DATE,
            primary_completion_date DATE,
            results_first_posted_date DATE,
            last_update_posted_date DATE,
            sponsor VARCHAR(500),
            lead_sponsor_class VARCHAR(50),
            collaborators TEXT[],
            conditions TEXT[],
            interventions JSONB,
            intervention_names TEXT[],
            intervention_types TEXT[],
            locations JSONB,
            location_countries TEXT[],
            keywords TEXT[],
            mesh_terms TEXT[],
            eligibility_criteria TEXT,
            gender VARCHAR(20),
            minimum_age VARCHAR(50),
            maximum_age VARCHAR(50),
            healthy_volunteers BOOLEAN,
            primary_outcomes JSONB,
            secondary_outcomes JSONB,
            arms JSONB,
            brief_summary TEXT,
            detailed_description TEXT,
            raw_json JSONB,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_ct_nct ON bronze.clinicaltrials(nct_id);
        CREATE INDEX IF NOT EXISTS idx_ct_status ON bronze.clinicaltrials(overall_status);
        CREATE INDEX IF NOT EXISTS idx_ct_phase ON bronze.clinicaltrials(phase);
        CREATE INDEX IF NOT EXISTS idx_ct_sponsor ON bronze.clinicaltrials(sponsor);
        CREATE INDEX IF NOT EXISTS idx_ct_conditions ON bronze.clinicaltrials USING GIN(conditions);
        CREATE INDEX IF NOT EXISTS idx_ct_interventions ON bronze.clinicaltrials USING GIN(intervention_names);
        CREATE INDEX IF NOT EXISTS idx_ct_processed ON bronze.clinicaltrials(processed_to_silver);
    """)

    conn.commit()
    logger.info("ClinicalTrials.gov tables ensured")


class ClinicalTrialsLoader:
    """Load data from ClinicalTrials.gov API v2."""

    def __init__(self, conn):
        self.conn = conn
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "DKDataPlatform/1.0"
        })

    def search_studies(
        self,
        query: str = None,
        condition: str = None,
        intervention: str = None,
        sponsor: str = None,
        status: List[str] = None,
        phase: List[str] = None,
        limit: int = None
    ) -> int:
        """
        Search and load clinical trials.

        Args:
            query: General search query
            condition: Condition/disease filter
            intervention: Intervention filter
            sponsor: Sponsor name filter
            status: List of status filters
            phase: List of phase filters
            limit: Maximum number of trials to load

        Returns:
            Number of trials loaded
        """
        cursor = self.conn.cursor()

        params = {
            "pageSize": PAGE_SIZE,
            "format": "json",
            "fields": "NCTId,OrgStudyId,BriefTitle,OfficialTitle,Acronym,OverallStatus,"
                      "Phase,StudyType,EnrollmentCount,EnrollmentType,StartDate,CompletionDate,"
                      "PrimaryCompletionDate,ResultsFirstPostDate,LastUpdatePostDate,"
                      "LeadSponsorName,LeadSponsorClass,CollaboratorName,Condition,InterventionName,"
                      "InterventionType,LocationCountry,Keyword,ConditionMesh,InterventionMesh,"
                      "EligibilityCriteria,Gender,MinimumAge,MaximumAge,HealthyVolunteers,"
                      "BriefSummary,DetailedDescription,ArmGroupLabel,ArmGroupDescription,"
                      "ArmGroupType,PrimaryOutcomeMeasure,SecondaryOutcomeMeasure"
        }

        if query:
            params["query.term"] = query
        if condition:
            params["query.cond"] = condition
        if intervention:
            params["query.intr"] = intervention
        if sponsor:
            params["query.spons"] = sponsor
        if status:
            params["filter.overallStatus"] = ",".join(status)
        if phase:
            params["filter.phase"] = ",".join(phase)

        total_loaded = 0
        next_page_token = None

        with tqdm(desc="Loading ClinicalTrials.gov", unit=" trials") as pbar:
            while True:
                if limit and total_loaded >= limit:
                    break

                if next_page_token:
                    params["pageToken"] = next_page_token

                try:
                    time.sleep(RATE_LIMIT_DELAY)
                    response = self.session.get(
                        f"{CTGOV_API_BASE}/studies",
                        params=params,
                        timeout=60
                    )
                    response.raise_for_status()
                    data = response.json()

                except requests.exceptions.RequestException as e:
                    logger.error(f"API error: {e}")
                    break

                studies = data.get("studies", [])
                if not studies:
                    break

                batch = []
                for study in studies:
                    if limit and total_loaded + len(batch) >= limit:
                        break

                    record = self._parse_study(study)
                    if record:
                        batch.append(record)

                if batch:
                    self._insert_batch(cursor, batch)
                    self.conn.commit()
                    total_loaded += len(batch)
                    pbar.update(len(batch))

                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break

        logger.info(f"Loaded {total_loaded} clinical trials")
        return total_loaded

    def _parse_study(self, study: Dict[str, Any]) -> Optional[tuple]:
        """Parse a study record from API response."""
        try:
            protocol = study.get("protocolSection", {})
            id_module = protocol.get("identificationModule", {})
            status_module = protocol.get("statusModule", {})
            design_module = protocol.get("designModule", {})
            sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
            conditions_module = protocol.get("conditionsModule", {})
            arms_module = protocol.get("armsInterventionsModule", {})
            eligibility_module = protocol.get("eligibilityModule", {})
            desc_module = protocol.get("descriptionModule", {})
            outcomes_module = protocol.get("outcomesModule", {})

            nct_id = id_module.get("nctId")
            if not nct_id:
                return None

            # Parse dates
            def parse_date(date_struct):
                if date_struct and isinstance(date_struct, dict):
                    return date_struct.get("date")
                return None

            # Parse interventions
            interventions = arms_module.get("interventions", [])
            intervention_names = [i.get("name") for i in interventions if i.get("name")]
            intervention_types = list(set([i.get("type") for i in interventions if i.get("type")]))

            # Parse sponsor
            lead_sponsor = sponsor_module.get("leadSponsor", {})
            collaborators = [c.get("name") for c in sponsor_module.get("collaborators", []) if c.get("name")]

            # Parse locations
            locations_module = protocol.get("contactsLocationsModule", {})
            locations = locations_module.get("locations", [])
            location_countries = list(set([loc.get("country") for loc in locations if loc.get("country")]))

            # Parse conditions
            conditions = conditions_module.get("conditions", [])
            keywords = conditions_module.get("keywords", [])

            # Parse outcomes
            primary_outcomes = outcomes_module.get("primaryOutcomes", [])
            secondary_outcomes = outcomes_module.get("secondaryOutcomes", [])

            # Parse arms
            arms = arms_module.get("armGroups", [])

            # Parse enrollment
            enrollment_info = design_module.get("enrollmentInfo", {})

            return (
                nct_id,
                id_module.get("orgStudyIdInfo", {}).get("id"),
                id_module.get("briefTitle"),
                id_module.get("officialTitle"),
                id_module.get("acronym"),
                status_module.get("overallStatus"),
                ",".join(design_module.get("phases", [])) or None,
                design_module.get("studyType"),
                enrollment_info.get("count"),
                enrollment_info.get("type"),
                parse_date(status_module.get("startDateStruct")),
                parse_date(status_module.get("completionDateStruct")),
                parse_date(status_module.get("primaryCompletionDateStruct")),
                parse_date(status_module.get("resultsFirstPostDateStruct")),
                parse_date(status_module.get("lastUpdatePostDateStruct")),
                lead_sponsor.get("name"),
                lead_sponsor.get("class"),
                collaborators or None,
                conditions or None,
                Json(interventions) if interventions else None,
                intervention_names or None,
                intervention_types or None,
                Json(locations) if locations else None,
                location_countries or None,
                keywords or None,
                None,  # mesh_terms - would need additional parsing
                eligibility_module.get("eligibilityCriteria"),
                eligibility_module.get("sex"),
                eligibility_module.get("minimumAge"),
                eligibility_module.get("maximumAge"),
                eligibility_module.get("healthyVolunteers") == "Yes",
                Json(primary_outcomes) if primary_outcomes else None,
                Json(secondary_outcomes) if secondary_outcomes else None,
                Json(arms) if arms else None,
                desc_module.get("briefSummary"),
                desc_module.get("detailedDescription"),
                Json(study),  # raw_json
            )

        except Exception as e:
            logger.debug(f"Error parsing study: {e}")
            return None

    def _insert_batch(self, cursor, records: List[tuple]):
        """Insert batch of records."""
        execute_values(
            cursor,
            """
            INSERT INTO bronze.clinicaltrials (
                nct_id, org_study_id, brief_title, official_title, acronym,
                overall_status, phase, study_type, enrollment, enrollment_type,
                start_date, completion_date, primary_completion_date,
                results_first_posted_date, last_update_posted_date,
                sponsor, lead_sponsor_class, collaborators, conditions,
                interventions, intervention_names, intervention_types,
                locations, location_countries, keywords, mesh_terms,
                eligibility_criteria, gender, minimum_age, maximum_age,
                healthy_volunteers, primary_outcomes, secondary_outcomes,
                arms, brief_summary, detailed_description, raw_json
            ) VALUES %s
            ON CONFLICT (nct_id) DO UPDATE SET
                overall_status = EXCLUDED.overall_status,
                enrollment = EXCLUDED.enrollment,
                last_update_posted_date = EXCLUDED.last_update_posted_date,
                raw_json = EXCLUDED.raw_json,
                source_updated_at = NOW()
            """,
            records
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load ClinicalTrials.gov data")
    parser.add_argument("--query", "-q", type=str, help="General search query")
    parser.add_argument("--condition", "-c", type=str, help="Condition/disease filter")
    parser.add_argument("--intervention", "-i", type=str, help="Intervention filter")
    parser.add_argument("--sponsor", "-s", type=str, help="Sponsor name filter")
    parser.add_argument("--status", nargs="+", help="Status filters")
    parser.add_argument("--phase", nargs="+", help="Phase filters")
    parser.add_argument("--limit", type=int, help="Maximum trials to load")

    args = parser.parse_args()

    logger.info("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    logger.info(f"Connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    ensure_tables(conn)

    try:
        loader = ClinicalTrialsLoader(conn)
        total = loader.search_studies(
            query=args.query,
            condition=args.condition,
            intervention=args.intervention,
            sponsor=args.sponsor,
            status=args.status,
            phase=args.phase,
            limit=args.limit
        )

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bronze.clinicaltrials")
        count = cursor.fetchone()[0]

        logger.info("\n=== Summary ===")
        logger.info(f"Loaded in this run: {total}")
        logger.info(f"Total in database: {count:,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
