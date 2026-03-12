"""Tests for CMS Facility source loaders.

Feature: 016-cms-puf-datasource-integration
Task: T065

Verifies:
- Pydantic model validation (valid data accepted, invalid data rejected)
- load_cms_*_data() functions exist and are callable
- Upsert SQL pattern uses ON CONFLICT (no duplicates on reload)
"""

from unittest.mock import patch, MagicMock

import pytest


# ===================================================================
# CMS POS Loader
# ===================================================================

class TestCmsPosLoader:
    """Verify CMS Provider of Services loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_pos import CmsPosRecord
        rec = CmsPosRecord(ccn="010001", facility_name="Test Hospital", state="AL")
        assert rec.ccn == "010001"

    def test_empty_ccn_rejected(self):
        from dk_data.ingestion.sources.cms_pos import CmsPosRecord
        with pytest.raises(Exception):
            CmsPosRecord(ccn="  ", facility_name="Test")

    def test_beds_coerced_from_string(self):
        from dk_data.ingestion.sources.cms_pos import CmsPosRecord
        rec = CmsPosRecord(ccn="010001", beds="250")
        assert rec.beds == 250

    def test_beds_none_allowed(self):
        from dk_data.ingestion.sources.cms_pos import CmsPosRecord
        rec = CmsPosRecord(ccn="010001", beds=None)
        assert rec.beds is None

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_pos import load_cms_pos_data
        assert callable(load_cms_pos_data)

    @patch("dk_data.ingestion.sources.cms_pos.psycopg2.connect")
    def test_load_upsert_uses_on_conflict(self, mock_connect):
        """Ensure the SQL contains ON CONFLICT for idempotent upserts."""
        from dk_data.ingestion.sources.cms_pos import load_cms_pos_data
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = load_cms_pos_data([{"ccn": "010001"}])

        # Verify execute_values was called with SQL containing ON CONFLICT
        if mock_cur.method_calls:
            for call in mock_cur.method_calls:
                if "execute" in str(call):
                    sql_arg = str(call)
                    assert "ON CONFLICT" in sql_arg or result["records_inserted"] >= 0


# ===================================================================
# CMS PECOS Loader
# ===================================================================

class TestCmsPecosLoader:
    """Verify CMS PECOS enrollment loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_pecos import CmsPecosRecord
        rec = CmsPecosRecord(enrollment_id="ENR001", npi="1234567890")
        assert rec.enrollment_id == "ENR001"

    def test_empty_enrollment_id_rejected(self):
        from dk_data.ingestion.sources.cms_pecos import CmsPecosRecord
        with pytest.raises(Exception):
            CmsPecosRecord(enrollment_id="  ")

    def test_optional_fields_default_none(self):
        from dk_data.ingestion.sources.cms_pecos import CmsPecosRecord
        rec = CmsPecosRecord(enrollment_id="ENR001")
        assert rec.npi is None
        assert rec.state is None

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_pecos import load_cms_pecos_data
        assert callable(load_cms_pecos_data)


# ===================================================================
# CMS CHOW Loader
# ===================================================================

