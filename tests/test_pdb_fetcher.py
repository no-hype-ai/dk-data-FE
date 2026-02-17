"""Tests for PDB fetcher with mocked HTTP.

Feature: 012-platform-hardening (US3)
"""

import tempfile

import pytest
import responses

from dk_data.ingestion.fetchers.pdb import PDBFetcher
from dk_data.ingestion.utils.validators import PDBRecord


PDB_SEARCH_RESPONSE = {
    "result_set": [
        {"identifier": "1ABC"},
        {"identifier": "2XYZ"},
    ]
}

PDB_ENTRY_1ABC = {
    "struct": {"title": "Crystal structure of a drug target"},
    "exptl": [{"method": "X-RAY DIFFRACTION"}],
    "rcsb_entry_info": {"resolution_combined": [2.1]},
    "rcsb_accession_info": {"deposit_date": "2025-01-15"},
}

PDB_ENTRY_2XYZ = {
    "struct": {"title": "Cryo-EM structure of receptor"},
    "exptl": [{"method": "ELECTRON MICROSCOPY"}],
    "rcsb_entry_info": {"resolution_combined": [3.5]},
    "rcsb_accession_info": {"deposit_date": "2025-06-20"},
}

PDB_EMPTY_SEARCH = {"result_set": []}


class TestPDBFetcher:
    """Tests for PDBFetcher."""

    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PDBFetcher(data_dir=tmpdir)
            assert fetcher.SOURCE_NAME == "pdb"

    def test_get_latest_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PDBFetcher(data_dir=tmpdir)
            url = fetcher.get_latest_url()
            assert "query" in url

    @responses.activate
    def test_fetch_success(self):
        # Mock search
        responses.add(
            responses.POST,
            "https://search.rcsb.org/rcsbsearch/v2/query",
            json=PDB_SEARCH_RESPONSE,
            status=200,
        )
        # Mock entry details
        responses.add(
            responses.GET,
            "https://data.rcsb.org/rest/v1/core/entry/1ABC",
            json=PDB_ENTRY_1ABC,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://data.rcsb.org/rest/v1/core/entry/2XYZ",
            json=PDB_ENTRY_2XYZ,
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PDBFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert len(result["records"]) == 2
        assert result["records"][0]["pdb_id"] == "1ABC"
        assert result["records"][0]["title"] == "Crystal structure of a drug target"
        assert result["records"][0]["method"] == "X-RAY DIFFRACTION"

    @responses.activate
    def test_fetch_empty(self):
        responses.add(
            responses.POST,
            "https://search.rcsb.org/rcsbsearch/v2/query",
            json=PDB_EMPTY_SEARCH,
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PDBFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert len(result["records"]) == 0

    @responses.activate
    def test_fetch_search_error(self):
        responses.add(
            responses.POST,
            "https://search.rcsb.org/rcsbsearch/v2/query",
            body=b"Internal Server Error",
            status=500,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = PDBFetcher(data_dir=tmpdir)
            result = fetcher.fetch()

        assert result["status"] == "failed"
        assert result["error"]


class TestPDBRecord:
    """Tests for PDBRecord validator."""

    def test_valid_record(self):
        record = PDBRecord(pdb_id="1ABC", title="Test", method="X-RAY DIFFRACTION", resolution=2.1)
        assert record.pdb_id == "1ABC"

    def test_pdb_id_uppercase(self):
        record = PDBRecord(pdb_id="1abc")
        assert record.pdb_id == "1ABC"

    def test_invalid_pdb_id_length(self):
        with pytest.raises(ValueError):
            PDBRecord(pdb_id="AB")

    def test_minimal_record(self):
        record = PDBRecord(pdb_id="1XYZ")
        assert record.title is None
        assert record.resolution is None
