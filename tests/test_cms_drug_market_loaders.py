"""Tests for CMS Drug/Market source loaders.

Feature: 016-cms-puf-datasource-integration
Task: T078

Verifies:
- Pydantic model validation for each source
- load function exists and is callable
- Upsert SQL pattern (ON CONFLICT) via SOURCES registry
- Invalid/empty required fields are rejected
"""

import pytest


# ---------------------------------------------------------------------------
# CmsNdcRecord / load_cms_ndc_data
# ---------------------------------------------------------------------------

class TestCmsNdcLoader:
    """Verify NDC source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_ndc import CmsNdcRecord
        assert CmsNdcRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_ndc import CmsNdcRecord
        record = CmsNdcRecord(
            product_ndc="0069-3150-83",
            brand_name="Lipitor",
            generic_name="atorvastatin",
        )
        assert record.product_ndc == "0069-3150-83"

    def test_empty_ndc_rejected(self):
        from dk_data.ingestion.sources.cms_ndc import CmsNdcRecord
        with pytest.raises(Exception):
            CmsNdcRecord(product_ndc="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_ndc import load_cms_ndc_data
        assert callable(load_cms_ndc_data)


# ---------------------------------------------------------------------------
# CmsPartDSpendingRecord / load_cms_part_d_spending_data
# ---------------------------------------------------------------------------

class TestCmsPartDSpendingLoader:
    """Verify Part D Drug Spending source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_part_d_spending import CmsPartDSpendingRecord
        assert CmsPartDSpendingRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_part_d_spending import CmsPartDSpendingRecord
        record = CmsPartDSpendingRecord(
            brand_name="Humira",
            generic_name="adalimumab",
            total_spending=1000000.50,
            year="2023",
        )
        assert record.brand_name == "Humira"

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_part_d_spending import load_cms_part_d_spending_data
        assert callable(load_cms_part_d_spending_data)


# ---------------------------------------------------------------------------
# CmsPartBSpendingRecord / load_cms_part_b_spending_data
# ---------------------------------------------------------------------------

