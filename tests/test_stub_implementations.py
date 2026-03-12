"""Tests for all 13 stub/placeholder implementations.

Verifies that every formerly-stubbed function now returns real data
(or raises explicitly) instead of hardcoded mocks/placeholders.

All external HTTP calls are mocked — no network required.
"""

import asyncio
import hashlib
import re
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


# =========================================================================
# Group A: HTA Body Fetchers
# =========================================================================

class TestHTAGBAFetcher:
    """G-BA scraper returns parsed decisions, not empty stub."""

    def test_gba_parses_html_with_drug_match(self, tmp_path):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        html = """
        <html><body>
        <table>
        <tr>
            <td><a href="/bewertungsverfahren/nutzenbewertung/123">
                Pembrolizumab — 2026-01-15 — Zusatznutzen belegt
            </a></td>
        </tr>
        </table>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get", return_value=mock_resp):
            records = fetcher._fetch_gba(drug_names=["pembrolizumab"], days_back=365)

        assert len(records) >= 1
        rec = records[0]
        assert rec["agency"] == "gba"
        assert rec["decision_id"].startswith("gba-")
        assert "pembrolizumab" in rec["drug_name"].lower()
        assert rec["decision_type"] == "Benefit proven"

    def test_gba_returns_empty_when_no_match(self, tmp_path):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        html = "<html><body><table><tr><td>Aspirin 2026-01-01</td></tr></table></body></html>"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get", return_value=mock_resp):
            records = fetcher._fetch_gba(drug_names=["pembrolizumab"], days_back=365)

        assert records == []

    def test_gba_handles_http_failure(self, tmp_path):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get",
                    side_effect=Exception("Connection refused")):
            records = fetcher._fetch_gba(drug_names=["test"], days_back=7)

        assert records == []


class TestHTAHASFetcher:
    """HAS scraper returns parsed decisions, not empty stub."""

    def test_has_parses_html_with_drug_match(self, tmp_path):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        html = """
        <html><body>
        <article>
            <a href="/jcms/opinion123">Nivolumab — 2026-02-10 — Favorable opinion</a>
        </article>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get", return_value=mock_resp):
            records = fetcher._fetch_has(drug_names=["nivolumab"], days_back=365)

        assert len(records) >= 1
        assert records[0]["agency"] == "has"
        assert records[0]["decision_type"] == "Favorable"

    def test_has_handles_http_failure(self, tmp_path):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get",
                    side_effect=Exception("Timeout")):
            records = fetcher._fetch_has(drug_names=["test"], days_back=7)

        assert records == []