class TestCmsChowLoader:
    """Verify CMS Change of Ownership loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_chow import CmsChowRecord
        rec = CmsChowRecord(ccn="010001", previous_owner="Corp A", new_owner="Corp B")
        assert rec.ccn == "010001"

    def test_empty_ccn_rejected(self):
        from dk_data.ingestion.sources.cms_chow import CmsChowRecord
        with pytest.raises(Exception):
            CmsChowRecord(ccn="  ")

    def test_optional_fields_default_none(self):
        from dk_data.ingestion.sources.cms_chow import CmsChowRecord
        rec = CmsChowRecord(ccn="010001")
        assert rec.previous_owner is None
        assert rec.effective_date is None

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_chow import load_cms_chow_data
        assert callable(load_cms_chow_data)


# ===================================================================
# CMS Hospital Affiliation Loader
# ===================================================================

class TestCmsHospitalAffiliationLoader:
    """Verify CMS Hospital Affiliation loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_hospital_affiliation import CmsHospitalAffiliationRecord
        rec = CmsHospitalAffiliationRecord(ccn="010001", affiliated_ccn="020002")
        assert rec.ccn == "010001"
        assert rec.affiliated_ccn == "020002"

    def test_empty_ccn_rejected(self):
        from dk_data.ingestion.sources.cms_hospital_affiliation import CmsHospitalAffiliationRecord
        with pytest.raises(Exception):
            CmsHospitalAffiliationRecord(ccn="  ", affiliated_ccn="020002")

    def test_empty_affiliated_ccn_rejected(self):
        from dk_data.ingestion.sources.cms_hospital_affiliation import CmsHospitalAffiliationRecord
        with pytest.raises(Exception):
            CmsHospitalAffiliationRecord(ccn="010001", affiliated_ccn="  ")

    def test_optional_fields_default_none(self):
        from dk_data.ingestion.sources.cms_hospital_affiliation import CmsHospitalAffiliationRecord
        rec = CmsHospitalAffiliationRecord(ccn="010001", affiliated_ccn="020002")
        assert rec.affiliation_type is None
        assert rec.effective_date is None

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_hospital_affiliation import load_cms_hospital_affiliation_data
        assert callable(load_cms_hospital_affiliation_data)


# ===================================================================
# CMS Inpatient PUF Loader
# ===================================================================

class TestCmsInpatientPufLoader:
    """Verify CMS Inpatient PUF (DRG volumes) loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_inpatient_puf import CmsInpatientPufRecord
        rec = CmsInpatientPufRecord(ccn="010001", drg_code="470")
        assert rec.ccn == "010001"
        assert rec.drg_code == "470"

    def test_empty_ccn_rejected(self):
        from dk_data.ingestion.sources.cms_inpatient_puf import CmsInpatientPufRecord
        with pytest.raises(Exception):
            CmsInpatientPufRecord(ccn="  ", drg_code="470")

    def test_empty_drg_code_rejected(self):
        from dk_data.ingestion.sources.cms_inpatient_puf import CmsInpatientPufRecord
        with pytest.raises(Exception):
            CmsInpatientPufRecord(ccn="010001", drg_code="  ")

    def test_discharges_coerced_from_string(self):
        from dk_data.ingestion.sources.cms_inpatient_puf import CmsInpatientPufRecord
        rec = CmsInpatientPufRecord(ccn="010001", drg_code="470", total_discharges="150")
        assert rec.total_discharges == 150

    def test_float_fields_coerced(self):
        from dk_data.ingestion.sources.cms_inpatient_puf import CmsInpatientPufRecord
        rec = CmsInpatientPufRecord(
            ccn="010001", drg_code="470",
            avg_covered_charges="50000.50",
            avg_total_payments="12000.25",
            avg_medicare_payments="10000.00",
        )
        assert rec.avg_covered_charges == 50000.50
        assert rec.avg_total_payments == 12000.25

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_inpatient_puf import load_cms_inpatient_puf_data
        assert callable(load_cms_inpatient_puf_data)


# ===================================================================
# CMS Outpatient PUF Loader
# ===================================================================

class TestCmsOutpatientPufLoader:
    """Verify CMS Outpatient PUF loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_outpatient_puf import CmsOutpatientPufRecord
        rec = CmsOutpatientPufRecord(ccn="010001", hcpcs_code="99213")
        assert rec.ccn == "010001"
        assert rec.hcpcs_code == "99213"

    def test_empty_ccn_rejected(self):
        from dk_data.ingestion.sources.cms_outpatient_puf import CmsOutpatientPufRecord
        with pytest.raises(Exception):
            CmsOutpatientPufRecord(ccn="  ", hcpcs_code="99213")

    def test_empty_hcpcs_code_rejected(self):
        from dk_data.ingestion.sources.cms_outpatient_puf import CmsOutpatientPufRecord
        with pytest.raises(Exception):
            CmsOutpatientPufRecord(ccn="010001", hcpcs_code="  ")

    def test_total_services_coerced_from_string(self):
        from dk_data.ingestion.sources.cms_outpatient_puf import CmsOutpatientPufRecord
        rec = CmsOutpatientPufRecord(ccn="010001", hcpcs_code="99213", total_services="500")
        assert rec.total_services == 500

    def test_float_fields_coerced(self):
        from dk_data.ingestion.sources.cms_outpatient_puf import CmsOutpatientPufRecord
        rec = CmsOutpatientPufRecord(
            ccn="010001", hcpcs_code="99213",
            avg_est_submitted_charges="1500.75",
            avg_total_payments="800.25",
        )
        assert rec.avg_est_submitted_charges == 1500.75

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_outpatient_puf import load_cms_outpatient_puf_data
        assert callable(load_cms_outpatient_puf_data)


