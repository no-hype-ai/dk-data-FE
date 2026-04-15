-- SQLMesh Model: mol_silver.atc_classifications
-- ATC therapeutic classification hierarchy hub (Item 2, feature 006)
-- Provides parent-child pointers for all 5 ATC levels so rules can walk
-- the hierarchy (e.g. D11AH05 → D11AH → D11A → D11 → D).
-- Sources: KEGG brite, ChEMBL, DrugBank. Priority: first non-null wins.

MODEL (
    name mol_silver.atc_classifications,
    kind FULL,
    cron '@weekly',
    grain atc_code,
    audits (
        not_null(columns := (atc_code)),
        unique_values(columns := (atc_code))
    )
);

-- Extract ATC codes from all available sources and derive the hierarchy.
-- ATC codes have a fixed structure:
--   Level 1: 1 letter        (A, B, C, ... V)
--   Level 2: 3 chars          (A01)
--   Level 3: 4 chars          (A01A)
--   Level 4: 5 chars          (A01AA)
--   Level 5: 7 chars          (A01AA01)
-- Parent is derived by truncating to the previous level's length.

WITH raw_atc_codes AS (
    -- Source 1: KEGG drug — atc_codes column (already extracted in bronze)
    SELECT DISTINCT UPPER(TRIM(code.value::TEXT, '"')) AS atc_code
    FROM mol_bronze.kegg_drug k,
         jsonb_array_elements(k.atc_codes) AS code
    WHERE k.atc_codes IS NOT NULL
      AND jsonb_array_length(k.atc_codes) > 0

    UNION

    -- Source 2: DrugBank — atc_codes JSONB array
    SELECT DISTINCT UPPER(TRIM(code.value::TEXT, '"')) AS atc_code
    FROM mol_bronze.drugbank_data d,
         jsonb_array_elements(d.raw_json->'atc_codes') AS code
    WHERE d.raw_json->'atc_codes' IS NOT NULL

    UNION

    -- Source 3: ChEMBL molecules — atc_classifications in raw_json
    SELECT DISTINCT UPPER(TRIM(code.value::TEXT, '"')) AS atc_code
    FROM mol_bronze.mol_bronze__chembl_molecules__2079710225 c,
         jsonb_array_elements_text(c.raw_json->'molecule_properties'->'atc_classifications') AS code
    WHERE c.raw_json->'molecule_properties'->'atc_classifications' IS NOT NULL
),

-- Filter to valid ATC code patterns (1-7 alphanumeric chars starting with letter)
valid_codes AS (
    SELECT atc_code
    FROM raw_atc_codes
    WHERE atc_code ~ '^[A-Z][0-9A-Z]{0,6}$'
      AND LENGTH(atc_code) IN (1, 3, 4, 5, 7)
),

-- Expand the hierarchy: for each Level 5 code, generate all ancestor levels
-- e.g. D11AH05 generates: D11AH05, D11AH, D11A, D11, D
all_levels AS (
    -- Level 5 codes (7 chars)
    SELECT atc_code FROM valid_codes WHERE LENGTH(atc_code) = 7
    UNION
    -- Level 4 ancestors (5 chars)
    SELECT DISTINCT LEFT(atc_code, 5) FROM valid_codes WHERE LENGTH(atc_code) >= 5
    UNION
    -- Level 3 ancestors (4 chars)
    SELECT DISTINCT LEFT(atc_code, 4) FROM valid_codes WHERE LENGTH(atc_code) >= 4
    UNION
    -- Level 2 ancestors (3 chars)
    SELECT DISTINCT LEFT(atc_code, 3) FROM valid_codes WHERE LENGTH(atc_code) >= 3
    UNION
    -- Level 1 ancestors (1 char)
    SELECT DISTINCT LEFT(atc_code, 1) FROM valid_codes WHERE LENGTH(atc_code) >= 1
)

SELECT
    al.atc_code,
    CASE LENGTH(al.atc_code)
        WHEN 7 THEN LEFT(al.atc_code, 5)  -- Level 5 → parent Level 4
        WHEN 5 THEN LEFT(al.atc_code, 4)  -- Level 4 → parent Level 3
        WHEN 4 THEN LEFT(al.atc_code, 3)  -- Level 3 → parent Level 2
        WHEN 3 THEN LEFT(al.atc_code, 1)  -- Level 2 → parent Level 1
        WHEN 1 THEN NULL                   -- Level 1 → no parent (root)
    END AS parent_atc_code,
    CASE LENGTH(al.atc_code)
        WHEN 1 THEN 1
        WHEN 3 THEN 2
        WHEN 4 THEN 3
        WHEN 5 THEN 4
        WHEN 7 THEN 5
    END AS level,
    NULL::TEXT AS description,  -- populated when WHO-CC bulk download is available
    'kegg_chembl_drugbank'::TEXT AS source,
    NOW() AS last_updated_at
FROM all_levels al
