"""Tests for CMS Drug/Market MVP fetchers and loaders.

Feature: 016-cms-puf-datasource-integration
Task: T078

Verifies:
- All 13 CMS drug/market fetchers inherit from BaseFetcher
- SOURCE_NAME and BASE_URL are set
- All 13 drug/market source loaders have Pydantic models and load functions
"""

import pytest


DRUG_MARKET_FETCHERS = [
    ("cms_ndc", "CMSNDCFetcher", "cms_ndc"),
    ("cms_part_d_spending", "CMSPartDSpendingFetcher", "cms_part_d_spending"),
    ("cms_part_b_spending", "CMSPartBSpendingFetcher", "cms_part_b_spending"),
    ("cms_formulary", "CMSFormularyFetcher", "cms_formulary"),
    ("cms_rbcs", "CMSRBCSFetcher", "cms_rbcs"),
    ("cms_usp", "CMSUSPFetcher", "cms_usp"),
    ("cms_nucc", "CMSNUCCFetcher", "cms_nucc"),
    ("cms_geographic_variation", "CMSGeographicVariationFetcher", "cms_geographic_variation"),
    ("cms_chronic_conditions", "CMSChronicConditionsFetcher", "cms_chronic_conditions"),
    ("cms_post_acute", "CMSPostAcuteFetcher", "cms_post_acute"),
    ("cms_dmepos", "CMSDMEPOSFetcher", "cms_dmepos"),
    ("cms_ddinter", "CMSDDInterFetcher", "cms_ddinter"),
    ("cms_stabilis", "CMSStabilisFetcher", "cms_stabilis"),
]

DRUG_MARKET_LOADERS = [
    "cms_ndc",
    "cms_part_d_spending",
    "cms_part_b_spending",
    "cms_formulary",
    "cms_rbcs",
    "cms_usp",
    "cms_nucc",
    "cms_geographic_variation",
    "cms_chronic_conditions",
    "cms_post_acute",
    "cms_dmepos",
    "cms_ddinter",
    "cms_stabilis",
]


class TestDrugMarketFetcherInheritance:
    """Verify all drug/market fetchers inherit from BaseFetcher."""

    @pytest.mark.parametrize("module,cls_name,source_name", DRUG_MARKET_FETCHERS)
    def test_inherits_base_fetcher(self, module, cls_name, source_name):
        import importlib
        from dk_data.ingestion.fetchers.base import BaseFetcher
        mod = importlib.import_module(f"dk_data.ingestion.fetchers.{module}")
        cls = getattr(mod, cls_name)
        assert issubclass(cls, BaseFetcher)

    @pytest.mark.parametrize("module,cls_name,source_name", DRUG_MARKET_FETCHERS)
    def test_source_name(self, module, cls_name, source_name):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.fetchers.{module}")
        cls = getattr(mod, cls_name)
        assert cls.SOURCE_NAME == source_name

    @pytest.mark.parametrize("module,cls_name,source_name", DRUG_MARKET_FETCHERS)
    def test_base_url_set(self, module, cls_name, source_name):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.fetchers.{module}")
        cls = getattr(mod, cls_name)
        assert cls.BASE_URL != ""

    @pytest.mark.parametrize("module,cls_name,source_name", DRUG_MARKET_FETCHERS)
    def test_has_fetch_method(self, module, cls_name, source_name):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.fetchers.{module}")
        cls = getattr(mod, cls_name)
        assert callable(getattr(cls, "fetch", None))


class TestAllDrugMarketFetchersRegistered:
    """Verify all drug/market fetchers are importable from __init__.py."""

    def test_all_importable(self):
        from dk_data.ingestion.fetchers import (
            CMSNDCFetcher,
            CMSPartDSpendingFetcher,
            CMSPartBSpendingFetcher,
            CMSFormularyFetcher,
            CMSRBCSFetcher,
            CMSUSPFetcher,
            CMSNUCCFetcher,
            CMSGeographicVariationFetcher,
            CMSChronicConditionsFetcher,
            CMSPostAcuteFetcher,
            CMSDMEPOSFetcher,
            CMSDDInterFetcher,
            CMSStabilisFetcher,
        )
        assert all([
            CMSNDCFetcher,
            CMSPartDSpendingFetcher,
            CMSPartBSpendingFetcher,
            CMSFormularyFetcher,
            CMSRBCSFetcher,
            CMSUSPFetcher,
            CMSNUCCFetcher,
            CMSGeographicVariationFetcher,
            CMSChronicConditionsFetcher,
            CMSPostAcuteFetcher,
            CMSDMEPOSFetcher,
            CMSDDInterFetcher,
            CMSStabilisFetcher,
        ])


class TestDrugMarketLoaders:
    """Verify all drug/market source loaders have load functions."""

    @pytest.mark.parametrize("source", DRUG_MARKET_LOADERS)
    def test_load_function_exists(self, source):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.sources.{source}")
        func_name = f"load_{source}_data"
        assert hasattr(mod, func_name), f"Missing {func_name} in sources/{source}.py"

    @pytest.mark.parametrize("source", DRUG_MARKET_LOADERS)
    def test_has_pydantic_model(self, source):
        import importlib
        mod = importlib.import_module(f"dk_data.ingestion.sources.{source}")
        model_classes = [
            name for name in dir(mod)
            if name.startswith("Cms") and not name.startswith("__")
        ]
        assert len(model_classes) > 0, f"No Pydantic model found in sources/{source}.py"
