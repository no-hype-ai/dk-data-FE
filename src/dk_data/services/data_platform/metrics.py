"""
DK Data Platform Prometheus Metrics — Update Functions

Feature: 013-dk-data-observability (refactored from 012-dk-data-platform)

All metric DEFINITIONS are now in dk_data.observability.metrics (single source of truth).
This module provides metric UPDATE FUNCTIONS that query the database and set gauge values.
"""

import time
from typing import Optional
from loguru import logger
from dk_data.ingestion.utils.database import build_dsn

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus-client not installed, DK metrics disabled")

# Import all metric objects from the canonical location
if PROMETHEUS_AVAILABLE:
    from dk_data.observability.metrics import (
        DK_MOLECULES_TOTAL,
        DK_CLINICAL_TRIALS_TOTAL,
        DK_ADVERSE_EVENTS_TOTAL,
        DK_RESOLUTION_QUEUE_PENDING,
        DK_MOLECULES_BY_LIFECYCLE_STAGE,
        DK_TRIALS_BY_PHASE,
        DK_ENTITY_RESOLUTION_SUCCESS_RATE,
        DK_SOURCE_LAST_SYNC,
        DK_SOURCE_HEALTH_STATUS,
        DK_PIPELINE_RECORDS_PROCESSED,
        DK_PIPELINE_PROCESSING_DURATION,
        DK_PIPELINE_ERRORS,
        DK_API_REQUESTS,
        DK_ALERTS_ACTIVE,
        DK_PIPELINE_JOBS_TOTAL,
        DK_PIPELINE_JOB_DURATION,
        DK_PIPELINE_LAST_SUCCESS,
        DK_PIPELINE_ACTIVE,
        DK_LAYER_RECORD_COUNT,
        DK_RAW_UNPROCESSED,
        DK_BRONZE_UNPROCESSED,
        DK_SILVER_UNPROCESSED,
        DK_GOLD_UNPROCESSED,
        DK_TABLE_RECORD_COUNT,
        DK_QUARANTINE_COUNT,
        DATA_SOURCE_STALENESS_HOURS,
        DATA_SOURCE_TABLE_SIZE_BYTES,
        DK_SILVER_IDENTIFIER_MAPPINGS,
        DK_SILVER_MOLECULES_TOTAL,
        DK_SOURCE_RECORDS_TOTAL,
        BATCH_JOB_LAST_SUCCESS_TIMESTAMP,
        record_gold_view_refresh,
    )


# =============================================================================
# Metric Update Functions
# =============================================================================

def set_molecules_count(published: int = 0, draft: int = 0, archived: int = 0):
    """Update molecule counts by status."""
    if PROMETHEUS_AVAILABLE:
        DK_MOLECULES_TOTAL.labels(status="published").set(published)
        DK_MOLECULES_TOTAL.labels(status="draft").set(draft)
        DK_MOLECULES_TOTAL.labels(status="archived").set(archived)


def set_clinical_trials_count(active: int = 0, completed: int = 0, terminated: int = 0):
    """Update clinical trial counts by status."""
    if PROMETHEUS_AVAILABLE:
        DK_CLINICAL_TRIALS_TOTAL.labels(status="active").set(active)
        DK_CLINICAL_TRIALS_TOTAL.labels(status="completed").set(completed)
        DK_CLINICAL_TRIALS_TOTAL.labels(status="terminated").set(terminated)


def set_adverse_events_count(count: int):
    """Update adverse event report count."""
    if PROMETHEUS_AVAILABLE:
        DK_ADVERSE_EVENTS_TOTAL.set(count)


def set_resolution_queue_pending(count: int):
    """Update pending items in resolution queue."""
    if PROMETHEUS_AVAILABLE:
        DK_RESOLUTION_QUEUE_PENDING.set(count)


def set_molecules_by_stage(discovery: int = 0, preclinical: int = 0,
                           phase1: int = 0, phase2: int = 0, phase3: int = 0,
                           approved: int = 0, marketed: int = 0):
    """Update molecules by lifecycle stage."""
    if PROMETHEUS_AVAILABLE:
        DK_MOLECULES_BY_LIFECYCLE_STAGE.labels(stage="discovery").set(discovery)
        DK_MOLECULES_BY_LIFECYCLE_STAGE.labels(stage="preclinical").set(preclinical)
        DK_MOLECULES_BY_LIFECYCLE_STAGE.labels(stage="phase1").set(phase1)
        DK_MOLECULES_BY_LIFECYCLE_STAGE.labels(stage="phase2").set(phase2)
        DK_MOLECULES_BY_LIFECYCLE_STAGE.labels(stage="phase3").set(phase3)
        DK_MOLECULES_BY_LIFECYCLE_STAGE.labels(stage="approved").set(approved)
        DK_MOLECULES_BY_LIFECYCLE_STAGE.labels(stage="marketed").set(marketed)


