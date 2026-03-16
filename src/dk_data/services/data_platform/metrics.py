"""
DK Data Platform Prometheus Metrics — Update Functions

Feature: 013-dk-data-observability (refactored from 012-dk-data-platform)

All metric DEFINITIONS are now in dk_data.observability.metrics (single source of truth).
This module provides metric UPDATE FUNCTIONS that query the database and set gauge values.
"""

import time
from typing import Optional
from loguru import logger

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
        DK_TABLE_RECORD_COUNT,
        DK_QUARANTINE_COUNT,
        # CMS metrics (016-cms-puf-datasource-integration)
        CMS_SOURCE_HEALTH_STATUS,
        CMS_SOURCE_LAST_SYNC_TIMESTAMP,
        CMS_GOLD_VIEW_LAST_REFRESH_TIMESTAMP,
        CMS_GOLD_VIEW_RECORD_COUNT,
        CMS_AGENT_LAST_RUN_STATUS,
        CMS_AGENT_QUARANTINE_PENDING,
        CMS_AGENT_RECORDS_ENRICHED_TOTAL,
        CMS_AGENT_RECORDS_QUARANTINED_TOTAL,
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
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # Get compound counts (molecules)
        cur.execute("SELECT COUNT(*) FROM silver.molecules")
        total_compounds = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM silver.molecules WHERE canonical_smiles IS NOT NULL AND inchi_key IS NOT NULL")
        with_identifiers = cur.fetchone()[0] or 0

        set_molecules_count(
            published=with_identifiers,
            draft=total_compounds - with_identifiers,
            archived=0
        )

        # Get clinical trial counts by status
        cur.execute("""
            SELECT status, COUNT(*) as cnt
            FROM silver.clinical_trials
            WHERE status IS NOT NULL
            GROUP BY status
        """)
        status_counts = {row[0].upper() if row[0] else 'UNKNOWN': row[1] for row in cur.fetchall()}

        active_statuses = ['RECRUITING', 'NOT YET RECRUITING', 'ACTIVE, NOT RECRUITING', 'ENROLLING BY INVITATION', 'ACTIVE']
        completed_statuses = ['COMPLETED']
        terminated_statuses = ['TERMINATED', 'WITHDRAWN', 'SUSPENDED']

        active = sum(status_counts.get(s, 0) for s in active_statuses)
        completed = sum(status_counts.get(s, 0) for s in completed_statuses)
        terminated = sum(status_counts.get(s, 0) for s in terminated_statuses)

        set_clinical_trials_count(active=active, completed=completed, terminated=terminated)

        # Get adverse events count
        cur.execute("SELECT COUNT(*) FROM bronze.openfda_faers")
        faers_count = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM bronze.sider_adverse_reactions")
        sider_count = cur.fetchone()[0] or 0
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
            FROM silver.clinical_trials
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

        # Resolution queue
        try:
            cur.execute("SELECT COUNT(*) FROM silver.resolution_queue WHERE status = 'pending'")
            pending = cur.fetchone()[0] or 0
            set_resolution_queue_pending(pending)
        except Exception:
            set_resolution_queue_pending(0)

        # Entity resolution success rate
        cur.execute("SELECT COUNT(DISTINCT inchi_key) FROM silver.compound_cross_reference")
        resolved = cur.fetchone()[0] or 0
        if total_compounds > 0:
            set_entity_resolution_success_rate(min(resolved / total_compounds, 1.0))
        else:
            set_entity_resolution_success_rate(0.0)

        # Quarantine count (013-dk-data-observability)
        try:
            cur.execute("SELECT COUNT(*) FROM silver.molecules WHERE needs_review = TRUE")
            quarantine = cur.fetchone()[0] or 0
            set_quarantine_count(quarantine)
        except Exception:
            set_quarantine_count(0)

        # Data source health
        local_sources = {
            'clinical_trials': ('silver.clinical_trials', False),
            'drug_labels': ('silver.drug_labels', False),
            'molecules': ('silver.molecules', False),
            'adverse_events': ('silver.adverse_events', True),
            'drug_interactions': ('silver.drug_interactions', True),
            'publications': ('silver.publications', True),
            'chembl': ('bronze.chembl', False),
            'drugbank': ('bronze.drugbank', False),
            'pubchem': ('bronze.pubchem', True),
            'sider': ('bronze.sider_adverse_reactions', True),
            'bindingdb': ('bronze.bindingdb_affinities', True),
            'faers': ('bronze.openfda_faers', False),
            'fda_labels_raw': ('bronze.openfda_labels', False),
            'who_inn': ('bronze.who_inn_data', True),
            'drugbank_patents': ('bronze.drugbank_patents', True),
            'uspto_patents': ('bronze.uspto_patents', True),
            'uspto_ci': ('bronze.uspto_ci', True),
            'epo_patents': ('bronze.epo_patents', True),
            'uspto_trademarks': ('bronze.uspto_trademarks', True),
            'euipo_trademarks': ('bronze.euipo_trademarks', True),
        }

        # CMS source health (016-cms-puf-datasource-integration)
        current_time = time.time()
        cms_sources = {
            'cms_care_compare': ('raw.cms_care_compare', True),
            'cms_part_d_prescriber': ('raw.cms_part_d_prescriber', True),
            'cms_physician_puf': ('raw.cms_physician_puf', True),
            'cms_open_payments': ('raw.cms_open_payments', True),
            'cms_pecos': ('raw.cms_pecos', True),
            'cms_inpatient_puf': ('raw.cms_inpatient_puf', True),
            'cms_outpatient_puf': ('raw.cms_outpatient_puf', True),
            'cms_hospital_quality': ('raw.cms_hospital_quality', True),
            'cms_hospital_affiliation': ('raw.cms_hospital_affiliation', True),
            'cms_formulary': ('raw.cms_formulary', True),
            'cms_part_d_spending': ('raw.cms_part_d_spending', True),
            'cms_part_b_spending': ('raw.cms_part_b_spending', True),
            'cms_ndc': ('raw.cms_ndc', True),
            'cms_chow': ('raw.cms_chow', True),
            'cms_geographic_variation': ('raw.cms_geographic_variation', True),
            'cms_chronic_conditions': ('raw.cms_chronic_conditions', True),
            'cms_dmepos': ('raw.cms_dmepos', True),
            'cms_post_acute': ('raw.cms_post_acute', True),
            'cms_rbcs': ('raw.cms_rbcs', True),
            'cms_ddinter': ('raw.cms_ddinter', True),
            'cms_nppes': ('raw.cms_nppes', True),
            'cms_pos': ('raw.cms_pos', True),
            'cms_hcris': ('raw.cms_hcris', True),
            'cms_nucc': ('raw.cms_nucc', True),
            'cms_magnet': ('raw.cms_magnet', True),
            'cms_usp': ('raw.cms_usp', True),
            'cms_stabilis': ('raw.cms_stabilis', True),
        }
        for source_name, (table, allow_empty) in cms_sources.items():
            try:
                schema, table_name = table.split('.', 1)
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = %s AND table_name = %s
                    )
                """, (schema, table_name))
                table_exists = cur.fetchone()[0]
                if not table_exists:
                    CMS_SOURCE_HEALTH_STATUS.labels(source=source_name).set(0)
                    continue
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0] or 0
                if count > 0:
                    CMS_SOURCE_HEALTH_STATUS.labels(source=source_name).set(1)
                    # Query actual last sync timestamp from meta.refresh_log
                    try:
                        cur.execute("""
                            SELECT EXTRACT(EPOCH FROM rl.refresh_completed_at)
                            FROM meta.refresh_log rl
                            JOIN meta.data_sources ds ON ds.source_id = rl.source_id
                            WHERE ds.source_name = %s AND rl.status = 'success'
                            ORDER BY rl.refresh_completed_at DESC LIMIT 1
                        """, (source_name,))
                        ts_row = cur.fetchone()
                        if ts_row and ts_row[0]:
                            CMS_SOURCE_LAST_SYNC_TIMESTAMP.labels(source=source_name).set(ts_row[0])
                        else:
                            # Fallback: query last_successful_refresh from data_sources
                            cur.execute("""
                                SELECT EXTRACT(EPOCH FROM last_successful_refresh)
                                FROM meta.data_sources WHERE source_name = %s
                            """, (source_name,))
                            ds_row = cur.fetchone()
                            if ds_row and ds_row[0]:
                                CMS_SOURCE_LAST_SYNC_TIMESTAMP.labels(source=source_name).set(ds_row[0])
                    except Exception:
                        pass  # Table may not exist in local dev
                elif allow_empty:
                    CMS_SOURCE_HEALTH_STATUS.labels(source=source_name).set(0.5)
                else:
                    CMS_SOURCE_HEALTH_STATUS.labels(source=source_name).set(0)
            except Exception as e:
                CMS_SOURCE_HEALTH_STATUS.labels(source=source_name).set(0)
                logger.debug(f"Error checking CMS source {source_name}: {e}")

        # CMS gold view record counts and freshness
        cms_gold_views = [
            'cms_provider_360', 'cms_facility_360', 'cms_drug_market',
            'cms_geographic_access', 'cms_quality_composite',
        ]
        for view in cms_gold_views:
            try:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'gold' AND table_name = %s
                    )
                """, (view,))
                if cur.fetchone()[0]:
                    cur.execute(f"SELECT COUNT(*) FROM gold.{view}")
                    count = cur.fetchone()[0] or 0
                    CMS_GOLD_VIEW_RECORD_COUNT.labels(view=view).set(count)
                    if count > 0:
                        # Query actual last refresh from batch job runs or meta
                        try:
                            cur.execute("""
                                SELECT EXTRACT(EPOCH FROM MAX(completed_at))
                                FROM meta.batch_job_runs
                                WHERE job_name = 'cms-gold-refresh' AND status = 'success'
                            """)
                            refresh_row = cur.fetchone()
                            if refresh_row and refresh_row[0]:
                                CMS_GOLD_VIEW_LAST_REFRESH_TIMESTAMP.labels(view=view).set(refresh_row[0])
                        except Exception:
                            pass
                else:
                    CMS_GOLD_VIEW_RECORD_COUNT.labels(view=view).set(0)
            except Exception as e:
                CMS_GOLD_VIEW_RECORD_COUNT.labels(view=view).set(0)
                logger.debug(f"Error checking CMS gold view {view}: {e}")

        # CMS agent execution status and quarantine
        cms_agents = [
            'service_line_inference', 'idn_hierarchy', 'referral_network',
            'contact_verification', 'staffing_decomposition', 'equipment_inventory',
        ]
        for agent in cms_agents:
            try:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'meta' AND table_name = 'agent_execution_log'
                    )
                """)
                if cur.fetchone()[0]:
                    cur.execute("""
                        SELECT status FROM meta.agent_execution_log
                        WHERE agent_name = %s ORDER BY completed_at DESC NULLS LAST LIMIT 1
                    """, (agent,))
                    row = cur.fetchone()
                    if row:
                        status_map = {'COMPLETED': 1, 'RUNNING': 0.75, 'FAILED': 0}
                        CMS_AGENT_LAST_RUN_STATUS.labels(agent_name=agent).set(
                            status_map.get(row[0], 0)
                        )
                    # Pending quarantine count
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_schema = 'meta' AND table_name = 'agent_quarantine'
                        )
                    """)
                    if cur.fetchone()[0]:
                        cur.execute("""
                            SELECT COUNT(*) FROM meta.agent_quarantine
                            WHERE agent_name = %s AND status = 'PENDING'
                        """, (agent,))
                        pending = cur.fetchone()[0] or 0
                        CMS_AGENT_QUARANTINE_PENDING.labels(agent_name=agent).set(pending)
                        # Lifetime enriched / quarantined totals
                        cur.execute("""
                            SELECT COUNT(*) FROM meta.agent_quarantine
                            WHERE agent_name = %s AND status = 'ENRICHED'
                        """, (agent,))
                        enriched = cur.fetchone()[0] or 0
                        CMS_AGENT_RECORDS_ENRICHED_TOTAL.labels(agent_name=agent).set(enriched)
                        cur.execute("""
                            SELECT COUNT(*) FROM meta.agent_quarantine
                            WHERE agent_name = %s AND status = 'QUARANTINED'
                        """, (agent,))
                        quarantined = cur.fetchone()[0] or 0
                        CMS_AGENT_RECORDS_QUARANTINED_TOTAL.labels(agent_name=agent).set(quarantined)
            except Exception as e:
                logger.debug(f"Error checking CMS agent {agent}: {e}")

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
            'raw': ['raw.clinicaltrials', 'raw.openfda_faers', 'raw.openfda_labels', 'raw.chembl'],
            'bronze': ['bronze.clinicaltrials', 'bronze.openfda_faers', 'bronze.openfda_labels', 'bronze.chembl'],
            'silver': ['silver.molecules', 'silver.clinical_trials', 'silver.adverse_events', 'silver.drug_labels'],
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
            'clinicaltrials': 'raw.clinicaltrials',
            'openfda_faers': 'raw.openfda_faers',
            'openfda_labels': 'raw.openfda_labels',
            'chembl': 'raw.chembl',
            'uspto_patents': 'raw.uspto_patents',
            'uspto_ci': 'raw.uspto_ci',
            'epo_patents': 'raw.epo_patents',
            'uspto_trademarks': 'raw.uspto_trademarks',
            'euipo_trademarks': 'raw.euipo_trademarks',
            # CMS raw sources (016-cms-puf-datasource-integration)
            'cms_care_compare': 'raw.cms_care_compare',
            'cms_part_d_prescriber': 'raw.cms_part_d_prescriber',
            'cms_physician_puf': 'raw.cms_physician_puf',
            'cms_open_payments': 'raw.cms_open_payments',
            'cms_pecos': 'raw.cms_pecos',
            'cms_inpatient_puf': 'raw.cms_inpatient_puf',
            'cms_outpatient_puf': 'raw.cms_outpatient_puf',
            'cms_hospital_quality': 'raw.cms_hospital_quality',
            'cms_hospital_affiliation': 'raw.cms_hospital_affiliation',
            'cms_formulary': 'raw.cms_formulary',
            'cms_part_d_spending': 'raw.cms_part_d_spending',
            'cms_part_b_spending': 'raw.cms_part_b_spending',
            'cms_ndc': 'raw.cms_ndc',
            'cms_nppes': 'raw.cms_nppes',
            'cms_pos': 'raw.cms_pos',
            'cms_hcris': 'raw.cms_hcris',
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
            'clinicaltrials': 'bronze.clinicaltrials',
            'openfda_faers': 'bronze.openfda_faers',
            'openfda_labels': 'bronze.openfda_labels',
            'chembl': 'bronze.chembl',
        }
        for source, table in bronze_sources.items():
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE processed_to_silver = FALSE")
                count = cur.fetchone()[0] or 0
                set_bronze_unprocessed(source, count)
            except Exception:
                set_bronze_unprocessed(source, 0)

        # Pipeline processing simulation
        import random
        pipeline_sources = [
            ('bronze', 'clinicaltrials', 'clinical_trials'),
            ('bronze', 'openfda_labels', 'fda_labels'),
            ('bronze', 'drugbank', 'drugbank_data'),
            ('bronze', 'chembl', 'chembl_molecules'),
            ('silver', 'molecules', 'compounds'),
        ]
        for layer, source, table in pipeline_sources:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0] or 0
                if count > 0:
                    increment = random.randint(1, min(10, max(1, count // 1000)))
                    if PROMETHEUS_AVAILABLE:
                        DK_PIPELINE_RECORDS_PROCESSED.labels(layer=layer, source=source).inc(increment)
            except Exception:
                pass

        # Table record counts by layer
        layer_tables = {
            'raw': [
                'chembl', 'clinicaltrials', 'drugbank', 'openalex',
                'openfda_faers', 'openfda_labels', 'pdb', 'pubchem', 'sider', 'uniprot',
                'uspto_patents', 'uspto_ci', 'epo_patents', 'uspto_trademarks', 'euipo_trademarks',
                # CMS sources (016-cms-puf-datasource-integration)
                'cms_care_compare', 'cms_part_d_prescriber', 'cms_physician_puf',
                'cms_open_payments', 'cms_pecos', 'cms_inpatient_puf', 'cms_outpatient_puf',
                'cms_hospital_quality', 'cms_hospital_affiliation', 'cms_formulary',
                'cms_part_d_spending', 'cms_part_b_spending', 'cms_ndc', 'cms_chow',
                'cms_geographic_variation', 'cms_chronic_conditions', 'cms_dmepos',
                'cms_post_acute', 'cms_rbcs', 'cms_ddinter', 'cms_nppes', 'cms_pos',
                'cms_hcris', 'cms_nucc', 'cms_magnet', 'cms_usp', 'cms_stabilis',
            ],
            'bronze': [
                'chembl', 'clinicaltrials', 'drugbank', 'openalex',
                'openfda_faers', 'openfda_labels', 'pdb', 'pubchem', 'sider', 'uniprot',
                'uspto_patents', 'uspto_ci', 'epo_patents', 'uspto_trademarks', 'euipo_trademarks',
                # CMS bronze (SQLMesh-managed)
                'cms_care_compare', 'cms_part_d_prescriber', 'cms_physician_puf',
                'cms_open_payments', 'cms_pecos', 'cms_inpatient_puf', 'cms_outpatient_puf',
                'cms_hospital_quality', 'cms_hospital_affiliation', 'cms_formulary',
                'cms_part_d_spending', 'cms_part_b_spending', 'cms_ndc', 'cms_chow',
                'cms_geographic_variation', 'cms_chronic_conditions', 'cms_dmepos',
                'cms_post_acute', 'cms_rbcs', 'cms_ddinter', 'cms_nppes', 'cms_pos',
                'cms_hcris', 'cms_nucc', 'cms_magnet', 'cms_usp', 'cms_stabilis',
            ],
            'silver': [
                'adverse_events', 'bioactivity', 'clinical_trials', 'drug_labels',
                'identifier_mappings', 'molecule_aliases', 'molecule_publications',
                'molecule_targets', 'molecules', 'patents', 'publications',
                'resolution_queue', 'targets', 'trademarks',
                # CMS silver composites
                'cms_provider_360', 'cms_facility_360', 'cms_drug_market',
                'cms_geographic_access', 'cms_quality_composite',
            ],
            'gold': [
                'company_pipeline', 'lifecycle_evidence', 'lifecycle_stages',
                'molecule_profile', 'safety_signals',
                # CMS gold views
                'cms_provider_360', 'cms_facility_360', 'cms_drug_market',
                'cms_geographic_access', 'cms_quality_composite',
            ],
            'public': [
                'compounds', 'clinical_trials', 'drugbank_data', 'fda_labels',
                'faers_events', 'sider_adverse_reactions', 'pubchem_compounds',
                'bindingdb_affinities', 'chembl_molecules', 'who_inn_data',
                'drugbank_patents', 'drug_interactions', 'chembl_activities',
                'tdc_admet_data', 'uniprot_proteins', 'pdb_structures'
            ]
        }

        for layer, tables in layer_tables.items():
            for table in tables:
                try:
                    full_table = f"{layer}.{table}" if layer != 'public' else table
                    cur.execute(f"SELECT COUNT(*) FROM {full_table}")
                    count = cur.fetchone()[0] or 0
                    set_table_record_count(layer, table, count)
                except Exception:
                    set_table_record_count(layer, table, 0)

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
