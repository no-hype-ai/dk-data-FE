"""Tests for UniProt fetcher with mocked HTTP.

Feature: 012-platform-hardening (US3)
"""

import tempfile
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from dk_data.ingestion.fetchers.uniprot import UniProtFetcher
from dk_data.ingestion.utils.validators import UniProtRecord


UNIPROT_SEARCH_RESPONSE = {
    "results": [
        {
            "primaryAccession": "P00533",
            "uniProtkbId": "EGFR_HUMAN",
            "proteinDescription": {
                "recommendedName": {
                    "fullName": {"value": "Epidermal growth factor receptor"}
                }
            },
            "genes": [{"geneName": {"value": "EGFR"}}],
            "organism": {"scientificName": "Homo sapiens"},
            "sequence": {"length": 1210},
            "comments": [
                {
                    "commentType": "FUNCTION",
                    "texts": [{"value": "Receptor tyrosine kinase involved in cell signaling."}],
                }
            ],
        },
        {
            "primaryAccession": "P04637",
            "uniProtkbId": "P53_HUMAN",
            "proteinDescription": {
                "recommendedName": {
                    "fullName": {"value": "Cellular tumor antigen p53"}
                }
            },
            "genes": [{"geneName": {"value": "TP53"}}],
            "organism": {"scientificName": "Homo sapiens"},
            "sequence": {"length": 393},
            "comments": [],
        },
    ]
}

UNIPROT_EMPTY_RESPONSE = {"results": []}


class TestUniProtFetcher:
    """Tests for UniProtFetcher."""

    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = UniProtFetcher(data_dir=tmpdir)
            assert fetcher.SOURCE_NAME == "uniprot"
            assert "rest.uniprot.org" in fetcher.BASE_URL

    def test_get_latest_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = UniProtFetcher(data_dir=tmpdir)
            url = fetcher.get_latest_url()
            assert "search" in url

    @responses.activate
    def test_fetch_success(self):
        responses.add(
            responses.GET,
            "https://rest.uniprot.org/uniprotkb/search",
            json=UNIPROT_SEARCH_RESPONSE,
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = UniProtFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert len(result["records"]) == 2
        assert result["hash"] is not None
        assert result["records"][0]["primaryAccession"] == "P00533"
        assert len(responses.calls) == 1
        request_url = responses.calls[0].request.url
        query_params = parse_qs(urlparse(request_url).query)
        assert query_params.get("query") == [UniProtFetcher.DEFAULT_QUERY]

    @responses.activate
    def test_fetch_empty(self):
        responses.add(
            responses.GET,
            "https://rest.uniprot.org/uniprotkb/search",
            json=UNIPROT_EMPTY_RESPONSE,
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = UniProtFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert len(result["records"]) == 0

    @responses.activate
    def test_fetch_http_error(self):
        responses.add(
            responses.GET,
            "https://rest.uniprot.org/uniprotkb/search",
            body=b"Service Unavailable",
            status=503,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = UniProtFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "failed"
        assert result["error"]


class TestUniProtRecord:
    """Tests for UniProtRecord validator."""

    def test_valid_record(self):
        record = UniProtRecord(
            accession="P00533",
            entry_name="EGFR_HUMAN",
            protein_name="Epidermal growth factor receptor",
            gene_name="EGFR",
            organism="Homo sapiens",
            sequence_length=1210,
        )
        assert record.accession == "P00533"
        assert record.gene_name == "EGFR"

    def test_minimal_record(self):
        record = UniProtRecord(accession="P00533")
        assert record.accession == "P00533"
        assert record.gene_name is None

    def test_empty_accession(self):
        with pytest.raises(ValueError):
            UniProtRecord(accession="")