class TestHTAPBACFetcher:
    """PBAC scraper returns parsed decisions, not empty stub."""

    def test_pbac_parses_html_with_drug_match(self, tmp_path):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        html = """
        <html><body>
        <table>
        <tr>
            <td><a href="/outcomes/pembrolizumab">
                Pembrolizumab 2026-03-01 Recommended for melanoma
            </a></td>
        </tr>
        </table>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get", return_value=mock_resp):
            records = fetcher._fetch_pbac(drug_names=["pembrolizumab"], days_back=365)

        assert len(records) >= 1
        assert records[0]["agency"] == "pbac"
        assert records[0]["decision_type"] == "Recommended"

    def test_pbac_handles_http_failure(self, tmp_path):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        with patch("dk_data.ingestion.fetchers.hta_bodies.requests.get",
                    side_effect=Exception("DNS error")):
            records = fetcher._fetch_pbac(drug_names=["test"], days_back=7)

        assert records == []


class TestHTADispatchUpdated:
    """Dispatch table no longer references stub methods."""

    def test_dispatch_table_has_no_stubs(self, tmp_path):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        fetcher = HTABodiesFetcher(data_dir=str(tmp_path))

        # The dispatch table should NOT reference any method with 'stub' in name
        dispatch = {
            "nice": fetcher._fetch_nice,
            "gba": fetcher._fetch_gba,
            "has": fetcher._fetch_has,
            "pbac": fetcher._fetch_pbac,
        }
        for agency, handler in dispatch.items():
            assert "stub" not in handler.__name__, f"{agency} still uses stub: {handler.__name__}"

    def test_no_stub_methods_remain(self):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        stub_methods = [m for m in dir(HTABodiesFetcher) if "stub" in m.lower()]
        assert stub_methods == [], f"Stub methods still exist: {stub_methods}"


class TestHTAHelpers:
    """Test shared helper methods for HTA scrapers."""

    def test_extract_date_iso(self):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        assert HTABodiesFetcher._extract_date_from_text("Decision on 2026-01-15") == "2026-01-15"

    def test_extract_date_european(self):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        assert HTABodiesFetcher._extract_date_from_text("Published 15/01/2026") == "2026-01-15"

    def test_extract_date_none(self):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        assert HTABodiesFetcher._extract_date_from_text("No date here") is None

    def test_match_drug_name(self):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        assert HTABodiesFetcher._match_drug_name(
            "Treatment with Pembrolizumab", ["pembrolizumab", "nivolumab"]
        ) == "pembrolizumab"

    def test_match_drug_name_no_match(self):
        from dk_data.ingestion.fetchers.hta_bodies import HTABodiesFetcher

        assert HTABodiesFetcher._match_drug_name(
            "Some other text", ["pembrolizumab"]
        ) is None


# =========================================================================
# Group B: SEC EDGAR Client
# =========================================================================

class TestSECEdgarXBRL:
    """_fetch_xbrl hits the Company Facts API instead of returning None."""

    def test_fetch_xbrl_returns_facts(self):
        from dk_data.services.external_apis.sec_edgar_client import SECEdgarClient
        from dk_data.models.market_intelligence import Filing

        client = SECEdgarClient()
        filing = Filing(
            accession="0001234567-26-000001",
            filing_date=date(2026, 1, 1),
            form="10-K",
            company_cik="78003",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "facts": {
                "us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {}},
                "dei": {"EntityRegistrantName": {}},
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_client):
            with patch.object(client.rate_limiter, "acquire", new_callable=AsyncMock):
                result = run(client._fetch_xbrl(filing))

        assert result is not None
        assert "us-gaap" in result

    def test_fetch_xbrl_returns_none_on_404(self):
        from dk_data.services.external_apis.sec_edgar_client import SECEdgarClient
        from dk_data.models.market_intelligence import Filing

        client = SECEdgarClient()
        filing = Filing(
            accession="0001234567-26-000001",
            filing_date=date(2026, 1, 1),
            form="10-K",
            company_cik="99999",
        )

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_client):
            with patch.object(client.rate_limiter, "acquire", new_callable=AsyncMock):
                result = run(client._fetch_xbrl(filing))

        assert result is None


class TestSECEdgarItem1:
    """_fetch_item1_business extracts only Item 1 section."""

    def test_extracts_item1_section(self):
        from dk_data.services.external_apis.sec_edgar_client import SECEdgarClient
        from dk_data.models.market_intelligence import Filing

        client = SECEdgarClient()
        filing = Filing(
            accession="0001234567-26-000001",
            filing_date=date(2026, 1, 1),
            form="10-K",
            company_cik="78003",
        )

        html = """
        <html><body>
        <h2>PART I</h2>
        <h3>Item 1. Business</h3>
        <p>We are a global pharmaceutical company that discovers, develops and
        commercializes medicines. Our key products include Keytruda and Gardasil.
        We have a robust pipeline with several Phase 3 candidates.</p>
        <h3>Item 1A. Risk Factors</h3>
        <p>Investing in our securities involves risk.</p>
        </body></html>
        """

        with patch.object(client, "_fetch_10k_html", new_callable=AsyncMock, return_value=html):
            result = run(client._fetch_item1_business(filing))

        # Should contain business description but NOT risk factors
        assert "pharmaceutical company" in result
        assert "Keytruda" in result
        assert "Investing in our securities" not in result

    def test_falls_back_to_full_text(self):
        from dk_data.services.external_apis.sec_edgar_client import SECEdgarClient
        from dk_data.models.market_intelligence import Filing

        client = SECEdgarClient()
        filing = Filing(
            accession="0001234567-26-000001",
            filing_date=date(2026, 1, 1),
            form="10-K",
            company_cik="78003",
        )

        # HTML without Item 1 markers
        html = "<html><body><p>Some content without item markers.</p></body></html>"

        with patch.object(client, "_fetch_10k_html", new_callable=AsyncMock, return_value=html):
            result = run(client._fetch_item1_business(filing))

        assert "Some content" in result


class TestSECEdgarPipelineAssets:
    """_extract_pipeline_assets returns real extracted compounds."""

    def test_extracts_phase_compounds(self):
        from dk_data.services.external_apis.sec_edgar_client import SECEdgarClient

        client = SECEdgarClient()

        content = """
        Our pipeline includes BMS-986165, which is currently in Phase 3
        clinical trials for the treatment of psoriasis. We are also developing
        ABT-199 in Phase 2 for chronic lymphocytic leukemia.
        Pembrolizumab has received NDA approval for melanoma.
        """

        assets = client._extract_pipeline_assets(content, "ACC-001")

        assert len(assets) >= 2
        names = [a.compound_name for a in assets]
        assert "BMS-986165" in names
        assert "ABT-199" in names

        # Check phase extraction
        bms = next(a for a in assets if a.compound_name == "BMS-986165")
        assert bms.phase == "Phase 3"
        assert bms.filing_accession == "ACC-001"
        assert bms.extract_confidence > 0.5

    def test_extracts_inn_stem_compounds(self):
        from dk_data.services.external_apis.sec_edgar_client import SECEdgarClient

        client = SECEdgarClient()

        content = """
        Trastuzumab is in Phase 2 trials for HER2-positive breast cancer.
        Nivolumab is being evaluated in Phase 1 for solid tumors.
        """

        assets = client._extract_pipeline_assets(content, "ACC-002")
        names = [a.compound_name.lower() for a in assets]

        assert any("trastuzumab" in n for n in names)

    def test_returns_empty_for_no_content(self):
        from dk_data.services.external_apis.sec_edgar_client import SECEdgarClient

        client = SECEdgarClient()
        assert client._extract_pipeline_assets("", "ACC-003") == []
        assert client._extract_pipeline_assets("short", "ACC-003") == []

    def test_deduplicates_by_compound(self):
        from dk_data.services.external_apis.sec_edgar_client import SECEdgarClient

        client = SECEdgarClient()

        content = """
        BMS-986165 is in Phase 3 for psoriasis.
        BMS-986165 is also in Phase 2 for lupus.
        """

        assets = client._extract_pipeline_assets(content, "ACC-004")
        bms_assets = [a for a in assets if a.compound_name == "BMS-986165"]
        # Should be deduplicated — keeps highest confidence
        assert len(bms_assets) == 1


# =========================================================================
# Group C: Data Platform Services
# =========================================================================

class TestLifecycleStageTransitions:
    """get_stage_transitions queries audit table, not placeholder."""

    def test_returns_transitions_from_db(self):
        from dk_data.services.data_platform.lifecycle_detection import LifecycleDetectionService

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_conn.fetch = AsyncMock(return_value=[
            {
                "previous_stage": "phase_2",
                "new_stage": "phase_3",
                "confidence": 0.85,
                "evidence_summary": "Auto-detected",
                "detected_at": datetime(2026, 1, 15, tzinfo=timezone.utc),
            }
        ])

        service = LifecycleDetectionService(db_pool=mock_pool)
        result = run(service.get_stage_transitions("test-uuid", days=90))

        assert len(result) == 1
        assert result[0]["previous_stage"] == "phase_2"
        assert result[0]["new_stage"] == "phase_3"
        assert result[0]["confidence"] == 0.85

        # Verify the SQL query was made with correct params
        mock_conn.fetch.assert_called_once()
        call_args = mock_conn.fetch.call_args
        assert "molecule_stage_history" in call_args[0][0]

    def test_returns_empty_when_no_history(self):
        from dk_data.services.data_platform.lifecycle_detection import LifecycleDetectionService

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.fetch = AsyncMock(return_value=[])

        service = LifecycleDetectionService(db_pool=mock_pool)
        result = run(service.get_stage_transitions("no-history-uuid", days=90))

        assert result == []


class TestLifecycleAuditInsert:
    """_update_molecule_stage writes to audit table."""

    def test_inserts_audit_record_on_stage_change(self):
        from dk_data.services.data_platform.lifecycle_detection import (
            LifecycleDetectionService, LifecycleStage,
        )

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.fetchrow = AsyncMock(return_value={"development_status": "phase_2"})
        mock_conn.execute = AsyncMock()

        service = LifecycleDetectionService(db_pool=mock_pool)
        run(service._update_molecule_stage("test-uuid", LifecycleStage.PHASE_3, 0.85))

        # Should have 2 execute calls: UPDATE molecules + INSERT history
        assert mock_conn.execute.call_count == 2
        insert_call = mock_conn.execute.call_args_list[1]
        assert "molecule_stage_history" in insert_call[0][0]


class TestSyncRunnerCredentials:
    """sync_runner uses env-var-first credential lookup."""

    def test_api_key_from_env(self):
        """Verify SYNC_APIKEY_* env var takes precedence."""
        from dk_data.services.data_platform.sync_runner import run_dynamic_source_ingestion

        import inspect
        source = inspect.getsource(run_dynamic_source_ingestion)

        assert "SYNC_APIKEY_" in source
        assert "SYNC_TOKEN_" in source
        assert "SYNC_CRED_" in source
        assert "os.environ.get" in source
        # No more "placeholder" or "In real impl" comments
        assert "In real impl" not in source
        assert "placeholder pattern" not in source


class TestBronzeChEMBLActivity:
    """_insert_bronze_chembl_activity does real INSERT."""

    def test_inserts_activity_record(self):
        from dk_data.services.data_platform.bronze_ingestion import BronzeIngestionService

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        service = BronzeIngestionService(db_pool=mock_pool)

        activity = {
            "activity_id": 12345,
            "molecule_chembl_id": "CHEMBL25",
            "target_chembl_id": "CHEMBL1824",
            "target_pref_name": "Cyclooxygenase-2",
            "target_organism": "Homo sapiens",
            "standard_type": "IC50",
            "standard_value": 10.5,
            "standard_units": "nM",
            "assay_chembl_id": "CHEMBL674345",
            "assay_type": "B",
            "pchembl_value": 7.98,
        }

        run(service._insert_bronze_chembl_activity(mock_conn, activity, raw_id=1))

        mock_conn.execute.assert_called_once()
        sql = mock_conn.execute.call_args[0][0]
        assert "bronze.chembl_activities" in sql
        assert "ON CONFLICT" in sql

    def test_skips_activity_without_molecule_id(self):
        from dk_data.services.data_platform.bronze_ingestion import BronzeIngestionService

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        service = BronzeIngestionService(db_pool=mock_pool)
        activity = {"activity_id": 99999}  # No molecule_chembl_id

        run(service._insert_bronze_chembl_activity(mock_conn, activity, raw_id=1))

        mock_conn.execute.assert_not_called()


# =========================================================================
# Group D: External API Clients
# =========================================================================

def _mock_httpx_client(mock_response):
    """Create a mock httpx.AsyncClient context manager returning mock_response."""
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    return mock_http


class TestAHRQHCUPNoMocks:
    """AHRQ HCUP raises on failure instead of returning mock data."""

    def test_inpatient_raises_on_non_200(self):
        from dk_data.services.external_apis.ahrq_hcup_client import AHRQHCUPClient

        client = AHRQHCUPClient()

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_http = _mock_httpx_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_http):
            with patch.object(client, "_rate_limiter", new_callable=MagicMock) as limiter:
                limiter.acquire = AsyncMock()
                with pytest.raises(RuntimeError, match="HTTP 500"):
                    run(client._query_inpatient_data("108", 2021, None))

    def test_ed_raises_on_non_200(self):
        from dk_data.services.external_apis.ahrq_hcup_client import AHRQHCUPClient

        client = AHRQHCUPClient()

        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_http = _mock_httpx_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_http):
            with patch.object(client, "_rate_limiter", new_callable=MagicMock) as limiter:
                limiter.acquire = AsyncMock()
                with pytest.raises(RuntimeError, match="HTTP 503"):
                    run(client._query_ed_data("108", 2021, None))

    def test_inpatient_returns_parsed_data_on_200(self):
        from dk_data.services.external_apis.ahrq_hcup_client import AHRQHCUPClient

        client = AHRQHCUPClient()

        # Simulate HCUPnet HTML response with stats
        html = """
        <table>
        <tr><td>Total discharges</td><td>1,234,567</td></tr>
        <tr><td>Mean LOS</td><td>4.5</td></tr>
        <tr><td>Mean charge</td><td>$45,000</td></tr>
        </table>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html

        mock_http = _mock_httpx_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_http):
            with patch.object(client, "_rate_limiter", new_callable=MagicMock) as limiter:
                limiter.acquire = AsyncMock()
                result = run(client._query_inpatient_data("108", 2021, None))

        assert len(result) == 1
        assert result[0].principal_diagnosis_code == "108"
        assert result[0].year == 2021

    def test_trending_conditions_raises_when_unreachable(self):
        from dk_data.services.external_apis.ahrq_hcup_client import AHRQHCUPClient

        client = AHRQHCUPClient()

        with patch.object(client, "_get_stats_for_code",
                          new_callable=AsyncMock, side_effect=Exception("unreachable")):
            with pytest.raises((RuntimeError, Exception), match="unreachable"):
                run(client.get_trending_conditions())