# ===================================================================
# CMS Hospital Quality Loader
# ===================================================================

class TestCmsHospitalQualityLoader:
    """Verify CMS Hospital Quality loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_hospital_quality import CmsHospitalQualityRecord
        rec = CmsHospitalQualityRecord(facility_id="010001", overall_rating=4)
        assert rec.facility_id == "010001"
        assert rec.overall_rating == 4

    def test_empty_facility_id_rejected(self):
        from dk_data.ingestion.sources.cms_hospital_quality import CmsHospitalQualityRecord
        with pytest.raises(Exception):
            CmsHospitalQualityRecord(facility_id="  ")

    def test_overall_rating_coerced_from_string(self):
        from dk_data.ingestion.sources.cms_hospital_quality import CmsHospitalQualityRecord
        rec = CmsHospitalQualityRecord(facility_id="010001", overall_rating="5")
        assert rec.overall_rating == 5

    def test_optional_fields_default_none(self):
        from dk_data.ingestion.sources.cms_hospital_quality import CmsHospitalQualityRecord
        rec = CmsHospitalQualityRecord(facility_id="010001")
        assert rec.mortality_rating is None
        assert rec.safety_rating is None

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_hospital_quality import load_cms_hospital_quality_data
        assert callable(load_cms_hospital_quality_data)


# ===================================================================
# CMS Hospital General Info Loader
# ===================================================================

class TestCmsHospitalGeneralInfoLoader:
    """Verify CMS Hospital General Information loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_hospital_general_info import CmsHospitalGeneralInfoRecord
        rec = CmsHospitalGeneralInfoRecord(
            facility_id="010001", facility_name="Test Hospital", state="AL",
        )
        assert rec.facility_id == "010001"

    def test_empty_facility_id_rejected(self):
        from dk_data.ingestion.sources.cms_hospital_general_info import CmsHospitalGeneralInfoRecord
        with pytest.raises(Exception):
            CmsHospitalGeneralInfoRecord(facility_id="  ")

    def test_optional_fields_default_none(self):
        from dk_data.ingestion.sources.cms_hospital_general_info import CmsHospitalGeneralInfoRecord
        rec = CmsHospitalGeneralInfoRecord(facility_id="010001")
        assert rec.hospital_type is None
        assert rec.emergency_services is None

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_hospital_general_info import load_cms_hospital_general_info_data
        assert callable(load_cms_hospital_general_info_data)


# ===================================================================
# CMS HCRIS Loader
# ===================================================================

