-- Migration 249: dev_silver.resolve_device — entity-resolution function for medical devices.
-- Feature: FDA medical devices ingestion (2026-04-21)
-- Pattern: matches existing mol/hcs/ind/hcp/ip resolve_* functions (migrations 178-188).
--
-- Priority tree (most-specific → least-specific):
--   1. UDI-DI             (Unique Device Identifier — globally unique per device model
--                          per FDA/GMDN; canonical when UDI source is ingested)
--   2. K-number           (510(k) clearance number — e.g. 'K180001')
--   3. PMA number         (PMA application number — e.g. 'P030004')
--   4. FEI number         (FDA Establishment Identifier — facility-level; useful for
--                          matching devices to manufacturer when other IDs absent)
--   5. Name fuzzy         (pg_trgm similarity ≥ 0.85 on normalized_name)
--
-- UDI-DI, k_number, pma_number, fei_number are stored in dev_silver.device_identifiers
-- with source values 'udi_di', 'k_number', 'pma_number', 'fei_number' respectively.
-- Name fuzzy reads from dev_silver.device_names.normalized_name.
--
-- STABLE PARALLEL SAFE: no writes; reads deterministic within a transaction.
-- SC-004 target: p99 ≤10ms on production-sized data (requires trigram GIN index
-- on dev_silver.device_names.normalized_name — registered in post_sqlmesh/000_hub_indexes.sql).

BEGIN;

CREATE OR REPLACE FUNCTION dev_silver.resolve_device(
    p_udi_di      text DEFAULT NULL,
    p_k_number    text DEFAULT NULL,
    p_pma_number  text DEFAULT NULL,
    p_fei_number  text DEFAULT NULL,
    p_name        text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. UDI-DI (most specific — globally unique device-model identifier per FDA UDI rule)
    IF p_udi_di IS NOT NULL THEN
        SELECT device_id INTO v_id
        FROM dev_silver.device_identifiers
        WHERE source = 'udi_di' AND identifier = p_udi_di;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. K-number (510(k) premarket notification)
    IF p_k_number IS NOT NULL THEN
        SELECT device_id INTO v_id
        FROM dev_silver.device_identifiers
        WHERE source = 'k_number' AND identifier = p_k_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. PMA number (premarket approval — base or supplement)
    IF p_pma_number IS NOT NULL THEN
        SELECT device_id INTO v_id
        FROM dev_silver.device_identifiers
        WHERE source = 'pma_number' AND identifier = p_pma_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 4. FEI number (FDA Establishment Identifier — manufacturer linkage)
    IF p_fei_number IS NOT NULL THEN
        SELECT device_id INTO v_id
        FROM dev_silver.device_identifiers
        WHERE source = 'fei_number' AND identifier = p_fei_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 5. Fuzzy name fallback via pg_trgm (threshold ≥ 0.85; min length 4)
    IF p_name IS NOT NULL THEN
        SELECT device_id INTO v_id
        FROM dev_silver.device_names
        WHERE similarity(LOWER(normalized_name), LOWER(TRIM(p_name))) >= 0.85
          AND LENGTH(normalized_name) >= 4 AND LENGTH(TRIM(p_name)) >= 4
        ORDER BY similarity(LOWER(normalized_name), LOWER(TRIM(p_name))) DESC, device_id ASC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION dev_silver.resolve_device IS
    'Resolve a medical-device hub ID from any combination of external identifiers. '
    'Priority: UDI-DI → K-number → PMA number → FEI number → name fuzzy (≥0.85). '
    'Returns NULL on no match. Part of the 12-hub silver architecture.';

-- Grants: analyst role can execute (read-only by nature — STABLE function)
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
    GRANT EXECUTE ON FUNCTION dev_silver.resolve_device(text, text, text, text, text) TO analyst;
  END IF;
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_user') THEN
    GRANT EXECUTE ON FUNCTION dev_silver.resolve_device(text, text, text, text, text) TO api_user;
  END IF;
END $$;

COMMIT;