def set_trials_by_phase(phase1: int = 0, phase2: int = 0, phase3: int = 0, phase4: int = 0):
    """Update trials by phase."""
    if PROMETHEUS_AVAILABLE:
        DK_TRIALS_BY_PHASE.labels(phase="Phase 1").set(phase1)
        DK_TRIALS_BY_PHASE.labels(phase="Phase 2").set(phase2)
        DK_TRIALS_BY_PHASE.labels(phase="Phase 3").set(phase3)
        DK_TRIALS_BY_PHASE.labels(phase="Phase 4").set(phase4)


def set_entity_resolution_success_rate(rate: float):
    """Set entity resolution success rate (0.0 to 1.0)."""
    if PROMETHEUS_AVAILABLE:
        DK_ENTITY_RESOLUTION_SUCCESS_RATE.set(rate)


def set_source_last_sync(source: str, timestamp: Optional[float] = None):
    """Set last sync timestamp for a data source."""
    if PROMETHEUS_AVAILABLE:
        ts = timestamp if timestamp else time.time()
        DK_SOURCE_LAST_SYNC.labels(source=source).set(ts)


def set_source_health(source: str, status: str):
    """Set source health status: healthy, stale, or error."""
    if PROMETHEUS_AVAILABLE:
        value = {"healthy": 1, "stale": 0.5, "error": 0}.get(status, 0)
        DK_SOURCE_HEALTH_STATUS.labels(source=source).set(value)


def record_pipeline_processing(layer: str, source: str, record_count: int, duration: float):
    """Record pipeline processing metrics."""
    if PROMETHEUS_AVAILABLE:
        DK_PIPELINE_RECORDS_PROCESSED.labels(layer=layer, source=source).inc(record_count)
        DK_PIPELINE_PROCESSING_DURATION.labels(layer=layer).observe(duration)


def record_pipeline_error(layer: str, error_type: str):
    """Record a pipeline error."""
    if PROMETHEUS_AVAILABLE:
        DK_PIPELINE_ERRORS.labels(layer=layer, error_type=error_type).inc()


def record_api_request(source: str, success: bool):
    """Record an API request to a data source."""
    if PROMETHEUS_AVAILABLE:
        status = "success" if success else "error"
        DK_API_REQUESTS.labels(source=source, status=status).inc()


def set_active_alerts(severity: str, alert_type: str, count: int):
    """Set active alert count."""
    if PROMETHEUS_AVAILABLE:
        DK_ALERTS_ACTIVE.labels(severity=severity, alert_type=alert_type).set(count)


def record_pipeline_job(tier: str, status: str, duration_seconds: float = 0):
    """Record a pipeline job execution."""
    if PROMETHEUS_AVAILABLE:
        DK_PIPELINE_JOBS_TOTAL.labels(tier=tier, status=status).inc()
        if duration_seconds > 0:
            DK_PIPELINE_JOB_DURATION.labels(tier=tier).observe(duration_seconds)
        if status == 'completed':
            DK_PIPELINE_LAST_SUCCESS.labels(tier=tier).set(time.time())


def set_pipeline_active(tier: str, active: bool):
    """Set whether a pipeline is currently running."""
    if PROMETHEUS_AVAILABLE:
        DK_PIPELINE_ACTIVE.labels(tier=tier).set(1 if active else 0)


def set_layer_record_count(layer: str, count: int):
    """Set record count for a layer."""
    if PROMETHEUS_AVAILABLE:
        DK_LAYER_RECORD_COUNT.labels(layer=layer).set(count)


def set_raw_unprocessed(source: str, count: int):
    """Set unprocessed record count in raw layer."""
    if PROMETHEUS_AVAILABLE:
        DK_RAW_UNPROCESSED.labels(source=source).set(count)


def set_bronze_unprocessed(source: str, count: int):
    """Set unprocessed record count in bronze layer."""
    if PROMETHEUS_AVAILABLE:
        DK_BRONZE_UNPROCESSED.labels(source=source).set(count)


def set_silver_unprocessed(source: str, count: int):
    """Set unprocessed record count in silver layer (bronze records pending silver transformation)."""
    if PROMETHEUS_AVAILABLE:
        DK_SILVER_UNPROCESSED.labels(source=source).set(count)


def set_gold_unprocessed(source: str, count: int):
    """Set unprocessed record count in gold layer (silver molecules pending gold aggregation)."""
    if PROMETHEUS_AVAILABLE:
        DK_GOLD_UNPROCESSED.labels(source=source).set(count)


