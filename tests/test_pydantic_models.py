"""Pydantic model validation tests.

Tests instantiation with valid data, missing required fields, type coercion,
and field validators for core data platform models.
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dk_data.ingestion.utils.validators import (
    CMSMedicareInpatientRecord,
    ACCTVCCertificationRecord,
    HRSAShortageAreaRecord,
    CMSHospitalInfoRecord,
    CMSCostReportRecord,
    StagingHospitalRecord,
    TargetScoreRecord,
    is_tavr_drg,
    estimate_total_volume,
    calculate_tier,
)


# ---- CMSMedicareInpatientRecord ----

class TestCMSMedicareInpatientRecord:
    def test_valid_record(self):
        record = CMSMedicareInpatientRecord(
            provider_id="100001",
            drg_code="266",
            total_discharges=42,
            fiscal_year=2023,
        )
        assert record.provider_id == "100001"
        assert record.drg_code == "266"
        assert record.total_discharges == 42

    def test_provider_id_short_rejected(self):
        """Provider IDs shorter than 6 chars are rejected by min_length."""
        with pytest.raises(ValidationError):
            CMSMedicareInpatientRecord(
                provider_id="1234",
                drg_code="267",
                total_discharges=10,
                fiscal_year=2023,
            )

    def test_provider_id_whitespace_stripped(self):
        record = CMSMedicareInpatientRecord(
            provider_id="  100001  ",
            drg_code="267",
            total_discharges=10,
            fiscal_year=2023,
        )
        assert record.provider_id == "100001"

    def test_state_uppercased(self):
        record = CMSMedicareInpatientRecord(
            provider_id="100001",
            provider_state="ca",
            drg_code="266",
            total_discharges=1,
            fiscal_year=2023,
        )
        assert record.provider_state == "CA"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            CMSMedicareInpatientRecord(provider_id="100001")

    def test_negative_discharges_rejected(self):
        with pytest.raises(ValidationError):
            CMSMedicareInpatientRecord(
                provider_id="100001",
                drg_code="266",
                total_discharges=-1,
                fiscal_year=2023,
            )

    def test_fiscal_year_bounds(self):
        with pytest.raises(ValidationError):
            CMSMedicareInpatientRecord(
                provider_id="100001",
                drg_code="266",
                total_discharges=1,
                fiscal_year=1999,
            )


# ---- ACCTVCCertificationRecord ----

class TestACCTVCCertificationRecord:
    def test_valid_record(self):
        record = ACCTVCCertificationRecord(
            facility_name="Test Hospital",
            certification_type="TAVR",
        )
        assert record.facility_name == "Test Hospital"

    def test_missing_facility_name(self):
        with pytest.raises(ValidationError):
            ACCTVCCertificationRecord(certification_type="TAVR")

    def test_state_uppercased(self):
        record = ACCTVCCertificationRecord(
            facility_name="Test", certification_type="TAVR", state="ny"
        )
        assert record.state == "NY"


# ---- HRSAShortageAreaRecord ----

class TestHRSAShortageAreaRecord:
    def test_valid_record(self):
        record = HRSAShortageAreaRecord(
            hpsa_id="12345",
            state_abbr="TX",
        )
        assert record.state_abbr == "TX"

    def test_hpsa_score_bounds(self):
        with pytest.raises(ValidationError):
            HRSAShortageAreaRecord(hpsa_id="1", state_abbr="TX", hpsa_score=30)


# ---- CMSHospitalInfoRecord ----

class TestCMSHospitalInfoRecord:
    def test_valid_record(self):
        record = CMSHospitalInfoRecord(
            provider_id="100001",
            hospital_name="General Hospital",
            state="CA",
        )
        assert record.hospital_name == "General Hospital"

    def test_rating_bounds(self):
        with pytest.raises(ValidationError):
            CMSHospitalInfoRecord(
                provider_id="100001",
                hospital_name="Test",
                state="CA",
                hospital_overall_rating=6,
            )


# ---- CMSCostReportRecord ----

class TestCMSCostReportRecord:
    def test_valid_record(self):
        record = CMSCostReportRecord(
            provider_id="100001",
            total_beds=200,
            operating_margin=Decimal("0.05"),
        )
        assert record.total_beds == 200

    def test_negative_beds_rejected(self):
        with pytest.raises(ValidationError):
            CMSCostReportRecord(provider_id="100001", total_beds=-1)


# ---- StagingHospitalRecord ----

class TestStagingHospitalRecord:
    def test_valid_record(self):
        record = StagingHospitalRecord(
            hospital_id="100001",
            hospital_name="Test Hospital",
            state="CA",
        )
        assert record.state == "CA"

    def test_latitude_longitude_bounds(self):
        with pytest.raises(ValidationError):
            StagingHospitalRecord(
                hospital_id="100001",
                hospital_name="Test",
                state="CA",
                latitude=Decimal("100"),
            )


# ---- TargetScoreRecord ----

class TestTargetScoreRecord:
    def test_valid_record(self):
        record = TargetScoreRecord(
            hospital_key=1,
            score_date=date(2024, 1, 15),
            total_trs=750,
            tier_classification="B",
        )
        assert record.tier_classification == "B"
        assert record.total_trs == 750

    def test_invalid_tier(self):
        with pytest.raises(ValidationError):
            TargetScoreRecord(
                hospital_key=1,
                score_date=date(2024, 1, 15),
                total_trs=500,
                tier_classification="F",
            )

    def test_trs_bounds(self):
        with pytest.raises(ValidationError):
            TargetScoreRecord(
                hospital_key=1,
                score_date=date(2024, 1, 15),
                total_trs=1500,
                tier_classification="A",
            )


# ---- Utility functions ----

class TestUtilityFunctions:
    def test_is_tavr_drg_true(self):
        assert is_tavr_drg("266") is True
        assert is_tavr_drg("267") is True

    def test_is_tavr_drg_false(self):
        assert is_tavr_drg("100") is False
        assert is_tavr_drg("") is False

    def test_estimate_total_volume(self):
        assert estimate_total_volume(65) == 100
        assert estimate_total_volume(0) == 0

    def test_calculate_tier(self):
        assert calculate_tier(900) == "A"
        assert calculate_tier(700) == "B"
        assert calculate_tier(500) == "C"
        assert calculate_tier(300) == "D"
        assert calculate_tier(100) == "E"