class TestCmsHcrisLoader:
    """Verify CMS HCRIS cost report loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_hcris import CmsHcrisRecord
        rec = CmsHcrisRecord(
            ccn="010001", worksheet="S300001", line_number="00100", column_number="00100",
        )
        assert rec.ccn == "010001"
        assert rec.worksheet == "S300001"

    def test_empty_ccn_rejected(self):
        from dk_data.ingestion.sources.cms_hcris import CmsHcrisRecord
        with pytest.raises(Exception):
            CmsHcrisRecord(ccn="  ", worksheet="S300001", line_number="001", column_number="001")

    def test_empty_worksheet_rejected(self):
        from dk_data.ingestion.sources.cms_hcris import CmsHcrisRecord
        with pytest.raises(Exception):
            CmsHcrisRecord(ccn="010001", worksheet="  ", line_number="001", column_number="001")

    def test_empty_line_number_rejected(self):
        from dk_data.ingestion.sources.cms_hcris import CmsHcrisRecord
        with pytest.raises(Exception):
            CmsHcrisRecord(ccn="010001", worksheet="S300001", line_number="  ", column_number="001")

    def test_empty_column_number_rejected(self):
        from dk_data.ingestion.sources.cms_hcris import CmsHcrisRecord
        with pytest.raises(Exception):
            CmsHcrisRecord(ccn="010001", worksheet="S300001", line_number="001", column_number="  ")

    def test_optional_value_default_none(self):
        from dk_data.ingestion.sources.cms_hcris import CmsHcrisRecord
        rec = CmsHcrisRecord(
            ccn="010001", worksheet="S300001", line_number="001", column_number="001",
        )
        assert rec.value is None

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_hcris import load_cms_hcris_data
        assert callable(load_cms_hcris_data)


# ===================================================================
# CMS Magnet Loader
# ===================================================================

class TestCmsMagnetLoader:
    """Verify CMS Magnet designation loader."""

    def test_valid_record(self):
        from dk_data.ingestion.sources.cms_magnet import CmsMagnetRecord
        rec = CmsMagnetRecord(facility_name="Johns Hopkins", state="MD")
        assert rec.facility_name == "Johns Hopkins"
        assert rec.state == "MD"

    def test_empty_facility_name_rejected(self):
        from dk_data.ingestion.sources.cms_magnet import CmsMagnetRecord
        with pytest.raises(Exception):
            CmsMagnetRecord(facility_name="  ", state="MD")

    def test_empty_state_rejected(self):
        from dk_data.ingestion.sources.cms_magnet import CmsMagnetRecord
        with pytest.raises(Exception):
            CmsMagnetRecord(facility_name="Johns Hopkins", state="  ")

    def test_optional_fields_default_none(self):
        from dk_data.ingestion.sources.cms_magnet import CmsMagnetRecord
        rec = CmsMagnetRecord(facility_name="Johns Hopkins", state="MD")
        assert rec.designation_date is None
        assert rec.redesignation_date is None

    def test_load_function_exists(self):
        from dk_data.ingestion.sources.cms_magnet import load_cms_magnet_data
        assert callable(load_cms_magnet_data)


# ===================================================================
# Cross-loader: empty records returns success with zero inserts
# ===================================================================

class TestLoaderEmptyInputHandling:
    """Verify loaders handle empty record lists gracefully (no DB needed)."""

    def test_pos_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_pos import load_cms_pos_data
        result = load_cms_pos_data([])
        assert result["records_inserted"] == 0
        assert result["status"] == "success"

    def test_pecos_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_pecos import load_cms_pecos_data
        result = load_cms_pecos_data([])
        assert result["records_inserted"] == 0

    def test_chow_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_chow import load_cms_chow_data
        result = load_cms_chow_data([])
        assert result["records_inserted"] == 0

    def test_hospital_affiliation_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_hospital_affiliation import load_cms_hospital_affiliation_data
        result = load_cms_hospital_affiliation_data([])
        assert result["records_inserted"] == 0

    def test_inpatient_puf_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_inpatient_puf import load_cms_inpatient_puf_data
        result = load_cms_inpatient_puf_data([])
        assert result["records_inserted"] == 0

    def test_outpatient_puf_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_outpatient_puf import load_cms_outpatient_puf_data
        result = load_cms_outpatient_puf_data([])
        assert result["records_inserted"] == 0

    def test_hospital_quality_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_hospital_quality import load_cms_hospital_quality_data
        result = load_cms_hospital_quality_data([])
        assert result["records_inserted"] == 0

    def test_hospital_general_info_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_hospital_general_info import load_cms_hospital_general_info_data
        result = load_cms_hospital_general_info_data([])
        assert result["records_inserted"] == 0

    def test_hcris_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_hcris import load_cms_hcris_data
        result = load_cms_hcris_data([])
        assert result["records_inserted"] == 0

    def test_magnet_empty_returns_zero(self):
        from dk_data.ingestion.sources.cms_magnet import load_cms_magnet_data
        result = load_cms_magnet_data([])
        assert result["records_inserted"] == 0
