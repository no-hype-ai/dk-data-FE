"""Tests for ACC TVC fetcher, loader, and validator with mocked HTTP.

Feature: 011-datasource-integration
Tasks: T073–T076 (ACC TVC data source research and update)

Tests use mocked HTTP responses so no external network calls are made.
"""

import csv
import io
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
import responses

from dk_data.ingestion.fetchers.acc_tvc import (
    ACCTVCFetcher,
    NCDR_HOSPITALS_URL,
    NCDR_TVT_METRICS_URL,
)
from dk_data.ingestion.sources.acc_tvc import (
    _apply_column_mapping,
    _detect_format,
    parse_date,
)
from dk_data.ingestion.utils.validators import ACCTVCCertificationRecord


# ---------------------------------------------------------------------------
# Sample CSV fixtures
# ---------------------------------------------------------------------------

def _tvt_metrics_csv(rows=None):
    """Build a TVTMetrics-style CSV string.

    Columns mirror the real NCDR TVTMetrics CSV.
    """
    if rows is None:
        rows = [
            {
                "FacilityLinkingID": "100001",
                "MPN": "010001",
                "AHA": "6010001",
                "NPI": "1234567890",
                "RegistryName": "TVT",
                "FacilityBrandedName": "Heart Hospital of the South",
                "State": "AL",
                "EnrollmentDate": "2015-03-15",
                "CumulativeTAVRvolume": "350",
                "AnnualTAVRVolume": "75",
                "EligiblePatients": "60",
                "TAVRSiteDifference": "",
                "TAVRSiteLowerCI": "",
                "TAVRSiteUpperCI": "",
                "ParticipantRating": "2",
            },
            {
                "FacilityLinkingID": "200002",
                "MPN": "050002",
                "AHA": "6050002",
                "NPI": "9876543210",
                "RegistryName": "TVT",
                "FacilityBrandedName": "Pacific Valve Center",
                "State": "CA",
                "EnrollmentDate": "2018-06-01",
                "CumulativeTAVRvolume": "120",
                "AnnualTAVRVolume": "40",
                "EligiblePatients": "",
                "TAVRSiteDifference": "",
                "TAVRSiteLowerCI": "",
                "TAVRSiteUpperCI": "",
                "ParticipantRating": "1",
            },
        ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _hospitals_csv(rows=None):
    """Build a Hospitals-style CSV string.

    Contains a subset of the ~30 real columns. We include the key merge
    column (FacilityLinkingID) and the TranscatheterValveCertification
    column that indicates TVC status.
    """
    if rows is None:
        rows = [
            {
                "FacilityLinkingID": "100001",
                "MPN": "010001",
                "AHA": "6010001",
                "NPI": "1234567890",
                "FacilityBrandedName": "Heart Hospital of the South",
                "Address": "123 Heart Lane",
                "City": "Birmingham",
                "State": "AL",
                "Zip": "35201",
                "Phone": "205-555-0100",
                "TranscatheterValveCertification": "Y",
            },
            {
                "FacilityLinkingID": "200002",
                "MPN": "050002",
                "AHA": "6050002",
                "NPI": "9876543210",
                "FacilityBrandedName": "Pacific Valve Center",
                "Address": "456 Ocean Blvd",
                "City": "Los Angeles",
                "State": "CA",
                "Zip": "90001",
                "Phone": "310-555-0200",
                "TranscatheterValveCertification": "N",
            },
            {
                "FacilityLinkingID": "300003",
                "MPN": "110003",
                "AHA": "6110003",
                "NPI": "1111111111",
                "FacilityBrandedName": "Northeast Cardiac",
                "Address": "789 Elm St",
                "City": "Boston",
                "State": "MA",
                "Zip": "02101",
                "Phone": "617-555-0300",
                "TranscatheterValveCertification": "Y",
            },
        ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _legacy_csv():
    """Build a legacy / manual-upload CSV string."""
    rows = [
        {
            "Facility Name": "Legacy Heart Center",
            "Address": "100 Main St",
            "City": "Dallas",
            "State": "TX",
            "Zip": "75201",
            "Certification Type": "Transcatheter Valve Certification",
            "Certification Date": "2024-01-15",
            "Expiration Date": "2027-01-15",
        },
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Tests: ACCTVCFetcher initialisation
# ---------------------------------------------------------------------------

class TestACCTVCFetcherInit:
    """Verify ACCTVCFetcher initialises correctly."""

    def test_fetcher_init(self, tmp_path):
        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        assert fetcher.SOURCE_NAME == "acc_tvc"
        assert "ncdr.com" in fetcher.BASE_URL
        assert fetcher.data_dir == tmp_path
        assert fetcher.session is not None

    def test_fetcher_init_defaults(self):
        fetcher = ACCTVCFetcher()
        assert fetcher.SOURCE_NAME == "acc_tvc"
        assert fetcher.data_dir.exists()

    def test_get_latest_url(self, tmp_path):
        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        url = fetcher.get_latest_url()
        assert url == NCDR_TVT_METRICS_URL
        assert "TVTMetrics" in url


# ---------------------------------------------------------------------------
# Tests: fetch() with mocked HTTP — happy path
# ---------------------------------------------------------------------------

class TestFetchHappyPath:
    """Verify the full fetch flow using mocked HTTP."""

    @responses.activate
    def test_fetch_tvt_and_hospitals_merged(self, tmp_path):
        """Both TVTMetrics and Hospitals succeed and merge on FacilityLinkingID."""
        responses.add(
            responses.GET,
            NCDR_TVT_METRICS_URL,
            body=_tvt_metrics_csv(),
            status=200,
            content_type="text/csv",
        )
        responses.add(
            responses.GET,
            NCDR_HOSPITALS_URL,
            body=_hospitals_csv(),
            status=200,
            content_type="text/csv",
        )

        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        result = fetcher.fetch()

        assert result["status"] == "success"
        assert result["records"] == 2  # 2 TVT records
        assert result["hash"] is not None
        assert "filepath" in result
        assert "hospital_filepath" in result

        # Verify the CSV file was written
        csv_path = Path(result["filepath"])
        assert csv_path.exists()

        # Read back and verify merge happened (Address column from Hospitals)
        with open(csv_path) as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["Address"] == "123 Heart Lane"
        assert rows[0]["City"] == "Birmingham"
        assert rows[0]["TranscatheterValveCertification"] == "Y"

    @responses.activate
    def test_fetch_tvt_only(self, tmp_path):
        """TVTMetrics succeeds, include_hospitals=False."""
        responses.add(
            responses.GET,
            NCDR_TVT_METRICS_URL,
            body=_tvt_metrics_csv(),
            status=200,
            content_type="text/csv",
        )

        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        result = fetcher.fetch(include_hospitals=False)

        assert result["status"] == "success"
        assert result["records"] == 2
        assert "hospital_filepath" not in result


# ---------------------------------------------------------------------------
# Tests: fetch() with mocked HTTP — fallback paths
# ---------------------------------------------------------------------------

class TestFetchFallback:
    """Verify fallback behaviour when primary endpoint fails."""

    @responses.activate
    def test_tvt_fails_hospitals_fallback(self, tmp_path):
        """TVTMetrics fails but Hospitals CSV provides TVC-certified facilities."""
        responses.add(
            responses.GET,
            NCDR_TVT_METRICS_URL,
            body="Internal Server Error",
            status=500,
        )
        responses.add(
            responses.GET,
            NCDR_HOSPITALS_URL,
            body=_hospitals_csv(),
            status=200,
            content_type="text/csv",
        )

        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        result = fetcher.fetch()

        assert result["status"] == "success"
        # Only TVC-certified hospitals extracted (100001 and 300003 have "Y")
        assert result["records"] == 2

    @responses.activate
    def test_both_endpoints_fail(self, tmp_path):
        """Both TVTMetrics and Hospitals fail — returns failed status."""
        responses.add(
            responses.GET,
            NCDR_TVT_METRICS_URL,
            body="Internal Server Error",
            status=500,
        )
        responses.add(
            responses.GET,
            NCDR_HOSPITALS_URL,
            body="Internal Server Error",
            status=500,
        )

        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        result = fetcher.fetch()

        assert result["status"] == "failed"
        assert "No data returned" in result["error"]

    @responses.activate
    def test_tvt_empty_csv(self, tmp_path):
        """TVTMetrics returns empty CSV with only headers."""
        empty_csv = "FacilityLinkingID,FacilityBrandedName,State\n"
        responses.add(
            responses.GET,
            NCDR_TVT_METRICS_URL,
            body=empty_csv,
            status=200,
            content_type="text/csv",
        )
        responses.add(
            responses.GET,
            NCDR_HOSPITALS_URL,
            body=_hospitals_csv(),
            status=200,
            content_type="text/csv",
        )

        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        result = fetcher.fetch()

        # Empty TVT + hospitals with certs -> extracts TVC facilities
        assert result["status"] == "success"
        assert result["records"] == 2  # 2 with cert == "Y"


# ---------------------------------------------------------------------------
# Tests: fetch() — error handling
# ---------------------------------------------------------------------------

class TestFetchErrorHandling:
    """Verify error handling in fetch()."""

    @responses.activate
    def test_fetch_network_timeout(self, tmp_path):
        """Network timeout should return failed status."""
        responses.add(
            responses.GET,
            NCDR_TVT_METRICS_URL,
            body=ConnectionError("Connection timed out"),
        )
        responses.add(
            responses.GET,
            NCDR_HOSPITALS_URL,
            body=ConnectionError("Connection timed out"),
        )

        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        result = fetcher.fetch()

        assert result["status"] == "failed"

    def test_fetch_unexpected_exception(self, tmp_path):
        """An unexpected exception in fetch() is caught."""
        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))

        with patch.object(
            fetcher, "_fetch_tvt_metrics", side_effect=RuntimeError("boom")
        ):
            result = fetcher.fetch()

        assert result["status"] == "failed"
        assert "boom" in result["error"]


# ---------------------------------------------------------------------------
# Tests: internal helpers
# ---------------------------------------------------------------------------

class TestMergeHospitalData:
    """Verify the merge logic between TVT and Hospital records."""

    def test_merge_by_facility_linking_id(self):
        tvt = [
            {"FacilityLinkingID": "100", "FacilityBrandedName": "Hosp A"},
            {"FacilityLinkingID": "200", "FacilityBrandedName": "Hosp B"},
        ]
        hospitals = [
            {
                "FacilityLinkingID": "100",
                "Address": "1 Main St",
                "City": "TestCity",
                "State": "TX",
                "Zip": "75001",
                "Phone": "555-0001",
                "TranscatheterValveCertification": "Y",
            },
        ]

        merged = ACCTVCFetcher._merge_hospital_data(tvt, hospitals)

        assert len(merged) == 2
        assert merged[0]["Address"] == "1 Main St"
        assert merged[0]["TranscatheterValveCertification"] == "Y"
        # Second record has no hospital match — fields absent
        assert merged[1].get("Address", "") == ""

    def test_merge_with_empty_hospitals(self):
        tvt = [{"FacilityLinkingID": "100", "Name": "A"}]
        merged = ACCTVCFetcher._merge_hospital_data(tvt, [])
        assert len(merged) == 1

    def test_merge_with_empty_tvt(self):
        hospitals = [{"FacilityLinkingID": "100", "Address": "1 Main St"}]
        merged = ACCTVCFetcher._merge_hospital_data([], hospitals)
        assert len(merged) == 0


class TestExtractTVCFromHospitals:
    """Verify TVC extraction from hospital records."""

    def test_extracts_certified_facilities(self):
        hospitals = [
            {"FacilityBrandedName": "A", "TranscatheterValveCertification": "Y"},
            {"FacilityBrandedName": "B", "TranscatheterValveCertification": "N"},
            {"FacilityBrandedName": "C", "TranscatheterValveCertification": "Y"},
            {"FacilityBrandedName": "D", "TranscatheterValveCertification": ""},
            {"FacilityBrandedName": "E", "TranscatheterValveCertification": "0"},
        ]

        result = ACCTVCFetcher._extract_tvc_from_hospitals(hospitals)

        assert len(result) == 2
        names = [r["FacilityBrandedName"] for r in result]
        assert "A" in names
        assert "C" in names

    def test_empty_hospitals(self):
        result = ACCTVCFetcher._extract_tvc_from_hospitals([])
        assert result == []


class TestWriteCSV:
    """Verify CSV writing."""

    def test_write_csv(self, tmp_path):
        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        records = [
            {"name": "A", "value": "1"},
            {"name": "B", "value": "2"},
        ]

        filepath = fetcher._write_csv(records, "test_output.csv")

        assert filepath.exists()
        with open(filepath) as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "A"

    def test_write_empty_csv(self, tmp_path):
        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        filepath = fetcher._write_csv([], "empty.csv")
        assert filepath.exists()
        assert filepath.read_text() == ""


# ---------------------------------------------------------------------------
# Tests: manual CSV upload
# ---------------------------------------------------------------------------

class TestManualCSVUpload:
    """Verify the load_manual_csv method."""

    def test_manual_upload_success(self, tmp_path):
        # Create a source CSV
        source_file = tmp_path / "source" / "manual_tvc.csv"
        source_file.parent.mkdir()
        source_file.write_text(_legacy_csv())

        data_dir = tmp_path / "data"
        fetcher = ACCTVCFetcher(data_dir=str(data_dir))
        result = fetcher.load_manual_csv(str(source_file))

        assert result["status"] == "success"
        assert result["records"] == 1
        assert result["source"] == "manual_upload"
        assert result["hash"] is not None
        assert Path(result["filepath"]).exists()

    def test_manual_upload_file_not_found(self, tmp_path):
        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        result = fetcher.load_manual_csv("/nonexistent/path.csv")

        assert result["status"] == "failed"
        assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# Tests: loader format detection and column mapping
# ---------------------------------------------------------------------------

class TestFormatDetection:
    """Verify auto-detection of CSV format in the loader."""

    def test_detect_ncdr_format(self):
        columns = [
            "FacilityLinkingID", "FacilityBrandedName", "State",
            "CumulativeTAVRvolume",
        ]
        assert _detect_format(columns) == "ncdr"

    def test_detect_legacy_format(self):
        columns = ["Facility Name", "City", "State", "Certification Type"]
        assert _detect_format(columns) == "legacy"

    def test_detect_with_registry_name(self):
        columns = ["RegistryName", "FacilityBrandedName"]
        assert _detect_format(columns) == "ncdr"


class TestColumnMapping:
    """Verify column mapping applies correctly."""

    def test_ncdr_column_mapping(self):
        import pandas as pd

        df = pd.DataFrame({
            "FacilityBrandedName": ["Hospital A"],
            "State": ["CA"],
            "Zip": ["90001"],
        })

        result = _apply_column_mapping(df, "ncdr")
        assert "facility_name" in result.columns
        assert "state" in result.columns
        assert "zip_code" in result.columns

    def test_legacy_column_mapping(self):
        import pandas as pd

        df = pd.DataFrame({
            "Facility Name": ["Hospital A"],
            "State": ["CA"],
            "Zip Code": ["90001"],
        })

        result = _apply_column_mapping(df, "legacy")
        assert "facility_name" in result.columns
        assert "zip_code" in result.columns


# ---------------------------------------------------------------------------
# Tests: date parsing
# ---------------------------------------------------------------------------

class TestDateParsing:
    """Verify parse_date handles various formats."""

    def test_iso_date(self):
        assert parse_date("2026-01-15") == date(2026, 1, 15)

    def test_us_date(self):
        assert parse_date("01/15/2026") == date(2026, 1, 15)

    def test_none_value(self):
        assert parse_date(None) is None

    def test_nan_value(self):
        assert parse_date(float("nan")) is None

    def test_invalid_date(self):
        assert parse_date("not-a-date") is None


# ---------------------------------------------------------------------------
# Tests: Pydantic validator — ACCTVCCertificationRecord
# ---------------------------------------------------------------------------

class TestACCTVCCertificationRecordValid:
    """Test that valid records pass Pydantic validation."""

    def test_full_record(self):
        record = ACCTVCCertificationRecord(
            facility_name="Heart Hospital of the South",
            facility_address="123 Heart Lane",
            city="Birmingham",
            state="AL",
            zip_code="35201",
            certification_type="Transcatheter Valve Certification",
            certification_date=date(2024, 1, 15),
            expiration_date=date(2027, 1, 15),
        )
        assert record.facility_name == "Heart Hospital of the South"
        assert record.state == "AL"
        assert record.certification_type == "Transcatheter Valve Certification"

    def test_minimal_record(self):
        record = ACCTVCCertificationRecord(
            facility_name="Minimal Hospital",
            certification_type="TVC",
        )
        assert record.facility_name == "Minimal Hospital"
        assert record.facility_address is None
        assert record.city is None
        assert record.state is None
        assert record.certification_date is None

    def test_state_uppercased(self):
        record = ACCTVCCertificationRecord(
            facility_name="Test",
            certification_type="TVC",
            state="ca",
        )
        assert record.state == "CA"

    def test_whitespace_stripped(self):
        record = ACCTVCCertificationRecord(
            facility_name="  Test Hospital  ",
            certification_type="  TVC  ",
        )
        assert record.facility_name == "Test Hospital"
        assert record.certification_type == "TVC"


class TestACCTVCCertificationRecordInvalid:
    """Test that invalid records are rejected."""

    def test_empty_facility_name_rejected(self):
        with pytest.raises(Exception):
            ACCTVCCertificationRecord(
                facility_name="",
                certification_type="TVC",
            )

    def test_missing_facility_name_rejected(self):
        with pytest.raises(Exception):
            ACCTVCCertificationRecord(
                certification_type="TVC",
            )

    def test_missing_certification_type_rejected(self):
        with pytest.raises(Exception):
            ACCTVCCertificationRecord(
                facility_name="Test",
            )

    def test_state_too_long_rejected(self):
        with pytest.raises(Exception):
            ACCTVCCertificationRecord(
                facility_name="Test",
                certification_type="TVC",
                state="CAL",
            )


# ---------------------------------------------------------------------------
# Tests: hash & log helpers (inherited from BaseFetcher)
# ---------------------------------------------------------------------------

class TestBaseFetcherHelpers:
    """Verify inherited BaseFetcher helpers work with ACCTVCFetcher."""

    def test_calculate_hash(self, tmp_path):
        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        test_file = tmp_path / "hash_test.txt"
        test_file.write_text("hello world")
        hash_val = fetcher.calculate_hash(test_file)
        assert len(hash_val) == 32  # MD5 hex digest length

    def test_log_fetch_result_success(self, tmp_path):
        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        # Should not raise
        fetcher.log_fetch_result({"status": "success", "records": 100})

    def test_log_fetch_result_failure(self, tmp_path):
        fetcher = ACCTVCFetcher(data_dir=str(tmp_path))
        # Should not raise
        fetcher.log_fetch_result({"status": "failed", "error": "timeout"})
