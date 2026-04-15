"""Unit tests for the evidence_tier classification logic.

Feature: 006-claims-engine-data-gaps (T015)

Validates the CASE expression mapping publication_type strings to
evidence tier categories A/B/C/D/U as defined in the mol_silver.publications
model.
"""

from __future__ import annotations

import pytest


def classify_evidence_tier(publication_type: str | None, source: str = "") -> str:
    """Pure-Python mirror of the SQL CASE expression in mol_silver.publications.

    This replicates the exact same logic so we can unit-test classification
    without a database connection.
    """
    # Tier A: Cochrane source or systematic review / meta-analysis
    if source == "cochrane_reviews":
        return "A"
    if publication_type is not None:
        pt_lower = publication_type.lower()
        if "systematic review" in pt_lower or "meta-analysis" in pt_lower:
            return "A"
        # Tier B: RCTs, clinical trials, controlled studies
        if "randomized" in pt_lower or "clinical trial" in pt_lower or "controlled" in pt_lower:
            return "B"
        # Tier C: Observational, cohort, case-control, real-world
        if (
            "observational" in pt_lower
            or "cohort" in pt_lower
            or "case-control" in pt_lower
            or "real-world" in pt_lower
        ):
            return "C"
        # Tier D: Case reports, editorials, comments, letters, opinions
        if (
            "case report" in pt_lower
            or "editorial" in pt_lower
            or "comment" in pt_lower
            or "letter" in pt_lower
            or "opinion" in pt_lower
        ):
            return "D"
    # Default: unclassified
    return "U"


# --- Tier A ---
@pytest.mark.parametrize(
    "publication_type,source,expected",
    [
        ("Systematic Review", "pubmed", "A"),
        ("systematic review of RCTs", "openalex", "A"),
        ("Meta-Analysis", "pubmed", "A"),
        ("meta-analysis of cohort studies", "openalex", "A"),
        ("Cochrane Review", "cochrane_reviews", "A"),
        (None, "cochrane_reviews", "A"),
        ("Intervention Review", "cochrane_reviews", "A"),
    ],
    ids=[
        "pubmed-systematic-review",
        "openalex-systematic-review-rcts",
        "pubmed-meta-analysis",
        "openalex-meta-analysis-cohort",
        "cochrane-review-type",
        "cochrane-null-pubtype",
        "cochrane-intervention-review",
    ],
)
def test_tier_a(publication_type: str | None, source: str, expected: str) -> None:
    assert classify_evidence_tier(publication_type, source) == expected


# --- Tier B ---
@pytest.mark.parametrize(
    "publication_type,expected",
    [
        ("Randomized Controlled Trial", "B"),
        ("Clinical Trial, Phase III", "B"),
        ("Clinical Trial", "B"),
        ("Controlled Clinical Trial", "B"),
        ("Randomized study of aspirin", "B"),
    ],
    ids=[
        "rct",
        "clinical-trial-phase-iii",
        "clinical-trial-generic",
        "controlled-clinical-trial",
        "randomized-study",
    ],
)
def test_tier_b(publication_type: str, expected: str) -> None:
    assert classify_evidence_tier(publication_type) == expected


# --- Tier C ---
@pytest.mark.parametrize(
    "publication_type,expected",
    [
        ("Observational Study", "C"),
        ("Cohort study of diabetes patients", "C"),
        ("Case-Control Study", "C"),
        ("Real-World Evidence Study", "C"),
        ("real-world data analysis", "C"),
    ],
    ids=[
        "observational",
        "cohort",
        "case-control",
        "real-world-evidence",
        "real-world-data",
    ],
)
def test_tier_c(publication_type: str, expected: str) -> None:
    assert classify_evidence_tier(publication_type) == expected


# --- Tier D ---
@pytest.mark.parametrize(
    "publication_type,expected",
    [
        ("Case Reports", "D"),
        ("Editorial", "D"),
        ("Comment", "D"),
        ("Letter", "D"),
        ("Expert Opinion", "D"),
        ("Letter to the Editor", "D"),
    ],
    ids=[
        "case-reports",
        "editorial",
        "comment",
        "letter",
        "expert-opinion",
        "letter-to-editor",
    ],
)
def test_tier_d(publication_type: str, expected: str) -> None:
    assert classify_evidence_tier(publication_type) == expected


# --- Tier U (unclassified) ---
@pytest.mark.parametrize(
    "publication_type,expected",
    [
        ("journal-article", "U"),
        ("review", "U"),
        ("book-chapter", "U"),
        (None, "U"),
        ("", "U"),
        ("Guideline", "U"),
    ],
    ids=[
        "journal-article",
        "generic-review",
        "book-chapter",
        "none",
        "empty-string",
        "guideline",
    ],
)
def test_tier_u(publication_type: str | None, expected: str) -> None:
    assert classify_evidence_tier(publication_type) == expected


def test_never_null() -> None:
    """evidence_tier must never be NULL — always returns a string."""
    result = classify_evidence_tier(None, "")
    assert result is not None
    assert isinstance(result, str)
    assert len(result) == 1
