"""Tests for CMS Facility MVP fetchers and loaders.

Feature: 016-cms-puf-datasource-integration
Task: T065

Verifies:
- All 10 CMS facility fetchers inherit from BaseFetcher
- SOURCE_NAME and BASE_URL are set
- All 10 facility source loaders have Pydantic models and load functions
"""

import pytest


FACILITY_FETCHERS = [
    ("cms_pos", "CMSPOSFetcher", "cms_pos"),
    ("cms_pecos", "CMSPECOSFetcher", "cms_pecos"),
    ("cms_chow", "CMSCHOWFetcher", "cms_chow"),
    ("cms_hospital_affiliation", "CMSHospitalAffiliationFetcher", "cms_hospital_affiliation"),
    ("cms_inpatient_puf", "CMSInpatientPUFFetcher", "cms_inpatient_puf"),
    ("cms_outpatient_puf", "CMSOutpatientPUFFetcher", "cms_outpatient_puf"),
    ("cms_hospital_quality", "CMSHospitalQualityFetcher", "cms_hospital_quality"),
    ("cms_hospital_general_info", "CMSHospitalGeneralInfoFetcher", "cms_hospital_general_info"),
    ("cms_hcris", "CMSHCRISFetcher", "cms_hcris"),
    ("cms_magnet", "CMSMagnetFetcher", "cms_magnet"),
]

FACILITY_LOADERS = [
    "cms_pos",
    "cms_pecos",
    "cms_chow",
    "cms_hospital_affiliation",
    "cms_inpatient_puf",
    "cms_outpatient_puf",
    "cms_hospital_quality",
    "cms_hospital_general_info",
    "cms_hcris",
    "cms_magnet",
]


class TestFacilityFetcherInheritance:
    """Verify all facility fetchers inherit from BaseFetcher."""

    @pytest.mark.parametrize("module,cls_name,source_name", FACILITY_FETCHERS)
    def test_inherits_base_fetcher(self, module, cls_name, source_name):
        import importlib
        from dk_data.ingestion.fetchers.base import BaseFetcher
        mod = importlib.import_module(f"dk_data.ingestion.fetchers.{module}")
        cls = getattr(mod, cls_name)
        assert issubclass(cls, BaseFetcher)

    @pytest.mark.parametrize("module,cls_name,source_name", FACILITY_FETCHERS)
    def test_source_name(self, module, cls_name, source_name):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.fetchers.{module}")
        cls = getattr(mod, cls_name)
        assert cls.SOURCE_NAME == source_name

    @pytest.mark.parametrize("module,cls_name,source_name", FACILITY_FETCHERS)
    def test_base_url_set(self, module, cls_name, source_name):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.fetchers.{module}")
        cls = getattr(mod, cls_name)
        assert cls.BASE_URL != ""

    @pytest.mark.parametrize("module,cls_name,source_name", FACILITY_FETCHERS)
    def test_has_fetch_method(self, module, cls_name, source_name):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.fetchers.{module}")
        cls = getattr(mod, cls_name)
        assert callable(getattr(cls, "fetch", None))


class TestAllFacilityFetchersRegistered:
    """Verify all facility fetchers are importable from __init__.py."""

    def test_all_importable(self):
        from dk_data.ingestion.fetchers import (
            CMSPOSFetcher,
            CMSPECOSFetcher,
            CMSCHOWFetcher,
            CMSHospitalAffiliationFetcher,
            CMSInpatientPUFFetcher,
            CMSOutpatientPUFFetcher,
            CMSHospitalQualityFetcher,
            CMSHospitalGeneralInfoFetcher,
            CMSHCRISFetcher,
            CMSMagnetFetcher,
        )
        assert all([
            CMSPOSFetcher,
            CMSPECOSFetcher,
            CMSCHOWFetcher,
            CMSHospitalAffiliationFetcher,
            CMSInpatientPUFFetcher,
            CMSOutpatientPUFFetcher,
            CMSHospitalQualityFetcher,
            CMSHospitalGeneralInfoFetcher,
            CMSHCRISFetcher,
            CMSMagnetFetcher,
        ])


class TestFacilityLoaders:
    """Verify all facility source loaders have load functions."""

    @pytest.mark.parametrize("source", FACILITY_LOADERS)
    def test_load_function_exists(self, source):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.sources.{source}")
        func_name = f"load_{source}_data"
        assert hasattr(mod, func_name), f"Missing {func_name} in sources/{source}.py"

    @pytest.mark.parametrize("source", FACILITY_LOADERS)
    def test_has_pydantic_model(self, source):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.sources.{source}")
        model_classes = [
            name for name in dir(mod)
            if name.startswith("Cms") and not name.startswith("__")
        ]
        assert len(model_classes) > 0, f"No Pydantic model found in sources/{source}.py"
