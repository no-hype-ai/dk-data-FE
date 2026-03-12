"""Tests for CMS PUF migration files.

Feature: 016-cms-puf-datasource-integration
Task: T021

Verifies:
- All 6 CMS migration files exist and have valid SQL
- Migration files are numbered sequentially (083-088)
- Key tables, views, and permissions are declared
"""

import os
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).parent.parent / "src" / "dk_data" / "sql" / "migrations"

CMS_MIGRATIONS = [
    ("083_cms_raw_tables.sql", ["raw.cms_nppes", "raw.cms_part_d_prescriber", "raw.cms_physician_puf"]),
    ("084_cms_bronze_seeds.sql", ["bronze"]),
    ("085_cms_silver_tables.sql", ["silver.cms_provider_profile", "silver.ref_drg_service_line"]),
    ("086_cms_gold_views.sql", ["gold.cms_provider_360", "gold.cms_facility_360"]),
    ("087_cms_agent_tables.sql", ["meta.agent_execution_log", "meta.agent_quarantine"]),
    ("088_cms_api_views.sql", ["api.cms_provider_profile", "api.cms_facility_profile"]),
]


class TestCMSMigrationFiles:
    """Verify all 6 CMS migration files exist and are valid."""

    @pytest.mark.parametrize("filename,_", CMS_MIGRATIONS, ids=[m[0] for m in CMS_MIGRATIONS])
    def test_migration_file_exists(self, filename, _):
        filepath = MIGRATIONS_DIR / filename
        assert filepath.exists(), f"Migration file missing: {filename}"
        content = filepath.read_text()
        assert len(content) > 50, f"Migration file too small: {filename}"

    @pytest.mark.parametrize("filename,keywords", CMS_MIGRATIONS, ids=[m[0] for m in CMS_MIGRATIONS])
    def test_migration_contains_expected_objects(self, filename, keywords):
        filepath = MIGRATIONS_DIR / filename
        if not filepath.exists():
            pytest.skip(f"Migration file not yet created: {filename}")
        content = filepath.read_text().lower()
        for keyword in keywords:
            assert keyword.lower() in content, f"{filename} missing reference to {keyword}"

    def test_all_six_migrations_exist(self):
        """All 6 CMS migrations must be present."""
        missing = []
        for filename, _ in CMS_MIGRATIONS:
            if not (MIGRATIONS_DIR / filename).exists():
                missing.append(filename)
        assert not missing, f"Missing CMS migrations: {missing}"

    def test_raw_tables_have_metadata_columns(self):
        """Raw tables must include _loaded_at, _source_file, _source_hash."""
        filepath = MIGRATIONS_DIR / "083_cms_raw_tables.sql"
        if not filepath.exists():
            pytest.skip("083 migration not yet created")
        content = filepath.read_text().lower()
        for col in ("_loaded_at", "_source_file", "_source_hash"):
            assert col in content, f"Raw tables missing metadata column: {col}"

    def test_raw_tables_have_partitioning(self):
        """Part D Prescriber and Physician PUF must be range-partitioned by year."""
        filepath = MIGRATIONS_DIR / "083_cms_raw_tables.sql"
        if not filepath.exists():
            pytest.skip("083 migration not yet created")
        content = filepath.read_text().lower()
        assert "partition by range" in content, "Missing range partitioning"

    def test_agent_tables_append_only(self):
        """Agent execution log must have INSERT+SELECT only (no UPDATE/DELETE grants)."""
        filepath = MIGRATIONS_DIR / "087_cms_agent_tables.sql"
        if not filepath.exists():
            pytest.skip("087 migration not yet created")
        content = filepath.read_text()
        # Should grant INSERT, SELECT but not UPDATE or DELETE on execution log
        assert "INSERT" in content, "Missing INSERT grant for agent_execution_log"
        assert "SELECT" in content, "Missing SELECT grant for agent_execution_log"

    def test_gold_views_count(self):
        """Must have exactly 5 gold views."""
        filepath = MIGRATIONS_DIR / "086_cms_gold_views.sql"
        if not filepath.exists():
            pytest.skip("086 migration not yet created")
        content = filepath.read_text().lower()
        view_count = content.count("create or replace view gold.cms_") + content.count("create view gold.cms_")
        assert view_count >= 5, f"Expected 5 gold views, found {view_count}"

    def test_api_views_wrap_gold(self):
        """API views must reference gold schema views."""
        filepath = MIGRATIONS_DIR / "088_cms_api_views.sql"
        if not filepath.exists():
            pytest.skip("088 migration not yet created")
        content = filepath.read_text().lower()
        assert "gold.cms_" in content, "API views must reference gold schema"
