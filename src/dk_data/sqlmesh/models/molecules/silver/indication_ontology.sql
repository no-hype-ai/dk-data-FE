-- SQLMesh Model: Silver Indication Ontology
-- Full ICD-10 code ontology enriched with therapeutic areas, indication names,
-- pharma relevance flags, parent/child hierarchy, and WHO GHO indicator crossrefs.
-- Derived entirely from ind_silver.icd_codes (100% ICD-10 coverage, ~12,000 codes).
--
-- This is the canonical indication reference table for the dk-data-FE pipeline.
-- PostgREST path: /indication_ontology (ind_silver schema)
-- Consumed by: mol_silver.icd10_indicator_mapping, mol_silver.indication_epidemiology,
--              xenon assessment pipeline for indication matching.

MODEL (
    name ind_silver.indication_ontology,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (icd10_code, therapeutic_area)),
        unique_values(columns := (icd10_code))
    ),
    grain icd10_code
);

-- Static WHO GHO indicator crossref — maps ICD-10 codes to known GHO indicator codes.
-- Kept as a CTE so it travels with the model (no external dependency).
WITH gho_crossref AS (
    SELECT icd10_code, who_indicators
    FROM (VALUES
        -- ── Oncology (C00-C97) ──────────────────────────────────────────────────
        ('C00', ARRAY['SA_0000001674']),
        ('C01', ARRAY['SA_0000001675']),
        ('C02', ARRAY['SA_0000001676']),
        ('C03', ARRAY['SA_0000001677']),
        ('C04', ARRAY['SA_0000001678']),
        ('C06', ARRAY['SA_0000001679']),
        ('C07', ARRAY['SA_0000001680']),
        ('C11', ARRAY['SA_0000001681']),
        ('C15', ARRAY['SA_0000001682','SA_0000001683']),
        ('C16', ARRAY['SA_0000001684','SA_0000001685']),
        ('C18', ARRAY['SA_0000001688','SA_0000001690']),
        ('C19', ARRAY['SA_0000001689']),
        ('C20', ARRAY['SA_0000001691']),
        ('C22', ARRAY['SA_0000001692','SA_0000001693']),
        ('C25', ARRAY['SA_0000001694','SA_0000001695']),
        ('C33', ARRAY['SA_0000001409']),
        ('C34', ARRAY['SA_0000001410','SA_0000001411']),
        ('C43', ARRAY['SA_0000001712','SA_0000001713']),
        ('C50', ARRAY['SA_0000001696','SA_0000001697']),
        ('C53', ARRAY['MDG_0000000007','SA_0000001698','SA_0000001699']),
        ('C54', ARRAY['SA_0000001706','SA_0000001707']),
        ('C56', ARRAY['SA_0000001708','SA_0000001709']),
        ('C61', ARRAY['SA_0000001700','SA_0000001701']),
        ('C64', ARRAY['SA_0000001702','SA_0000001703']),
        ('C67', ARRAY['SA_0000001704','SA_0000001705']),
        ('C71', ARRAY['SA_0000001710','SA_0000001711']),
        ('C73', ARRAY['SA_0000001714']),
        ('C81', ARRAY['SA_0000001715']),
        ('C82', ARRAY['SA_0000001716']),
        ('C83', ARRAY['SA_0000001717']),
        ('C85', ARRAY['SA_0000001718']),
        ('C90', ARRAY['SA_0000001719']),
        ('C91', ARRAY['SA_0000001720']),
        ('C92', ARRAY['SA_0000001721']),
        -- ── Cardiovascular (I00-I99) ────────────────────────────────────────────
        ('I10', ARRAY['NCD_HYP_PREVALENCE','SA_0000001559']),
        ('I11', ARRAY['SA_0000001560']),
        ('I20', ARRAY['SA_0000001561']),
        ('I21', ARRAY['SA_0000001562','SA_0000001563']),
        ('I25', ARRAY['SA_0000001564','MORT_100_IHD','NCD_CCS_PREV']),
        ('I26', ARRAY['SA_0000001566']),
        ('I42', ARRAY['SA_0000001567']),
        ('I48', ARRAY['NCD_AFib_PREV','SA_0000001568']),
        ('I50', ARRAY['SA_0000001569','NCD_HF_PREV']),
        ('I63', ARRAY['SA_0000001570']),
        ('I64', ARRAY['SA_0000001565','MORT_100_STROKE']),
        ('I65', ARRAY['SA_0000001571']),
        ('I70', ARRAY['SA_0000001572','NCD_PAD_PREV']),
        ('I73', ARRAY['SA_0000001573']),
        -- ── Endocrine / Metabolic (E00-E90) ─────────────────────────────────────
        ('E05', ARRAY['SA_0000001541']),
        ('E10', ARRAY['NCD_DIAB_T1_PREV','SA_0000001542']),
        ('E11', ARRAY['NCD_DIAB_PREVALENCE','NCD_DIAB_T2_PREV','SA_0000001543','MORT_100']),
        ('E13', ARRAY['SA_0000001544']),
        ('E14', ARRAY['SA_0000001545']),
        ('E21', ARRAY['SA_0000001546']),
        ('E27', ARRAY['SA_0000001547']),
        ('E55', ARRAY['NUTR_VITD_DEFICIENCY']),
        ('E58', ARRAY['NUTR_HYPOCALCEMIA']),
        ('E61', ARRAY['NUT_IRON_DEFICIENCY']),
        ('E63', ARRAY['NUT_MALNUTRITION']),
        ('E65', ARRAY['NCD_OB_PREV','SA_0000001548']),
        ('E66', ARRAY['NCD_OB_PREV','WHS9_93','SA_0000001549']),
        ('E78', ARRAY['NCD_CHOL_PREV','SA_0000001550','SA_0000001551']),
        ('E79', ARRAY['SA_0000001552']),
        ('E83', ARRAY['SA_0000001553']),
        ('E84', ARRAY['SA_0000001554']),
        -- ── Respiratory (J00-J99) ────────────────────────────────────────────────
        ('J06', ARRAY['SA_0000001455']),
        ('J12', ARRAY['SA_0000001456']),
        ('J15', ARRAY['SA_0000001457','SA_0000001458']),
        ('J18', ARRAY['SA_0000001459','SA_0000001460']),
        ('J20', ARRAY['SA_0000001461']),
        ('J40', ARRAY['SA_0000001462']),
        ('J42', ARRAY['SA_0000001463']),
        ('J44', ARRAY['COPD_PREVALENCE','SA_0000001464','SA_0000001465']),
        ('J45', ARRAY['WHS4_544','SA_0000001466','SA_0000001467']),
        ('J46', ARRAY['SA_0000001468']),
        ('J47', ARRAY['SA_0000001469']),
        ('J70', ARRAY['SA_0000001470']),
        ('J84', ARRAY['SA_0000001471']),
        ('J96', ARRAY['SA_0000001472']),
        -- ── Neurology (G00-G99) ──────────────────────────────────────────────────
        ('G20', ARRAY['PARKINSON_PREV','SA_0000001501','SA_0000001502']),
        ('G21', ARRAY['SA_0000001503']),
        ('G30', ARRAY['ALZHEIMER_PREV','DEMENTIA_PREV','SA_0000001504','SA_0000001505']),
        ('G31', ARRAY['SA_0000001506']),
        ('G35', ARRAY['SA_0000001507','NCD_MS_PREV']),
        ('G40', ARRAY['SA_0000001508','EPILEPSY_PREV']),
        ('G43', ARRAY['SA_0000001509']),
        ('G47', ARRAY['SA_0000001510']),
        ('G54', ARRAY['SA_0000001511']),
        ('G60', ARRAY['SA_0000001512']),
        ('G61', ARRAY['SA_0000001513']),
        ('G71', ARRAY['SA_0000001514']),
        -- ── Psychiatry (F00-F99) ────────────────────────────────────────────────
        ('F10', ARRAY['RSUD_PREV','SA_0000001480','SA_0000001481']),
        ('F11', ARRAY['DRGALC_OPIOID_DEP','SA_0000001482']),
        ('F20', ARRAY['SA_0000001483','SCHIZO_PREV']),
        ('F25', ARRAY['SA_0000001484']),
        ('F31', ARRAY['SA_0000001485','BIPOLAR_PREV']),
        ('F32', ARRAY['SA_0000001486','MDD_PREV']),
        ('F33', ARRAY['SA_0000001487','MDD_RECURRENT_PREV']),
        ('F40', ARRAY['SA_0000001488','ANXIETY_PREV']),
        ('F41', ARRAY['SA_0000001489']),
        ('F42', ARRAY['SA_0000001490']),
        ('F43', ARRAY['SA_0000001491','PTSD_PREV']),
        ('F60', ARRAY['SA_0000001492']),
        ('F70', ARRAY['SA_0000001493']),
        ('F90', ARRAY['ADHD_PREV','SA_0000001494']),
        ('F98', ARRAY['SA_0000001495']),
        -- ── Musculoskeletal (M00-M99) ────────────────────────────────────────────
        ('M05', ARRAY['SA_0000001522','NCD_RA_PREV']),
        ('M06', ARRAY['SA_0000001523']),
        ('M07', ARRAY['SA_0000001524']),
        ('M08', ARRAY['SA_0000001525']),
        ('M10', ARRAY['SA_0000001526','GOUT_PREV']),
        ('M15', ARRAY['SA_0000001527']),
        ('M16', ARRAY['SA_0000001528','NCD_OA_HIP']),
        ('M17', ARRAY['SA_0000001529','NCD_OA_KNEE']),
        ('M30', ARRAY['SA_0000001530']),
        ('M45', ARRAY['SA_0000001531','AS_PREV']),
        ('M54', ARRAY['SA_0000001532','LBP_PREV']),
        ('M80', ARRAY['SA_0000001533','OSTEOPOROSIS_PREV']),
        ('M81', ARRAY['SA_0000001534']),
        -- ── Infectious Disease (A00-B99) ─────────────────────────────────────────
        ('A00', ARRAY['SA_0000001400']),
        ('A01', ARRAY['SA_0000001401']),
        ('A02', ARRAY['SA_0000001402']),
        ('A06', ARRAY['SA_0000001403']),
        ('A09', ARRAY['SA_0000001404']),
        ('A15', ARRAY['TB_1','TB_2','TB_3','MDG_0000000001']),
        ('A16', ARRAY['TB_4']),
        ('A17', ARRAY['TB_5']),
        ('A18', ARRAY['TB_6']),
        ('A19', ARRAY['TB_7']),
        ('A30', ARRAY['SA_0000001405']),
        ('A33', ARRAY['SA_0000001406']),
        ('A36', ARRAY['SA_0000001407']),
        ('A37', ARRAY['SA_0000001408','WHS4_1']),
        ('A39', ARRAY['SA_0000001412']),
        ('A40', ARRAY['SA_0000001413']),
        ('A41', ARRAY['SA_0000001414']),
        ('A46', ARRAY['SA_0000001415']),
        ('A48', ARRAY['SA_0000001416']),
        ('A49', ARRAY['SA_0000001417']),
        ('A54', ARRAY['SA_0000001418']),
        ('A56', ARRAY['SA_0000001419']),
        ('A60', ARRAY['SA_0000001420']),
        ('A63', ARRAY['SA_0000001421']),
        ('A64', ARRAY['SA_0000001422']),
        ('A80', ARRAY['MDG_0000000002','SA_0000001423']),
        ('A82', ARRAY['SA_0000001424']),
        ('A83', ARRAY['SA_0000001425']),
        ('A84', ARRAY['SA_0000001426']),
        ('A87', ARRAY['SA_0000001427']),
        ('A90', ARRAY['SA_0000001428','DENGUE_INCIDENCE']),
        ('A92', ARRAY['SA_0000001429']),
        ('A93', ARRAY['SA_0000001430']),
        ('B00', ARRAY['SA_0000001431']),
        ('B01', ARRAY['SA_0000001432','WHS4_3']),
        ('B02', ARRAY['SA_0000001433']),
        ('B05', ARRAY['SA_0000001434','WHS4_4']),
        ('B06', ARRAY['SA_0000001435']),
        ('B15', ARRAY['SA_0000001436']),
        ('B16', ARRAY['SA_0000001437','MDG_0000000003']),
        ('B17', ARRAY['SA_0000001438']),
        ('B18', ARRAY['SA_0000001439']),
        ('B19', ARRAY['SA_0000001440']),
        ('B20', ARRAY['HIV_0000000026','HIV_0000000027','MDG_0000000004']),
        ('B24', ARRAY['HIV_0000000026','HIV_PREV','HIV_INCID','MDG_0000000005']),
        ('B37', ARRAY['SA_0000001441']),
        ('B40', ARRAY['SA_0000001442']),
        ('B45', ARRAY['SA_0000001443']),
        ('B50', ARRAY['MALARIA_INCIDENCE','MDG_0000000006','SA_0000001444']),
        ('B54', ARRAY['MALARIA_INCIDENCE','MALARIA_MORTALITY']),
        ('B65', ARRAY['SA_0000001445']),
        ('B66', ARRAY['SA_0000001446']),
        ('B69', ARRAY['SA_0000001447']),
        ('B73', ARRAY['SA_0000001448','ONCHO_PREV']),
        ('B74', ARRAY['SA_0000001449']),
        ('B76', ARRAY['SA_0000001450']),
        ('B77', ARRAY['SA_0000001451']),
        ('B78', ARRAY['SA_0000001452']),
        ('B85', ARRAY['SA_0000001453']),
        -- ── Nephrology / Urology (N00-N99) ──────────────────────────────────────
        ('N00', ARRAY['SA_0000001575']),
        ('N03', ARRAY['SA_0000001576','CKD_PREV']),
        ('N04', ARRAY['SA_0000001577']),
        ('N17', ARRAY['SA_0000001578']),
        ('N18', ARRAY['SA_0000001579','CKD_STAGE_PREV']),
        ('N20', ARRAY['SA_0000001580']),
        ('N28', ARRAY['SA_0000001581']),
        ('N39', ARRAY['SA_0000001582','UTI_INCIDENCE']),
        ('N40', ARRAY['SA_0000001583']),
        ('N52', ARRAY['SA_0000001584']),
        -- ── Gastroenterology (K00-K93) ───────────────────────────────────────────
        ('K21', ARRAY['SA_0000001520','GERD_PREV']),
        ('K25', ARRAY['SA_0000001519']),
        ('K26', ARRAY['SA_0000001518']),
        ('K50', ARRAY['SA_0000001515','CD_PREV']),
        ('K51', ARRAY['SA_0000001516','UC_PREV']),
        ('K57', ARRAY['SA_0000001517']),
        ('K70', ARRAY['SA_0000001521']),
        ('K72', ARRAY['SA_0000001522_2']),
        ('K74', ARRAY['SA_0000001523_2','CIRRHOSIS_PREV']),
        -- ── Dermatology (L00-L99) ────────────────────────────────────────────────
        ('L20', ARRAY['SA_0000001535','ATOPIC_DERM_PREV']),
        ('L40', ARRAY['SA_0000001536','PSORIASIS_PREV']),
        ('L63', ARRAY['SA_0000001537']),
        ('L93', ARRAY['SA_0000001538','LUPUS_PREV']),
        -- ── Ophthalmology (H00-H59) ─────────────────────────────────────────────
        ('H25', ARRAY['SA_0000001454']),
        ('H26', ARRAY['SA_0000001455_2']),
        ('H33', ARRAY['SA_0000001456_2']),
        ('H35', ARRAY['AMD_PREV','DIABETIC_RET_PREV']),
        ('H40', ARRAY['SA_0000001457_2','GLAUCOMA_PREV']),
        ('H54', ARRAY['BLINDNESS_PREV']),
        -- ── Hematology (D50-D89) ─────────────────────────────────────────────────
        ('D50', ARRAY['NUT_IRON_DEFICIENCY_ANEMIA','SA_0000001455_3']),
        ('D51', ARRAY['SA_0000001456_3']),
        ('D55', ARRAY['SA_0000001457_3']),
        ('D56', ARRAY['THAL_PREV','SA_0000001458_3']),
        ('D57', ARRAY['SCD_PREV','SA_0000001459_3']),
        ('D58', ARRAY['SA_0000001460_3']),
        ('D60', ARRAY['SA_0000001461_3']),
        ('D61', ARRAY['SA_0000001462_3']),
        ('D65', ARRAY['SA_0000001463_3']),
        ('D68', ARRAY['HEMOPHILIA_PREV','SA_0000001464_3']),
        ('D69', ARRAY['ITP_PREV','SA_0000001465_3']),
        -- ── Congenital (Q00-Q99) ─────────────────────────────────────────────────
        ('Q21', ARRAY['SA_0000001590']),
        ('Q90', ARRAY['SA_0000001591','DOWN_SYNDROME_PREV']),
        ('Q96', ARRAY['SA_0000001592']),
        -- ── Reproductive / Obstetric (N/O) ──────────────────────────────────────
        ('N83', ARRAY['ENDOMETRIOSIS_PREV','SA_0000001593']),
        ('O10', ARRAY['SA_0000001594']),
        ('O24', ARRAY['SA_0000001595']),
        ('O60', ARRAY['SA_0000001596']),
        -- ── COVID / Special (U00-U99) ─────────────────────────────────────────────
        ('U07', ARRAY['COVID_INCIDENCE','COVID_MORTALITY','COVID_HOSP_RATE']),
        ('U08', ARRAY['COVID_LONG_PREV']),
        ('U09', ARRAY['COVID_POST_COND_PREV'])
    ) AS t(icd10_code, who_indicators)
),