class TestTDCClientDBLookup:
    """TDC search_by_smiles queries the database."""

    def test_returns_predictions_from_db(self):
        from dk_data.services.external_apis.tdc_client import TDCClient

        client = TDCClient()

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_conn.fetch = AsyncMock(return_value=[
            {"smiles": "CCO", "property_name": "Caco2", "property_value": -5.2, "dataset": "Caco2_Wang"},
        ])

        result = run(client.search_by_smiles("CCO", db_pool=mock_pool))

        assert result.success is True
        assert result.data["predictions_available"] is True
        assert result.data["count"] == 1

    def test_returns_not_available_when_no_rows(self):
        from dk_data.services.external_apis.tdc_client import TDCClient

        client = TDCClient()

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn.fetch = AsyncMock(return_value=[])

        result = run(client.search_by_smiles("INVALID_SMILES", db_pool=mock_pool))

        assert result.success is True
        assert result.data["predictions_available"] is False

    def test_returns_not_available_without_pool(self):
        from dk_data.services.external_apis.tdc_client import TDCClient

        client = TDCClient()

        result = run(client.search_by_smiles("CCO"))

        assert result.success is True
        assert result.data["predictions_available"] is False


class TestNORDClientNoHardcoded:
    """NORD client scrapes the real site instead of returning hardcoded orgs."""

    def test_fallback_scrapes_org_directory(self):
        from dk_data.services.external_apis.nord_client import NORDClient

        client = NORDClient()

        html = """
        <html><body>
        <a href="/organizations/cf-foundation/">Cystic Fibrosis Foundation</a>
        <a href="/organizations/nord/">NORD</a>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", new_callable=AsyncMock, return_value=mock_http):
            result = run(client._get_common_organizations_for_disease("cystic fibrosis"))

        assert len(result) == 2
        names = [o.name for o in result]
        assert "Cystic Fibrosis Foundation" in names
        assert "NORD" in names

    def test_returns_empty_on_http_error(self):
        from dk_data.services.external_apis.nord_client import NORDClient

        client = NORDClient()

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", new_callable=AsyncMock, return_value=mock_http):
            result = run(client._get_common_organizations_for_disease("test disease"))

        assert result == []

    def test_no_hardcoded_disease_org_map(self):
        """Verify DISEASE_ORG_MAP class variable no longer exists."""
        from dk_data.services.external_apis.nord_client import NORDClient

        assert not hasattr(NORDClient, "DISEASE_ORG_MAP")


# =========================================================================
# Group E: Monitoring
# =========================================================================

class TestMonitoringNoPlaceholders:
    """Monitoring endpoints query real DB, not hardcoded values."""

    def test_latency_not_hardcoded_50(self):
        """Verify the external API latency is no longer hardcoded to 50."""
        import inspect
        from dk_data.api.routes.monitoring import list_data_sources

        source = inspect.getsource(list_data_sources)
        # Should not contain the old hardcoded pattern
        assert 'latency_ms"] = 50' not in source
        assert '"latency_ms": 50' not in source
        # Should query ingestion_jobs for duration
        assert "ingestion_jobs" in source

    def test_schedules_queries_db(self):
        """Verify /schedules endpoint queries raw.sync_schedules."""
        import inspect
        from dk_data.api.routes.monitoring import list_sync_schedules

        source = inspect.getsource(list_sync_schedules)
        assert "sync_schedules" in source
        assert "psycopg2" in source

    def test_sync_jobs_queries_db(self):
        """Verify /sync-jobs endpoint queries raw.ingestion_jobs."""
        import inspect
        from dk_data.api.routes.monitoring import list_sync_jobs

        source = inspect.getsource(list_sync_jobs)
        assert "ingestion_jobs" in source
        # Should support status and source filters
        assert "status" in source
        assert "source" in source

    def test_active_jobs_queries_db(self):
        """Verify /sync-jobs/active queries for running jobs."""
        import inspect
        from dk_data.api.routes.monitoring import list_active_sync_jobs

        source = inspect.getsource(list_active_sync_jobs)
        assert "ingestion_jobs" in source
        assert "running" in source


# =========================================================================
# Model: market_intelligence.py
# =========================================================================

class TestMarketIntelligenceModels:
    """market_intelligence.py models exist and serialize correctly."""

    def test_filing_model(self):
        from dk_data.models.market_intelligence import Filing

        f = Filing(
            accession="0001234567-26-000001",
            filing_date=date(2026, 1, 1),
            form="10-K",
            company_cik="78003",
        )
        d = f.to_dict()
        assert d["accession"] == "0001234567-26-000001"
        assert d["form"] == "10-K"

    def test_product_revenue_model(self):
        from dk_data.models.market_intelligence import ProductRevenue

        pr = ProductRevenue(
            product_name="Keytruda",
            revenue_usd=25118.0,
            period="annual",
            year=2025,
            yoy_growth=0.15,
        )
        d = pr.to_dict()
        assert d["product_name"] == "Keytruda"
        assert d["revenue_usd"] == 25118.0

    def test_pipeline_asset_model(self):
        from dk_data.models.market_intelligence import PipelineAsset

        pa = PipelineAsset(
            compound_name="BMS-986165",
            phase="Phase 3",
            indication="Psoriasis",
            extract_confidence=0.85,
        )
        d = pa.to_dict()
        assert d["compound_name"] == "BMS-986165"
        assert d["phase"] == "Phase 3"
        assert d["extract_confidence"] == 0.85


# =========================================================================
# Migration files exist
# =========================================================================

class TestMigrationFiles:
    """Verify new migration SQL files exist and are valid."""

    def test_094_molecule_stage_history_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "src/dk_data/sql/migrations/094_molecule_stage_history.sql"
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "silver.molecule_stage_history" in content
        assert "molecule_id" in content
        assert "previous_stage" in content
        assert "new_stage" in content

    def test_095_bronze_chembl_activities_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "src/dk_data/sql/migrations/095_bronze_chembl_activities.sql"
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "bronze.chembl_activities" in content
        assert "molecule_chembl_id" in content
        assert "activity_type" in content
        assert "ON CONFLICT" not in content  # Migration is CREATE TABLE, not INSERT
