"""CT.gov intervention-name normalizer.

Takes the raw `intervention.name` string from ClinicalTrials.gov and emits
zero or more candidate INNs. Drops dose suffixes, parentheticals, multi-drug
arm labels, placebo/control strings, and imaging tracer prefixes.
"""

from __future__ import annotations

import re


_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")
_DOSE_RE = re.compile(
    r"\s+\d+(?:\.\d+)?\s*(?:MG|MCG|UG|G|UNITS?|IU|ML|MG/ML|MG/KG|%)\b.*",
    re.IGNORECASE,
)
_SPLIT_RE = re.compile(r"\s*,\s*|\s+(?:or|and|plus|\+|/|vs\.?)\s+", re.IGNORECASE)

# PET / SPECT imaging tracers — diagnostic, not therapeutic.
_TRACER_PREFIXES = ("68ga-", "99mtc-", "18f-", "11c-", "64cu-", "89zr-", "177lu-")

# Trial-arm labels that aren't drugs at all.
_BLOCK_TOKENS = {
    "placebo",
    "vehicle",
    "saline",
    "matching placebo",
    "sham",
    "best supportive care",
    "standard of care",
    "soc",
    "no intervention",
    "control",
}


def normalize_intervention_name(raw: str) -> list[str]:
    """Split a CT.gov intervention name into one or more candidate INNs.

    Handles dose suffixes (`Baricitinib 2 MG`), parenthetical descriptors
    (`(single-dose group)`), multi-drug arms (`A, B or C`, `A + B`),
    placebo/control strings, and imaging tracer prefixes.
    """
    if not raw:
        return []
    s = _PAREN_RE.sub(" ", raw)
    parts = _SPLIT_RE.split(s)
    out: list[str] = []
    for p in parts:
        p = _DOSE_RE.sub("", p).strip(" -")
        if not p:
            continue
        low = p.lower()
        if low in _BLOCK_TOKENS:
            continue
        if any(tok in low for tok in ("placebo", "vehicle", "saline")):
            continue
        if low.startswith(_TRACER_PREFIXES):
            continue
        out.append(p)
    return out
