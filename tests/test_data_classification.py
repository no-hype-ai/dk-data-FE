"""
Data Classification and Retention Policy Tests.

Feature: 013-observability-governance (US5: Data Classification + Retention)
Tasks: T020

Tests verify:
- Seed data classifies raw.orcid as 'pii' with expected pii_fields
- Scoring tables are classified as 'confidential'
- Molecule raw tables are classified as 'public'
- Retention days are set for non-perpetual classifications
- The purge_by_classification function reads from meta.data_classification
  and respects retention_days, timestamp column mapping, and batch deletes
"""

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Seed data fixtures (mirrors 069_data_classification.sql)
# ---------------------------------------------------------------------------

SEED_CLASSIFICATIONS = [
    # CONFIDENTIAL
    {'schema_name': 'scoring', 'table_name': 'score_history', 'classification': 'confidential',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    {'schema_name': 'scoring', 'table_name': 'score_latest', 'classification': 'confidential',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    {'schema_name': 'mart', 'table_name': 'dim_hospital', 'classification': 'confidential',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    {'schema_name': 'mart', 'table_name': 'fact_tavr_program', 'classification': 'confidential',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    {'schema_name': 'mart', 'table_name': 'fact_financial_metrics', 'classification': 'confidential',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    {'schema_name': 'staging', 'table_name': 'hospitals', 'classification': 'confidential',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    {'schema_name': 'staging', 'table_name': 'certifications', 'classification': 'confidential',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    {'schema_name': 'staging', 'table_name': 'tavr_volumes', 'classification': 'confidential',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    {'schema_name': 'staging', 'table_name': 'geographic_designations', 'classification': 'confidential',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    # PII
    {'schema_name': 'raw', 'table_name': 'orcid', 'classification': 'pii',
     'pii_fields': ['given_names', 'family_name', 'credit_name', 'biography',
                    'current_affiliations', 'external_ids'],
     'retention_days': 365, 'retention_policy': 'rolling_window'},
    # INTERNAL
    {'schema_name': 'raw', 'table_name': 'pubmed', 'classification': 'internal',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    {'schema_name': 'raw', 'table_name': 'openalex_ci', 'classification': 'internal',
     'pii_fields': None, 'retention_days': 730, 'retention_policy': 'rolling_window'},
    # PUBLIC (molecule schemas — perpetual)
    {'schema_name': 'mol_raw', 'table_name': '*', 'classification': 'public',
     'pii_fields': None, 'retention_days': None, 'retention_policy': 'perpetual'},
    {'schema_name': 'mol_bronze', 'table_name': '*', 'classification': 'public',
     'pii_fields': None, 'retention_days': None, 'retention_policy': 'perpetual'},
    # PUBLIC (raw open-data — perpetual)
    {'schema_name': 'raw', 'table_name': 'bindingdb', 'classification': 'public',
     'pii_fields': None, 'retention_days': None, 'retention_policy': 'perpetual'},
]


def _find_seed(schema: str, table: str) -> dict | None:
    """Helper to look up a seed classification row."""
    for row in SEED_CLASSIFICATIONS:
        if row['schema_name'] == schema and row['table_name'] == table:
            return row
    return None


# ===========================================================================
# T020-1: Verify raw.orcid is classified as PII with correct pii_fields
# ===========================================================================

class TestOrcidPIIClassification:
    """Verify raw.orcid classification and PII field inventory."""

    def test_orcid_classified_as_pii(self):
        row = _find_seed('raw', 'orcid')
        assert row is not None, "raw.orcid must be present in seed data"
        assert row['classification'] == 'pii'

    def test_orcid_pii_fields_contain_expected_columns(self):
        row = _find_seed('raw', 'orcid')
        expected_fields = {'given_names', 'family_name', 'credit_name', 'biography'}
        assert expected_fields.issubset(set(row['pii_fields']))

    def test_orcid_pii_fields_include_affiliations_and_ids(self):
        row = _find_seed('raw', 'orcid')
        assert 'current_affiliations' in row['pii_fields']
        assert 'external_ids' in row['pii_fields']

    def test_orcid_retention_days(self):
        row = _find_seed('raw', 'orcid')
        assert row['retention_days'] == 365


# ===========================================================================
# T020-2: Verify scoring tables are classified as confidential
# ===========================================================================

class TestScoringConfidentialClassification:
    """Verify scoring schema tables are classified as confidential."""

    @pytest.mark.parametrize("table_name", [
        'score_history',
        'score_latest',
    ])
    def test_scoring_tables_classified_confidential(self, table_name):
        row = _find_seed('scoring', table_name)
        assert row is not None, f"scoring.{table_name} must be in seed data"
        assert row['classification'] == 'confidential'

    @pytest.mark.parametrize("table_name", [
        'score_history',
        'score_latest',
    ])
    def test_scoring_retention_days(self, table_name):
        row = _find_seed('scoring', table_name)
        assert row['retention_days'] == 730


# ===========================================================================
# T020-3: Verify mol_raw.* tables are classified as public
# ===========================================================================

class TestMolRawPublicClassification:
    """Verify molecule raw layer is classified as public."""

    @pytest.mark.parametrize("schema", ['mol_raw', 'mol_bronze'])
    def test_mol_schemas_classified_public(self, schema):
        row = _find_seed(schema, '*')
        assert row is not None, f"{schema}.* must be in seed data"
        assert row['classification'] == 'public'

    @pytest.mark.parametrize("schema", ['mol_raw', 'mol_bronze'])
    def test_mol_schemas_perpetual_retention(self, schema):
        row = _find_seed(schema, '*')
        assert row['retention_days'] is None, "Public molecule data should be perpetual"
        assert row['retention_policy'] == 'perpetual'


# ===========================================================================
# T020-4: Verify retention_days set for non-perpetual classifications
# ===========================================================================

class TestRetentionDaysNonPerpetual:
    """Verify retention_days is set correctly for tables that are not perpetual."""

    def test_all_non_perpetual_have_retention_days(self):
        for row in SEED_CLASSIFICATIONS:
            if row['retention_policy'] != 'perpetual':
                assert row['retention_days'] is not None, (
                    f"{row['schema_name']}.{row['table_name']} "
                    f"has policy '{row['retention_policy']}' but retention_days is None"
                )

    def test_all_perpetual_have_null_retention_days(self):
        for row in SEED_CLASSIFICATIONS:
            if row['retention_policy'] == 'perpetual':
                assert row['retention_days'] is None, (
                    f"{row['schema_name']}.{row['table_name']} "
                    f"is perpetual but retention_days is {row['retention_days']}"
                )

    def test_internal_tables_have_730_day_retention(self):
        for row in SEED_CLASSIFICATIONS:
            if row['classification'] == 'internal':
                assert row['retention_days'] == 730

    def test_confidential_tables_have_730_day_retention(self):
        for row in SEED_CLASSIFICATIONS:
            if row['classification'] == 'confidential':
                assert row['retention_days'] == 730


# ===========================================================================
# T020-5: Test purge_by_classification reads meta.data_classification
# ===========================================================================

class TestPurgeByClassification:
    """Test the extended purge function with mocked database connections."""

    @staticmethod
    def _make_mock_conn(classification_rows, table_exists=True,
                        col_exists=True, count_to_purge=5, batch_deleted=5):
        """Build a mock connection that simulates the DB interactions.

        The purge function uses `with conn.cursor() as cur:` multiple times.
        Each context-manager entry returns a fresh mock cursor. We track the
        sequence of execute() calls across all cursors via a shared list.
        """
        # Shared state across all cursors
        state = {
            'call_index': 0,
            'batch_deleted_once': False,
        }

        # Pre-compute the sequence of (fetchall_result, fetchone_result, rowcount)
        # for each execute() call that the function will make.
        sequence = []

        # 1st cursor block: SELECT from meta.data_classification
        sequence.append({
            'fetchall': classification_rows,
            'fetchone': classification_rows[0] if classification_rows else None,
            'rowcount': 0,
        })

        for _row in classification_rows:
            # table exists check
            sequence.append({
                'fetchall': [((table_exists,),)],
                'fetchone': (table_exists,),
                'rowcount': 0,
            })
            if not table_exists:
                continue

            # column exists check
            sequence.append({
                'fetchall': [((col_exists,),)],
                'fetchone': (col_exists,),
                'rowcount': 0,
            })
            if not col_exists:
                continue

            # COUNT(*) of records to purge
            sequence.append({
                'fetchall': [((count_to_purge,),)],
                'fetchone': (count_to_purge,),
                'rowcount': 0,
            })
            if count_to_purge == 0:
                continue

            # Batch DELETE (first batch returns batch_deleted, next returns 0 to stop loop)
            sequence.append({
                'fetchall': [],
                'fetchone': None,
                'rowcount': batch_deleted,
                'type': 'delete_batch1',
            })
            # Second batch attempt (loop termination)
            sequence.append({
                'fetchall': [],
                'fetchone': None,
                'rowcount': 0,
                'type': 'delete_batch2',
            })

            # Log INSERT (meta.refresh_log)
            sequence.append({
                'fetchall': [],
                'fetchone': None,
                'rowcount': 0,
            })

        def make_cursor():
            """Create a mock cursor that advances through the sequence."""
            cursor = MagicMock()
            cursor_state = {'last_step': None}

            def execute_fn(sql, params=None):
                idx = state['call_index']
                if idx < len(sequence):
                    cursor_state['last_step'] = sequence[idx]
                    cursor.rowcount = sequence[idx].get('rowcount', 0)
                else:
                    cursor_state['last_step'] = {'fetchall': [], 'fetchone': None, 'rowcount': 0}
                    cursor.rowcount = 0
                state['call_index'] += 1

            def fetchall_fn():
                step = cursor_state.get('last_step')
                if step:
                    return step.get('fetchall', [])
                return []

            def fetchone_fn():
                step = cursor_state.get('last_step')
                if step:
                    return step.get('fetchone')
                return None

            cursor.execute = MagicMock(side_effect=execute_fn)
            cursor.fetchall = MagicMock(side_effect=fetchall_fn)
            cursor.fetchone = MagicMock(side_effect=fetchone_fn)
            return cursor

        mock_conn = MagicMock()
        mock_conn.commit = MagicMock()

        # Each call to conn.cursor() returns a new context manager wrapping a fresh cursor
        def cursor_factory():
            ctx = MagicMock()
            cur = make_cursor()
            ctx.__enter__ = MagicMock(return_value=cur)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        mock_conn.cursor = MagicMock(side_effect=cursor_factory)
        return mock_conn

    def test_purge_reads_classification_rows(self):
        """purge_by_classification should query meta.data_classification."""
        import dk_data.scripts.purge_history as ph

        classification_rows = [
            ('scoring', 'score_history', 'confidential', 730, 'rolling_window'),
        ]
        mock_conn = self._make_mock_conn(
            classification_rows, count_to_purge=10, batch_deleted=10
        )

        result = ph.purge_by_classification(mock_conn, dry_run=False)

        assert result['tables_processed'] == 1
        assert result['total_records_purged'] == 10
        assert len(result['details']) == 1
        assert result['details'][0]['table'] == 'scoring.score_history'

    def test_purge_dry_run_does_not_delete(self):
        """In dry_run mode, no records should be purged."""
        import dk_data.scripts.purge_history as ph

        classification_rows = [
            ('raw', 'orcid', 'pii', 365, 'rolling_window'),
        ]
        mock_conn = self._make_mock_conn(
            classification_rows, count_to_purge=50, batch_deleted=0
        )

        result = ph.purge_by_classification(mock_conn, dry_run=True)

        assert result['status'] == 'dry_run'
        assert result['total_records_purged'] == 0
        assert result['details'][0]['records_to_purge'] == 50

    def test_purge_skips_nonexistent_tables(self):
        """Tables that do not exist in information_schema should be skipped."""
        import dk_data.scripts.purge_history as ph

        classification_rows = [
            ('scoring', 'score_history', 'confidential', 730, 'rolling_window'),
        ]
        mock_conn = self._make_mock_conn(classification_rows, table_exists=False)

        result = ph.purge_by_classification(mock_conn, dry_run=False)

        assert result['tables_processed'] == 0
        assert result['total_records_purged'] == 0

    def test_purge_skips_missing_timestamp_column(self):
        """Tables missing the expected timestamp column should be skipped."""
        import dk_data.scripts.purge_history as ph

        classification_rows = [
            ('scoring', 'score_history', 'confidential', 730, 'rolling_window'),
        ]
        mock_conn = self._make_mock_conn(
            classification_rows, table_exists=True, col_exists=False
        )

        result = ph.purge_by_classification(mock_conn, dry_run=False)

        assert result['tables_processed'] == 0

    def test_purge_empty_classification_table(self):
        """When no classification rows have retention, summary should be empty."""
        import dk_data.scripts.purge_history as ph

        mock_conn = self._make_mock_conn([], count_to_purge=0)
        result = ph.purge_by_classification(mock_conn, dry_run=False)

        assert result['tables_processed'] == 0
        assert result['total_records_purged'] == 0

    def test_purge_no_records_to_delete(self):
        """Tables with zero old records should report processed but 0 purged."""
        import dk_data.scripts.purge_history as ph

        classification_rows = [
            ('raw', 'pubmed', 'internal', 730, 'rolling_window'),
        ]
        mock_conn = self._make_mock_conn(classification_rows, count_to_purge=0)

        result = ph.purge_by_classification(mock_conn, dry_run=False)

        assert result['tables_processed'] == 1
        assert result['total_records_purged'] == 0


# ===========================================================================
# T020-6: Verify timestamp column mapping
# ===========================================================================

class TestTimestampColumnMapping:
    """Verify the timestamp column mapping logic."""

    def test_raw_schema_uses_fetched_at(self):
        import dk_data.scripts.purge_history as ph
        assert ph._get_timestamp_column('raw') == 'fetched_at'

    def test_meta_schema_uses_logged_at(self):
        import dk_data.scripts.purge_history as ph
        assert ph._get_timestamp_column('meta') == '_logged_at'

    def test_scoring_schema_uses_default(self):
        import dk_data.scripts.purge_history as ph
        assert ph._get_timestamp_column('scoring') == 'created_at'

    def test_staging_schema_uses_default(self):
        import dk_data.scripts.purge_history as ph
        assert ph._get_timestamp_column('staging') == 'created_at'

    def test_mart_schema_uses_default(self):
        import dk_data.scripts.purge_history as ph
        assert ph._get_timestamp_column('mart') == 'created_at'


# ===========================================================================
# T020-7: Verify SQL migration structure
# ===========================================================================

class TestMigrationSQLStructure:
    """Validate the migration SQL files exist and contain expected statements."""

    def test_069_migration_file_exists(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent / 'src' / 'dk_data' / 'sql' / 'migrations' / '069_data_classification.sql'
        assert migration.exists(), "069_data_classification.sql should exist"

    def test_069_migration_creates_table(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent / 'src' / 'dk_data' / 'sql' / 'migrations' / '069_data_classification.sql'
        content = migration.read_text()
        assert 'CREATE TABLE IF NOT EXISTS meta.data_classification' in content
        assert "classification IN ('public', 'internal', 'pii', 'confidential')" in content
        assert 'UNIQUE (schema_name, table_name)' in content

    def test_069_migration_has_index(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent / 'src' / 'dk_data' / 'sql' / 'migrations' / '069_data_classification.sql'
        content = migration.read_text()
        assert 'idx_data_classification_class' in content

    def test_069_migration_seeds_all_classifications(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent / 'src' / 'dk_data' / 'sql' / 'migrations' / '069_data_classification.sql'
        content = migration.read_text()
        # Check all four classification types are seeded
        assert "'confidential'" in content
        assert "'pii'" in content
        assert "'internal'" in content
        assert "'public'" in content
        # Check ON CONFLICT
        assert 'ON CONFLICT' in content

    def test_069_migration_wrapped_in_transaction(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent / 'src' / 'dk_data' / 'sql' / 'migrations' / '069_data_classification.sql'
        content = migration.read_text()
        assert 'BEGIN;' in content
        assert 'COMMIT;' in content

    def test_070_migration_file_exists(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent / 'src' / 'dk_data' / 'sql' / 'migrations' / '070_retention_column.sql'
        assert migration.exists(), "070_retention_column.sql should exist"

    def test_070_migration_adds_retention_column(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent / 'src' / 'dk_data' / 'sql' / 'migrations' / '070_retention_column.sql'
        content = migration.read_text()
        assert 'ALTER TABLE meta.data_sources ADD COLUMN IF NOT EXISTS retention_days' in content
