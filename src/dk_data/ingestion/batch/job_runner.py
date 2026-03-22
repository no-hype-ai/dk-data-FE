"""
Job Runner Module
Feature: 002-production-readiness
Tasks: T043, T061

Executes batch jobs either locally (subprocess) or via Kubernetes.
Includes Prometheus metrics for job monitoring.
"""

import os
import subprocess
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

# Import observability metrics
try:
    from dk_data.observability.metrics import (
        record_job_duration,
        record_job_records,
        increment_job_failure,
        mark_job_success,
    )
    from dk_data.observability import get_logger
    logger = get_logger(__name__)
    METRICS_AVAILABLE = True
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    METRICS_AVAILABLE = False

    # Define no-op metric functions
    def record_job_duration(job_name: str, duration: float) -> None:
        pass

    def record_job_records(job_name: str, count: int) -> None:
        pass

    def increment_job_failure(job_name: str) -> None:
        pass

    def mark_job_success(job_name: str) -> None:
        pass


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


@dataclass
class JobResult:
    """Result of a job execution."""
    run_id: int | None
    job_name: str
    status: JobStatus
    started_at: datetime
    completed_at: datetime | None
    records_processed: int | None
    error_message: str | None
    k8s_job_name: str | None = None


class JobRunner(ABC):
    """Abstract base class for job runners."""

    @abstractmethod
    def run_job(self, job_name: str, triggered_by: str, user: str | None = None) -> JobResult:
        """Execute a job and return the result."""
        pass

    @abstractmethod
    def get_job_status(self, run_id: int) -> JobResult | None:
        """Get the status of a job run."""
        pass


