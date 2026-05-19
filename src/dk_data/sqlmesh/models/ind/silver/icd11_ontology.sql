-- SQLMesh Model: Silver ICD-11 Ontology (Indication Domain)
-- WHO ICD-11 disease classification enriched with pharma-relevant therapeutic area
-- classification and relevance flags. Complements ind_silver.indication_ontology
-- (ICD-10 curated reference).
--
-- Source: ind_bronze.icd11_codes (WHO ICD-11 API via mol_raw.who_icd)
-- Grain: icd11_code
-- Usage: cross-reference for drug-disease linkage, indication prevalence, market sizing.
--        ind_silver.indication_ontology for ICD-10;
--        this model for ICD-11 (newer, richer definitions).
--
-- Therapeutic area classification uses ICD-11 chapter prefix patterns:
--   01: Infections/infestations → infectious_disease
--   02: Neoplasms              → oncology
--   03: Blood/immune           → hematology_immunology
--   04: Endocrine/metabolic    → endocrinology_metabolic
--   05: Mental/behavioural     → psychiatry_cns
--   06: Nervous system         → neurology
--   07: Sleep disorders        → neurology
--   08: Ear/mastoid            → otolaryngology
--   09: Circulatory system     → cardiovascular
--   10: Respiratory            → respiratory
--   11: Digestive              → gastroenterology
--   12: Skin                   → dermatology
--   13: Musculoskeletal        → musculoskeletal
--   14: Genitourinary/sexual   → nephrology_urology
--   15: Pregnancy              → obstetrics_gynecology
--   16: Neonatal conditions    → neonatology
--   17: Congenital anomalies   → congenital_disorders
-- Feature: 019-cms-puf-platform-reconciliation (indication bronze layer)

MODEL (
    name ind_silver.icd11_ontology,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (icd11_code, therapeutic_area)),
        unique_values(columns := (icd11_code))
    ),
    grain icd11_code
);

SELECT DISTINCT ON (b.icd11_code)
    gen_random_uuid()                   AS id,
    b.icd11_code,
    b.title,
    b.definition,
    b.class_kind,
    b.parent_code,
    b.is_leaf,
    b.browser_url,
    b.parent_uris,
    b.child_uris,
    b.inclusion_terms,
    b.exclusion_terms,
    b.exclusion_terms2,

    -- Therapeutic area classification from ICD-11 chapter prefix.
    -- ICD-11 stem codes begin with two-digit chapter prefix (e.g. "1A", "2B", "XA").
    CASE
        WHEN b.icd11_code ~ '^[01][A-Z]'     THEN 'infectious_disease'
        WHEN b.icd11_code ~ '^2[A-Z]'        THEN 'oncology'
        WHEN b.icd11_code ~ '^3[A-Z]'        THEN 'hematology_immunology'
        WHEN b.icd11_code ~ '^4[A-Z]'        THEN 'endocrinology_metabolic'
        WHEN b.icd11_code ~ '^5[A-Z]'        THEN 'psychiatry_cns'
        WHEN b.icd11_code ~ '^6[A-Z]'        THEN 'psychiatry_cns'
        WHEN b.icd11_code ~ '^7[A-Z]'        THEN 'neurology'
        WHEN b.icd11_code ~ '^8[A-Z]'        THEN 'neurology'
        WHEN b.icd11_code ~ '^9[A-Z]'        THEN 'otolaryngology'
        WHEN b.icd11_code ~ '^[A][A-Z]'      THEN 'cardiovascular'
        WHEN b.icd11_code ~ '^[B][A-Z]'      THEN 'respiratory'
        WHEN b.icd11_code ~ '^[C][A-Z]'      THEN 'digestive'
        WHEN b.icd11_code ~ '^[D][A-Z]'      THEN 'dermatology'
        WHEN b.icd11_code ~ '^[E][A-Z]'      THEN 'musculoskeletal'
        WHEN b.icd11_code ~ '^[F][A-Z]'      THEN 'nephrology_urology'
        WHEN b.icd11_code ~ '^[G][A-Z]'      THEN 'obstetrics_gynecology'
        WHEN b.icd11_code ~ '^[H][A-Z]'      THEN 'neonatology'
        WHEN b.icd11_code ~ '^[J][A-Z]'      THEN 'congenital_disorders'
        WHEN b.icd11_code ~ '^[K][A-Z]'      THEN 'symptoms_signs'
        WHEN b.icd11_code ~ '^[L][A-Z]'      THEN 'injury_trauma'
        WHEN b.icd11_code ~ '^[M][A-Z]'      THEN 'external_causes'
        WHEN b.icd11_code ~ '^[N][A-Z]'      THEN 'factors_health_status'
        WHEN b.icd11_code ~ '^[X][A-Z]'      THEN 'special_purposes'
        ELSE 'other'
    END                                 AS therapeutic_area,

    -- Pharma relevance: most disease categories are pharma-relevant;
    -- exclude symptoms/signs (K), external causes (M), factors (N)
    CASE
        WHEN b.icd11_code ~ '^[KMN][A-Z]' THEN FALSE
        WHEN b.class_kind = 'block'        THEN FALSE
        ELSE TRUE
    END                                 AS is_pharma_relevant,

    b.source,
    b.source_updated_at,
    NOW()                               AS created_at,
    NOW()                               AS updated_at

FROM ind_bronze.icd11_codes b
WHERE b.icd11_code IS NOT NULL
ORDER BY b.icd11_code, b.source_updated_at DESC;
