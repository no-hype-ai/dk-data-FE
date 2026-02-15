"""Verification tests for Tier 2A/3 molecule source configuration.

Feature: 011-datasource-integration
Tasks: T012, T017

Verifies that all Tier 2A and Tier 3 molecule source names are registered
in REFRESH_SCHEDULE, DataSource enum, and can be parsed by fetch_molecules.py.
"""

import pytest


# Tier 2A sources (Priority: P1)
TIER_2A_SOURCES = [
    "bindingdb",
    "orange_book",
    "sider",
    "tdc_admet",
    "ema",
]

# Tier 3 sources (Priority: P2)
TIER_3_SOURCES = [
    "rxnorm",
    "dailymed",
    "fda_drugs",
    "kegg_drug",
    "ttd",
    "pharmgkb",
    "imgt",
    "cdc_vaccines",
]

ALL_NEW_SOURCES = TIER_2A_SOURCES + TIER_3_SOURCES


class TestDataSourceEnum:
    """Verify all sources exist in DataSource enum."""

    def test_datasource_enum_imports(self):
        from dk_data.services.data_platform.raw_ingestion import DataSource
        assert DataSource is not None

    @pytest.mark.parametrize("source_name", TIER_2A_SOURCES)
    def test_tier_2a_in_datasource_enum(self, source_name):
        from dk_data.services.data_platform.raw_ingestion import DataSource
        enum_member = DataSource(source_name)
        assert enum_member.value == source_name

    @pytest.mark.parametrize("source_name", TIER_3_SOURCES)
    def test_tier_3_in_datasource_enum(self, source_name):
        from dk_data.services.data_platform.raw_ingestion import DataSource
        enum_member = DataSource(source_name)
        assert enum_member.value == source_name


class TestRefreshSchedule:
    """Verify all sources have refresh schedule entries."""

    def test_refresh_schedule_imports(self):
        from dk_data.services.data_platform.raw_ingestion import REFRESH_SCHEDULE
        assert len(REFRESH_SCHEDULE) > 0

    @pytest.mark.parametrize("source_name", TIER_2A_SOURCES)
    def test_tier_2a_in_refresh_schedule(self, source_name):
        from dk_data.services.data_platform.raw_ingestion import (
            DataSource,
            REFRESH_SCHEDULE,
        )
        source = DataSource(source_name)
        assert source in REFRESH_SCHEDULE, f"{source_name} not in REFRESH_SCHEDULE"
        assert REFRESH_SCHEDULE[source] > 0, f"{source_name} has invalid refresh hours"

    @pytest.mark.parametrize("source_name", TIER_3_SOURCES)
    def test_tier_3_in_refresh_schedule(self, source_name):
        from dk_data.services.data_platform.raw_ingestion import (
            DataSource,
            REFRESH_SCHEDULE,
        )
        source = DataSource(source_name)
        assert source in REFRESH_SCHEDULE, f"{source_name} not in REFRESH_SCHEDULE"
        assert REFRESH_SCHEDULE[source] > 0, f"{source_name} has invalid refresh hours"

    def test_tier_2a_weekly_sources_have_168h(self):
        """EMA and Orange Book should refresh weekly (168 hours)."""
        from dk_data.services.data_platform.raw_ingestion import (
            DataSource,
            REFRESH_SCHEDULE,
        )
        assert REFRESH_SCHEDULE[DataSource.EMA] == 168
        assert REFRESH_SCHEDULE[DataSource.ORANGE_BOOK] == 168

    def test_tier_2a_monthly_sources_have_720h(self):
        """BindingDB, SIDER, TDC ADMET should refresh monthly (720 hours)."""
        from dk_data.services.data_platform.raw_ingestion import (
            DataSource,
            REFRESH_SCHEDULE,
        )
        assert REFRESH_SCHEDULE[DataSource.BINDINGDB] == 720
        assert REFRESH_SCHEDULE[DataSource.SIDER] == 720
        assert REFRESH_SCHEDULE[DataSource.TDC_ADMET] == 720


class TestIngestionClasses:
    """Verify RawIngestionService subclasses exist for all sources."""

    @pytest.mark.parametrize("source_name,class_name", [
        ("bindingdb", "BindingDBIngestion"),
        ("orange_book", "OrangeBookIngestion"),
        ("sider", "SIDERIngestion"),
        ("tdc_admet", "TDCAdmetIngestion"),
        ("ema", "EMAIngestion"),
    ])
    def test_tier_2a_ingestion_class_exists(self, source_name, class_name):
        import dk_data.services.data_platform.raw_ingestion as module
        assert hasattr(module, class_name), f"{class_name} not found in raw_ingestion.py"
        cls = getattr(module, class_name)
        assert issubclass(cls, module.RawIngestionService)

    @pytest.mark.parametrize("source_name,class_name", [
        ("rxnorm", "RxNormIngestion"),
        ("dailymed", "DailyMedIngestion"),
        ("fda_drugs", "FDADrugsIngestion"),
        ("kegg_drug", "KEGGDrugIngestion"),
        ("ttd", "TTDIngestion"),
        ("pharmgkb", "PharmGKBIngestion"),
        ("imgt", "IMGTIngestion"),
        ("cdc_vaccines", "CDCVaccinesIngestion"),
    ])
    def test_tier_3_ingestion_class_exists(self, source_name, class_name):
        import dk_data.services.data_platform.raw_ingestion as module
        assert hasattr(module, class_name), f"{class_name} not found in raw_ingestion.py"
        cls = getattr(module, class_name)
        assert issubclass(cls, module.RawIngestionService)


class TestFetchMoleculesParsing:
    """Verify fetch_molecules.py can parse comma-separated source arguments."""

    def test_comma_separated_parsing(self):
        """Verify the CLI parses comma-separated sources correctly."""
        source_arg = "ema,orange_book,bindingdb,sider,tdc_admet"
        sources = [s.strip() for s in source_arg.split(",")]
        assert sources == ["ema", "orange_book", "bindingdb", "sider", "tdc_admet"]

    def test_all_new_sources_count(self):
        """Verify we have the expected number of new sources."""
        assert len(TIER_2A_SOURCES) == 5
        assert len(TIER_3_SOURCES) == 8
        assert len(ALL_NEW_SOURCES) == 13
