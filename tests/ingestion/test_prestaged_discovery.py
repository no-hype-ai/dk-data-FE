"""Tests for walk_prestaged_root and group_by_table (T028, T030).

Uses zero-byte .dump placeholders — magic-byte validation is tested separately
in test_prestaged_validate.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dk_data.ingestion.prestaged import group_by_table, walk_prestaged_root
from dk_data.ingestion.prestaged_types import PrestagedArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dump(path: Path) -> Path:
    """Create a zero-byte placeholder .dump file and its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _build_fixture_tree(root: Path) -> list[Path]:
    """Mirror the fixture layout from tests/fixtures/prestaged/README.md.

    Returns the list of .dump files created (4 total):
      - 2 × mol_raw / chembl_sample  (staging, raw layout)
      - 1 × mol_bronze / pubchem      (staging, hashed-dir layout)
      - 1 × mol_bronze / clinicaltrials (loose layout)
    """
    staging = root / "_staging" / "archive-001" / "dk-data-files"
    loose = root / "_loose_dumps"

    dumps = [
        _make_dump(staging / "mol_raw" / "chembl_sample" / "1_chembl_sample.dump"),
        _make_dump(staging / "mol_raw" / "chembl_sample" / "retry_chembl_sample.dump"),
        _make_dump(staging / "mol_bronze" / "mol_bronze__pubchem__abc123" / "pubchem.dump"),
        _make_dump(loose / "mol_bronze" / "mol_bronze__clinicaltrials__def456-008.dump"),
    ]
    return dumps


# ---------------------------------------------------------------------------
# T028 – walk_prestaged_root
# ---------------------------------------------------------------------------

class TestWalkPrestagedRoot:
    def test_walk_finds_both_layouts(self, tmp_path: Path) -> None:
        """All four .dump files across staging and loose layouts are discovered."""
        expected_dumps = _build_fixture_tree(tmp_path)

        artifacts = walk_prestaged_root(tmp_path)

        assert len(artifacts) == len(expected_dumps)

        found_paths = {a.path for a in artifacts}
        assert found_paths == set(expected_dumps)

        # Spot-check schema / table / tier for each discovered artifact
        by_path = {a.path: a for a in artifacts}

        raw_chunk = by_path[
            tmp_path / "_staging/archive-001/dk-data-files/mol_raw/chembl_sample/1_chembl_sample.dump"
        ]
        assert raw_chunk.target_schema == "mol_raw"
        assert raw_chunk.target_table == "chembl_sample"
        assert raw_chunk.tier == "raw"
        assert raw_chunk.chunk_index == "1_"

        retry_chunk = by_path[
            tmp_path / "_staging/archive-001/dk-data-files/mol_raw/chembl_sample/retry_chembl_sample.dump"
        ]
        assert retry_chunk.chunk_index == "retry_"

        bronze_staging = by_path[
            tmp_path / "_staging/archive-001/dk-data-files/mol_bronze/mol_bronze__pubchem__abc123/pubchem.dump"
        ]
        assert bronze_staging.target_schema == "mol_bronze"
        assert bronze_staging.target_table == "pubchem"
        assert bronze_staging.tier == "bronze"
        assert bronze_staging.chunk_index == ""

        loose = by_path[
            tmp_path / "_loose_dumps/mol_bronze/mol_bronze__clinicaltrials__def456-008.dump"
        ]
        assert loose.target_schema == "mol_bronze"
        assert loose.target_table == "clinicaltrials"
        assert loose.tier == "bronze"
        assert loose.chunk_index == ""

    def test_walk_ignores_non_dump_files(self, tmp_path: Path) -> None:
        """.txt and other non-.dump files are not returned."""
        _build_fixture_tree(tmp_path)

        # Add a stray text file inside a table_dir
        txt_file = (
            tmp_path
            / "_staging/archive-001/dk-data-files/mol_raw/chembl_sample/should_be_ignored.txt"
        )
        txt_file.write_text("not a dump")

        # Also add one at the schema-dir level (between table dirs)
        schema_level_txt = (
            tmp_path / "_staging/archive-001/dk-data-files/mol_raw/not_a_dump.txt"
        )
        schema_level_txt.write_text("also not a dump")

        artifacts = walk_prestaged_root(tmp_path)

        artifact_paths = {a.path for a in artifacts}
        assert txt_file not in artifact_paths
        assert schema_level_txt not in artifact_paths
        # All .dump files are still found
        assert len(artifacts) == 4

    def test_walk_fails_fast_on_missing_root(self, tmp_path: Path) -> None:
        """FileNotFoundError is raised immediately when root does not exist."""
        missing = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError):
            walk_prestaged_root(missing)


# ---------------------------------------------------------------------------
# T030 – group_by_table chunk ordering
# ---------------------------------------------------------------------------

def _artifact_with_chunk(chunk_index: str) -> PrestagedArtifact:
    """Create a minimal PrestagedArtifact with a given chunk_index for sorting tests."""
    return PrestagedArtifact(
        path=Path(f"/fake/{chunk_index or 'none'}.dump"),
        target_schema="mol_raw",
        target_table="test_table",
        tier="raw",
        chunk_index=chunk_index,
        size_bytes=0,
    )


class TestGroupByTable:
    def test_group_by_table_orders_chunks(self) -> None:
        """Chunks are returned in lexical chunk_index order: '' < '1' < '3' < 'retry'."""
        artifacts = [
            _artifact_with_chunk("3"),
            _artifact_with_chunk("retry"),
            _artifact_with_chunk("1"),
            _artifact_with_chunk(""),
        ]

        result = group_by_table(artifacts)

        assert len(result) == 1
        key = ("mol_raw", "test_table")
        assert key in result

        ordered_chunks = [a.chunk_index for a in result[key]]
        assert ordered_chunks == ["", "1", "3", "retry"]

    def test_group_by_table_separates_tables(self) -> None:
        """Artifacts for different (schema, table) pairs are in separate groups."""
        a1 = PrestagedArtifact(
            path=Path("/fake/a.dump"),
            target_schema="mol_raw",
            target_table="table_a",
            tier="raw",
            chunk_index="",
            size_bytes=0,
        )
        a2 = PrestagedArtifact(
            path=Path("/fake/b.dump"),
            target_schema="mol_bronze",
            target_table="table_b",
            tier="bronze",
            chunk_index="",
            size_bytes=0,
        )

        result = group_by_table([a1, a2])

        assert ("mol_raw", "table_a") in result
        assert ("mol_bronze", "table_b") in result
        assert len(result[("mol_raw", "table_a")]) == 1
        assert len(result[("mol_bronze", "table_b")]) == 1