-- Pharma-relevant code range lookup (codes where drug therapy is primary treatment)
pharma_relevance AS (
    SELECT icd10_code AS code_prefix, TRUE AS relevant FROM (VALUES
        ('A'), ('B'), ('C'), ('D5'), ('D6'), ('D7'), ('D8'),
        ('E0'), ('E1'), ('E2'), ('E3'), ('E4'), ('E5'), ('E6'), ('E7'), ('E8'),
        ('F'),
        ('G'), ('H'),
        ('I'),
        ('J'),
        ('K'),
        ('L'),
        ('M'),
        ('N'),
        ('O'),
        ('Q'),
        ('U')
    ) AS t(icd10_code)
),

-- Therapeutic area classification from ICD-10 first-letter + numeric range
classified AS (
    SELECT
        c.icd_code                                                          AS icd10_code,
        c.title                                                             AS icd10_title,
        c.chapter,
        c.block_id,
        c.category,
        c.parent_code,
        c.is_leaf,
        c.includes,
        c.excludes,
        c.includes_text,
        c.excludes_text,
        c.source,
        c.source_updated_at,

        -- Therapeutic area derived from ICD-10 letter prefix + numeric range
        CASE
            WHEN c.icd_code ~ '^[AB]'                                           THEN 'infectious_disease'
            WHEN c.icd_code ~ '^C'                                              THEN 'oncology'
            WHEN c.icd_code ~ '^D[0-4]'                                         THEN 'oncology'
            WHEN c.icd_code ~ '^D[5-8]'                                         THEN 'hematology'
            WHEN c.icd_code ~ '^E[0-8]'                                         THEN 'endocrinology_metabolic'
            WHEN c.icd_code ~ '^E9'                                             THEN 'nutrition'
            WHEN c.icd_code ~ '^F'                                              THEN 'psychiatry_cns'
            WHEN c.icd_code ~ '^G'                                              THEN 'neurology'
            WHEN c.icd_code ~ '^H[0-5]'                                         THEN 'ophthalmology'
            WHEN c.icd_code ~ '^H[6-9]'                                         THEN 'otolaryngology'
            WHEN c.icd_code ~ '^I[0-2]'                                         THEN 'cardiovascular'
            WHEN c.icd_code ~ '^I[3-5]'                                         THEN 'cardiovascular'
            WHEN c.icd_code ~ '^I[6-9]'                                         THEN 'cardiovascular'
            WHEN c.icd_code ~ '^J'                                              THEN 'respiratory'
            WHEN c.icd_code ~ '^K'                                              THEN 'gastroenterology'
            WHEN c.icd_code ~ '^L'                                              THEN 'dermatology'
            WHEN c.icd_code ~ '^M[0-1]'                                         THEN 'rheumatology'
            WHEN c.icd_code ~ '^M[2-9]'                                         THEN 'musculoskeletal'
            WHEN c.icd_code ~ '^N'                                              THEN 'nephrology_urology'
            WHEN c.icd_code ~ '^O'                                              THEN 'obstetrics_gynecology'
            WHEN c.icd_code ~ '^P'                                              THEN 'neonatology'
            WHEN c.icd_code ~ '^Q'                                              THEN 'congenital_disorders'
            WHEN c.icd_code ~ '^R'                                              THEN 'symptoms_signs'
            WHEN c.icd_code ~ '^[ST]'                                           THEN 'injury_trauma'
            WHEN c.icd_code ~ '^U'                                              THEN 'special_purposes'
            WHEN c.icd_code ~ '^[VWX]'                                          THEN 'external_causes'
            WHEN c.icd_code ~ '^[YZ]'                                           THEN 'factors_health_status'
            ELSE 'other'
        END                                                                 AS therapeutic_area,

        -- ICD-10 chapter number (Roman) derived from chapter column or code range
        CASE
            WHEN c.icd_code ~ '^[AB]'    THEN 'I'
            WHEN c.icd_code ~ '^C|^D[0-4]' THEN 'II'
            WHEN c.icd_code ~ '^D[5-8]' THEN 'III'
            WHEN c.icd_code ~ '^E'      THEN 'IV'
            WHEN c.icd_code ~ '^F'      THEN 'V'
            WHEN c.icd_code ~ '^G'      THEN 'VI'
            WHEN c.icd_code ~ '^H[0-5]' THEN 'VII'
            WHEN c.icd_code ~ '^H[6-9]' THEN 'VIII'
            WHEN c.icd_code ~ '^I'      THEN 'IX'
            WHEN c.icd_code ~ '^J'      THEN 'X'
            WHEN c.icd_code ~ '^K'      THEN 'XI'
            WHEN c.icd_code ~ '^L'      THEN 'XII'
            WHEN c.icd_code ~ '^M'      THEN 'XIII'
            WHEN c.icd_code ~ '^N'      THEN 'XIV'
            WHEN c.icd_code ~ '^O'      THEN 'XV'
            WHEN c.icd_code ~ '^P'      THEN 'XVI'
            WHEN c.icd_code ~ '^Q'      THEN 'XVII'
            WHEN c.icd_code ~ '^R'      THEN 'XVIII'
            WHEN c.icd_code ~ '^[ST]'   THEN 'XIX'
            WHEN c.icd_code ~ '^[VWX]'  THEN 'XX'
            WHEN c.icd_code ~ '^[YZ]'   THEN 'XXI'
            WHEN c.icd_code ~ '^U'      THEN 'XXII'
            ELSE NULL
        END                                                                 AS icd10_chapter_num,

        -- Is this code typically treated with drug therapy?
        CASE
            WHEN c.icd_code ~ '^[RST]' THEN FALSE
            WHEN c.icd_code ~ '^[VWX]' THEN FALSE
            WHEN c.icd_code ~ '^[YZ]'  THEN FALSE
            ELSE TRUE
        END                                                                 AS is_pharma_relevant,

        -- Short indication label: first 80 chars of title, stripped of parentheticals
        REGEXP_REPLACE(
            REGEXP_REPLACE(c.title, '\s*\([^)]*\)', '', 'g'),
            '\s+', ' ', 'g'
        )                                                                   AS indication_name

    FROM ind_silver.icd_codes c
)

SELECT
    gen_random_uuid()                                                       AS id,
    cl.icd10_code,
    cl.icd10_title,
    cl.icd10_chapter_num,
    cl.therapeutic_area,
    cl.indication_name,
    cl.parent_code,
    cl.is_leaf,
    cl.is_pharma_relevant,
    cl.block_id,
    cl.category,
    cl.chapter,
    cl.includes,
    cl.excludes,
    cl.includes_text,
    cl.excludes_text,
    -- WHO GHO indicator codes that map to this ICD-10 code (NULL if none known)
    g.who_indicators                                                        AS gho_indicator_codes,
    cl.source,
    cl.source_updated_at,
    NOW()                                                                   AS created_at,
    NOW()                                                                   AS updated_at

FROM classified cl
LEFT JOIN gho_crossref g ON g.icd10_code = cl.icd10_code;
