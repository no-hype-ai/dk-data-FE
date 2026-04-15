"""Parameterized tests for evidence_tier classification logic.

Tests the Python implementation of the Oxford CEBM-inspired evidence tier
CASE logic that mirrors the SQL in mol_silver.publications.

Feature: 006-claims-engine-data-gaps (T015)

Tiers:
  A = Cochrane / systematic review / meta-analysis
  B = Randomized controlled trial
  C = Observational / cohort / case-control
  D = Case report / editorial / opinion / letter / comment
  U = Unclassified (default fallback, never NULL)
"""

from __future__ import annotations

import json
import pytest
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# Python implementation mirroring the SQL CASE expression
# ---------------------------------------------------------------------------

def classify_evidence_tier(
    source: str,
    publication_type: Optional[str] = None,
    publication_types: Optional[Any] = None,
    doi: Optional[str] = None,
) -> str:
    """Classify a publication into Oxford CEBM-inspired evidence tiers A-D/U.

    Mirrors the SQL CASE expression in mol_silver.publications exactly.

    Args:
        source:           Source identifier string (e.g. 'pubmed', 'openalex').
        publication_type: Single string publication type (OpenAlex / EuropePMC).
        publication_types: JSONB-like list of type strings (PubMed).
        doi:              DOI string for Cochrane override check.

    Returns:
        Single character tier: 'A', 'B', 'C', 'D', or 'U'. Never None.
    """
    # Normalise publication_types to a list of strings
    if isinstance(publication_types, str):
        try:
            pt_list: List[str] = json.loads(publication_types)
        except (ValueError, TypeError):
            pt_list = [publication_types]
    elif isinstance(publication_types, list):
        pt_list = publication_types
    else:
        pt_list = []

    def any_ilike(lst: List[Any], *patterns: str) -> bool:
        """Return True if any element in lst contains any pattern (case-insensitive)."""
        for item in lst:
            if not isinstance(item, str):
                continue
            lower = item.lower()
            for pat in patterns:
                if pat.lower() in lower:
                    return True
        return False

    # --- Cochrane override ---
    if source == 'cochrane_reviews':
        return 'A'
    if doi and doi.startswith('10.1002/14651858'):
        return 'A'

    # --- PubMed: classify by publication_types list ---
    if source == 'pubmed':
        if any_ilike(pt_list, 'systematic review', 'meta-analysis', 'cochrane'):
            return 'A'
        if any_ilike(pt_list, 'randomized controlled trial', 'controlled clinical trial'):
            return 'B'
        if any_ilike(pt_list, 'observational study', 'cohort', 'case-control', 'real-world'):
            return 'C'
        if any_ilike(pt_list, 'case report', 'case series', 'editorial',
                     'expert opinion', 'comment', 'letter'):
            return 'D'
        return 'U'

    # --- OpenAlex: exact match on LOWER(publication_type) ---
    if source == 'openalex':
        pt_lower = (publication_type or '').lower()
        if pt_lower in ('systematic-review', 'meta-analysis', 'cochrane-review'):
            return 'A'
        if pt_lower in ('randomized-controlled-trial', 'controlled-clinical-trial', 'clinical-trial'):
            return 'B'
        if pt_lower in ('observational-study', 'cohort-study', 'case-control',
                        'retrospective-study', 'prospective-study'):
            return 'C'
        if pt_lower in ('case-report', 'case-series', 'editorial',
                        'letter', 'comment', 'expert-opinion'):
            return 'D'
        return 'U'

    # --- EuropePMC: substring match on LOWER(publication_type) ---
    if source == 'europepmc':
        pt_lower = (publication_type or '').lower()
        if any(p in pt_lower for p in ('systematic review', 'meta-analysis', 'cochrane')):
            return 'A'
        if any(p in pt_lower for p in ('randomized controlled trial', 'controlled clinical trial')):
            return 'B'
        if any(p in pt_lower for p in ('observational', 'cohort', 'case-control', 'real-world')):
            return 'C'
        if any(p in pt_lower for p in ('case report', 'case series', 'editorial',
                                        'expert opinion', 'comment', 'letter')):
            return 'D'
        return 'U'

    # --- All other sources → unclassified ---
    return 'U'


# ---------------------------------------------------------------------------
# Test cases: (source, publication_type, publication_types, doi, expected_tier)
# ---------------------------------------------------------------------------

