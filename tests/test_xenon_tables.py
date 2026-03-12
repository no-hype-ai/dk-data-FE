"""
Xenon table write/read round-trip tests via PostgREST.

Feature: 015-assessment-dashboard-integration
Task: T014 — Test xenon.assessment_generated and xenon.publication_evidence
       tables for write/read round-trips, constraint enforcement, and dedup.

Tests verify SC-002 (xenon tables operational).
"""

import os
import uuid
import hashlib
import pytest
import time
import jwt as pyjwt

pytestmark = pytest.mark.integration

POSTGREST_URL = os.getenv("POSTGREST_URL", "http://localhost:3030")
JWT_SECRET = os.getenv("PGRST_JWT_SECRET", os.getenv("JWT_SECRET", "super-secret-jwt-token-for-postgrest"))

SECTION_TYPES = [
    "executive_summary",
    "key_metrics",
    "financial_analysis",
    "hcp_segmentation",
    "patient_journey",
    "market_opportunity",
    "dosing_administration",
    "risk_assessment",
    "strategic_recommendations",
    "investment_thesis",
]


def create_jwt_token(role: str, secret: str = JWT_SECRET, expired: bool = False) -> str:
    """Create a JWT token for testing."""
    exp = int(time.time()) - 3600 if expired else int(time.time()) + 3600
    payload = {
        "role": role,
        "exp": exp,
        "iat": int(time.time()),
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def analyst_headers() -> dict:
    """Return authorization headers for analyst role targeting the xenon schema."""
    token = create_jwt_token("analyst")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
        "Content-Profile": "xenon",
        "Accept-Profile": "xenon",
    }


