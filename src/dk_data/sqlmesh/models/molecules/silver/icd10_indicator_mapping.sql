-- SQLMesh Model: Silver ICD-10 Indicator Mapping (static seed)
-- Maps WHO GHO indicator codes to ICD-10 codes and metric types.
-- Referenced by mol_silver.indication_epidemiology to join WHO GHO data to disease codes.
-- 17 rows covering the major WHO indicators used in epidemiology analysis.
-- This is a static reference table — no raw/bronze source.

MODEL (
    name mol_silver.icd10_indicator_mapping,
    kind FULL,
    cron '@yearly',
    audits (
        not_null(columns := (who_indicator, icd10_code))
    ),
    grain who_indicator
);

-- Static mapping: WHO GHO indicator → ICD-10 code + metric_type
-- metric_type values: incidence_rate, prevalence_rate, mortality_rate, mortality_count
SELECT who_indicator, icd10_code, metric_type, indication_label
FROM (VALUES
    ('SA_0000001688', 'C18', 'incidence_rate',   'Colorectal cancer'),
    ('SA_0000001690', 'C18', 'mortality_rate',   'Colorectal cancer mortality'),
    ('SA_0000001410', 'C34', 'incidence_rate',   'Lung cancer'),
    ('SA_0000001411', 'C34', 'mortality_rate',   'Lung cancer mortality'),
    ('SA_0000001696', 'C50', 'incidence_rate',   'Breast cancer'),
    ('SA_0000001697', 'C50', 'mortality_rate',   'Breast cancer mortality'),
    ('SA_0000001700', 'C61', 'incidence_rate',   'Prostate cancer'),
    ('MORT_100', 'E11',      'prevalence_rate',  'Type 2 diabetes'),
    ('NCD_DIAB_PREVALENCE', 'E11', 'prevalence_rate', 'Diabetes mellitus prevalence'),
    ('WHS4_544', 'J45',      'prevalence_rate',  'Asthma'),
    ('COPD_PREVALENCE', 'J44', 'prevalence_rate', 'COPD'),
    ('SA_0000001564', 'I25',  'mortality_rate',   'Ischaemic heart disease'),
    ('SA_0000001565', 'I64',  'mortality_rate',   'Stroke'),
    ('ALZHEIMER_PREV', 'G30', 'prevalence_rate',  'Alzheimer disease'),
    ('PARKINSON_PREV', 'G20', 'prevalence_rate',  'Parkinson disease'),
    ('HIV_0000000026', 'B24', 'prevalence_rate',  'HIV/AIDS'),
    ('RSUD_PREV', 'F10',      'prevalence_rate',  'Alcohol use disorders')
) AS t(who_indicator, icd10_code, metric_type, indication_label);