class LocalJobRunner(JobRunner):
    """
    Runs jobs locally via subprocess.
    Used for local development and testing.
    """

    # Mapping of job names to commands
    # Scripts are organized under /app/scripts/{data,ops,utils}/
    # Job name → command mapping. One entry per ops.sync_schedules source.
    # All fetch-* jobs write to mol_raw.*; transforms run via SQLMesh.
    JOB_COMMANDS = {
        # ── TAVR / CMS (legacy) ──
        "fetch-cms-all": ["python", "-m", "ingestion.fetch_data", "--source", "all"],
        "fetch-cms-hospitals": ["python", "-m", "ingestion.fetch_data", "--source", "cms_hospital_info"],
        "fetch-cms-inpatient": ["python", "-m", "ingestion.fetch_data", "--source", "cms_inpatient"],
        "fetch-acc-tvc": ["python", "-m", "ingestion.fetch_data", "--source", "acc_tvc"],
        "fetch-hrsa": ["python", "-m", "ingestion.fetch_data", "--source", "hrsa"],
        "catalog-refresh": ["python", "scripts/data/catalog_refresh.py"],
        "check-freshness": ["python", "scripts/data/check_freshness.py"],
        "purge-history": ["python", "scripts/data/purge_history.py"],

        # ── Molecule platform: fetch (raw ingestion only) ──
        "fetch-clinicaltrials": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "clinicaltrials_gov"],
        "fetch-openfda-labels": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "openfda_labels"],
        "fetch-openfda-faers": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "openfda_faers"],
        "fetch-chembl": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "chembl"],
        "fetch-pubchem": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "pubchem"],
        "fetch-sec-edgar": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "sec_edgar"],
        "fetch-uniprot": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "uniprot"],
        "fetch-openalex": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "openalex"],
        "fetch-openalex-ci": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "openalex_ci"],
        "fetch-pubmed": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "pubmed"],
        "fetch-drugbank": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "drugbank"],
        "fetch-dailymed": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "dailymed"],
        "fetch-cochrane": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "cochrane_reviews"],
        "fetch-ema": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "ema_regulatory"],
        "fetch-hta": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "hta_decisions"],
        "fetch-purple-book": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "purple_book"],
        "fetch-epo-patents": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "epo_patents"],
        "fetch-euipo-trademarks": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "euipo_trademarks"],
        "fetch-uspto-patents": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "uspto_patents"],
        "fetch-uspto-trademarks": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "uspto_trademarks"],
        "fetch-uspto-ci": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "uspto_ci"],
        "fetch-who-gho": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "who_gho"],
        "fetch-hrsa-shortage": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "hrsa_shortage_areas"],
        "fetch-acc-tvc-cert": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "acc_tvc_certification"],
        "fetch-journal-rss": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "journal_rss"],
        "fetch-medical-news": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "medical_news"],
        "fetch-ct-indication-stats": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "ct_gov_indication_stats"],

        # ── SQLMesh transforms (Bronze → Silver → Gold) ──
        # These are invoked after fetch jobs complete.
        "mol-bronze-transform": ["python", "-m", "dk_data.ingestion.transform_molecules", "--layer", "bronze"],
        "mol-silver-transform": ["python", "-m", "dk_data.ingestion.transform_molecules", "--layer", "silver"],
        "mol-gold-aggregate": ["python", "-m", "dk_data.ingestion.transform_molecules", "--layer", "gold"],
        "mol-ip-bronze-transform": ["python", "-m", "dk_data.ingestion.transform_molecules", "--layer", "ip_bronze"],
        "mol-ip-silver-transform": ["python", "-m", "dk_data.ingestion.transform_molecules", "--layer", "ip_silver"],
        "mol-ip-gold-aggregate": ["python", "-m", "dk_data.ingestion.transform_molecules", "--layer", "ip_gold"],
        "mol-pipeline-full": ["python", "-m", "dk_data.ingestion.run_molecule_pipeline"],

        # ── Per-source full pipeline (fetch + SQLMesh bronze + silver) ──
        "pipeline-clinicaltrials": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "clinicaltrials_gov", "--with-transform"],
        "pipeline-openfda-labels": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "openfda_labels", "--with-transform"],
        "pipeline-openfda-faers": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "openfda_faers", "--with-transform"],
        "pipeline-chembl": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "chembl", "--with-transform"],
        "pipeline-sec-edgar": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "sec_edgar", "--with-transform"],
    }

    def __init__(self, db_config: dict[str, Any]):
        self.db_config = db_config
        self.working_dir = os.getenv("WORKING_DIR", "/app")

    def _get_connection(self):
        return psycopg2.connect(**self.db_config)

    def _record_job_start(self, job_name: str, triggered_by: str, user: str | None) -> int:
        """Record job start in database and return run_id."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO meta.ops_batch_job_runs
                (job_id, triggered_by, triggered_by_user, started_at, status)
                SELECT job_id, %s, %s, NOW(), 'running'
                FROM meta.ops_batch_jobs WHERE job_name = %s
                RETURNING run_id
            """, (triggered_by, user, job_name))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else 0
        finally:
            conn.close()

    def _record_job_completion(
        self,
        run_id: int,
        status: JobStatus,
        records_processed: int | None,
        error_message: str | None
    ):
        """Record job completion in database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE meta.ops_batch_job_runs
                SET completed_at = NOW(),
                    status = %s,
                    records_processed = %s,
                    error_message = %s
                WHERE run_id = %s
            """, (status.value, records_processed, error_message, run_id))

            # Also update batch_jobs table
            cursor.execute("""
                UPDATE meta.ops_batch_jobs bj
                SET last_run_at = bjr.completed_at,
                    last_run_status = bjr.status,
                    last_run_duration_seconds = EXTRACT(EPOCH FROM (bjr.completed_at - bjr.started_at))::INTEGER
                FROM meta.ops_batch_job_runs bjr
                WHERE bjr.run_id = %s AND bj.job_id = bjr.job_id
            """, (run_id,))

            conn.commit()
        finally:
            conn.close()

    def run_job(self, job_name: str, triggered_by: str, user: str | None = None) -> JobResult:
        """Execute a job locally via subprocess."""
        if job_name not in self.JOB_COMMANDS:
            increment_job_failure(job_name)
            return JobResult(
                run_id=None,
                job_name=job_name,
                status=JobStatus.FAILURE,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                records_processed=None,
                error_message=f"Unknown job: {job_name}",
            )

        started_at = datetime.now()
        start_time = time.time()
        run_id = self._record_job_start(job_name, triggered_by, user)

        try:
            command = self.JOB_COMMANDS[job_name]
            logger.info(f"Running job {job_name}", command=" ".join(command), run_id=run_id)

            result = subprocess.run(
                command,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
                env={**os.environ, **{
                    "POSTGRES_HOST": self.db_config.get("host", "localhost"),
                    "POSTGRES_PORT": str(self.db_config.get("port", 5432)),
                    "POSTGRES_USER": self.db_config.get("user", "postgres"),
                    "POSTGRES_PASSWORD": self.db_config.get("password", ""),
                    "POSTGRES_DB": self.db_config.get("database", "dk_data"),
                }},
            )

            completed_at = datetime.now()
            duration = time.time() - start_time

            # Record job duration metric
            record_job_duration(job_name, duration)

            if result.returncode == 0:
                status = JobStatus.SUCCESS
                error_message = None
                mark_job_success(job_name)
                logger.info(f"Job {job_name} completed successfully", duration=duration, run_id=run_id)
            else:
                status = JobStatus.FAILURE
                error_message = result.stderr[:1000] if result.stderr else "Unknown error"
                increment_job_failure(job_name)
                logger.error(f"Job {job_name} failed", error=error_message, duration=duration, run_id=run_id)

            self._record_job_completion(run_id, status, None, error_message)

            return JobResult(
                run_id=run_id,
                job_name=job_name,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                records_processed=None,
                error_message=error_message,
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            record_job_duration(job_name, duration)
            increment_job_failure(job_name)
            self._record_job_completion(run_id, JobStatus.FAILURE, None, "Job timed out")
            logger.error(f"Job {job_name} timed out", duration=duration, run_id=run_id)
            return JobResult(
                run_id=run_id,
                job_name=job_name,
                status=JobStatus.FAILURE,
                started_at=started_at,
                completed_at=datetime.now(),
                records_processed=None,
                error_message="Job timed out after 1 hour",
            )
        except Exception as e:
            duration = time.time() - start_time
            record_job_duration(job_name, duration)
            increment_job_failure(job_name)
            error_msg = str(e)[:1000]
            self._record_job_completion(run_id, JobStatus.FAILURE, None, error_msg)
            logger.error(f"Job {job_name} failed with exception", error=error_msg, duration=duration, run_id=run_id)
            return JobResult(
                run_id=run_id,
                job_name=job_name,
                status=JobStatus.FAILURE,
                started_at=started_at,
                completed_at=datetime.now(),
                records_processed=None,
                error_message=error_msg,
            )

    def get_job_status(self, run_id: int) -> JobResult | None:
        """Get the status of a job run."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT bjr.*, bj.job_name
                FROM meta.ops_batch_job_runs bjr
                JOIN meta.ops_batch_jobs bj ON bjr.job_id = bj.job_id
                WHERE bjr.run_id = %s
            """, (run_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return JobResult(
                run_id=row["run_id"],
                job_name=row["job_name"],
                status=JobStatus(row["status"]),
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                records_processed=row["records_processed"],
                error_message=row["error_message"],
                k8s_job_name=row.get("k8s_job_name"),
            )
        finally:
            conn.close()


class K8sJobRunner(JobRunner):
    """
    Runs jobs via Kubernetes Job API.
    Used in production Kubernetes environments.
    """

    def __init__(self, db_config: dict[str, Any], namespace: str = "dk-data"):
        self.db_config = db_config
        self.namespace = namespace
        self._k8s_client = None

    @property
    def k8s_client(self):
        """Lazy-load Kubernetes client."""
        if self._k8s_client is None:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            self._k8s_client = client.BatchV1Api()
        return self._k8s_client

    def _get_connection(self):
        return psycopg2.connect(**self.db_config)

    def run_job(self, job_name: str, triggered_by: str, user: str | None = None) -> JobResult:
        """Create a Kubernetes Job from a CronJob template."""
        from kubernetes import client

        started_at = datetime.now()
        k8s_job_name = f"{job_name}-{uuid.uuid4().hex[:8]}"

        try:
            # Get the CronJob spec to use as template
            cronjob = self.k8s_client.read_namespaced_cron_job(
                name=job_name,
                namespace=self.namespace
            )

            # Create Job from CronJob template
            job_spec = cronjob.spec.job_template.spec
            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    name=k8s_job_name,
                    namespace=self.namespace,
                    labels={
                        "app": job_name,
                        "triggered-by": triggered_by,
                    },
                ),
                spec=job_spec,
            )

            # Create the job
            self.k8s_client.create_namespaced_job(
                namespace=self.namespace,
                body=job
            )

            # Record in database
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO meta.ops_batch_job_runs
                    (job_id, triggered_by, triggered_by_user, started_at, status, k8s_job_name)
                    SELECT job_id, %s, %s, NOW(), 'running', %s
                    FROM meta.ops_batch_jobs WHERE job_name = %s
                    RETURNING run_id
                """, (triggered_by, user, k8s_job_name, job_name))
                result = cursor.fetchone()
                run_id = result[0] if result else None
                conn.commit()
            finally:
                conn.close()

            return JobResult(
                run_id=run_id,
                job_name=job_name,
                status=JobStatus.RUNNING,
                started_at=started_at,
                completed_at=None,
                records_processed=None,
                error_message=None,
                k8s_job_name=k8s_job_name,
            )

        except Exception as e:
            logger.error(f"Failed to create K8s job {job_name}: {e}")
            return JobResult(
                run_id=None,
                job_name=job_name,
                status=JobStatus.FAILURE,
                started_at=started_at,
                completed_at=datetime.now(),
                records_processed=None,
                error_message=str(e)[:1000],
            )

    def get_job_status(self, run_id: int) -> JobResult | None:
        """Get the status of a job run, checking K8s if still running."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT bjr.*, bj.job_name
                FROM meta.ops_batch_job_runs bjr
                JOIN meta.ops_batch_jobs bj ON bjr.job_id = bj.job_id
                WHERE bjr.run_id = %s
            """, (run_id,))
            row = cursor.fetchone()

            if not row:
                return None

            # If still running, check K8s for updates
            if row["status"] == "running" and row["k8s_job_name"]:
                try:
                    k8s_job = self.k8s_client.read_namespaced_job(
                        name=row["k8s_job_name"],
                        namespace=self.namespace
                    )

                    if k8s_job.status.succeeded:
                        cursor.execute("""
                            UPDATE meta.ops_batch_job_runs
                            SET status = 'success', completed_at = NOW()
                            WHERE run_id = %s
                        """, (run_id,))
                        conn.commit()
                        row["status"] = "success"
                    elif k8s_job.status.failed:
                        cursor.execute("""
                            UPDATE meta.ops_batch_job_runs
                            SET status = 'failure', completed_at = NOW()
                            WHERE run_id = %s
                        """, (run_id,))
                        conn.commit()
                        row["status"] = "failure"
                except Exception as e:
                    logger.warning(f"Could not check K8s job status: {e}")

            return JobResult(
                run_id=row["run_id"],
                job_name=row["job_name"],
                status=JobStatus(row["status"]),
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                records_processed=row["records_processed"],
                error_message=row["error_message"],
                k8s_job_name=row.get("k8s_job_name"),
            )
        finally:
            conn.close()


def get_job_runner(db_config: dict[str, Any]) -> JobRunner:
    """Factory function to get the appropriate job runner."""
    mode = os.getenv("JOB_RUNNER_MODE", "local")

    if mode == "k8s":
        namespace = os.getenv("K8S_NAMESPACE", "dk-data")
        return K8sJobRunner(db_config, namespace)
    else:
        return LocalJobRunner(db_config)