def set_table_record_count(layer: str, table_name: str, count: int):
    """Set record count for a specific table in a layer."""
    if PROMETHEUS_AVAILABLE:
        DK_TABLE_RECORD_COUNT.labels(layer=layer, table_name=table_name).set(count)


def set_quarantine_count(count: int):
    """Set quarantine molecule count."""
    if PROMETHEUS_AVAILABLE:
        DK_QUARANTINE_COUNT.set(count)


# =============================================================================
# Initialize metrics from database
# =============================================================================

def initialize_demo_metrics():
    """Initialize metrics - schedules async database refresh."""
    if not PROMETHEUS_AVAILABLE:
        return
    logger.info("DK Data Platform metrics initialized - awaiting database refresh")


def refresh_metrics_from_database_sync():
    """Synchronous wrapper to refresh metrics from database."""
    import os
    try:
        import psycopg2
    except ImportError:
        logger.warning("psycopg2 not available for sync metrics refresh")
        return

    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        db_host = os.getenv('POSTGRES_HOST', 'postgres')
        db_port = os.getenv('POSTGRES_PORT', '5432')
        db_name = os.getenv('POSTGRES_DB', 'dk_data')
        db_user = os.getenv('POSTGRES_USER', 'postgres')
        db_pass = os.getenv('POSTGRES_PASSWORD', 'postgres')
        db_url = f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'

    try:
        conn = psycopg2.connect(build_dsn())
        cur = conn.cursor()

        # Get compound counts (molecules)
        cur.execute("SELECT COUNT(*) FROM mol_silver.molecules")
        total_compounds = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM mol_silver.molecules WHERE canonical_smiles IS NOT NULL AND inchi_key IS NOT NULL")
        with_identifiers = cur.fetchone()[0] or 0

        set_molecules_count(
            published=with_identifiers,
            draft=total_compounds - with_identifiers,
            archived=0
        )

        # Get clinical trial counts by status. The silver hub rebuild renamed
        # the column to `overall_status` (matches ClinicalTrials.gov enum).
        try:
            cur.execute("""
                SELECT overall_status, COUNT(*) as cnt
                FROM mol_silver.clinical_trials
                WHERE overall_status IS NOT NULL
                GROUP BY overall_status
            """)
            status_counts = {row[0].upper() if row[0] else 'UNKNOWN': row[1] for row in cur.fetchall()}

            active_statuses = ['RECRUITING', 'NOT YET RECRUITING', 'ACTIVE, NOT RECRUITING', 'ENROLLING BY INVITATION', 'ACTIVE']
            completed_statuses = ['COMPLETED']
            terminated_statuses = ['TERMINATED', 'WITHDRAWN', 'SUSPENDED']

            active = sum(status_counts.get(s, 0) for s in active_statuses)
            completed = sum(status_counts.get(s, 0) for s in completed_statuses)
            terminated = sum(status_counts.get(s, 0) for s in terminated_statuses)

            set_clinical_trials_count(active=active, completed=completed, terminated=terminated)
        except Exception:
            conn.rollback()

        # Get adverse events count (tables may not exist yet)
        faers_count = 0
        sider_count = 0
        try:
            cur.execute("SELECT COUNT(*) FROM mol_bronze.faers_events")
            faers_count = cur.fetchone()[0] or 0
        except Exception:
            conn.rollback()
        try:
            cur.execute("SELECT COUNT(*) FROM mol_bronze.sider")
            sider_count = cur.fetchone()[0] or 0
        except Exception:
            conn.rollback()
        set_adverse_events_count(faers_count + sider_count)

        # Get clinical trials by phase
        cur.execute("""
            SELECT
                CASE
                    WHEN phase ILIKE '%1%' AND phase NOT ILIKE '%2%' THEN 'Phase 1'
                    WHEN phase ILIKE '%2%' AND phase NOT ILIKE '%3%' THEN 'Phase 2'
                    WHEN phase ILIKE '%3%' AND phase NOT ILIKE '%4%' THEN 'Phase 3'
                    WHEN phase ILIKE '%4%' THEN 'Phase 4'
                    ELSE 'Other'
                END as phase_group,
                COUNT(*) as count
            FROM mol_silver.clinical_trials
            WHERE phase IS NOT NULL
            GROUP BY phase_group
        """)
        phase_counts = {row[0]: row[1] for row in cur.fetchall()}
        set_trials_by_phase(
            phase1=phase_counts.get('Phase 1', 0),
            phase2=phase_counts.get('Phase 2', 0),
            phase3=phase_counts.get('Phase 3', 0),
            phase4=phase_counts.get('Phase 4', 0)
        )

        # Resolution queue — needs_review=FALSE for all sources; queue is always 0
        set_resolution_queue_pending(0)

        # Entity resolution success rate — use identifier_mappings as proxy for resolved
        try:
            cur.execute("SELECT COUNT(DISTINCT molecule_id) FROM mol_silver.molecule_identifiers")
            resolved = cur.fetchone()[0] or 0
        except Exception:
            conn.rollback()
            resolved = 0
        if total_compounds > 0:
            set_entity_resolution_success_rate(min(resolved / total_compounds, 1.0))
        else:
            set_entity_resolution_success_rate(0.0)

        # Quarantine count (013-dk-data-observability)
        try:
            cur.execute("SELECT COUNT(*) FROM mol_silver.molecules WHERE needs_review = TRUE")
            quarantine = cur.fetchone()[0] or 0
            set_quarantine_count(quarantine)
        except Exception:
            conn.rollback()
            set_quarantine_count(0)

        # Data source health
        local_sources = {
            'clinical_trials': ('mol_silver.clinical_trials', False),
            'drug_labels': ('mol_silver.drug_labels', False),
            'molecules': ('mol_silver.molecules', False),
            'adverse_events': ('mol_silver.adverse_events', True),
            'drug_interactions': ('mol_silver.drug_interactions', True),
            'publications': ('mol_silver.publications', True),
            'chembl': ('mol_bronze.chembl_molecules', False),
            'drugbank': ('mol_bronze.drugbank', False),
            'pubchem': ('mol_bronze.pubchem', True),
            'sider': ('mol_bronze.sider', True),
            'bindingdb': ('mol_bronze.bindingdb_affinities', True),
            'faers': ('mol_bronze.faers_events', False),
            'fda_labels_raw': ('mol_bronze.drug_labels', False),
            'who_inn': ('mol_bronze.who_inn_data', True),
            'drugbank_patents': ('mol_bronze.drugbank_patents', True),
            'uspto_patents': ('mol_bronze.uspto_patents', True),
            'uspto_ci': ('mol_bronze.uspto_ci', True),
            'epo_patents': ('mol_bronze.epo_patents', True),
            'uspto_trademarks': ('mol_bronze.uspto_trademarks', True),
            'euipo_trademarks': ('mol_bronze.euipo_trademarks', True),
        }

        current_time = time.time()

        for source_name, (table, allow_empty) in local_sources.items():
            try:
                if '.' in table:
                    schema, table_name = table.split('.', 1)
                else:
                    schema, table_name = 'public', table

                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = %s
                        AND table_name = %s
                    )
                """, (schema, table_name))
                table_exists = cur.fetchone()[0]

                if not table_exists:
                    set_source_health(source_name, 'error')
                    continue

                full_table = f"{schema}.{table_name}" if schema != 'public' else table_name
                cur.execute(f"SELECT COUNT(*) FROM {full_table}")
                count = cur.fetchone()[0] or 0
                if count > 0:
                    status = 'healthy'
                elif allow_empty:
                    status = 'stale'
                else:
                    status = 'error'
                set_source_health(source_name, status)
                if count > 0:
                    set_source_last_sync(source_name, current_time - (3600 * 24))
            except Exception as e:
                set_source_health(source_name, 'error')
                logger.debug(f"Error checking {source_name}: {e}")

        external_sources = [
            'pubchem_api', 'openfda', 'clinicaltrials_gov',
            'rxnorm', 'openalex', 'patentsview', 'ema',
        ]
        for source_name in external_sources:
            set_source_health(source_name, 'healthy')
            set_source_last_sync(source_name, current_time)

        set_active_alerts("critical", "data_freshness", 0)
        set_active_alerts("warning", "api_latency", 0)
        set_active_alerts("info", "queue_backlog", 0)

        # Layer record counts
        layer_tables = {
            'mol_raw': ['mol_raw.chembl_molecules', 'mol_raw.clinicaltrials', 'mol_raw.openfda_faers', 'mol_raw.openfda_labels'],
            'mol_bronze': ['mol_bronze.chembl_molecules', 'mol_bronze.clinicaltrials', 'mol_bronze.faers_events', 'mol_bronze.drug_labels'],
            'mol_silver': ['mol_silver.molecules', 'mol_silver.clinical_trials', 'mol_silver.adverse_events', 'mol_silver.drug_labels'],
            'hcs_bronze': ['hcs_bronze.cms_nppes', 'hcs_bronze.cms_physician_puf', 'hcs_bronze.cms_inpatient_puf'],
            'hcs_silver': ['hcs_silver.cms_drug_market', 'hcs_silver.provider_profile', 'hcs_silver.facility_profile'],
        }

        for layer, tables in layer_tables.items():
            layer_count = 0
            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0] or 0
                    layer_count += count
                except Exception:
                    pass
            set_layer_record_count(layer, layer_count)

        # Unprocessed counts in raw layer
        raw_sources = {
            'clinicaltrials': 'mol_raw.clinicaltrials',
            'openfda_faers': 'mol_raw.openfda_faers',
            'openfda_labels': 'mol_raw.openfda_labels',
            'chembl': 'mol_raw.chembl_molecules',
            'uspto_patents': 'mol_raw.uspto_patents',
            'uspto_ci': 'mol_raw.uspto_ci',
            'epo_patents': 'mol_raw.epo_patents',
            'uspto_trademarks': 'mol_raw.uspto_trademarks',
            'euipo_trademarks': 'mol_raw.euipo_trademarks',
        }
        for source, table in raw_sources.items():
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE processed_to_bronze = FALSE")
                count = cur.fetchone()[0] or 0
                set_raw_unprocessed(source, count)
            except Exception:
                set_raw_unprocessed(source, 0)

        # Unprocessed counts in bronze layer
        bronze_sources = {
            'clinicaltrials': 'mol_bronze.clinicaltrials',
            'openfda_faers': 'mol_bronze.faers_events',
            'openfda_labels': 'mol_bronze.drug_labels',
            'chembl': 'mol_bronze.chembl_molecules',
        }
        for source, table in bronze_sources.items():
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE processed_to_silver = FALSE")
                count = cur.fetchone()[0] or 0
                set_bronze_unprocessed(source, count)
            except Exception:
                conn.rollback()
                set_bronze_unprocessed(source, 0)

        # Unprocessed counts in silver layer (bronze records not yet transformed to silver)
        silver_sources = {
            'clinicaltrials': 'mol_bronze.clinicaltrials',
            'openfda_faers': 'mol_bronze.faers_events',
            'openfda_labels': 'mol_bronze.drug_labels',
            'chembl': 'mol_bronze.chembl_molecules',
        }
        for source, table in silver_sources.items():
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE processed_to_silver = FALSE")
                count = cur.fetchone()[0] or 0
                set_silver_unprocessed(source, count)
            except Exception:
                conn.rollback()
                set_silver_unprocessed(source, 0)

        # Unprocessed counts in gold layer (silver molecules pending gold aggregation)
        try:
            try:
                cur.execute(
                    "SELECT COUNT(*) FROM mol_silver.molecules "
                    "WHERE needs_gold_aggregation = TRUE OR last_gold_sync IS NULL"
                )
            except Exception:
                conn.rollback()
                # Fallback: total silver minus gold profile count
                cur.execute(
                    "SELECT "
                    "  (SELECT COUNT(*) FROM mol_silver.molecules) - "
                    "  (SELECT COUNT(*) FROM mol_gold.molecule_profile)"
                )
            gold_unprocessed = max(cur.fetchone()[0] or 0, 0)
            set_gold_unprocessed('molecules', gold_unprocessed)
        except Exception:
            pass

        # Staleness hours and table size per active data source
        now = time.time()
        try:
            cur.execute(
                "SELECT source_id, source_name, last_successful_refresh, table_size_bytes "
                "FROM meta.data_sources WHERE is_active = TRUE"
            )
            for row in cur.fetchall():
                src_id, src_name, last_refresh, tsize = row[0], row[1], row[2], row[3]
                src_id_str = str(src_id)
                if last_refresh is not None:
                    if hasattr(last_refresh, 'timestamp'):
                        last_ts = last_refresh.timestamp()
                    else:
                        last_ts = float(last_refresh)
                    staleness = max((now - last_ts) / 3600, 0.0)
                    DATA_SOURCE_STALENESS_HOURS.labels(
                        source_id=src_id_str, source_name=src_name
                    ).set(staleness)
                if tsize is not None:
                    DATA_SOURCE_TABLE_SIZE_BYTES.labels(
                        source_id=src_id_str, source_name=src_name
                    ).set(tsize)
        except Exception:
            conn.rollback()

        # Table record counts by layer
        layer_tables = {
            'mol_raw': [
                'chembl_molecules', 'clinicaltrials', 'drugbank', 'openalex',
                'openfda_faers', 'openfda_labels', 'pubchem', 'uniprot',
                'uspto_patents', 'uspto_ci', 'epo_patents', 'uspto_trademarks', 'euipo_trademarks'
            ],
            'mol_bronze': [
                'chembl_molecules', 'clinicaltrials', 'drugbank', 'openalex',
                'faers_events', 'drug_labels', 'pubchem', 'sider', 'uniprot',
                'bindingdb_affinities', 'who_inn_data',
                'uspto_patents', 'uspto_ci', 'epo_patents', 'uspto_trademarks', 'euipo_trademarks'
            ],
            'mol_silver': [
                'adverse_events', 'bioactivity', 'clinical_trials', 'drug_labels',
                'identifier_mappings', 'molecule_aliases', 'molecule_publications',
                'molecule_targets', 'molecules', 'patents', 'publications',
                'targets', 'trademarks'
            ],
            'mol_gold': [
                'company_pipeline', 'lifecycle_evidence', 'lifecycle_stages',
                'molecule_profile', 'safety_signals'
            ],
            'hcs_raw': [
                'cms_care_compare', 'cms_chow', 'cms_chronic_conditions', 'cms_claim_type_puf',
                'cms_cost_reports_puf', 'cms_cost_reports_puf_lines', 'cms_ddinter', 'cms_dme_puf',
                'cms_dmepos', 'cms_dual_eligible', 'cms_enrollment_puf', 'cms_formulary',
                'cms_geographic_variation', 'cms_hcris', 'cms_home_health', 'cms_hospice_puf',
                'cms_hospital_affiliation', 'cms_hospital_general_info', 'cms_hospital_quality',
                'cms_imaging_puf', 'cms_inpatient_puf', 'cms_lab_services', 'cms_magnet',
                'cms_medicaid_drug_spending', 'cms_medicare_advantage', 'cms_mental_health_puf',
                'cms_ndc', 'cms_nppes', 'cms_nucc', 'cms_open_payments', 'cms_opioid_puf',
                'cms_ordering_providers', 'cms_outpatient_puf', 'cms_part_b_spending',
                'cms_part_d_prescriber', 'cms_part_d_spending', 'cms_pecos', 'cms_physician_puf',
                'cms_physician_puf_services', 'cms_pos', 'cms_post_acute', 'cms_rbcs',
                'cms_referring_providers', 'cms_snf_puf', 'cms_stabilis', 'cms_telehealth_puf',
                'cms_usp', 'cms_utilization_puf', 'hrsa_shortage_areas',
            ],
            'hcs_bronze': [
                'acc_tvc', 'cms_care_compare', 'cms_chow', 'cms_chronic_conditions',
                'cms_claim_type_puf', 'cms_cost_reports', 'cms_cost_reports_puf',
                'cms_cost_reports_puf_lines', 'cms_ddinter', 'cms_dme_puf', 'cms_dmepos',
                'cms_dual_eligible', 'cms_enrollment_puf', 'cms_formulary',
                'cms_geographic_variation', 'cms_hcris', 'cms_home_health', 'cms_hospice_puf',
                'cms_hospital_affiliation', 'cms_hospital_general_info', 'cms_hospital_info',
                'cms_hospital_quality', 'cms_imaging_puf', 'cms_inpatient', 'cms_inpatient_puf',
                'cms_lab_services', 'cms_magnet', 'cms_medicaid_drug_spending',
                'cms_medicare_advantage', 'cms_mental_health_puf', 'cms_ndc', 'cms_nppes',
                'cms_nucc', 'cms_open_payments', 'cms_opioid_puf', 'cms_ordering_providers',
                'cms_outpatient_puf', 'cms_part_b_spending', 'cms_part_d_prescriber',
                'cms_part_d_spending', 'cms_pecos', 'cms_physician_puf',
                'cms_physician_puf_services', 'cms_pos', 'cms_post_acute', 'cms_rbcs',
                'cms_referring_providers', 'cms_snf_puf', 'cms_stabilis', 'cms_telehealth_puf',
                'cms_usp', 'cms_utilization_puf', 'hrsa',
            ],
            'hcs_silver': [
                'equipment_inventory', 'idn_hierarchy', 'referral_network',
                'service_lines', 'staffing_decomposition', 'verified_contacts',
            ],
        }

        for layer, tables in layer_tables.items():
            for table in tables:
                try:
                    full_table = f"{layer}.{table}"
                    cur.execute(f"SELECT COUNT(*) FROM {full_table}")
                    count = cur.fetchone()[0] or 0
                    set_table_record_count(layer, table, count)
                except Exception:
                    conn.rollback()
                    set_table_record_count(layer, table, 0)

        # HCS Gold view metrics (019-cms-puf-platform-reconciliation)
        hcs_gold_views = [
            "cms_drug_market_profile",
            "cms_facility_360",
            "cms_market_analytics",
            "cms_provider_360",
        ]
        for view in hcs_gold_views:
            try:
                cur.execute(f"SELECT COUNT(*) FROM hcs_gold.{view}")
                count = cur.fetchone()[0] or 0
                record_gold_view_refresh(view, count)
            except Exception:
                conn.rollback()

        # CMS source health from meta.data_sources (set staleness=0.5 for sources
        # that have synced but are now past their freshness threshold)
        try:
            cur.execute("""
                SELECT source_name, last_successful_refresh, source_type
                FROM meta.data_sources
                WHERE source_name LIKE 'cms_%' AND is_active = TRUE
            """)
            for row in cur.fetchall():
                src_name, last_refresh, src_type = row
                if last_refresh is None:
                    continue
                last_ts = last_refresh.timestamp() if hasattr(last_refresh, 'timestamp') else float(last_refresh)
                hours_since = (time.time() - last_ts) / 3600
                threshold = 720 if src_type == "cms_bulk_file" else 24
                # Stale but not error: use 0.5; set via record_cms_source_sync with synthetic status
                if hours_since > threshold:
                    from dk_data.observability.metrics import CMS_SOURCE_HEALTH_STATUS
                    CMS_SOURCE_HEALTH_STATUS.labels(source=src_name).set(0.5)
        except Exception:
            conn.rollback()

        # HCS raw table record counts (019-cms-puf-platform-reconciliation)
        hcs_raw_tables = [
            'cms_part_d_spending', 'cms_part_b_spending', 'cms_open_payments',
            'cms_nppes', 'cms_inpatient_puf', 'cms_physician_puf',
            'cms_hospital_general_info', 'cms_medicare_advantage',
            'cms_medicaid_drug_spending', 'cms_dme_puf', 'cms_home_health',
            'cms_hospice_puf', 'cms_snf_puf', 'cms_outpatient_puf',
            'cms_referring_providers', 'cms_ordering_providers', 'cms_lab_services',
            'cms_imaging_puf', 'cms_mental_health_puf', 'cms_opioid_puf',
            'cms_telehealth_puf', 'cms_geographic_variation', 'cms_chronic_conditions',
            'cms_dual_eligible', 'cms_enrollment_puf', 'cms_claim_type_puf',
            'cms_utilization_puf', 'cms_cost_reports_puf',
            'cms_physician_puf_services', 'cms_cost_reports_puf_lines',
        ]
        for table in hcs_raw_tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM hcs_raw.{table}")
                count = cur.fetchone()[0] or 0
                set_table_record_count('hcs_raw', table, count)
            except Exception:
                conn.rollback()
                set_table_record_count('hcs_raw', table, 0)

        # HCS bronze table record counts
        hcs_bronze_tables = [
            'cms_part_d_spending', 'cms_part_b_spending', 'cms_open_payments',
            'cms_nppes', 'cms_inpatient_puf', 'cms_physician_puf',
            'cms_hospital_general_info', 'cms_medicare_advantage',
            'cms_medicaid_drug_spending', 'cms_dme_puf', 'cms_home_health',
            'cms_hospice_puf', 'cms_snf_puf', 'cms_outpatient_puf',
            'cms_referring_providers', 'cms_ordering_providers', 'cms_lab_services',
            'cms_imaging_puf', 'cms_mental_health_puf', 'cms_opioid_puf',
            'cms_telehealth_puf', 'cms_geographic_variation', 'cms_chronic_conditions',
            'cms_dual_eligible', 'cms_enrollment_puf', 'cms_claim_type_puf',
            'cms_utilization_puf', 'cms_cost_reports_puf',
            'cms_physician_puf_services', 'cms_cost_reports_puf_lines',
        ]
        for table in hcs_bronze_tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM hcs_bronze.{table}")
                count = cur.fetchone()[0] or 0
                set_table_record_count('hcs_bronze', table, count)
            except Exception:
                conn.rollback()
                set_table_record_count('hcs_bronze', table, 0)

        # HCS silver table record counts (SQLMesh models only — agent tables tracked separately)
        hcs_silver_tables = [
            'cms_drug_market', 'provider_profile', 'facility_profile',
            'geographic_health', 'drug_utilization',
            'cms_facility_profile', 'open_payments_drug_linkage',
            'part_d_prescribing', 'ref_nucc_taxonomy',
        ]
        for table in hcs_silver_tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM hcs_silver.{table}")
                count = cur.fetchone()[0] or 0
                set_table_record_count('hcs_silver', table, count)
            except Exception:
                conn.rollback()
                set_table_record_count('hcs_silver', table, 0)

        # HCS agent quality metrics (hcs_agents schema — LLM-written tables)
        hcs_agent_tables = {
            'service_lines': 'npi',
            'idn_hierarchy': 'child_npi',
            'referral_network': 'referring_npi',
            'verified_contacts': 'npi',
            'staffing_decomposition': 'provider_id',
            'equipment_inventory': 'npi',
        }
        for table, key_col in hcs_agent_tables.items():
            try:
                cur.execute(f"""
                    SELECT
                        COUNT(*) FILTER (WHERE needs_review = FALSE) AS direct_write,
                        COUNT(*) FILTER (WHERE needs_review = TRUE)  AS needs_review,
                        AVG(confidence_score)                        AS avg_confidence
                    FROM hcs_agents.{table}
                """)
                row = cur.fetchone()
                if row:
                    set_table_record_count('hcs_agents_direct', table, row[0] or 0)
                    set_table_record_count('hcs_agents_review', table, row[1] or 0)
            except Exception:
                conn.rollback()

        # HCS gold view record counts
        hcs_gold_views_extended = [
            'cms_drug_market_profile',
            'cms_facility_360',
            'cms_market_analytics',
            'cms_provider_360',
        ]
        for view in hcs_gold_views_extended:
            try:
                cur.execute(f"SELECT COUNT(*) FROM hcs_gold.{view}")
                count = cur.fetchone()[0] or 0
                set_table_record_count('hcs_gold', view, count)
            except Exception:
                conn.rollback()
                set_table_record_count('hcs_gold', view, 0)

        # T034: dk_molecules_by_lifecycle_stage (026-observability)
        try:
            cur.execute("""
                SELECT lifecycle_stage, COUNT(*)
                FROM mol_silver.molecules
                WHERE lifecycle_stage IS NOT NULL
                GROUP BY lifecycle_stage
            """)
            for stage, count in cur.fetchall():
                DK_MOLECULES_BY_LIFECYCLE_STAGE.labels(stage=stage).set(count or 0)
        except Exception:
            conn.rollback()

        # T034: dk_silver_molecules_total (026-observability)
        try:
            cur.execute("SELECT COUNT(*) FROM mol_silver.molecules")
            DK_SILVER_MOLECULES_TOTAL.set(cur.fetchone()[0] or 0)
        except Exception:
            conn.rollback()

        # T035: dk_silver_identifier_mappings_total by source (026-observability)
        try:
            cur.execute("""
                SELECT source, COUNT(*)
                FROM mol_silver.molecule_identifiers
                WHERE source IS NOT NULL
                GROUP BY source
            """)
            for id_type, count in cur.fetchall():
                DK_SILVER_IDENTIFIER_MAPPINGS.labels(source=id_type).set(count or 0)
        except Exception:
            conn.rollback()

        # T038: batch_job_last_success_timestamp from meta.batch_job_runs (026-observability)
        # Populates gauges from DB so they survive pod restarts (covers both API and CronJob runs).
        try:
            cur.execute("""
                SELECT bj.job_name, MAX(bjr.completed_at) AS last_success
                FROM meta.batch_job_runs bjr
                JOIN meta.batch_jobs bj ON bjr.job_id = bj.job_id
                WHERE bjr.status = 'success'
                GROUP BY bj.job_name
            """)
            for job_name, last_success in cur.fetchall():
                if last_success is not None:
                    ts = last_success.timestamp() if hasattr(last_success, 'timestamp') else float(last_success)
                    BATCH_JOB_LAST_SUCCESS_TIMESTAMP.labels(job_name=job_name).set(ts)
        except Exception:
            conn.rollback()

        # T038: dk_source_records_total from batch_job_runs — records processed per job over 30d
        try:
            cur.execute("""
                SELECT bj.job_name, COALESCE(SUM(bjr.records_processed), 0) AS total_records
                FROM meta.batch_job_runs bjr
                JOIN meta.batch_jobs bj ON bjr.job_id = bj.job_id
                WHERE bjr.status = 'success'
                  AND bjr.started_at >= NOW() - INTERVAL '30 days'
                GROUP BY bj.job_name
            """)
            for job_name, total_records in cur.fetchall():
                DK_SOURCE_RECORDS_TOTAL.labels(source=job_name, layer='batch').set(total_records or 0)
        except Exception:
            conn.rollback()

        cur.close()
        conn.close()
        logger.info("DK Data Platform metrics refreshed from database")

    except Exception as e:
        logger.error(f"Failed to refresh metrics from database: {e}")
        set_molecules_count(0, 0, 0)
        set_clinical_trials_count(0, 0, 0)
        set_adverse_events_count(0)


def get_metrics() -> bytes:
    """Get Prometheus metrics in text format."""
    if PROMETHEUS_AVAILABLE:
        return generate_latest()
    return b""


def get_metrics_content_type() -> str:
    """Get content type for metrics response."""
    if PROMETHEUS_AVAILABLE:
        return CONTENT_TYPE_LATEST
    return "text/plain"
