"""Tests for DrugBank fetcher and validator.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (DrugBank)

Tests use mocked HTTP responses so no external network calls are made.
"""

import os
import textwrap
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from dk_data.ingestion.fetchers.drugbank import DrugBankFetcher
from dk_data.ingestion.utils.validators import DrugBankRecord


# ---------------------------------------------------------------------------
# Sample DrugBank XML fixtures
# ---------------------------------------------------------------------------

SAMPLE_DRUGBANK_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <drugbank xmlns="http://www.drugbank.ca"
              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
              xsi:schemaLocation="http://www.drugbank.ca http://www.drugbank.ca/docs/drugbank.xsd"
              version="5.1">
      <drug type="biotech" created="2005-06-13" updated="2024-01-01">
        <drugbank-id primary="true">DB00001</drugbank-id>
        <drugbank-id>BTD00024</drugbank-id>
        <name>Lepirudin</name>
        <description>Lepirudin is a recombinant hirudin.</description>
        <cas-number>138068-37-8</cas-number>
        <indication>For the treatment of heparin-induced thrombocytopenia.</indication>
        <pharmacodynamics>Lepirudin acts as a direct thrombin inhibitor.</pharmacodynamics>
        <categories>
          <category>
            <category>Antithrombotic Agents</category>
          </category>
          <category>
            <category>Direct Thrombin Inhibitors</category>
          </category>
        </categories>
        <targets>
          <target>
            <id>BE0000048</id>
            <name>Prothrombin</name>
            <actions>
              <action>inhibitor</action>
            </actions>
          </target>
        </targets>
        <enzymes>
          <enzyme>
            <id>BE0002793</id>
            <name>Cytochrome P450 3A4</name>
            <actions>
              <action>substrate</action>
            </actions>
          </enzyme>
        </enzymes>
      </drug>
      <drug type="small molecule" created="2005-06-13" updated="2024-01-01">
        <drugbank-id primary="true">DB00002</drugbank-id>
        <name>Cetuximab</name>
        <description>Cetuximab is a chimeric monoclonal antibody.</description>
        <cas-number>205923-56-4</cas-number>
        <indication>For treatment of EGFR-expressing colorectal cancer.</indication>
        <pharmacodynamics>Cetuximab binds to EGFR.</pharmacodynamics>
        <categories>
          <category>
            <category>Antineoplastic Agents</category>
          </category>
        </categories>
        <targets/>
        <enzymes/>
      </drug>
    </drugbank>
""")

SAMPLE_DRUGBANK_XML_NO_NS = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <drugbank>
      <drug type="biotech">
        <drugbank-id primary="true">DB00099</drugbank-id>
        <name>TestDrug</name>
        <description>A test drug.</description>
        <cas-number>12345-67-8</cas-number>
        <indication>For testing.</indication>
        <pharmacodynamics>Test pharmacodynamics.</pharmacodynamics>
        <categories/>
        <targets/>
        <enzymes/>
      </drug>
    </drugbank>
""")


# ---------------------------------------------------------------------------
# Tests: fetcher initialization
# ---------------------------------------------------------------------------

