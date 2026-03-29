"""IMGT (ImMunoGeneTics) gene database fetcher — antibody/biologic sequences.

IMGT provides standardized gene sequences for immunoglobulins (antibodies)
and T-cell receptors, critical for biologic drug development.

Public REST API: https://www.imgt.org/genedb/
  GET /GENElect?query=7.1+Homo+sapiens&species=Homo+sapiens&group=IGHV
  Returns FASTA sequences for a specific gene group.

IMGT GENE-DB covers:
  - Homo sapiens IG (IGHV, IGHD, IGHJ, IGKV, IGKJ, IGLV, IGLJ) — antibody genes
  - Homo sapiens TR (TRAV, TRBV, TRGV, TRDV) — T-cell receptor genes

Bulk strategy: enumerate known gene groups and fetch each group's sequences.
Each gene-group response is one JSONB record in mol_raw.imgt (migration 096).

Note: IMGT server availability varies. Returns status='source_unavailable'
gracefully when unreachable, so the pipeline continues without this source.
"""

import hashlib
import logging
from typing import Any, Dict, List

import requests
from .base import BaseFetcher

logger = logging.getLogger(__name__)

_GENEDB_URL = "https://www.imgt.org/genedb/GENElect"

# Human immunoglobulin and T-cell receptor gene groups
_HUMAN_GENE_GROUPS = [
    # Immunoglobulin heavy chain
    "IGHV", "IGHD", "IGHJ",
    # Immunoglobulin kappa light chain
    "IGKV", "IGKJ",
    # Immunoglobulin lambda light chain
    "IGLV", "IGLJ",
    # T-cell receptor alpha/beta
    "TRAV", "TRAJ", "TRBV", "TRBD", "TRBJ",
    # T-cell receptor gamma/delta
    "TRGV", "TRGJ", "TRDV", "TRDD", "TRDJ",
]


class IMGTFetcher(BaseFetcher):
    """Fetcher for IMGT GENE-DB human immunoglobulin and TCR sequences."""

    SOURCE_NAME = "imgt"
    BASE_URL = "https://www.imgt.org"

    def get_latest_url(self) -> str:
        return f"{_GENEDB_URL}?query=7.1+Homo+sapiens&species=Homo+sapiens&group=IGHV"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch IMGT gene sequences for all human IG and TR gene groups.

        Each gene group response is stored as one record with:
          gene_group  — e.g., "IGHV"
          species     — "Homo sapiens"
          fasta_data  — raw FASTA sequence text
          record_count — number of alleles in this group

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            status='source_unavailable' when IMGT server is unreachable.
        """
        try:
            records = self._fetch_all_groups()

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

        except Exception as exc:
            logger.exception("IMGT fetch failed: %s", exc)
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(exc)}
            self.log_fetch_result(result)
            return result

    def _fetch_all_groups(self) -> List[Dict[str, Any]]:
        """Fetch FASTA sequences for each gene group."""
        records: List[Dict[str, Any]] = []

        for group in _HUMAN_GENE_GROUPS:
            try:
                params = {
                    "query": "7.1 Homo sapiens",
                    "species": "Homo sapiens",
                    "group": group,
                }
                logger.info("IMGT: fetching gene group %s", group)
                resp = self.session.get(_GENEDB_URL, params=params, timeout=60)

                if resp.status_code == 404:
                    logger.debug("IMGT: 404 for group %s, skipping", group)
                    continue
                resp.raise_for_status()

                fasta_text = resp.text
                # Count sequences (each starts with ">")
                allele_count = fasta_text.count("\n>") + (1 if fasta_text.startswith(">") else 0)

                record: Dict[str, Any] = {
                    "gene_group": group,
                    "species": "Homo sapiens",
                    "fasta_data": fasta_text,
                    "allele_count": allele_count,
                    "source_url": resp.url,
                }
                records.append(record)
                logger.info("IMGT: %s — %d alleles", group, allele_count)

            except Exception as exc:
                logger.warning("IMGT: failed to fetch group %s: %s", group, exc)
                continue

        return records