TIER_TEST_CASES = [
    # --- Cochrane override (always A) ---
    ('cochrane_reviews', 'systematic-review', [], None, 'A'),
    ('cochrane_reviews', None, [], None, 'A'),
    ('cochrane_reviews', 'journal-article', ['Journal Article'], None, 'A'),
    ('pubmed', None, [], '10.1002/14651858.CD001234', 'A'),
    ('openalex', 'journal-article', [], '10.1002/14651858.CD005678.pub3', 'A'),

    # --- PubMed Tier A ---
    ('pubmed', None, ['Systematic Review'], None, 'A'),
    ('pubmed', None, ['Meta-Analysis'], None, 'A'),
    ('pubmed', None, ['Journal Article', 'Meta-Analysis'], None, 'A'),
    ('pubmed', None, ['Cochrane Database of Systematic Reviews'], None, 'A'),
    ('pubmed', None, ['Systematic Review', 'Meta-Analysis'], None, 'A'),

    # --- PubMed Tier B ---
    ('pubmed', None, ['Randomized Controlled Trial'], None, 'B'),
    ('pubmed', None, ['Journal Article', 'Randomized Controlled Trial'], None, 'B'),
    ('pubmed', None, ['Controlled Clinical Trial'], None, 'B'),

    # --- PubMed Tier C ---
    ('pubmed', None, ['Observational Study'], None, 'C'),
    ('pubmed', None, ['Journal Article', 'Cohort Study'], None, 'C'),
    ('pubmed', None, ['Case-Control Study'], None, 'C'),
    ('pubmed', None, ['Real-World Evidence'], None, 'C'),

    # --- PubMed Tier D ---
    ('pubmed', None, ['Case Report'], None, 'D'),
    ('pubmed', None, ['Case Series'], None, 'D'),
    ('pubmed', None, ['Editorial'], None, 'D'),
    ('pubmed', None, ['Expert Opinion'], None, 'D'),
    ('pubmed', None, ['Comment'], None, 'D'),
    ('pubmed', None, ['Letter'], None, 'D'),

    # --- PubMed Tier U ---
    ('pubmed', None, ['Journal Article'], None, 'U'),
    ('pubmed', None, [], None, 'U'),
    ('pubmed', None, ['News'], None, 'U'),

    # --- OpenAlex Tier A ---
    ('openalex', 'systematic-review', [], None, 'A'),
    ('openalex', 'meta-analysis', [], None, 'A'),
    ('openalex', 'cochrane-review', [], None, 'A'),

    # --- OpenAlex Tier B ---
    ('openalex', 'randomized-controlled-trial', [], None, 'B'),
    ('openalex', 'controlled-clinical-trial', [], None, 'B'),
    ('openalex', 'clinical-trial', [], None, 'B'),

    # --- OpenAlex Tier C ---
    ('openalex', 'observational-study', [], None, 'C'),
    ('openalex', 'cohort-study', [], None, 'C'),
    ('openalex', 'case-control', [], None, 'C'),
    ('openalex', 'retrospective-study', [], None, 'C'),
    ('openalex', 'prospective-study', [], None, 'C'),

    # --- OpenAlex Tier D ---
    ('openalex', 'case-report', [], None, 'D'),
    ('openalex', 'case-series', [], None, 'D'),
    ('openalex', 'editorial', [], None, 'D'),
    ('openalex', 'letter', [], None, 'D'),
    ('openalex', 'comment', [], None, 'D'),
    ('openalex', 'expert-opinion', [], None, 'D'),

    # --- OpenAlex Tier U (journal-article is too broad → U) ---
    ('openalex', 'journal-article', [], None, 'U'),
    ('openalex', None, [], None, 'U'),
    ('openalex', 'preprint', [], None, 'U'),

    # --- EuropePMC Tier A ---
    ('europepmc', 'systematic review', [], None, 'A'),
    ('europepmc', 'meta-analysis', [], None, 'A'),

    # --- EuropePMC Tier B ---
    ('europepmc', 'randomized controlled trial', [], None, 'B'),

    # --- EuropePMC Tier C ---
    ('europepmc', 'observational study', [], None, 'C'),
    ('europepmc', 'cohort study', [], None, 'C'),

    # --- EuropePMC Tier D ---
    ('europepmc', 'editorial', [], None, 'D'),
    ('europepmc', 'letter', [], None, 'D'),

    # --- EuropePMC Tier U ---
    ('europepmc', 'journal article', [], None, 'U'),

    # --- Unknown source → always U ---
    ('journal_rss', 'journal-article', [], None, 'U'),
    ('journal_rss', 'meta-analysis', [], None, 'U'),
    ('unknown_source', 'systematic-review', ['Systematic Review'], None, 'U'),
]


