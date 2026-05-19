"""Adapter unit tests for high-complexity MCP adapters.

Feature: 015-assessment-dashboard-integration
Task: T079

Tests verify adapter normalize() outputs are parseable by bronze models (FR-025).
"""

import pytest

# --- Registry backlog matrix (#415 Phase 0 T0.3) ---------------------------
#
# The full MCP adapter registry (~28 modules) is kept visible below as the
# authoritative Phase 2+ backlog. Only a small subset is actually built today;
# the rest are EXPECTED to be absent and are marked xfail(strict=True) so the
# matrix stays green without hiding any backlog row.
#
# BUILT_ADAPTERS is the single source of truth for "which modules currently
# ship a real importable Adapter(BaseAdapter) satisfying the contract". It was
# derived EMPIRICALLY by importing every module + instantiating Adapter().
#
# strict=True is intentional: when Phase 2+ lands a backlog adapter, its xfail
# will XPASS and FAIL this suite. That is the signal — the future worker MUST
# add that module name to BUILT_ADAPTERS (and drop any class/method-level
# xfail marker on its dedicated test class) so it runs as a real assertion.
BUILT_ADAPTERS: set[str] = {
    "chembl",
    "clinicaltrials",
    "cochrane",
    "drugbank",
    "ema",
    "ema_labels",
    "epo_patents",
    "hta_decisions",
    "openalex",
    "openfda_faers",
    "openfda_labels",
    "orange_book",
    "orcid",
    "pdb_structures",
    "pubchem",
    "pubmed",
    "sec_edgar",
    "uniprot",
    "uspto_patents",
}

_BACKLOG_XFAIL_REASON = "registry backlog — adapter not yet built (#415 Phase 2+)"


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
        assert adapter.raw_schema == "mol_raw"


class TestSecEdgarAdapter:
    """Test SEC EDGAR adapter."""

    def _get_adapter(self):
        from dk_data.services.mcp.adapters.sec_edgar import Adapter
        return Adapter()

    def test_adapter_properties(self):
        adapter = self._get_adapter()
        assert adapter.source_name == "sec_edgar"
        assert adapter.raw_table == "sec_edgar"
        assert adapter.raw_schema == "mol_raw"


class TestAllAdaptersImportable:
    """Verify all 28 adapter modules are importable and have Adapter class."""

    ADAPTER_MODULES = [
        "clinicaltrials", "chembl", "openfda_faers", "openfda_labels", "ema_labels",
        "drugbank", "pubmed", "openalex", "uniprot",
        "ema", "hta_decisions", "cochrane", "orange_book",
        "uspto_patents", "epo_patents", "sec_edgar",
        "who_icd", "pdb_structures", "orcid",
        "journal_rss", "medical_news", "uspto_trademarks", "euipo_trademarks",
        "cms_inpatient", "cms_hospital_info", "cms_cost_reports",
        "acc_tvc", "hrsa", "pubchem",
    ]

    @pytest.mark.parametrize(
        "module_name",
        [
            name
            if name in BUILT_ADAPTERS
            else pytest.param(
                name,
                marks=pytest.mark.xfail(
                    strict=True, reason=_BACKLOG_XFAIL_REASON
                ),
            )
            for name in ADAPTER_MODULES
        ],
    )
    def test_adapter_importable(self, module_name):
        import importlib
        mod = importlib.import_module(f"dk_data.services.mcp.adapters.{module_name}")
        assert hasattr(mod, "Adapter"), f"Missing Adapter class in {module_name}"
        adapter = mod.Adapter()
        assert adapter.source_name, f"Missing source_name in {module_name}"
        assert adapter.raw_table, f"Missing raw_table in {module_name}"
        assert adapter.raw_schema in ("mol_raw", "raw", "hcs_raw"), f"Invalid raw_schema in {module_name}"
