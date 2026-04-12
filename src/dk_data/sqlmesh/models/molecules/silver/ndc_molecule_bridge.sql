-- SQLMesh Model: mol_silver.ndc_molecule_bridge
-- Maps National Drug Codes (NDC) → molecule_id.
--
-- Purpose: enables cross-domain queries between CMS drug spend data and the
-- molecule registry. CMS Part D, Medicaid, and HCPCS drug tables use NDC as
-- their primary drug identifier; molecules are keyed by molecule_id (chembl_id).
--
-- Sources:
--   • mol_silver.drug_labels  — FDA labels have ndc_codes (JSONB array) + molecule_id
--   • mol_silver.molecule_identifiers (ndc type) — second pass from identifier bridge
--
-- Grain: (ndc, molecule_id) — one row per unique NDC↔molecule pair.
--   An NDC may map to multiple molecules (e.g. combination products).
--   A molecule will have many NDCs (different formulations/manufacturers).
--
-- NDC normalization: stored as-is from source; joining layers strip dashes via
--   REPLACE(ndc, '-', '') to handle 10- vs 11-digit and hyphenated forms.
--
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name mol_silver.ndc_molecule_bridge,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (ndc, molecule_id)
    ),
    cron '@daily',
    audits (
        not_null(columns := (ndc, molecule_id))
    ),
    grain (ndc, molecule_id),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- Source 1: FDA NDC directory — product_ndc + package_ndcs, linked via generic_name alias match
WITH from_labels AS (
    SELECT DISTINCT
        pkg_ndc                 AS ndc,
        m.molecule_id,
        'fda_ndc'               AS source,
        0.9                     AS confidence
    FROM mol_bronze.fda_ndc n
    JOIN mol_silver.molecules m
        ON LOWER(REGEXP_REPLACE(n.generic_name, '[^a-zA-Z0-9]', '', 'g'))
         = LOWER(REGEXP_REPLACE(m.canonical_name, '[^a-zA-Z0-9]', '', 'g'))
    CROSS JOIN LATERAL unnest(COALESCE(n.package_ndcs, ARRAY[n.product_ndc])) AS pkg_ndc
    WHERE n.generic_name IS NOT NULL
      AND m.molecule_id IS NOT NULL
      AND pkg_ndc IS NOT NULL
      AND pkg_ndc != ''
),

-- Source 2: identifier_mappings NDC entries (may cover additional formulations)
from_id_mappings AS (
    SELECT DISTINCT
        im.identifier     AS ndc,
        im.molecule_id,
        'identifier_mappings'   AS source,
        im.confidence
    FROM mol_silver.molecule_identifiers im
    WHERE im.source = 'ndc'
      AND im.identifier IS NOT NULL
),

combined AS (
    SELECT * FROM from_labels
    UNION
    SELECT * FROM from_id_mappings
)

SELECT
    gen_random_uuid()   AS id,
    ndc,
    molecule_id,
    source,
    confidence,
    NOW()               AS created_at
FROM combined
WHERE ndc IS NOT NULL
  AND molecule_id IS NOT NULL;