class TestAssessmentGenerated:
    """Test xenon.assessment_generated write/read via PostgREST."""

    def test_write_read_roundtrip(self, postgrest_client):
        """Write an assessment record and read it back."""
        molecule_id = str(uuid.uuid4())
        payload = {
            "molecule_id": molecule_id,
            "section_type": "executive_summary",
            "content": {"summary": "Test executive summary content"},
            "version": 1,
            "generation_source": "test-agent-v1",
        }
        headers = analyst_headers()

        # Write
        resp = postgrest_client.post("/assessment_generated", json=payload, headers=headers)
        assert resp.status_code in (200, 201), f"Write failed: {resp.status_code} {resp.text}"
        created = resp.json()
        assert isinstance(created, list)
        assert len(created) > 0
        record = created[0]
        assert record["molecule_id"] == molecule_id
        assert record["section_type"] == "executive_summary"
        assert record["version"] == 1

        # Read back
        resp = postgrest_client.get(
            f"/assessment_generated?molecule_id=eq.{molecule_id}",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["content"]["summary"] == "Test executive summary content"

    @pytest.mark.parametrize("section_type", SECTION_TYPES)
    def test_all_section_types_accepted(self, postgrest_client, section_type):
        """All 10 section types should be insertable."""
        molecule_id = str(uuid.uuid4())
        payload = {
            "molecule_id": molecule_id,
            "section_type": section_type,
            "content": {"test": True},
            "version": 1,
        }
        headers = analyst_headers()
        resp = postgrest_client.post("/assessment_generated", json=payload, headers=headers)
        assert resp.status_code in (200, 201), (
            f"Section type '{section_type}' rejected: {resp.status_code} {resp.text}"
        )

    def test_invalid_section_type_rejected(self, postgrest_client):
        """Invalid section_type should be rejected by CHECK constraint."""
        molecule_id = str(uuid.uuid4())
        payload = {
            "molecule_id": molecule_id,
            "section_type": "invalid_type",
            "content": {"test": True},
            "version": 1,
        }
        headers = analyst_headers()
        resp = postgrest_client.post("/assessment_generated", json=payload, headers=headers)
        # CHECK constraint violation
        assert resp.status_code in (400, 409, 500)

    def test_unique_constraint_violation(self, postgrest_client):
        """Duplicate (molecule_id, section_type, version) should be rejected."""
        molecule_id = str(uuid.uuid4())
        payload = {
            "molecule_id": molecule_id,
            "section_type": "key_metrics",
            "content": {"metrics": [1, 2, 3]},
            "version": 1,
        }
        headers = analyst_headers()

        # First insert succeeds
        resp = postgrest_client.post("/assessment_generated", json=payload, headers=headers)
        assert resp.status_code in (200, 201)

        # Duplicate insert fails
        resp = postgrest_client.post("/assessment_generated", json=payload, headers=headers)
        assert resp.status_code == 409, f"Expected 409 Conflict, got {resp.status_code}"

    def test_version_incrementing(self, postgrest_client):
        """Different versions of same (molecule_id, section_type) should coexist."""
        molecule_id = str(uuid.uuid4())
        headers = analyst_headers()

        for version in [1, 2, 3]:
            payload = {
                "molecule_id": molecule_id,
                "section_type": "financial_analysis",
                "content": {"version": version, "data": f"v{version}"},
                "version": version,
            }
            resp = postgrest_client.post("/assessment_generated", json=payload, headers=headers)
            assert resp.status_code in (200, 201), f"Version {version} failed: {resp.text}"

        # Read all versions
        resp = postgrest_client.get(
            f"/assessment_generated?molecule_id=eq.{molecule_id}&order=version",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert [d["version"] for d in data] == [1, 2, 3]


class TestPublicationEvidence:
    """Test xenon.publication_evidence write/read via PostgREST."""

    def test_write_read_roundtrip(self, postgrest_client):
        """Write a publication evidence record and read it back."""
        molecule_id = str(uuid.uuid4())
        content_hash = hashlib.sha256(f"test-{uuid.uuid4()}".encode()).hexdigest()
        payload = {
            "molecule_id": molecule_id,
            "trial_nct_id": "NCT12345678",
            "endpoint_name": "Overall Survival",
            "endpoint_type": "primary",
            "hazard_ratio": 0.73,
            "p_value": 0.001,
            "sample_size": 500,
            "confidence_score": 0.85,
            "evidence_source": "publication",
            "doi": "10.1000/test.12345",
            "content_hash": content_hash,
        }
        headers = analyst_headers()

        # Write
        resp = postgrest_client.post("/publication_evidence", json=payload, headers=headers)
        assert resp.status_code in (200, 201), f"Write failed: {resp.status_code} {resp.text}"
        created = resp.json()
        assert isinstance(created, list)
        assert len(created) > 0
        assert created[0]["molecule_id"] == molecule_id
        assert float(created[0]["confidence_score"]) == 0.85

        # Read back
        resp = postgrest_client.get(
            f"/publication_evidence?molecule_id=eq.{molecule_id}",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["endpoint_name"] == "Overall Survival"

    def test_content_hash_dedup(self, postgrest_client):
        """Duplicate content_hash should be rejected."""
        molecule_id = str(uuid.uuid4())
        content_hash = hashlib.sha256(f"dedup-test-{uuid.uuid4()}".encode()).hexdigest()
        payload = {
            "molecule_id": molecule_id,
            "endpoint_name": "PFS",
            "confidence_score": 0.70,
            "evidence_source": "publication",
            "content_hash": content_hash,
        }
        headers = analyst_headers()

        # First insert
        resp = postgrest_client.post("/publication_evidence", json=payload, headers=headers)
        assert resp.status_code in (200, 201)

        # Duplicate content_hash with different molecule
        payload2 = {**payload, "molecule_id": str(uuid.uuid4())}
        resp = postgrest_client.post("/publication_evidence", json=payload2, headers=headers)
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}"

    def test_confidence_score_check_rejects_above_1(self, postgrest_client):
        """confidence_score > 1.0 should be rejected by CHECK constraint."""
        payload = {
            "molecule_id": str(uuid.uuid4()),
            "endpoint_name": "ORR",
            "confidence_score": 1.5,
            "evidence_source": "publication",
            "content_hash": hashlib.sha256(f"invalid-{uuid.uuid4()}".encode()).hexdigest(),
        }
        headers = analyst_headers()
        resp = postgrest_client.post("/publication_evidence", json=payload, headers=headers)
        assert resp.status_code in (400, 409, 500)

    def test_confidence_score_check_rejects_below_0(self, postgrest_client):
        """confidence_score < 0.0 should be rejected by CHECK constraint."""
        payload = {
            "molecule_id": str(uuid.uuid4()),
            "endpoint_name": "ORR",
            "confidence_score": -0.1,
            "evidence_source": "publication",
            "content_hash": hashlib.sha256(f"invalid2-{uuid.uuid4()}".encode()).hexdigest(),
        }
        headers = analyst_headers()
        resp = postgrest_client.post("/publication_evidence", json=payload, headers=headers)
        assert resp.status_code in (400, 409, 500)

    def test_boundary_confidence_scores(self, postgrest_client):
        """Boundary values 0.0 and 1.0 should be accepted."""
        headers = analyst_headers()

        for score in [0.0, 1.0]:
            payload = {
                "molecule_id": str(uuid.uuid4()),
                "endpoint_name": "test_boundary",
                "confidence_score": score,
                "evidence_source": "publication",
                "content_hash": hashlib.sha256(
                    f"boundary-{score}-{uuid.uuid4()}".encode()
                ).hexdigest(),
            }
            resp = postgrest_client.post("/publication_evidence", json=payload, headers=headers)
            assert resp.status_code in (200, 201), (
                f"Confidence score {score} should be accepted, got {resp.status_code}"
            )