class TestDrugBankFetcherInit:
    """Verify DrugBankFetcher initializes correctly."""

    def test_fetcher_init(self, tmp_path):
        """Fetcher can be instantiated with a custom data_dir."""
        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "test-key-123"}):
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))

        assert fetcher.SOURCE_NAME == "drugbank"
        assert fetcher.BASE_URL == "https://go.drugbank.com"
        assert fetcher.data_dir == tmp_path
        assert fetcher.session is not None
        assert fetcher.api_key == "test-key-123"

    def test_fetcher_init_no_api_key(self, tmp_path):
        """Fetcher initializes without API key (with warning)."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove DRUGBANK_API_KEY if present
            os.environ.pop("DRUGBANK_API_KEY", None)
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))

        assert fetcher.api_key is None

    def test_fetcher_data_dir_created(self, tmp_path):
        """Verify the data directory is created on init."""
        data_path = tmp_path / "sub" / "raw"
        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "key"}):
            DrugBankFetcher(data_dir=str(data_path))  # side-effect: creates dir
        assert data_path.exists()


# ---------------------------------------------------------------------------
# Tests: get_latest_url
# ---------------------------------------------------------------------------

class TestDrugBankGetLatestUrl:
    """Verify the URL returned by get_latest_url."""

    def test_get_latest_url(self, tmp_path):
        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "key"}):
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert url == "https://go.drugbank.com/releases/latest/downloads/all-full-database"
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# Tests: XML parsing
# ---------------------------------------------------------------------------

class TestDrugBankXMLParsing:
    """Test the XML parsing logic with sample data."""

    def test_parse_drugbank_xml_with_namespace(self, tmp_path):
        """Parse a DrugBank XML file with namespace."""
        xml_file = tmp_path / "drugbank.xml"
        xml_file.write_text(SAMPLE_DRUGBANK_XML)

        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "key"}):
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))

        records = fetcher._parse_drugbank_xml(str(xml_file))

        assert len(records) == 2

        # First drug: Lepirudin
        rec1 = records[0]
        assert rec1["drugbank_id"] == "DB00001"
        assert rec1["name"] == "Lepirudin"
        assert rec1["cas_number"] == "138068-37-8"
        assert rec1["description"] is not None
        assert "hirudin" in rec1["description"]
        assert rec1["indication"] is not None
        assert rec1["pharmacodynamics"] is not None
        assert rec1["categories"] is not None
        assert len(rec1["categories"]) == 2
        assert "Antithrombotic Agents" in rec1["categories"]
        assert rec1["targets"] is not None
        assert len(rec1["targets"]) == 1
        assert rec1["targets"][0]["name"] == "Prothrombin"
        assert rec1["enzymes"] is not None
        assert len(rec1["enzymes"]) == 1

        # Second drug: Cetuximab
        rec2 = records[1]
        assert rec2["drugbank_id"] == "DB00002"
        assert rec2["name"] == "Cetuximab"

    def test_parse_drugbank_xml_without_namespace(self, tmp_path):
        """Parse a DrugBank XML file without namespace."""
        xml_file = tmp_path / "drugbank_no_ns.xml"
        xml_file.write_text(SAMPLE_DRUGBANK_XML_NO_NS)

        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "key"}):
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))

        records = fetcher._parse_drugbank_xml(str(xml_file))

        assert len(records) == 1
        assert records[0]["drugbank_id"] == "DB00099"
        assert records[0]["name"] == "TestDrug"

    def test_parse_drugbank_xml_max_entries(self, tmp_path):
        """Verify max_entries limit is respected."""
        xml_file = tmp_path / "drugbank.xml"
        xml_file.write_text(SAMPLE_DRUGBANK_XML)

        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "key"}):
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))

        records = fetcher._parse_drugbank_xml(str(xml_file), max_entries=1)
        assert len(records) == 1


# ---------------------------------------------------------------------------
# Tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

class TestDrugBankFetchWithMock:
    """Verify the full fetch flow using mocked HTTP."""

    def test_fetch_success(self, tmp_path):
        """fetch() returns success when XML is downloaded and parsed."""
        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "test-key"}):
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))

        # Write sample XML to the expected download location
        xml_path = tmp_path / "drugbank_full.xml"
        xml_path.write_text(SAMPLE_DRUGBANK_XML)

        # Mock the download to write our sample XML
        with patch.object(fetcher, "_download_drugbank_xml", return_value=str(xml_path)):
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert result["record_count"] == 2
        assert len(result["records"]) == 2
        assert result["hash"] is not None

    def test_fetch_fails_without_api_key(self, tmp_path):
        """fetch() returns failed when no API key is set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DRUGBANK_API_KEY", None)
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))

        result = fetcher.fetch()

        assert result["status"] == "failed"
        assert "DRUGBANK_API_KEY" in result["error"]
        assert result["records"] == []

    def test_fetch_handles_download_error(self, tmp_path):
        """fetch() returns failed when download raises an exception."""
        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "test-key"}):
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher,
            "_download_drugbank_xml",
            side_effect=Exception("Connection refused"),
        ):
            result = fetcher.fetch()

        assert result["status"] == "failed"
        assert "Connection refused" in result["error"]

    def test_fetch_empty_xml(self, tmp_path):
        """fetch() returns success with 0 records when XML has no drugs."""
        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "test-key"}):
            fetcher = DrugBankFetcher(data_dir=str(tmp_path))

        empty_xml = '<?xml version="1.0"?><drugbank xmlns="http://www.drugbank.ca"></drugbank>'
        xml_path = tmp_path / "drugbank_full.xml"
        xml_path.write_text(empty_xml)

        with patch.object(fetcher, "_download_drugbank_xml", return_value=str(xml_path)):
            result = fetcher.fetch()

        assert result["status"] == "success"
        assert result["record_count"] == 0


