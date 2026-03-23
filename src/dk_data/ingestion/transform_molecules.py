#!/usr/bin/env python3
"""CLI for running molecule data transformations via SQLMesh.

Feature: 012-dk-data-platform
Description: Entry point for molecule data transformation pipeline (Bronze -> Silver -> Gold)

Usage:
    python -m ingestion.transform_molecules --layer bronze
    python -m ingestion.transform_molecules --layer silver
    python -m ingestion.transform_molecules --layer gold
    python -m ingestion.transform_molecules --layer all
    python -m ingestion.transform_molecules --model mol_bronze.chembl
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Observability (013-dk-data-observability T023+T030)
try:
    from dk_data.observability import setup_telemetry, get_tracer
    from dk_data.observability.logging import setup_logging, get_logger
    from dk_data.observability.reporting import report_completion
    _OBS_AVAILABLE = True
except ImportError:
    _OBS_AVAILABLE = False

import logging
logger = logging.getLogger(__name__)


# SQLMesh model definitions by layer
LAYER_MODELS = {
    'bronze': [
        'mol_bronze.chembl',
        'mol_bronze.pubchem',
        'mol_bronze.clinicaltrials',
        'mol_bronze.openfda_labels',
        'mol_bronze.faers_events',
        'mol_bronze.drugbank',
    ],
    'silver': [
        # mol_silver.molecules is the master entity table — populated from ChEMBL bronze.
        # Must run FIRST so entity linking in all downstream models can resolve molecule_id.
        'mol_silver.molecules',
        'mol_silver.bioactivity',
        'mol_silver.molecule_aliases',   # must run before adverse_events (adverse_events JOINs it)
        'mol_silver.drug_labels',
        'mol_silver.adverse_events',     # depends on molecule_aliases
        'mol_silver.clinical_trials',
        'mol_silver.identifier_mappings',
    ],
    'gold': [
        'mol_gold.molecule_profile',
        'mol_gold.safety_signals',
        'mol_gold.lifecycle_stages',
        'mol_gold.lifecycle_evidence',
        'mol_gold.advocacy_sentiment',
        'mol_gold.advocacy_groups',
        'mol_gold.regulatory_timeline',
        'mol_gold.financial_summary',
        'mol_gold.competitive_landscape',
        'mol_gold.company_pipeline',
    ],
    # IP / Patent / Trademark + supplemental bronze models
    'ip_bronze': [
        'mol_bronze.uspto_patents',
        'mol_bronze.uspto_ci',
        'mol_bronze.epo_patents',
        'mol_bronze.uspto_trademarks',
        'mol_bronze.euipo_trademarks',
        'mol_bronze.pubmed',
        'mol_bronze.ema',
        'mol_bronze.hta_decisions',
        'mol_bronze.cochrane_reviews',
        'mol_bronze.sec_edgar',
        'mol_bronze.journal_rss',
        'mol_bronze.medical_news',
        'mol_bronze.cms_inpatient',
        'mol_bronze.cms_hospital_info',
        'mol_bronze.cms_cost_reports',
        'mol_bronze.acc_tvc',
        'mol_bronze.hrsa',
        'mol_bronze.pdb_structures',
        'mol_bronze.who_icd',
        'mol_bronze.dailymed',
        'mol_bronze.sider',
        'mol_bronze.bindingdb',
        'mol_bronze.openalex',
        'mol_bronze.uniprot',
        'mol_bronze.orange_book',
        'mol_bronze.purple_book',
        'mol_bronze.who_gho',
        'mol_bronze.ct_gov_indication_stats',
    ],
    'ip_silver': [
        'mol_silver.patents',
        'mol_silver.trademarks',
        'mol_silver.publications',
        'mol_silver.targets',
        'mol_silver.regulatory_decisions',
        'mol_silver.financial_data',
        'mol_silver.news_signals',
        'mol_silver.dailymed_labels',
        'mol_silver.patent_exclusivities',
        'mol_silver.molecule_publications',
        'mol_silver.molecule_targets',
    ],
    'ip_gold': [
        'mol_gold.advocacy_groups',
    ],
}


def get_sqlmesh_config_path() -> Path:
    """Get the path to SQLMesh configuration."""
    # Check for SQLMESH_CONFIG environment variable first
    config_env = os.getenv('SQLMESH_CONFIG')
    if config_env:
        return Path(config_env)

    # Default to project location
    default_paths = [
        Path(__file__).parent.parent / 'sqlmesh' / 'config.yaml',
        Path('/app/sqlmesh/config.yaml'),
        Path('./sqlmesh/config.yaml'),
    ]

    for path in default_paths:
        if path.exists():
            return path

    raise FileNotFoundError("SQLMesh config.yaml not found")


def run_sqlmesh_command(command: list[str], timeout: int = 3600) -> dict:
    """
    Run a SQLMesh command.

    Args:
        command: Command list to execute
        timeout: Command timeout in seconds

    Returns:
        Result dictionary with status, stdout, stderr
    """
    import tempfile
    import shutil

    try:
        config_path = get_sqlmesh_config_path()

        # SQLMesh writes logs to {config_dir}/logs/ which may not be writable
        # (e.g. when config is inside site-packages). Copy to a temp dir first.
        tmpdir = tempfile.mkdtemp(prefix='sqlmesh_run_')
        try:
            shutil.copytree(str(config_path.parent), tmpdir, dirs_exist_ok=True)
            os.makedirs(os.path.join(tmpdir, 'logs'), exist_ok=True)
            work_config = os.path.join(tmpdir, 'config.yaml')
            full_command = ['sqlmesh', '--paths', tmpdir] + command
        except Exception as copy_err:
            # Fall back to original path if copy fails
            logger.warning(f"Could not copy SQLMesh config to tmpdir: {copy_err}")
            tmpdir = None
            work_config = str(config_path)
            full_command = ['sqlmesh', '--paths', str(config_path.parent)] + command

        logger.info(f"Running: {' '.join(full_command)}")

        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **os.environ,
                'SQLMESH_CONFIG': work_config,
                'OTEL_SDK_DISABLED': 'true',  # Disable trace exporter to avoid connection errors
            }
        )

        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

        if result.returncode == 0:
            return {
                'status': 'success',
                'stdout': result.stdout,
                'stderr': result.stderr,
            }
        else:
            return {
                'status': 'failed',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'error': f"Exit code: {result.returncode}",
            }

    except subprocess.TimeoutExpired:
        return {
            'status': 'failed',
            'error': f"Command timed out after {timeout} seconds",
        }
    except FileNotFoundError as e:
        return {
            'status': 'failed',
            'error': str(e),
        }
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
        }


def _direct_sql_transform(model_name: str, start: str, end: str) -> dict:
    """
    Direct SQL fallback for INCREMENTAL_BY_TIME_RANGE models when SQLMesh cannot
    process the current interval.

    Root cause: for @monthly models, the current-month interval ends in the future
    (e.g. end = 2026-04-01). SQLMesh refuses to run intervals whose end time has
    not yet been reached, even with --ignore-cron. Restate also cannot target a
    future interval.  This fallback bypasses the scheduler entirely:
      1. Resolves the active snapshot table from pg_views
      2. Reads the model SQL, strips MODEL() block, substitutes @start_dt / @end_dt
      3. Inserts directly into the snapshot table (ON CONFLICT DO NOTHING for idempotency)

    Args:
        model_name: Fully qualified model name (e.g., mol_bronze.who_gho)
        start: Start date ISO string passed to @start_dt
        end:   End date ISO string passed to @end_dt (must include today + 1 day to capture
               records inserted today, since BETWEEN is inclusive and records have timestamps
               throughout the day)

    Returns:
        Result dictionary with status, rows_inserted, and stdout/error keys.
    """
    import re as _re
    import psycopg2 as _pg

    schema, table = model_name.split('.')
    pg_host = os.environ.get('POSTGRES_HOST', 'postgres')
    pg_port = int(os.environ.get('POSTGRES_PORT', '5432'))
    pg_user = os.environ.get('POSTGRES_USER', 'postgres')
    pg_db   = os.environ.get('POSTGRES_DB', 'dk_data')
    pg_pw   = os.environ.get('POSTGRES_PASSWORD', 'postgres')

    try:
        conn = _pg.connect(host=pg_host, port=pg_port, user=pg_user, password=pg_pw, dbname=pg_db)
        conn.autocommit = True
    except Exception as exc:
        return {'status': 'failed', 'error': f'DB connect failed: {exc}'}

    # ── 1. Resolve active snapshot table ──────────────────────────────────────
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT definition FROM pg_views WHERE schemaname=%s AND viewname=%s",
                (schema, table),
            )
            row = cur.fetchone()
    except Exception as exc:
        conn.close()
        return {'status': 'failed', 'error': f'Could not query pg_views: {exc}'}

    if not row:
        conn.close()
        return {'status': 'failed', 'error': f'View {schema}.{table} not found in pg_views'}

    m = _re.search(rf'FROM {schema}\.({schema}__{table}__\d+)', row[0])
    if not m:
        conn.close()
        return {'status': 'failed', 'error': f'Cannot parse snapshot table from view: {row[0][:200]}'}
    snapshot_table = f'{schema}."{m.group(1)}"'
    logger.info(f'Direct SQL transform: {model_name} → snapshot {snapshot_table}')

    # ── 2. Find model SQL file ─────────────────────────────────────────────────
    try:
        config_path = get_sqlmesh_config_path()
    except FileNotFoundError as exc:
        conn.close()
        return {'status': 'failed', 'error': str(exc)}

    # Search by model name inside file content (handles filenames that differ from table name,
    # e.g. indication_epidemiology.sql defines model 'ind_silver.epidemiology')
    sql_files = [
        f for f in config_path.parent.rglob('*.sql')
        if _re.search(rf'\bname\s+{_re.escape(model_name)}\b', f.read_text())
    ]
    if not sql_files:
        conn.close()
        return {'status': 'failed', 'error': f'No SQL file found for {model_name}'}

    sql_raw = sql_files[0].read_text()

    # Strip MODEL(...) block (handles multiline, including nested parens in audits)
    sql_body = _re.sub(r'MODEL\s*\(.*?\)\s*;', '', sql_raw, flags=_re.DOTALL).strip()

    # Substitute SQLMesh macro parameters only when present
    sql_body = sql_body.replace('@start_dt', f"'{start}'")
    sql_body = sql_body.replace('@end_dt',   f"'{end}'")
    sql_body = sql_body.rstrip(';').strip()

    # ── 3. Execute INSERT INTO snapshot_table SELECT ... ──────────────────────
    insert_sql = (
        f"INSERT INTO {snapshot_table}\n"
        f"{sql_body}\n"
        f"ON CONFLICT DO NOTHING"
    )

    try:
        with conn.cursor() as cur:
            cur.execute(insert_sql)
            rows = cur.rowcount if cur.rowcount >= 0 else 0
        conn.close()
        logger.info(f'Direct SQL transform {model_name}: {rows} rows inserted into {snapshot_table}')
        return {'status': 'success', 'stdout': f'INSERT 0 {rows}', 'rows_inserted': rows}
    except Exception as exc:
        conn.close()
        return {'status': 'failed', 'error': str(exc)[:500]}


def transform_model(model_name: str, start_days_back: int = 30) -> dict:
    """
    Run transformation for a specific model.

    Args:
        model_name: Fully qualified model name (e.g., mol_bronze.chembl)
        start_days_back: How many days back to set --start for SQLMesh. Use 2 for
            hot-path single-molecule ingestion (xenon-triggered); keep 30 for
            scheduled cron runs to pick up any late-arriving raw records.

    Returns:
        Result dictionary
    """
    logger.info(f"Transforming model: {model_name} (lookback={start_days_back}d)")

    # Use 'sqlmesh run --select-model' for hot-path transforms.
    # 'plan --auto-apply' re-applies the ENTIRE environment plan, causing cascading failures
    # when unrelated models (e.g. epo_patents) have errors, and leaves stale plan locks.
    # The prod environment is already initialized by the sqlmesh-scheduler; 'run' is sufficient.
    #
    # Pass --start N days ago and --end tomorrow to guarantee late-arriving raw records
    # are processed. INCREMENTAL_BY_TIME_RANGE models mark intervals as "complete" in SQLMesh
    # state; without --start, newly inserted raw records in a previously-completed interval
    # (e.g. March 22 records when state tracks "processed through March 23") are silently
    # skipped. The models also have `lookback` set (4 for @weekly, 7 for @daily), which
    # tells SQLMesh to reprocess recent intervals even when they appear complete in state.
    from datetime import date, timedelta
    start = (date.today() - timedelta(days=start_days_back)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    result = run_sqlmesh_command([
        'run', '--select-model', model_name,
        '--ignore-cron', '--no-auto-upstream',
        '--start', start,
        '--end', tomorrow,
    ], timeout=420)  # 7-minute max; large models (publications, clinicaltrials) can take 3-4 min with 1000+ records

    def _no_models_ready(r: dict) -> bool:
        s = (r.get('stdout') or '').lower()
        return r.get('status') == 'success' and (
            'no models are ready' in s or ('no models' in s and 'run' in s)
        )

    # Detect "no models are ready to run": this happens for INCREMENTAL_BY_TIME_RANGE
    # models when:
    #   a) the cron interval was already processed (even with 0 rows) before new data arrived
    #   b) the interval end time is in the future (current month not yet over) —
    #      SQLMesh refuses to run even with --ignore-cron
    #
    # Fallback chain:
    #   1. Try plan --restate-model (marks intervals as pending; works for past intervals)
    #   2. If still no rows, use _direct_sql_transform to bypass the scheduler entirely
    #      (required for the current month's interval whose end date is in the future)
    if _no_models_ready(result):
        logger.warning(
            f"Model {model_name}: no interval ready — trying plan --restate-model "
            f"({start}–{date.today().isoformat()}) then direct SQL fallback."
        )
        restate = run_sqlmesh_command([
            'plan',
            '--restate-model', model_name,
            '--start', start,
            '--end', date.today().isoformat(),  # plan restate cannot use a future end date
            '--auto-apply', '--no-prompts',
        ], timeout=600)

        if restate.get('status') == 'success':
            logger.info(f"Model {model_name} restate plan applied; running now")
            result = run_sqlmesh_command([
                'run', '--select-model', model_name,
                '--ignore-cron', '--no-auto-upstream',
                '--start', start,
                '--end', tomorrow,
            ], timeout=420)
        else:
            restate_detail = restate.get('stderr') or restate.get('stdout') or restate.get('error', '')
            logger.warning(
                f"Model {model_name} restate plan failed: {restate_detail[:200]} — "
                f"falling through to direct SQL transform."
            )

        # If still no rows after restate (current-month interval end is in the future),
        # execute the model SQL directly against the active snapshot table.
        if _no_models_ready(result):
            logger.warning(
                f"Model {model_name}: SQLMesh cannot process current-period interval "
                f"(end date is in the future). Using direct SQL fallback."
            )
            # Use first-of-current-month as start to capture all unprocessed raw records.
            month_start = date.today().replace(day=1).isoformat()
            result = _direct_sql_transform(model_name, month_start, tomorrow)

    if result.get('status') == 'success':
        logger.info(f"Model {model_name} transformed successfully")
    else:
        detail = result.get('stderr') or result.get('stdout') or result.get('error', '')
        logger.error(f"Model {model_name} transformation failed: {result.get('error')} — {detail[:500]}")

    return result


def transform_layer(layer: str) -> dict:
    """
    Run transformations for all models in a layer.

    Args:
        layer: Layer name (bronze, silver, gold)

    Returns:
        Combined results dictionary
    """
    if layer not in LAYER_MODELS:
        return {'status': 'failed', 'error': f'Unknown layer: {layer}'}

    models = LAYER_MODELS[layer]
    results = {}
    success_count = 0
    fail_count = 0

    logger.info(f"Transforming {layer} layer ({len(models)} models)")

    for model_name in models:
        logger.info(f"\n{'-'*40}")
        logger.info(f"Model: {model_name}")
        logger.info(f"{'-'*40}")

        result = transform_model(model_name)
        results[model_name] = result

        if result.get('status') == 'success':
            success_count += 1
        else:
            fail_count += 1

    return {
        'status': 'success' if fail_count == 0 else 'partial',
        'layer': layer,
        'models': results,
        'success_count': success_count,
        'fail_count': fail_count,
    }


def transform_all_layers() -> dict:
    """
    Run transformations for all layers in order.

    Returns:
        Combined results dictionary
    """
    all_results = {}
    total_success = 0
    total_fail = 0

    # Process layers in order: molecule pipeline then IP pipeline
    for layer in ['bronze', 'silver', 'gold', 'ip_bronze', 'ip_silver', 'ip_gold']:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing {layer.upper()} layer")
        logger.info(f"{'='*60}")

        result = transform_layer(layer)
        all_results[layer] = result

        total_success += result.get('success_count', 0)
        total_fail += result.get('fail_count', 0)

        # Stop if layer failed completely
        if result.get('status') == 'failed':
            logger.error(f"Layer {layer} failed completely, stopping pipeline")
            break

    return {
        'status': 'success' if total_fail == 0 else 'partial',
        'layers': all_results,
        'success_count': total_success,
        'fail_count': total_fail,
    }


def run_plan() -> dict:
    """
    Run SQLMesh plan to preview changes.

    Returns:
        Result dictionary
    """
    logger.info("Running SQLMesh plan...")
    return run_sqlmesh_command(['plan', '--no-prompts'])


def run_apply() -> dict:
    """
    Apply SQLMesh changes (run all pending transformations).

    Returns:
        Result dictionary
    """
    logger.info("Applying SQLMesh transformations...")
    return run_sqlmesh_command(['run'])


def print_summary(results: dict):
    """Print transformation summary."""
    print("\n" + "=" * 60)
    print("MOLECULE TRANSFORMATION SUMMARY")
    print("=" * 60)

    if 'layers' in results:
        for layer, layer_result in results['layers'].items():
            status = layer_result.get('status', 'unknown')
            status_icon = '✓' if status == 'success' else '⚠' if status == 'partial' else '✗'
            models_count = len(layer_result.get('models', {}))
            success = layer_result.get('success_count', 0)
            layer_result.get('fail_count', 0)
            print(f"\n  {status_icon} {layer.upper():10} ({success}/{models_count} models)")

            for model_name, model_result in layer_result.get('models', {}).items():
                model_status = model_result.get('status', 'unknown')
                model_icon = '✓' if model_status == 'success' else '✗'
                short_name = model_name.split('.')[-1]
                print(f"      {model_icon} {short_name}")

        print(f"\nTotal: {results.get('success_count', 0)} succeeded, {results.get('fail_count', 0)} failed")

    elif 'models' in results:
        layer = results.get('layer', 'unknown')
        print(f"\n  Layer: {layer.upper()}")

        for model_name, model_result in results['models'].items():
            model_status = model_result.get('status', 'unknown')
            model_icon = '✓' if model_status == 'success' else '✗'
            short_name = model_name.split('.')[-1]
            print(f"      {model_icon} {short_name}")

        print(f"\nTotal: {results.get('success_count', 0)} succeeded, {results.get('fail_count', 0)} failed")

    else:
        status = results.get('status', 'unknown')
        print(f"  Status: {status}")

        if results.get('stdout'):
            print(f"\n  Output:\n{results['stdout'][:1000]}")

        if results.get('error'):
            print(f"\n  Error: {results['error']}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Run molecule data transformations via SQLMesh',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --layer bronze              Transform bronze layer models
  %(prog)s --layer silver              Transform silver layer models
  %(prog)s --layer gold                Transform gold layer models
  %(prog)s --layer all                 Transform all layers (bronze->silver->gold)
  %(prog)s --model mol_bronze.chembl   Transform specific model
  %(prog)s --plan                      Preview pending changes
  %(prog)s --apply                     Apply all pending transformations
        """
    )

    parser.add_argument(
        '--layer', '-l',
        choices=['bronze', 'silver', 'gold', 'ip_bronze', 'ip_silver', 'ip_gold', 'all'],
        help='Layer to transform'
    )
    parser.add_argument(
        '--model', '-m',
        help='Specific model to transform (fully qualified name)'
    )
    parser.add_argument(
        '--plan', '-p',
        action='store_true',
        help='Preview pending changes (SQLMesh plan)'
    )
    parser.add_argument(
        '--apply', '-a',
        action='store_true',
        help='Apply all pending transformations'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Configure observability (013-dk-data-observability)
    global logger
    job_name = f"mol-transform-{args.layer}" if args.layer else "mol-transform"
    if _OBS_AVAILABLE:
        setup_telemetry("mol-transform")
        setup_logging("mol-transform")
        logger = get_logger(__name__)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate arguments
    if not any([args.layer, args.model, args.plan, args.apply]):
        parser.print_help()
        return 1

    logger.info(f"Started at: {datetime.now().isoformat()}")

    start_time = time.monotonic()
    status = "failure"
    records = 0

    try:
        tracer = get_tracer(__name__) if _OBS_AVAILABLE else None

        def _do_transform():
            if args.plan:
                return run_plan()
            elif args.apply:
                return run_apply()
            elif args.model:
                return transform_model(args.model)
            elif args.layer == 'all':
                return transform_all_layers()
            else:
                return transform_layer(args.layer)

        if tracer:
            with tracer.start_as_current_span(f"{job_name}-execution") as span:
                span.set_attribute("layer", args.layer or args.model or "plan/apply")
                results = _do_transform()
                records = results.get('success_count', 0)
                span.set_attribute("records_fetched", records)
        else:
            results = _do_transform()
            records = results.get('success_count', 0)

        # Print summary
        print_summary(results)

        logger.info(f"Completed at: {datetime.now().isoformat()}")

        if results.get('status') == 'failed':
            return 1
        status = "success"
        return 0

    except Exception as e:
        logger.error(f"Transform failed: {e}")
        return 1

    finally:
        duration = time.monotonic() - start_time
        if _OBS_AVAILABLE:
            try:
                asyncio.run(report_completion(
                    job_name=job_name,
                    status=status,
                    duration_seconds=duration,
                    records_processed=records,
                ))
            except Exception as e:
                logger.warning(f"Failed to report completion: {e}")


if __name__ == '__main__':
    sys.exit(main())