@pytest.mark.parametrize(
    "source, publication_type, publication_types, doi, expected",
    TIER_TEST_CASES,
    ids=[
        f"{i:03d}_{src}_{exp}"
        for i, (src, _, __, ___, exp) in enumerate(TIER_TEST_CASES)
    ],
)
def test_evidence_tier_classification(
    source, publication_type, publication_types, doi, expected
) -> None:
    """Each parameterized case should return the expected evidence tier."""
    result = classify_evidence_tier(
        source=source,
        publication_type=publication_type,
        publication_types=publication_types,
        doi=doi,
    )
    assert result == expected, (
        f"Expected tier '{expected}' for source={source!r}, "
        f"publication_type={publication_type!r}, "
        f"publication_types={publication_types!r}, doi={doi!r}; "
        f"got '{result}'"
    )


def test_result_never_null() -> None:
    """classify_evidence_tier must never return None — always a 1-char string."""
    for source, pt, pts, doi, _ in TIER_TEST_CASES:
        result = classify_evidence_tier(source, pt, pts, doi)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) == 1
        assert result in ('A', 'B', 'C', 'D', 'U')


def test_cochrane_source_always_a() -> None:
    """Any record with source='cochrane_reviews' must always return 'A'."""
    test_inputs = [
        ('cochrane_reviews', None, [], None),
        ('cochrane_reviews', 'journal-article', [], None),
        ('cochrane_reviews', 'letter', ['Letter'], None),
        ('cochrane_reviews', 'preprint', ['Preprint'], '10.1234/other'),
    ]
    for source, pt, pts, doi in test_inputs:
        assert classify_evidence_tier(source, pt, pts, doi) == 'A', (
            f"cochrane_reviews must always be 'A', got other for pt={pt!r}"
        )


def test_pubmed_case_report_is_d() -> None:
    """PubMed 'Case Report' type → Tier D."""
    result = classify_evidence_tier('pubmed', None, ['Case Report'], None)
    assert result == 'D'


def test_unknown_pubmed_type_is_u() -> None:
    """PubMed 'Journal Article' alone (no typed subtype) → Tier U."""
    result = classify_evidence_tier('pubmed', None, ['Journal Article'], None)
    assert result == 'U'


def test_population_rate_typed_inputs() -> None:
    """At least 95% of typed (non-U) test inputs should correctly classify.

    Verifies that the classifier has high coverage for known typed inputs.
    """
    typed_cases = [
        (src, pt, pts, doi, exp)
        for src, pt, pts, doi, exp in TIER_TEST_CASES
        if exp != 'U'
    ]
    assert len(typed_cases) > 0, "Need at least some typed test cases"

    correct = sum(
        1 for src, pt, pts, doi, exp in typed_cases
        if classify_evidence_tier(src, pt, pts, doi) == exp
    )
    population_rate = correct / len(typed_cases)
    assert population_rate >= 0.95, (
        f"Population rate for typed inputs is {population_rate:.1%} "
        f"({correct}/{len(typed_cases)}) — expected >= 95%"
    )


def test_cochrane_doi_prefix_is_a() -> None:
    """DOI starting with '10.1002/14651858' → Tier A regardless of source."""
    assert classify_evidence_tier('pubmed', None, [], '10.1002/14651858.CD001234') == 'A'
    assert classify_evidence_tier(
        'openalex', 'journal-article', [], '10.1002/14651858.CD005678.pub3'
    ) == 'A'


def test_openalex_journal_article_is_u() -> None:
    """OpenAlex 'journal-article' is intentionally U — too broad to classify."""
    assert classify_evidence_tier('openalex', 'journal-article', [], None) == 'U'


def test_pubmed_json_string_publication_types() -> None:
    """publication_types passed as JSON string should be parsed correctly."""
    result = classify_evidence_tier(
        'pubmed', None, '["Randomized Controlled Trial", "Journal Article"]', None
    )
    assert result == 'B'


def test_total_test_case_count() -> None:
    """Sanity check: at least 50 parameterized test cases are defined."""
    assert len(TIER_TEST_CASES) >= 50, (
        f"Expected >= 50 test cases, got {len(TIER_TEST_CASES)}"
    )


def test_never_null() -> None:
    """evidence_tier must never be NULL — always returns a string (legacy compat)."""
    result = classify_evidence_tier('unknown', None, None, None)
    assert result is not None
    assert isinstance(result, str)
    assert len(result) == 1