# ---------------------------------------------------------------------------
# Tests: Pydantic validator — valid records
# ---------------------------------------------------------------------------

class TestDrugBankRecordValid:
    """Test that valid records pass Pydantic validation."""

    def test_drugbank_record_valid(self):
        """A fully populated record validates successfully."""
        record = DrugBankRecord(
            drugbank_id="DB00001",
            name="Lepirudin",
            description="A recombinant hirudin.",
            cas_number="138068-37-8",
            categories=["Antithrombotic Agents", "Direct Thrombin Inhibitors"],
            targets=[{"id": "BE0000048", "name": "Prothrombin", "actions": ["inhibitor"]}],
            enzymes=[{"id": "BE0002793", "name": "CYP3A4", "actions": ["substrate"]}],
            indication="For treatment of HIT.",
            pharmacodynamics="Direct thrombin inhibitor.",
        )

        assert record.drugbank_id == "DB00001"
        assert record.name == "Lepirudin"
        assert record.cas_number == "138068-37-8"
        assert len(record.categories) == 2
        assert record.targets is not None
        assert record.enzymes is not None

    def test_minimal_record(self):
        """A record with only drugbank_id validates."""
        record = DrugBankRecord(drugbank_id="DB00001")
        assert record.drugbank_id == "DB00001"
        assert record.name is None
        assert record.description is None
        assert record.categories is None
        assert record.targets is None

    def test_drugbank_id_with_whitespace(self):
        """Whitespace in drugbank_id is stripped."""
        record = DrugBankRecord(drugbank_id="  DB00001  ")
        assert record.drugbank_id == "DB00001"

    def test_various_drugbank_id_formats(self):
        """Various valid DrugBank ID formats are accepted."""
        for db_id in ["DB00001", "DB13579", "DB99999"]:
            record = DrugBankRecord(drugbank_id=db_id)
            assert record.drugbank_id == db_id


# ---------------------------------------------------------------------------
# Tests: Pydantic validator — invalid records
# ---------------------------------------------------------------------------

class TestDrugBankRecordInvalid:
    """Test that invalid records are rejected by Pydantic."""

    def test_drugbank_id_not_starting_with_db(self):
        """A drugbank_id not starting with 'DB' is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            DrugBankRecord(drugbank_id="XX00001")
        errors = exc_info.value.errors()
        assert any("drugbank_id" in str(e) or "DB" in str(e) for e in errors)

    def test_empty_drugbank_id(self):
        """An empty drugbank_id is rejected."""
        with pytest.raises(ValidationError):
            DrugBankRecord(drugbank_id="")

    def test_missing_drugbank_id(self):
        """Omitting drugbank_id raises ValidationError."""
        with pytest.raises(ValidationError):
            DrugBankRecord()

    def test_drugbank_id_only_whitespace(self):
        """A drugbank_id of only whitespace is rejected."""
        with pytest.raises(ValidationError):
            DrugBankRecord(drugbank_id="   ")

    def test_drugbank_id_numeric_only(self):
        """A purely numeric drugbank_id is rejected."""
        with pytest.raises(ValidationError):
            DrugBankRecord(drugbank_id="00001")

    def test_drugbank_id_lowercase(self):
        """A lowercase 'db' prefix is rejected."""
        with pytest.raises(ValidationError):
            DrugBankRecord(drugbank_id="db00001")
