-- Migration 250: dev_silver devices hub — table DDL
-- Feature: FDA medical devices ingestion (2026-04-21) — 12th canonical hub.
-- Pattern: DDL only; population is handled by SQLMesh models under dev/silver/.
--
-- Three tables:
--   dev_silver.devices              — hub PK bigint, priority-hash derived
--   dev_silver.device_identifiers   — multi-source external IDs (k_number, pma_number,
--                                     pma_supplement, fei_number, udi_di, gudid_key, gmdn_code)
--   dev_silver.device_names         — canonical + aliases with normalized_name (trigram)
--
-- resolve_device() from migration 249 reads from these tables.
-- Trigram GIN index on device_names.normalized_name is idempotently re-created
-- in post_sqlmesh/000_hub_indexes.sql after SQLMesh rebuilds.

BEGIN;

-- ---------------------------------------------------------------------------
-- dev_silver.devices — canonical device entity hub
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dev_silver.devices (
    device_id          BIGINT PRIMARY KEY,                   -- deterministic hash; Rule H1 immutable
    canonical_name     TEXT NOT NULL,
    primary_identifier TEXT,                                  -- highest-priority available ID
    primary_source     TEXT NOT NULL CHECK (primary_source IN (
        'udi_di', 'k_number', 'pma_number', 'fei_number', 'name'
    )),

    -- Classification (FDA product_code → joins dev_silver.fda_classification)
    product_code       TEXT,
    device_class       TEXT,                                  -- '1', '2', '3', 'U', 'N', 'HDE'
    regulation_number  TEXT,

    -- Lifecycle flags (populated from classification catalog when product_code matches)
    is_implant             BOOLEAN,
    is_life_sustaining     BOOLEAN,
    is_drug_delivery_combo BOOLEAN,

    -- Provenance
    data_sources       JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dev_silver_devices_product_code
    ON dev_silver.devices (product_code);
CREATE INDEX IF NOT EXISTS idx_dev_silver_devices_device_class
    ON dev_silver.devices (device_class);
CREATE INDEX IF NOT EXISTS idx_dev_silver_devices_canonical_name_trgm
    ON dev_silver.devices USING GIN (LOWER(canonical_name) gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- dev_silver.device_identifiers — external IDs per device
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dev_silver.device_identifiers (
    device_id     BIGINT NOT NULL REFERENCES dev_silver.devices(device_id) ON DELETE CASCADE,
    source        TEXT   NOT NULL CHECK (source IN (
        'udi_di', 'udi_pi', 'k_number', 'pma_number', 'pma_supplement',
        'fei_number', 'registration_number', 'gudid_key', 'gmdn_code'
    )),
    identifier    TEXT   NOT NULL,
    is_primary    BOOLEAN DEFAULT FALSE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, identifier)
);

CREATE INDEX IF NOT EXISTS idx_dev_silver_device_identifiers_device
    ON dev_silver.device_identifiers (device_id);

-- ---------------------------------------------------------------------------
-- dev_silver.device_names — canonical + aliases with normalized_name
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dev_silver.device_names (
    device_id       BIGINT NOT NULL REFERENCES dev_silver.devices(device_id) ON DELETE CASCADE,
    normalized_name TEXT   NOT NULL,                          -- lower+trim+whitespace-collapse
    display_name    TEXT   NOT NULL,
    name_kind       TEXT   NOT NULL CHECK (name_kind IN (
        'canonical', 'brand', 'trade', 'generic', 'alias'
    )),
    source          TEXT   NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (normalized_name, device_id, source)
);

CREATE INDEX IF NOT EXISTS idx_dev_silver_device_names_device
    ON dev_silver.device_names (device_id);
CREATE INDEX IF NOT EXISTS idx_dev_silver_device_names_normalized_trgm
    ON dev_silver.device_names USING GIN (LOWER(normalized_name) gin_trgm_ops);

COMMENT ON TABLE dev_silver.devices IS
    'Canonical medical-device hub (12th silver hub). device_id = deterministic '
    'bigint hash of priority-highest identifier (UDI-DI → k_number → pma_number '
    '→ fei_number → normalized_name). Immutable once assigned (Rule H1). '
    'Populated by SQLMesh models dev_silver.devices, device_identifiers, device_names '
    'which read from dev_bronze.openfda_device_{510k,pma,classification}.';

COMMENT ON TABLE dev_silver.device_identifiers IS
    'Multi-source external IDs per device. Read by dev_silver.resolve_device().';

COMMENT ON TABLE dev_silver.device_names IS
    'Device names (canonical + aliases). normalized_name has a trigram GIN index '
    'powering resolve_device tier 5 (fuzzy ≥0.85) within SC-004 p99 ≤10ms.';

COMMIT;
