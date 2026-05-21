"""Async repository for `mol_silver.moa_enrichment_cache`.

Tiny CRUD wrapper. Used by `lookup_moa()` as cache tier between the
in-memory static dict and the external-API resolver.

Sentinel for negative cache (looked up, found nothing) keeps us from
hammering OpenFDA/ChEMBL for the same unknown MOA on every request.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from .moa_enrichment import MoaEnrichment


# Sentinel returned from `fetch_cached` when the row exists but is negative.
# Distinguishes "negative cache hit" from "cache miss" (None).
class _NegativeHit:
    """Marker: looked up before, resolver returned nothing."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "<NegativeHit>"


NEGATIVE_HIT = _NegativeHit()


async def fetch_cached(
    pool: Any,
    moa_key: str,
) -> MoaEnrichment | _NegativeHit | None:
    """Look up a cached MOA enrichment.

    Returns:
        - ``MoaEnrichment``  → cache hit, real data
        - ``NEGATIVE_HIT``   → cache hit, but resolver previously found nothing
        - ``None``           → cache miss; caller should resolve from APIs
    """
    sql = """
        SELECT fda_pharm_class_moa, fda_pharm_class_epc, targets, atc_prefix, is_negative
        FROM mol_silver.moa_enrichment_cache
        WHERE moa_key = $1
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, moa_key)
    except Exception as e:
        logger.warning(f"MOA cache read failed for {moa_key!r}: {e}")
        return None

    if row is None:
        return None
    if row["is_negative"]:
        return NEGATIVE_HIT
    return MoaEnrichment(
        fda_pharm_class_moa=row["fda_pharm_class_moa"],
        fda_pharm_class_epc=row["fda_pharm_class_epc"],
        targets=tuple(row["targets"] or ()),
        atc_prefix=row["atc_prefix"],
    )


async def persist(
    pool: Any,
    moa_key: str,
    enrichment: MoaEnrichment | None,
    source: str,
    confidence: int = 50,
) -> None:
    """Persist a resolver result (or negative sentinel) to the cache.

    ``enrichment=None`` → write a negative row so we don't re-query.
    Upsert on conflict so concurrent resolvers don't fight.
    """
    is_negative = enrichment is None
    sql = """
        INSERT INTO mol_silver.moa_enrichment_cache (
            moa_key, fda_pharm_class_moa, fda_pharm_class_epc, targets,
            atc_prefix, source, confidence, is_negative, hit_count, cached_at, last_used_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1, now(), now())
        ON CONFLICT (moa_key) DO UPDATE SET
            fda_pharm_class_moa = EXCLUDED.fda_pharm_class_moa,
            fda_pharm_class_epc = EXCLUDED.fda_pharm_class_epc,
            targets             = EXCLUDED.targets,
            atc_prefix          = EXCLUDED.atc_prefix,
            source              = EXCLUDED.source,
            confidence          = EXCLUDED.confidence,
            is_negative         = EXCLUDED.is_negative,
            last_used_at        = now()
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                sql,
                moa_key,
                None if is_negative else enrichment.fda_pharm_class_moa,
                None if is_negative else enrichment.fda_pharm_class_epc,
                list(enrichment.targets) if not is_negative else [],
                None if is_negative else enrichment.atc_prefix,
                "negative" if is_negative else source,
                confidence,
                is_negative,
            )
    except Exception as e:
        logger.warning(f"MOA cache write failed for {moa_key!r}: {e}")


async def bump_hit_count(pool: Any, moa_key: str) -> None:
    """Best-effort hit-count update. Fire-and-forget; never raises."""
    sql = """
        UPDATE mol_silver.moa_enrichment_cache
           SET hit_count = hit_count + 1,
               last_used_at = now()
         WHERE moa_key = $1
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(sql, moa_key)
    except Exception as e:
        logger.debug(f"MOA cache hit_count bump failed for {moa_key!r}: {e}")
