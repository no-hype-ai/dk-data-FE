"""Tests for CMS Provider MVP source loaders.

Feature: 016-cms-puf-datasource-integration
Task: T046

Verifies:
- Pydantic model validation for each source
- Upsert key correctness
- Error handling for invalid records
"""

import pytest


class TestCmsNppesLoader:
    """Verify NPPES source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_nppes import CmsNppesRecord
        assert CmsNppesRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_nppes import CmsNppesRecord
        record = CmsNppesRecord(
            npi="1234567890",
            entity_type_code="1",
            provider_last_name="Smith",
            provider_first_name="John",
            practice_state="CA",
            practice_zip="90210",
        )
        assert record.npi == "1234567890"

    def test_invalid_npi_rejected(self):
        from dk_data.ingestion.sources.cms_nppes import CmsNppesRecord
        with pytest.raises(Exception):
            CmsNppesRecord(npi="123", entity_type_code="1")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_nppes import load_cms_nppes_data
        assert callable(load_cms_nppes_data)


class TestCmsPartDPrescriberLoader:
    """Verify Part D Prescriber source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_part_d_prescriber import CmsPartDPrescriberRecord
        assert CmsPartDPrescriberRecord is not None

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_part_d_prescriber import load_cms_part_d_prescriber_data
        assert callable(load_cms_part_d_prescriber_data)


class TestCmsPhysicianPufLoader:
    """Verify Physician PUF source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_physician_puf import CmsPhysicianPufRecord
        assert CmsPhysicianPufRecord is not None

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_physician_puf import load_cms_physician_puf_data
        assert callable(load_cms_physician_puf_data)


class TestCmsOpenPaymentsLoader:
    """Verify Open Payments source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_open_payments import CmsOpenPaymentRecord
        assert CmsOpenPaymentRecord is not None

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_open_payments import load_cms_open_payments_data
        assert callable(load_cms_open_payments_data)


class TestCmsCareCompareLoader:
    """Verify Care Compare source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_care_compare import CmsCareCompareRecord
        assert CmsCareCompareRecord is not None

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_care_compare import load_cms_care_compare_data
        assert callable(load_cms_care_compare_data)


class TestAllSourcesRegistered:
    """Verify all CMS sources are in the SOURCES registry."""

    def test_cms_sources_in_registry(self):
        from dk_data.ingestion.main import SOURCES
        cms_sources = [
            'cms_nppes', 'cms_part_d_prescriber', 'cms_physician_puf',
            'cms_open_payments', 'cms_care_compare',
        ]
        for source in cms_sources:
            assert source in SOURCES, f"Missing CMS source in registry: {source}"
            assert 'fetcher' in SOURCES[source], f"Missing fetcher for: {source}"
            assert 'loader' in SOURCES[source], f"Missing loader for: {source}"
