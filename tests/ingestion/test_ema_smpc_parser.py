"""Parametrized tests for EMA SmPC section header regex matching.

Feature: 006-claims-engine-data-gaps (Item 10, T054)

Tests the parse_smpc_text function against various SmPC section header
formats seen in EMA product documents.
"""

from __future__ import annotations

import pytest

from dk_data.ingestion.parsers.ema_smpc import (
    SECTION_MAPPINGS,
    _SECTION_HEADER_RE,
    parse_smpc_text,
)


# ---------------------------------------------------------------------------
# Section header regex tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "header_line, expected_section_num",
    [
        # Standard format: "4.1 Therapeutic indications"
        ("4.1 Therapeutic indications", "4.1"),
        # With trailing period: "4.1. Therapeutic indications"
        ("4.1. Therapeutic indications", "4.1"),
        # Uppercase: "4.1 THERAPEUTIC INDICATIONS"
        ("4.1 THERAPEUTIC INDICATIONS", "4.1"),
        # Extra whitespace
        ("  4.1   Therapeutic indications  ", "4.1"),
        # Double-digit section
        ("5.1 Pharmacodynamic properties", "5.1"),
        ("5.2 Pharmacokinetic properties", "5.2"),
        ("5.3 Preclinical safety data", "5.3"),
        # Section 4.3 contraindications
        ("4.3 Contraindications", "4.3"),
        # Section 4.8 adverse reactions
        ("4.8 Undesirable effects", "4.8"),
        # Section 4.9 overdose
        ("4.9 Overdose", "4.9"),
    ],
    ids=[
        "standard_4.1",
        "trailing_period_4.1",
        "uppercase_4.1",
        "extra_whitespace_4.1",
        "section_5.1",
        "section_5.2",
        "section_5.3",
        "section_4.3",
        "section_4.8",
        "section_4.9",
    ],
)
def test_section_header_regex_matches(header_line: str, expected_section_num: str):
    """Verify the regex correctly extracts section numbers from various header formats."""
    match = _SECTION_HEADER_RE.search(header_line)
    assert match is not None, f"Regex did not match: {header_line!r}"
    actual = match.group(1).rstrip(".")
    assert actual == expected_section_num


@pytest.mark.parametrize(
    "line",
    [
        # Plain text without section numbering
        "This is just regular paragraph text.",
        # Numbered list items (should NOT match as section headers)
        "1. First item in a list",
        # Table content
        "4.1%  Incidence rate in treatment group",
        # Empty string
        "",
    ],
    ids=["plain_text", "numbered_list", "percentage", "empty"],
)
def test_section_header_regex_no_false_positives(line: str):
    """Verify the regex does not match non-section-header text."""
    match = _SECTION_HEADER_RE.search(line)
    # Either no match, or matched section is not in our mappings
    if match:
        section_num = match.group(1).rstrip(".")
        assert section_num not in SECTION_MAPPINGS, (
            f"False positive: {line!r} matched section {section_num}"
        )


# ---------------------------------------------------------------------------
# Full parse_smpc_text tests
# ---------------------------------------------------------------------------

_SAMPLE_SMPC = """
1. NAME OF THE MEDICINAL PRODUCT
Dupixent 300 mg solution for injection in pre-filled syringe

2. QUALITATIVE AND QUANTITATIVE COMPOSITION
Each pre-filled syringe contains 300 mg of dupilumab.

4.1 Therapeutic indications
Dupixent is indicated for the treatment of moderate-to-severe atopic
dermatitis in adults and adolescents 12 years and older who are candidates
for systemic therapy.

4.2 Posology and method of administration
The recommended dose of Dupixent for adult patients is an initial dose of
600 mg (two 300 mg injections), followed by 300 mg given every other week.

4.3 Contraindications
Hypersensitivity to the active substance or to any of the excipients.

4.8 Undesirable effects
Summary of the safety profile: the most commonly reported adverse reactions
were injection site reactions.

5.1 Pharmacodynamic properties
Pharmacotherapeutic group: immunosuppressants, interleukin inhibitors.
ATC code: D11AH05.

5.2 Pharmacokinetic properties
Following a subcutaneous dose of 600 mg, mean peak concentration was reached
by approximately day 7.

6. PHARMACEUTICAL PARTICULARS
Storage conditions and shelf life details.
"""


def test_parse_smpc_text_extracts_mapped_sections():
    """Verify parse_smpc_text extracts all expected sections from sample text."""
    result = parse_smpc_text(_SAMPLE_SMPC)

    assert "indications_and_usage" in result
    assert "Dupixent" in result["indications_and_usage"]
    assert "atopic" in result["indications_and_usage"]

    assert "dosage_and_administration" in result
    assert "600 mg" in result["dosage_and_administration"]

    assert "contraindications" in result
    assert "Hypersensitivity" in result["contraindications"]

    assert "adverse_reactions" in result
    assert "injection site reactions" in result["adverse_reactions"]

    assert "pharmacodynamics" in result
    assert "D11AH05" in result["pharmacodynamics"]

    assert "pharmacokinetics" in result
    assert "subcutaneous" in result["pharmacokinetics"]


def test_parse_smpc_text_empty_input():
    """Verify empty or whitespace-only input returns empty dict."""
    assert parse_smpc_text("") == {}
    assert parse_smpc_text("   \n  ") == {}


def test_parse_smpc_text_no_sections():
    """Verify text with no section headers returns empty dict."""
    result = parse_smpc_text("Just a plain text document with no sections.")
    assert result == {}


def test_all_section_mappings_have_valid_column_names():
    """Verify all section mappings produce valid silver column names."""
    for section_num, (col_name, label) in SECTION_MAPPINGS.items():
        assert col_name.isidentifier(), (
            f"Section {section_num} column name {col_name!r} is not a valid identifier"
        )
        assert label, f"Section {section_num} has empty label"
