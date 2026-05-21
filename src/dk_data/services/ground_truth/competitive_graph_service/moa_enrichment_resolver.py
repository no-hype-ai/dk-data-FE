"""External-API resolver for unknown MOAs.

When `lookup_moa()` misses both the static dict and the DB cache, this
module queries OpenFDA (and optionally ChEMBL) to extract canonical
pharm_class strings. Targets and ATC are best-effort — usually empty
when resolved by API, since OpenFDA labels don't carry gene-symbol
or ATC-prefix data in a structured way.

A negative result is still useful: caching it prevents repeated
external calls for the same unknown MOA. See `moa_enrichment_repo.persist`.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from loguru import logger

from .moa_enrichment import MoaEnrichment


def _most_common(values: list[str]) -> str | None:
    """Return the most frequent non-empty string in ``values``, or None."""
    counts = Counter(v for v in values if v)
    if not counts:
        return None
    return counts.most_common(1)[0][0]


async def _query_openfda_pharm_class(
    openfda_client: Any,
    moa_key: str,
    field: str,
) -> list[Any]:
    """Best-effort OpenFDA label search; returns labels or empty list."""
    try:
        return await openfda_client.search_drug_labels(
            query=moa_key, search_field=field, limit=5,
        )
    except Exception as e:
        logger.debug(f"OpenFDA {field} lookup failed for {moa_key!r}: {e}")
        return []


async def resolve_from_openfda(
    openfda_client: Any,
    moa_key: str,
) -> MoaEnrichment | None:
    """Resolve a free-text MOA against OpenFDA drug labels.

    Returns ``MoaEnrichment`` if labels matched; ``None`` if no hit.
    """
    moa_labels, epc_labels = await asyncio.gather(
        _query_openfda_pharm_class(openfda_client, moa_key, "openfda.pharm_class_moa"),
        _query_openfda_pharm_class(openfda_client, moa_key, "openfda.pharm_class_epc"),
        return_exceptions=False,
    )

    pharm_class_moa = _most_common(
        [lbl.pharm_class_moa[0] for lbl in moa_labels if lbl.pharm_class_moa]
    )
    pharm_class_epc = _most_common(
        [lbl.pharm_class_epc[0] for lbl in (moa_labels + epc_labels) if lbl.pharm_class_epc]
    )

    if not pharm_class_moa and not pharm_class_epc:
        return None

    # Strip trailing "[EPC]" / "[MoA]" annotations — OpenFDA's search layer
    # appends these when querying; the canonical EPC value usually omits them.
    def _strip(s: str | None) -> str | None:
        if not s:
            return None
        return s.replace(" [EPC]", "").replace(" [MoA]", "").strip()

    return MoaEnrichment(
        fda_pharm_class_moa=_strip(pharm_class_moa),
        fda_pharm_class_epc=_strip(pharm_class_epc),
        targets=(),
        atc_prefix=None,
    )
