-- SQLMesh Model: mol_silver.ndc_molecule_bridge
-- Maps National Drug Codes (NDC) → molecule_id.
--
-- Purpose: enables cross-domain queries between CMS drug spend data and the
-- molecule registry. CMS Part D, Medicaid, and HCPCS drug tables use NDC as
-- their primary drug identifier; molecules are keyed by molecule_id (chembl_id).
--
-- Sources:
--   • mol_silver.drug_labels  — FDA labels have ndc_codes (JSONB array) + molecule_id
--   • mol_silver.identifier_mappings (ndc type) — second pass from identifier bridge
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
    grain (ndc, molecule_id)
);

-- Source 1: FDA drug labels (ndc_codes JSONB array, directly linked to molecule)
WITH from_labels AS (
    SELECT DISTINCT
        ndc_code                AS ndc,
        dl.molecule_id,
        'openfda_labels'        AS source,
        1.0                     AS confidence
    FROM mol_silver.drug_labels dl
    CROSS JOIN LATERAL jsonb_array_elements_text(
        COALESCE(dl.ndc_codes, '[]'::jsonb)
    ) AS ndc_code
    WHERE dl.molecule_id IS NOT NULL
      AND ndc_code IS NOT NULL
      AND ndc_code != ''
),

-- Source 2: identifier_mappings NDC entries (may cover additional formulations)
from_id_mappings AS (
    SELECT DISTINCT
        im.identifier_value     AS ndc,
        im.molecule_id,
        'identifier_mappings'   AS source,
        im.confidence
    FROM mol_silver.identifier_mappings im
    WHERE im.identifier_type = 'ndc'
      AND im.identifier_value IS NOT NULL
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
