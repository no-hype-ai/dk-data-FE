"""Silver antipattern grep test.

Feature: 001-silver-medallion-rebuild
Task: T004 (CI gate) / T121 (post-rewrite verification)
FR-015–FR-020 / SC-012: Zero occurrences of the 5 banned silver antipatterns.

These tests mirror the CI grep jobs in ci.yaml but run as pytest so that:
  - Developers get local feedback before push
  - The test suite reports specific line numbers, not just file names
  - pytest --tb=short gives a readable failure report
"""

import re
import pathlib
import pytest


MODELS_DIR = pathlib.Path(__file__).parent.parent / "src" / "dk_data" / "sqlmesh" / "models"


def _sql_files():
    """Return all .sql files under the silver models directory."""
    if not MODELS_DIR.exists():
        return []
    return list(MODELS_DIR.rglob("*.sql"))


def _grep(pattern: str, flags: int = 0) -> list[tuple[pathlib.Path, int, str]]:
    """Search all silver model SQL files for `pattern`.

    Returns a list of (file, line_number, line_text) for each match.
    """
    compiled = re.compile(pattern, flags)
    hits = []
    for sql_file in _sql_files():
        # Only check silver models — bronze and gold use different rules
        if "silver" not in str(sql_file):
            continue
        text = sql_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                hits.append((sql_file, lineno, line.strip()))
    return hits


class TestSilverAntipatterns:
    """FR-015–FR-020: The 5 banned silver antipatterns must not appear in any silver model."""

    def test_s1_no_or_join_between_hub_identifiers(self):
        """S1: OR-join between two hub-eligible identifiers (FR-015).

        e.g. a.inchi_key = b.inchi_key OR LOWER(a.name) = LOWER(b.name)
        Forces hash join to degrade to a nested loop — O(N²) on large tables.
        Fix: join on ONE identifier only, resolve ambiguity via the crosswalk.
        """
        hub_ids = (
            r"inchi_key|chembl_id|pubchem_cid|unii|ndc|rxcui|"
            r"npi|ccn|orcid|patent_number|trademark_id"
        )
        pattern = rf"\.({hub_ids})\s*=.*\bOR\b.*\.(name|canonical_name|brand_name|generic_name)"
        hits = _grep(pattern, re.IGNORECASE)
        _assert_no_hits("S1", hits, "OR-join between hub-eligible identifiers (FR-015)")

    def test_s2_no_leading_wildcard_like(self):
        """S2: Leading-wildcard LIKE against indexed columns (FR-016).

        e.g. LIKE '%' || name || '%'
        Forces a full sequential scan — index is skipped.
        Fix: use pg_trgm GIN index + similarity() or replace with a trigram lookup.
        """
        hits = _grep(r"LIKE\s+'%'\s*\|\|", re.IGNORECASE)
        _assert_no_hits("S2", hits, "leading-wildcard LIKE (FR-016)")

    def test_s3_no_correlated_scalar_subquery_in_select(self):
        """S3: Correlated scalar subqueries in SELECT lists (FR-017).

        e.g. SELECT (SELECT id FROM hub WHERE hub.key = outer.key)
        Runs once per output row — O(N) DB round trips.
        Fix: rewrite as a LEFT JOIN to the hub crosswalk table.
        """
        hits = _grep(r"SELECT\s+\(SELECT\s+\S.*?FROM\s+\S", re.IGNORECASE | re.DOTALL)
        _assert_no_hits("S3", hits, "correlated scalar subquery in SELECT list (FR-017)")

    def test_s4_no_distinct_on_over_union_all(self):
        """S4: Global DISTINCT ON over multi-way UNION ALL (FR-018).

        e.g. DISTINCT ON (...) ... UNION ALL ...
        Sorts the full union result set — extremely expensive on large tables.
        Fix: deduplicate each branch individually before the UNION ALL.
        """
        hits = _grep(r"DISTINCT\s+ON.*UNION\s+ALL|UNION\s+ALL.*DISTINCT\s+ON", re.IGNORECASE)
        _assert_no_hits("S4", hits, "DISTINCT ON over UNION ALL (FR-018)")

    def test_s5_no_similarity_mixed_with_equals_in_or(self):
        """S5: similarity() combined with = in the same OR clause (FR-019).

        e.g. similarity(a, b) >= 0.85 OR col = 'value'
        Forces a sequential scan even if an index exists on col.
        Fix: separate the similarity fallback into a UNION branch after the equi-join.
        """
        hits = _grep(
            r"similarity\s*\(.*\)\s*(>=|>|<=|<)\s*[0-9.]+\s+(OR|AND).*=",
            re.IGNORECASE,
        )
        _assert_no_hits("S5", hits, "similarity() mixed with = in OR clause (FR-019)")


def _assert_no_hits(
    tag: str,
    hits: list[tuple[pathlib.Path, int, str]],
    description: str,
) -> None:
    if not hits:
        return
    lines = [f"  {f.relative_to(MODELS_DIR)}:{n}: {txt}" for f, n, txt in hits[:20]]
    report = "\n".join(lines)
    pytest.fail(
        f"{tag} antipattern ({description}) found in {len(hits)} location(s):\n"
        f"{report}\n"
        f"Fix all occurrences before merging."
    )
