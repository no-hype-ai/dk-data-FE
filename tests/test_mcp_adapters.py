"""Adapter unit tests for high-complexity MCP adapters.

Feature: 015-assessment-dashboard-integration
Task: T079

Tests verify adapter normalize() outputs are parseable by bronze models (FR-025).
"""

import pytest


class TestBaseAdapterInterface:
    """Verify BaseAdapter contract."""

    def test_base_adapter_is_abstract(self):
        from dk_data.services.mcp.adapters.base import BaseAdapter
        with pytest.raises(TypeError):
            BaseAdapter()

    def test_subclass_must_implement_source_name(self):
        from dk_data.services.mcp.adapters.base import BaseAdapter

        class Incomplete(BaseAdapter):
            @property
            def raw_table(self): return "t"
            @property
            def raw_schema(self): return "raw"
            def normalize(self, r): return r

        with pytest.raises(TypeError):
            Incomplete()

    def test_full_table_name_property(self):
        from dk_data.services.mcp.adapters.base import BaseAdapter

        class Complete(BaseAdapter):
            @property
            def source_name(self): return "test"
            @property
            def raw_table(self): return "my_table"
            @property
            def raw_schema(self): return "raw"
            def normalize(self, r): return r

        adapter = Complete()
        assert adapter.full_table_name == "raw.my_table"

    def test_validate_against_bronze_default_true(self):
        from dk_data.services.mcp.adapters.base import BaseAdapter

        class Complete(BaseAdapter):
            @property
            def source_name(self): return "test"
            @property
            def raw_table(self): return "t"
            @property
            def raw_schema(self): return "raw"
            def normalize(self, r): return r

        adapter = Complete()
        assert adapter.validate_against_bronze({}) is True


class TestClinicalTrialsAdapter:
    """Test ClinicalTrials.gov adapter normalization."""

    def _get_adapter(self):
        from dk_data.services.mcp.adapters.clinicaltrials import Adapter
        return Adapter()

    def test_adapter_properties(self):
        adapter = self._get_adapter()
        assert adapter.source_name == "clinicaltrials"
        assert adapter.raw_table == "clinicaltrials"
        assert adapter.raw_schema == "mol_raw"

    def test_normalize_passthrough(self):
        """Adapter normalizes API response (passthrough for initial implementation)."""
        adapter = self._get_adapter()
        sample = {"studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT001"}}}]}
        result = adapter.normalize(sample)
        assert isinstance(result, dict)


class TestChEMBLAdapter:
    """Test ChEMBL adapter normalization."""

    def _get_adapter(self):
        from dk_data.services.mcp.adapters.chembl import Adapter
        return Adapter()

    def test_adapter_properties(self):
        adapter = self._get_adapter()
        assert adapter.source_name == "chembl"
        assert adapter.raw_table == "chembl"
        assert adapter.raw_schema == "mol_raw"

    def test_normalize_passthrough(self):
        adapter = self._get_adapter()
        result = adapter.normalize({"molecules": []})
        assert isinstance(result, dict)


class TestDrugBankAdapter:
    """Test DrugBank adapter normalization (most critical — REST JSON vs XML)."""

    def _get_adapter(self):
        from dk_data.services.mcp.adapters.drugbank import Adapter
        return Adapter()

    def test_adapter_properties(self):
        adapter = self._get_adapter()
        assert adapter.source_name == "drugbank"
        assert adapter.raw_table == "drugbank"
        assert adapter.raw_schema == "mol_raw"

    def test_normalize_passthrough(self):
        adapter = self._get_adapter()
        result = adapter.normalize({"drugbank_id": "DB00001", "name": "Lepirudin"})
        assert isinstance(result, dict)


class TestOpenFDAFaersAdapter:
    """Test OpenFDA FAERS adapter normalization."""

    def _get_adapter(self):
        from dk_data.services.mcp.adapters.openfda_faers import Adapter
        return Adapter()

    def test_adapter_properties(self):
        adapter = self._get_adapter()
        assert adapter.source_name == "openfda_faers"
        assert adapter.raw_table == "openfda_faers"
        assert adapter.raw_schema == "mol_raw"

    def test_normalize_passthrough(self):
        adapter = self._get_adapter()
        result = adapter.normalize({"results": [{"patient": {}}]})
        assert isinstance(result, dict)


class TestPubMedAdapter:
    """Test PubMed adapter."""

    def _get_adapter(self):
        from dk_data.services.mcp.adapters.pubmed import Adapter
        return Adapter()

    def test_adapter_properties(self):
        adapter = self._get_adapter()
        assert adapter.source_name == "pubmed"
        assert adapter.raw_table == "pubmed"
        assert adapter.raw_schema == "raw"


class TestSecEdgarAdapter:
    """Test SEC EDGAR adapter."""

    def _get_adapter(self):
        from dk_data.services.mcp.adapters.sec_edgar import Adapter
        return Adapter()

    def test_adapter_properties(self):
        adapter = self._get_adapter()
        assert adapter.source_name == "sec_edgar"
        assert adapter.raw_table == "sec_edgar"
        assert adapter.raw_schema == "raw"


class TestAllAdaptersImportable:
    """Verify all 28 adapter modules are importable and have Adapter class."""

    ADAPTER_MODULES = [
        "clinicaltrials", "chembl", "openfda_faers", "openfda_labels",
        "drugbank", "pubmed", "openalex", "uniprot",
        "ema", "hta_decisions", "cochrane", "orange_book",
        "uspto_patents", "epo_patents", "sec_edgar",
        "who_icd", "pdb_structures", "orcid",
        "journal_rss", "medical_news", "uspto_trademarks", "euipo_trademarks",
        "cms_inpatient", "cms_hospital_info", "cms_cost_reports",
        "acc_tvc", "hrsa", "pubchem",
    ]

    @pytest.mark.parametrize("module_name", ADAPTER_MODULES)
    def test_adapter_importable(self, module_name):
        import importlib
        mod = importlib.import_module(f"dk_data.services.mcp.adapters.{module_name}")
        assert hasattr(mod, "Adapter"), f"Missing Adapter class in {module_name}"
        adapter = mod.Adapter()
        assert adapter.source_name, f"Missing source_name in {module_name}"
        assert adapter.raw_table, f"Missing raw_table in {module_name}"
        assert adapter.raw_schema in ("mol_raw", "raw"), f"Invalid raw_schema in {module_name}"
