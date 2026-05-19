"""Tests for validate_magic_bytes and compute_sha256 (T029).

Each test writes a real file so the implementations can open it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


from dk_data.ingestion.prestaged import compute_sha256, validate_magic_bytes
from dk_data.ingestion.prestaged_types import PGDMP_MAGIC, PrestagedArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _artifact(path: Path) -> PrestagedArtifact:
    return PrestagedArtifact(
        path=path,
        target_schema="mol_raw",
        target_table="test_table",
        tier="raw",
        chunk_index="",
        size_bytes=path.stat().st_size,
    )


# ---------------------------------------------------------------------------
# T029 – validate_magic_bytes
# ---------------------------------------------------------------------------

class TestValidateMagicBytes:
    def test_magic_ok_on_pgdmp(self, tmp_path: Path) -> None:
        """File starting with PGDMP magic bytes → magic_ok=True."""
        f = tmp_path / "valid.dump"
        f.write_bytes(PGDMP_MAGIC + b"\x00" * 100)

        result = validate_magic_bytes(_artifact(f))

        assert result.magic_ok is True

    def test_magic_fail_on_other(self, tmp_path: Path) -> None:
        """File starting with unrecognised bytes → magic_ok=False."""
        f = tmp_path / "garbage.dump"
        f.write_bytes(b"GARB\x00" * 20)

        result = validate_magic_bytes(_artifact(f))

        assert result.magic_ok is False

    def test_magic_fail_on_empty_file(self, tmp_path: Path) -> None:
        """Zero-byte file → magic_ok=False (can't match 5 magic bytes)."""
        f = tmp_path / "empty.dump"
        f.write_bytes(b"")

        result = validate_magic_bytes(_artifact(f))

        assert result.magic_ok is False

    def test_original_artifact_unchanged(self, tmp_path: Path) -> None:
        """validate_magic_bytes returns a *new* artifact; original is immutable."""
        f = tmp_path / "valid.dump"
        f.write_bytes(PGDMP_MAGIC + b"\xff" * 10)

        original = _artifact(f)
        result = validate_magic_bytes(original)

        assert original.magic_ok is False  # default
        assert result.magic_ok is True
        assert result is not original


# ---------------------------------------------------------------------------
# compute_sha256
# ---------------------------------------------------------------------------

class TestComputeSha256:
    def test_sha256_matches_hashlib(self, tmp_path: Path) -> None:
        """compute_sha256 produces the same digest as hashlib.sha256 directly."""
        content = b"hello prestaged world\n" * 1000
        f = tmp_path / "chunk.dump"
        f.write_bytes(content)

        result = compute_sha256(_artifact(f))

        expected = hashlib.sha256(content).hexdigest()
        assert result.sha256 == expected

    def test_sha256_cached_by_inode(self, tmp_path: Path) -> None:
        """Calling compute_sha256 twice on the same inode returns the cached value."""
        import dk_data.ingestion.prestaged as mod

        f = tmp_path / "cached.dump"
        f.write_bytes(b"inode cache test")

        # Clear cache to isolate the test
        mod._SHA_CACHE.clear()

        a = _artifact(f)
        r1 = compute_sha256(a)
        assert len(mod._SHA_CACHE) == 1

        # Second call must not add a second entry
        r2 = compute_sha256(a)
        assert len(mod._SHA_CACHE) == 1
        assert r1.sha256 == r2.sha256
