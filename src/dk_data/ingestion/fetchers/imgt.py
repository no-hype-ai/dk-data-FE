"""IMGT (ImMunoGeneTics) gene database fetcher — antibody/biologic sequences.

IMGT provides standardized gene sequences for immunoglobulins (antibodies)
and T-cell receptors, critical for biologic drug development.

Data source (official bulk download):
  IMGT/GENE-DB flat-file downloads at https://www.imgt.org/download/GENE-DB/
  These are the officially recommended programmatic access method.
  No API key or rate limiting — single bulk FASTA file per download.

  File: IMGTGENE-DB-ReferenceSequences.fasta-nt-WithoutGaps-F+ORF+inframeP
  Contains all functional (F), ORF, and in-frame pseudogene reference sequences
  for all species as ungapped nucleotide FASTA.

  FASTA header format: >GENENAME|SPECIES|FUNCTIONALITY|...
  e.g.: >IGHV1-2*02|Homo sapiens|F|...

Previous approach (GENElect URL per gene group) was fragile web scraping of
a parameterized HTML query interface — not a documented REST API.

IMGT GENE-DB covers:
  - Homo sapiens IG (IGHV, IGHD, IGHJ, IGKV, IGKJ, IGLV, IGLJ) — antibody genes
  - Homo sapiens TR (TRAV, TRBV, TRGV, TRDV) — T-cell receptor genes

Each gene-group response is one JSONB record in mol_raw.imgt (migration 096).

Note: IMGT server availability varies. Returns status='source_unavailable'
gracefully when unreachable, so the pipeline continues without this source.
"""

import hashlib
import logging
from collections import defaultdict
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Official IMGT/GENE-DB bulk flat-file download (no auth, no rate limit).
# Ungapped NT FASTA — functional + ORF + in-frame pseudogene reference sequences.
_BULK_FASTA_URL = (
    "https://www.imgt.org/download/GENE-DB/"
    "IMGTGENE-DB-ReferenceSequences.fasta-nt-WithoutGaps-F+ORF+inframeP"
)

# Human immunoglobulin and T-cell receptor gene group prefixes (for filtering)
_HUMAN_GENE_GROUPS = [
    "IGHV", "IGHD", "IGHJ",
    "IGKV", "IGKJ",
    "IGLV", "IGLJ",
    "TRAV", "TRAJ", "TRBV", "TRBD", "TRBJ",
    "TRGV", "TRGJ", "TRDV", "TRDD", "TRDJ",
]

_HUMAN_SPECIES_TAG = "Homo sapiens"


class IMGTFetcher(BaseFetcher):
    """Fetcher for IMGT GENE-DB human immunoglobulin and TCR sequences.

    Downloads the official IMGT bulk FASTA file and partitions records
    by gene group, keeping the same output schema as before.
    """

    SOURCE_NAME = "imgt"
    BASE_URL = "https://www.imgt.org"

    def get_latest_url(self) -> str:
        return _BULK_FASTA_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch IMGT gene sequences for all human IG and TR gene groups.

        Downloads the official bulk FASTA and partitions by gene group.
        Each gene group becomes one record with:
          gene_group   — e.g., "IGHV"
          species      — "Homo sapiens"
          fasta_data   — FASTA text for sequences in this group
          allele_count — number of alleles in this group

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            status='source_unavailable' when IMGT server is unreachable.
        """
        try:
            records = self._fetch_and_partition()

            if not records:
                msg = "IMGT: no gene group data retrieved (server may be unavailable)"
                logger.warning(msg)
                result = {"status": "source_unavailable", "records": [], "record_count": 0, "hash": None, "error": msg}
                self.log_fetch_result(result)
                return result

            content_hash = hashlib.md5(
                "".join(r.get("gene_group", "") for r in records).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except RuntimeError as rt_exc:
            logger.warning("IMGT: %s", rt_exc)
            result = {
                "status": "source_unavailable",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(rt_exc),
                "attempted_url": _BULK_FASTA_URL,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("IMGT fetch failed: %s", exc)
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(exc)}
            self.log_fetch_result(result)
            return result

    def _fetch_and_partition(self) -> List[Dict[str, Any]]:
        """Download the bulk FASTA and split by gene group for Homo sapiens."""
        logger.info("IMGT: downloading bulk FASTA from %s", _BULK_FASTA_URL)
        try:
            resp = self.session.get(_BULK_FASTA_URL, timeout=300)
            if resp.status_code != 200:
                logger.warning(
                    "IMGT: bulk FASTA endpoint returned HTTP %d — source unavailable (url=%s)",
                    resp.status_code,
                    _BULK_FASTA_URL,
                )
                raise RuntimeError(
                    f"IMGT endpoint returned HTTP {resp.status_code} (url={_BULK_FASTA_URL})"
                )
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning("IMGT: bulk FASTA download failed: %s", exc)
            return []

        fasta_text = resp.text
        logger.info("IMGT: downloaded %.1f MB", len(fasta_text) / 1_048_576)

        # Split into per-sequence blocks (each starting with ">")
        # FASTA header: >GENENAME|SPECIES|FUNCTIONALITY|...
        group_sequences: Dict[str, List[str]] = defaultdict(list)
        current_header = ""
        current_seq_lines: List[str] = []

        for line in fasta_text.splitlines():
            if line.startswith(">"):
                # Flush previous sequence
                if current_header:
                    group = self._extract_group(current_header)
                    if group:
                        block = current_header + "\n" + "\n".join(current_seq_lines)
                        group_sequences[group].append(block)
                current_header = line
                current_seq_lines = []
            else:
                current_seq_lines.append(line)

        # Flush final sequence
        if current_header:
            group = self._extract_group(current_header)
            if group:
                block = current_header + "\n" + "\n".join(current_seq_lines)
                group_sequences[group].append(block)

        records: List[Dict[str, Any]] = []
        for group in _HUMAN_GENE_GROUPS:
            blocks = group_sequences.get(group, [])
            if not blocks:
                continue
            fasta_for_group = "\n".join(blocks)
            records.append({
                "gene_group": group,
                "species": _HUMAN_SPECIES_TAG,
                "fasta_data": fasta_for_group,
                "allele_count": len(blocks),
                "source_url": _BULK_FASTA_URL,
            })
            logger.info("IMGT: %s — %d alleles", group, len(blocks))

        return records

    @staticmethod
    def _extract_group(header: str) -> str:
        """Extract gene group from FASTA header if it's a human sequence.

        Header format: >GENENAME|SPECIES|...
        e.g.: >IGHV1-2*02|Homo sapiens|F|...

        Returns group prefix (e.g. "IGHV") or "" if not a human IG/TR gene.
        """
        parts = header.lstrip(">").split("|")
        if len(parts) < 2:
            return ""
        gene_name = parts[0].strip()
        species = parts[1].strip()
        if species != _HUMAN_SPECIES_TAG:
            return ""
        for group in _HUMAN_GENE_GROUPS:
            if gene_name.startswith(group):
                return group
        return ""