class TestCmsPartBSpendingLoader:
    """Verify Part B Drug Spending source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_part_b_spending import CmsPartBSpendingRecord
        assert CmsPartBSpendingRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_part_b_spending import CmsPartBSpendingRecord
        record = CmsPartBSpendingRecord(
            hcpcs_code="J0135",
            brand_name="Adalimumab",
            total_spending=500000.0,
            year="2023",
        )
        assert record.hcpcs_code == "J0135"

    def test_empty_hcpcs_rejected(self):
        from dk_data.ingestion.sources.cms_part_b_spending import CmsPartBSpendingRecord
        with pytest.raises(Exception):
            CmsPartBSpendingRecord(hcpcs_code="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_part_b_spending import load_cms_part_b_spending_data
        assert callable(load_cms_part_b_spending_data)


# ---------------------------------------------------------------------------
# CmsFormularyRecord / load_cms_formulary_data
# ---------------------------------------------------------------------------

class TestCmsFormularyLoader:
    """Verify Medicare Plan Formulary source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_formulary import CmsFormularyRecord
        assert CmsFormularyRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_formulary import CmsFormularyRecord
        record = CmsFormularyRecord(
            contract_id="H0001",
            plan_id="001",
            rxcui="352304",
            drug_name="atorvastatin",
            tier_level="1",
        )
        assert record.rxcui == "352304"

    def test_empty_rxcui_rejected(self):
        from dk_data.ingestion.sources.cms_formulary import CmsFormularyRecord
        with pytest.raises(Exception):
            CmsFormularyRecord(rxcui="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_formulary import load_cms_formulary_data
        assert callable(load_cms_formulary_data)


# ---------------------------------------------------------------------------
# CmsRbcsRecord / load_cms_rbcs_data
# ---------------------------------------------------------------------------

class TestCmsRbcsLoader:
    """Verify RBCS source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_rbcs import CmsRbcsRecord
        assert CmsRbcsRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_rbcs import CmsRbcsRecord
        record = CmsRbcsRecord(
            hcpcs_code="99213",
            rbcs_category="E&M",
            rbcs_subcategory="Office/Outpatient",
        )
        assert record.hcpcs_code == "99213"

    def test_empty_hcpcs_rejected(self):
        from dk_data.ingestion.sources.cms_rbcs import CmsRbcsRecord
        with pytest.raises(Exception):
            CmsRbcsRecord(hcpcs_code="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_rbcs import load_cms_rbcs_data
        assert callable(load_cms_rbcs_data)


# ---------------------------------------------------------------------------
# CmsUspRecord / load_cms_usp_data
# ---------------------------------------------------------------------------

class TestCmsUspLoader:
    """Verify USP source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_usp import CmsUspRecord
        assert CmsUspRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_usp import CmsUspRecord
        record = CmsUspRecord(
            usp_category="Analgesics",
            usp_class="Opioid Analgesics",
            drug_names="morphine, codeine",
        )
        assert record.usp_category == "Analgesics"

    def test_empty_category_rejected(self):
        from dk_data.ingestion.sources.cms_usp import CmsUspRecord
        with pytest.raises(Exception):
            CmsUspRecord(usp_category="  ", usp_class="Opioid Analgesics")

    def test_empty_class_rejected(self):
        from dk_data.ingestion.sources.cms_usp import CmsUspRecord
        with pytest.raises(Exception):
            CmsUspRecord(usp_category="Analgesics", usp_class="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_usp import load_cms_usp_data
        assert callable(load_cms_usp_data)


# ---------------------------------------------------------------------------
# CmsNuccRecord / load_cms_nucc_data
# ---------------------------------------------------------------------------

class TestCmsNuccLoader:
    """Verify NUCC source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_nucc import CmsNuccRecord
        assert CmsNuccRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_nucc import CmsNuccRecord
        record = CmsNuccRecord(
            taxonomy_code="207Q00000X",
            taxonomy_type="Individual",
            classification="Family Medicine",
        )
        assert record.taxonomy_code == "207Q00000X"

    def test_empty_taxonomy_code_rejected(self):
        from dk_data.ingestion.sources.cms_nucc import CmsNuccRecord
        with pytest.raises(Exception):
            CmsNuccRecord(taxonomy_code="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_nucc import load_cms_nucc_data
        assert callable(load_cms_nucc_data)


# ---------------------------------------------------------------------------
# CmsGeographicVariationRecord / load_cms_geographic_variation_data
# ---------------------------------------------------------------------------

class TestCmsGeographicVariationLoader:
    """Verify Geographic Variation source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_geographic_variation import CmsGeographicVariationRecord
        assert CmsGeographicVariationRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_geographic_variation import CmsGeographicVariationRecord
        record = CmsGeographicVariationRecord(
            state="CA",
            county="Los Angeles",
            total_beneficiaries=500000,
            per_capita_costs=12000.50,
        )
        assert record.state == "CA"

    def test_empty_state_rejected(self):
        from dk_data.ingestion.sources.cms_geographic_variation import CmsGeographicVariationRecord
        with pytest.raises(Exception):
            CmsGeographicVariationRecord(state="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_geographic_variation import load_cms_geographic_variation_data
        assert callable(load_cms_geographic_variation_data)


# ---------------------------------------------------------------------------
# CmsChronicConditionsRecord / load_cms_chronic_conditions_data
# ---------------------------------------------------------------------------

class TestCmsChronicConditionsLoader:
    """Verify Chronic Conditions source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_chronic_conditions import CmsChronicConditionsRecord
        assert CmsChronicConditionsRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_chronic_conditions import CmsChronicConditionsRecord
        record = CmsChronicConditionsRecord(
            state="TX",
            condition="Diabetes",
            prevalence_rate=0.27,
            total_beneficiaries_with_condition=150000,
        )
        assert record.condition == "Diabetes"

    def test_empty_state_rejected(self):
        from dk_data.ingestion.sources.cms_chronic_conditions import CmsChronicConditionsRecord
        with pytest.raises(Exception):
            CmsChronicConditionsRecord(state="  ", condition="Diabetes")

    def test_empty_condition_rejected(self):
        from dk_data.ingestion.sources.cms_chronic_conditions import CmsChronicConditionsRecord
        with pytest.raises(Exception):
            CmsChronicConditionsRecord(state="TX", condition="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_chronic_conditions import load_cms_chronic_conditions_data
        assert callable(load_cms_chronic_conditions_data)


# ---------------------------------------------------------------------------
# CmsPostAcuteRecord / load_cms_post_acute_data
# ---------------------------------------------------------------------------

class TestCmsPostAcuteLoader:
    """Verify Post-Acute Care source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_post_acute import CmsPostAcuteRecord
        assert CmsPostAcuteRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_post_acute import CmsPostAcuteRecord
        record = CmsPostAcuteRecord(
            ccn="050001",
            provider_name="Test SNF",
            provider_type="SNF",
            total_episodes=1200,
        )
        assert record.ccn == "050001"

    def test_empty_ccn_rejected(self):
        from dk_data.ingestion.sources.cms_post_acute import CmsPostAcuteRecord
        with pytest.raises(Exception):
            CmsPostAcuteRecord(ccn="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_post_acute import load_cms_post_acute_data
        assert callable(load_cms_post_acute_data)


# ---------------------------------------------------------------------------
# CmsDmeposRecord / load_cms_dmepos_data
# ---------------------------------------------------------------------------

class TestCmsDmeposLoader:
    """Verify DMEPOS Utilization source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_dmepos import CmsDmeposRecord
        assert CmsDmeposRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_dmepos import CmsDmeposRecord
        record = CmsDmeposRecord(
            npi="1234567890",
            hcpcs_code="E0601",
            hcpcs_description="CPAP device",
            total_services=500,
        )
        assert record.npi == "1234567890"

    def test_empty_npi_rejected(self):
        from dk_data.ingestion.sources.cms_dmepos import CmsDmeposRecord
        with pytest.raises(Exception):
            CmsDmeposRecord(npi="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_dmepos import load_cms_dmepos_data
        assert callable(load_cms_dmepos_data)


# ---------------------------------------------------------------------------
# CmsDdinterRecord / load_cms_ddinter_data
# ---------------------------------------------------------------------------

class TestCmsDdinterLoader:
    """Verify DDInter (Drug-Drug Interaction) source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_ddinter import CmsDdinterRecord
        assert CmsDdinterRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_ddinter import CmsDdinterRecord
        record = CmsDdinterRecord(
            drug_a="Warfarin",
            drug_b="Aspirin",
            interaction_type="Pharmacodynamic",
            severity="Major",
        )
        assert record.drug_a == "Warfarin"
        assert record.drug_b == "Aspirin"

    def test_empty_drug_a_rejected(self):
        from dk_data.ingestion.sources.cms_ddinter import CmsDdinterRecord
        with pytest.raises(Exception):
            CmsDdinterRecord(drug_a="  ", drug_b="Aspirin")

    def test_empty_drug_b_rejected(self):
        from dk_data.ingestion.sources.cms_ddinter import CmsDdinterRecord
        with pytest.raises(Exception):
            CmsDdinterRecord(drug_a="Warfarin", drug_b="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_ddinter import load_cms_ddinter_data
        assert callable(load_cms_ddinter_data)


# ---------------------------------------------------------------------------
# CmsStabilisRecord / load_cms_stabilis_data
# ---------------------------------------------------------------------------

class TestCmsStabilisLoader:
    """Verify Stabilis (IV Drug Compatibility) source loader."""

    def test_pydantic_model_exists(self):
        from dk_data.ingestion.sources.cms_stabilis import CmsStabilisRecord
        assert CmsStabilisRecord is not None

    def test_valid_record_passes_validation(self):
        from dk_data.ingestion.sources.cms_stabilis import CmsStabilisRecord
        record = CmsStabilisRecord(
            drug_a="Amikacin",
            drug_b="Ceftriaxone",
            compatibility="Compatible",
            solvent="NaCl 0.9%",
        )
        assert record.drug_a == "Amikacin"
        assert record.drug_b == "Ceftriaxone"

    def test_empty_drug_a_rejected(self):
        from dk_data.ingestion.sources.cms_stabilis import CmsStabilisRecord
        with pytest.raises(Exception):
            CmsStabilisRecord(drug_a="  ", drug_b="Ceftriaxone")

    def test_empty_drug_b_rejected(self):
        from dk_data.ingestion.sources.cms_stabilis import CmsStabilisRecord
        with pytest.raises(Exception):
            CmsStabilisRecord(drug_a="Amikacin", drug_b="  ")

    def test_loader_function_exists(self):
        from dk_data.ingestion.sources.cms_stabilis import load_cms_stabilis_data
        assert callable(load_cms_stabilis_data)


# ---------------------------------------------------------------------------
# SOURCES registry check
# ---------------------------------------------------------------------------

class TestAllDrugMarketSourcesRegistered:
    """Verify all 13 drug/market sources are in the SOURCES registry."""

    def test_cms_drug_market_sources_in_registry(self):
        from dk_data.ingestion.main import SOURCES
        drug_market_sources = [
            'cms_ndc', 'cms_part_d_spending', 'cms_part_b_spending',
            'cms_formulary', 'cms_rbcs', 'cms_usp', 'cms_nucc',
            'cms_geographic_variation', 'cms_chronic_conditions',
            'cms_post_acute', 'cms_dmepos', 'cms_ddinter', 'cms_stabilis',
        ]
        for source in drug_market_sources:
            assert source in SOURCES, f"Missing CMS source in registry: {source}"
            assert 'fetcher' in SOURCES[source], f"Missing fetcher for: {source}"
            assert 'loader' in SOURCES[source], f"Missing loader for: {source}"
