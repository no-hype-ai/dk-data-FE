-- SQLMesh Model: Silver Indication Ontology
-- Full ICD-10 code ontology enriched with therapeutic areas, indication names,
-- pharma relevance flags, parent/child hierarchy, and WHO GHO indicator crossrefs.
--
-- Self-contained: all code/title data is embedded as a static VALUES registry,
-- removing the dependency on ind_silver.icd_codes (which requires WHO ICD-11
-- OAuth2 credentials). Coverage: all codes in mol_silver.icd10_indicator_mapping
-- plus commonly assessed indications in pharma (oncology, cardiovascular, CNS, etc.).
--
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

-- ── Static WHO GHO indicator crossref ──────────────────────────────────────
WITH gho_crossref AS (
    SELECT icd10_code, who_indicators
    FROM (VALUES
        -- Oncology (C00-C97)
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
        ('C22', ARRAY['NCDMORT3070']),
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
        -- Cardiovascular (I00-I99)
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
        -- Endocrine / Metabolic (E00-E90)
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
        ('E66', ARRAY['NCD_OB_PREV','WHS9_93','SA_0000001549']),
        ('E78', ARRAY['NCD_CHOL_PREV','SA_0000001550','SA_0000001551']),
        ('E79', ARRAY['SA_0000001552']),
        ('E83', ARRAY['SA_0000001553']),
        ('E84', ARRAY['SA_0000001554']),
        -- Respiratory (J00-J99)
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
        ('J84', ARRAY['SA_0000001471']),
        ('J96', ARRAY['SA_0000001472']),
        -- Neurology (G00-G99)
        ('G20', ARRAY['PARKINSON_PREV','SA_0000001501','SA_0000001502']),
        ('G30', ARRAY['ALZHEIMER_PREV','DEMENTIA_PREV','SA_0000001504','SA_0000001505']),
        ('G35', ARRAY['SA_0000001507','NCD_MS_PREV']),
        ('G40', ARRAY['SA_0000001508','EPILEPSY_PREV']),
        ('G43', ARRAY['SA_0000001509']),
        -- Psychiatry (F00-F99)
        ('F10', ARRAY['RSUD_PREV','SA_0000001480','SA_0000001481']),
        ('F11', ARRAY['DRGALC_OPIOID_DEP','SA_0000001482']),
        ('F20', ARRAY['SA_0000001483','SCHIZO_PREV']),
        ('F31', ARRAY['SA_0000001485','BIPOLAR_PREV']),
        ('F32', ARRAY['SA_0000001486','MDD_PREV']),
        ('F33', ARRAY['SA_0000001487','MDD_RECURRENT_PREV']),
        ('F40', ARRAY['SA_0000001488','ANXIETY_PREV']),
        ('F90', ARRAY['ADHD_PREV','SA_0000001494']),
        -- Musculoskeletal (M00-M99)
        ('M05', ARRAY['SA_0000001522','NCD_RA_PREV']),
        ('M06', ARRAY['SA_0000001523']),
        ('M10', ARRAY['SA_0000001526','GOUT_PREV']),
        ('M16', ARRAY['SA_0000001528','NCD_OA_HIP']),
        ('M17', ARRAY['SA_0000001529','NCD_OA_KNEE']),
        ('M45', ARRAY['SA_0000001531','AS_PREV']),
        ('M54', ARRAY['SA_0000001532','LBP_PREV']),
        ('M80', ARRAY['SA_0000001533','OSTEOPOROSIS_PREV']),
        -- Infectious Disease (A00-B99)
        ('A15', ARRAY['TB_1','TB_2','TB_3','MDG_0000000001']),
        ('B16', ARRAY['SA_0000001437','MDG_0000000003']),
        ('B18', ARRAY['SA_0000001439']),
        ('B20', ARRAY['HIV_0000000026','HIV_0000000027','MDG_0000000004']),
        ('B24', ARRAY['HIV_0000000026','HIV_PREV','HIV_INCID','MDG_0000000005']),
        ('B50', ARRAY['MALARIA_INCIDENCE','MDG_0000000006','SA_0000001444']),
        -- Nephrology (N00-N99)
        ('N03', ARRAY['SA_0000001576','CKD_PREV']),
        ('N18', ARRAY['SA_0000001579','CKD_STAGE_PREV']),
        ('N39', ARRAY['SA_0000001582','UTI_INCIDENCE']),
        ('N40', ARRAY['SA_0000001583']),
        -- Gastroenterology (K00-K93)
        ('K50', ARRAY['SA_0000001515','CD_PREV']),
        ('K51', ARRAY['SA_0000001516','UC_PREV']),
        ('K70', ARRAY['SA_0000001521']),
        ('K74', ARRAY['CIRRHOSIS_PREV']),
        -- Dermatology (L00-L99)
        ('L20', ARRAY['SA_0000001535','ATOPIC_DERM_PREV']),
        ('L40', ARRAY['SA_0000001536','PSORIASIS_PREV']),
        ('L93', ARRAY['SA_0000001538','LUPUS_PREV']),
        -- Hematology (D50-D89)
        ('D56', ARRAY['THAL_PREV']),
        ('D57', ARRAY['SCD_PREV']),
        ('D68', ARRAY['HEMOPHILIA_PREV']),
        ('D69', ARRAY['ITP_PREV']),
        -- COVID / Special (U00-U99)
        ('U07', ARRAY['COVID_INCIDENCE','COVID_MORTALITY','COVID_HOSP_RATE']),
        ('U08', ARRAY['COVID_LONG_PREV']),
        ('U09', ARRAY['COVID_POST_COND_PREV'])
    ) AS t(icd10_code, who_indicators)
),

-- ── Static code registry (replaces ind_silver.icd_codes dependency) ──────
-- All pharma-relevant ICD-10 codes with titles. Covers every code in
-- mol_silver.icd10_indicator_mapping plus commonly assessed drug indications.
code_registry AS (
    SELECT icd_code, title, chapter, block_id, category, parent_code, is_leaf
    FROM (VALUES
        -- ── Lip / Oral cavity (C00-C14) ──────────────────────────────────────
        ('C00', 'Malignant neoplasm of lip',                                                    'II','C00-C14','C00',  NULL,  FALSE),
        ('C01', 'Malignant neoplasm of base of tongue',                                         'II','C01-C02','C01',  NULL,  FALSE),
        ('C02', 'Malignant neoplasm of other and unspecified parts of tongue',                  'II','C01-C02','C02',  NULL,  FALSE),
        ('C03', 'Malignant neoplasm of gum',                                                    'II','C03-C06','C03',  NULL,  FALSE),
        ('C04', 'Malignant neoplasm of floor of mouth',                                         'II','C03-C06','C04',  NULL,  FALSE),
        ('C06', 'Malignant neoplasm of other and unspecified parts of mouth',                   'II','C03-C06','C06',  NULL,  FALSE),
        ('C07', 'Malignant neoplasm of parotid gland',                                          'II','C07-C08','C07',  NULL,  FALSE),
        ('C11', 'Malignant neoplasm of nasopharynx',                                            'II','C09-C14','C11',  NULL,  FALSE),
        -- ── Oesophagus / stomach (C15-C26) ───────────────────────────────────
        ('C15', 'Malignant neoplasm of oesophagus',                                             'II','C15-C26','C15',  NULL,  FALSE),
        ('C16', 'Malignant neoplasm of stomach',                                                'II','C15-C26','C16',  NULL,  FALSE),
        ('C18', 'Malignant neoplasm of colon',                                                  'II','C15-C26','C18',  NULL,  FALSE),
        ('C18.9','Malignant neoplasm of colon, unspecified',                                    'II','C15-C26','C18.9','C18', TRUE),
        ('C19', 'Malignant neoplasm of rectosigmoid junction',                                  'II','C15-C26','C19',  NULL,  FALSE),
        ('C20', 'Malignant neoplasm of rectum',                                                 'II','C15-C26','C20',  NULL,  FALSE),
        ('C22', 'Malignant neoplasm of liver and intrahepatic bile ducts',                      'II','C22-C24','C22',  NULL,  FALSE),
        ('C22.0','Hepatocellular carcinoma',                                                     'II','C22-C24','C22.0','C22', TRUE),
        ('C22.1','Intrahepatic bile duct carcinoma',                                             'II','C22-C24','C22.1','C22', TRUE),
        ('C22.9','Malignant neoplasm of liver, unspecified',                                    'II','C22-C24','C22.9','C22', TRUE),
        ('C25', 'Malignant neoplasm of pancreas',                                               'II','C15-C26','C25',  NULL,  FALSE),
        ('C25.9','Malignant neoplasm of pancreas, unspecified',                                 'II','C15-C26','C25.9','C25', TRUE),
        -- ── Respiratory (C30-C39) ─────────────────────────────────────────────
        ('C33', 'Malignant neoplasm of trachea',                                                'II','C30-C39','C33',  NULL,  FALSE),
        ('C34', 'Malignant neoplasm of bronchus and lung',                                      'II','C30-C39','C34',  NULL,  FALSE),
        ('C34.1','Malignant neoplasm of upper lobe, bronchus or lung',                          'II','C30-C39','C34.1','C34', TRUE),
        ('C34.9','Malignant neoplasm of bronchus or lung, unspecified',                         'II','C30-C39','C34.9','C34', TRUE),
        -- ── Skin / melanoma (C43-C44) ─────────────────────────────────────────
        ('C43', 'Malignant melanoma of skin',                                                   'II','C43-C44','C43',  NULL,  FALSE),
        ('C43.9','Malignant melanoma of skin, unspecified',                                     'II','C43-C44','C43.9','C43', TRUE),
        -- ── Breast (C50) ──────────────────────────────────────────────────────
        ('C50', 'Malignant neoplasm of breast',                                                 'II','C50',    'C50',  NULL,  FALSE),
        ('C50.9','Malignant neoplasm of breast, unspecified',                                   'II','C50',    'C50.9','C50', TRUE),
        -- ── Female genital (C51-C58) ──────────────────────────────────────────
        ('C53', 'Malignant neoplasm of cervix uteri',                                           'II','C51-C58','C53',  NULL,  FALSE),
        ('C54', 'Malignant neoplasm of corpus uteri',                                           'II','C51-C58','C54',  NULL,  FALSE),
        ('C56', 'Malignant neoplasm of ovary',                                                  'II','C51-C58','C56',  NULL,  FALSE),
        -- ── Male genital (C60-C63) ────────────────────────────────────────────
        ('C61', 'Malignant neoplasm of prostate',                                               'II','C60-C63','C61',  NULL,  FALSE),
        -- ── Urinary tract (C64-C68) ───────────────────────────────────────────
        ('C64', 'Malignant neoplasm of kidney, except renal pelvis',                            'II','C64-C68','C64',  NULL,  FALSE),
        ('C64.9','Malignant neoplasm of kidney, except renal pelvis, unspecified',              'II','C64-C68','C64.9','C64', TRUE),
        ('C67', 'Malignant neoplasm of bladder',                                                'II','C64-C68','C67',  NULL,  FALSE),
        ('C67.9','Malignant neoplasm of bladder, unspecified',                                  'II','C64-C68','C67.9','C67', TRUE),
        -- ── Brain / CNS (C69-C72) ─────────────────────────────────────────────
        ('C71', 'Malignant neoplasm of brain',                                                  'II','C69-C72','C71',  NULL,  FALSE),
        ('C71.9','Malignant neoplasm of brain, unspecified',                                    'II','C69-C72','C71.9','C71', TRUE),
        -- ── Thyroid / endocrine glands (C73-C75) ─────────────────────────────
        ('C73', 'Malignant neoplasm of thyroid gland',                                          'II','C73-C75','C73',  NULL,  FALSE),
        -- ── Lymphoma (C81-C86) ────────────────────────────────────────────────
        ('C81', 'Hodgkin lymphoma',                                                             'II','C81-C86','C81',  NULL,  FALSE),
        ('C81.9','Hodgkin lymphoma, unspecified',                                               'II','C81-C86','C81.9','C81', TRUE),
        ('C82', 'Follicular lymphoma',                                                          'II','C81-C86','C82',  NULL,  FALSE),
        ('C83', 'Non-follicular lymphoma',                                                      'II','C81-C86','C83',  NULL,  FALSE),
        ('C83.3','Diffuse large B-cell lymphoma',                                               'II','C81-C86','C83.3','C83', TRUE),
        ('C85', 'Other and unspecified types of non-Hodgkin lymphoma',                          'II','C81-C86','C85',  NULL,  FALSE),
        -- ── Multiple myeloma / plasma cell (C88-C90) ─────────────────────────
        ('C90', 'Multiple myeloma and malignant plasma cell neoplasms',                         'II','C88-C90','C90',  NULL,  FALSE),
        ('C90.0','Multiple myeloma',                                                             'II','C88-C90','C90.0','C90', TRUE),
        -- ── Leukaemia (C91-C95) ───────────────────────────────────────────────
        ('C91', 'Lymphoid leukaemia',                                                           'II','C91-C95','C91',  NULL,  FALSE),
        ('C91.0','Acute lymphoblastic leukaemia (ALL)',                                         'II','C91-C95','C91.0','C91', TRUE),
        ('C91.1','Chronic lymphocytic leukaemia of B-cell type',                               'II','C91-C95','C91.1','C91', TRUE),
        ('C92', 'Myeloid leukaemia',                                                            'II','C91-C95','C92',  NULL,  FALSE),
        ('C92.0','Acute myeloblastic leukaemia',                                                'II','C91-C95','C92.0','C92', TRUE),
        ('C92.1','Chronic myeloid leukaemia, BCR-ABL-positive',                                'II','C91-C95','C92.1','C92', TRUE),
        -- ── Hematology (D50-D89) ──────────────────────────────────────────────
        ('D50', 'Iron deficiency anaemia',                                                      'III','D50-D53','D50', NULL,  FALSE),
        ('D56', 'Thalassaemia',                                                                 'III','D55-D59','D56', NULL,  FALSE),
        ('D57', 'Sickle-cell disorders',                                                        'III','D55-D59','D57', NULL,  FALSE),
        ('D57.0','Haemoglobin-SS disease with crisis',                                         'III','D55-D59','D57.0','D57', TRUE),
        ('D68', 'Other coagulation defects',                                                    'III','D65-D69','D68', NULL,  FALSE),
        ('D69', 'Purpura and other haemorrhagic conditions',                                    'III','D65-D69','D69', NULL,  FALSE),
        -- ── Endocrine / Metabolic (E00-E90) ──────────────────────────────────
        ('E05', 'Thyrotoxicosis (hyperthyroidism)',                                             'IV','E00-E07','E05', NULL,  FALSE),
        ('E10', 'Type 1 diabetes mellitus',                                                     'IV','E10-E14','E10', NULL,  FALSE),
        ('E10.9','Type 1 diabetes mellitus without complications',                              'IV','E10-E14','E10.9','E10', TRUE),
        ('E11', 'Type 2 diabetes mellitus',                                                     'IV','E10-E14','E11', NULL,  FALSE),
        ('E11.9','Type 2 diabetes mellitus without complications',                              'IV','E10-E14','E11.9','E11', TRUE),
        ('E13', 'Other specified diabetes mellitus',                                            'IV','E10-E14','E13', NULL,  FALSE),
        ('E14', 'Unspecified diabetes mellitus',                                                'IV','E10-E14','E14', NULL,  FALSE),
        ('E21', 'Hyperparathyroidism and other disorders of parathyroid gland',                'IV','E20-E35','E21', NULL,  FALSE),
        ('E27', 'Other disorders of adrenal gland',                                             'IV','E20-E35','E27', NULL,  FALSE),
        ('E55', 'Vitamin D deficiency',                                                         'IV','E50-E64','E55', NULL,  FALSE),
        ('E58', 'Dietary calcium deficiency',                                                   'IV','E50-E64','E58', NULL,  FALSE),
        ('E61', 'Deficiency of other nutrient elements',                                        'IV','E50-E64','E61', NULL,  FALSE),
        ('E63', 'Other nutritional deficiencies',                                               'IV','E50-E64','E63', NULL,  FALSE),
        ('E66', 'Obesity',                                                                       'IV','E65-E68','E66', NULL,  FALSE),
        ('E66.0','Obesity due to excess calories',                                              'IV','E65-E68','E66.0','E66', TRUE),
        ('E66.9','Obesity, unspecified',                                                        'IV','E65-E68','E66.9','E66', TRUE),
        ('E78', 'Disorders of lipoprotein metabolism and other lipidaemias',                    'IV','E70-E90','E78', NULL,  FALSE),
        ('E78.0','Pure hypercholesterolaemia',                                                  'IV','E70-E90','E78.0','E78', TRUE),
        ('E78.5','Hyperlipidaemia, unspecified',                                                'IV','E70-E90','E78.5','E78', TRUE),
        ('E79', 'Disorders of purine and pyrimidine metabolism',                                'IV','E70-E90','E79', NULL,  FALSE),
        ('E83', 'Disorders of mineral metabolism',                                              'IV','E70-E90','E83', NULL,  FALSE),
        ('E84', 'Cystic fibrosis',                                                              'IV','E70-E90','E84', NULL,  FALSE),
        -- ── Mental / Behavioural (F00-F99) ────────────────────────────────────
        ('F10', 'Mental and behavioural disorders due to use of alcohol',                       'V','F10-F19','F10', NULL,  FALSE),
        ('F11', 'Mental and behavioural disorders due to use of opioids',                       'V','F10-F19','F11', NULL,  FALSE),
        ('F20', 'Schizophrenia',                                                                'V','F20-F29','F20', NULL,  FALSE),
        ('F20.9','Schizophrenia, unspecified',                                                  'V','F20-F29','F20.9','F20', TRUE),
        ('F25', 'Schizoaffective disorders',                                                    'V','F20-F29','F25', NULL,  FALSE),
        ('F31', 'Bipolar affective disorder',                                                   'V','F30-F39','F31', NULL,  FALSE),
        ('F31.9','Bipolar affective disorder, unspecified',                                     'V','F30-F39','F31.9','F31', TRUE),
        ('F32', 'Depressive episode',                                                           'V','F30-F39','F32', NULL,  FALSE),
        ('F32.9','Depressive episode, unspecified',                                             'V','F30-F39','F32.9','F32', TRUE),
        ('F33', 'Recurrent depressive disorder',                                                'V','F30-F39','F33', NULL,  FALSE),
        ('F40', 'Phobic anxiety disorders',                                                     'V','F40-F48','F40', NULL,  FALSE),
        ('F41', 'Other anxiety disorders',                                                      'V','F40-F48','F41', NULL,  FALSE),
        ('F41.1','Generalised anxiety disorder',                                                'V','F40-F48','F41.1','F41', TRUE),
        ('F42', 'Obsessive-compulsive disorder',                                                'V','F40-F48','F42', NULL,  FALSE),
        ('F43', 'Reaction to severe stress and adjustment disorders',                           'V','F40-F48','F43', NULL,  FALSE),
        ('F43.1','Post-traumatic stress disorder',                                              'V','F40-F48','F43.1','F43', TRUE),
        ('F60', 'Specific personality disorders',                                               'V','F60-F69','F60', NULL,  FALSE),
        ('F70', 'Mild intellectual disability',                                                 'V','F70-F79','F70', NULL,  FALSE),
        ('F90', 'Hyperkinetic disorders',                                                       'V','F90-F98','F90', NULL,  FALSE),
        ('F90.0','Disturbance of activity and attention (ADHD)',                                'V','F90-F98','F90.0','F90', TRUE),
        ('F98', 'Other behavioural and emotional disorders with onset in childhood',            'V','F90-F98','F98', NULL,  FALSE),
        -- ── Nervous system (G00-G99) ──────────────────────────────────────────
        ('G20', 'Parkinson disease',                                                            'VI','G20-G26','G20', NULL,  FALSE),
        ('G21', 'Secondary Parkinsonism',                                                       'VI','G20-G26','G21', NULL,  FALSE),
        ('G30', 'Alzheimer disease',                                                            'VI','G30-G32','G30', NULL,  FALSE),
        ('G30.9','Alzheimer disease, unspecified',                                              'VI','G30-G32','G30.9','G30', TRUE),
        ('G35', 'Multiple sclerosis',                                                           'VI','G35-G37','G35', NULL,  FALSE),
        ('G40', 'Epilepsy',                                                                     'VI','G40-G47','G40', NULL,  FALSE),
        ('G40.9','Epilepsy, unspecified',                                                       'VI','G40-G47','G40.9','G40', TRUE),
        ('G43', 'Migraine',                                                                     'VI','G40-G47','G43', NULL,  FALSE),
        ('G47', 'Sleep disorders',                                                              'VI','G40-G47','G47', NULL,  FALSE),
        ('G54', 'Nerve root and plexus disorders',                                              'VI','G50-G59','G54', NULL,  FALSE),
        ('G60', 'Hereditary and idiopathic neuropathy',                                         'VI','G60-G64','G60', NULL,  FALSE),
        ('G61', 'Inflammatory polyneuropathy',                                                  'VI','G60-G64','G61', NULL,  FALSE),
        ('G71', 'Primary disorders of muscles',                                                 'VI','G70-G73','G71', NULL,  FALSE),
        -- ── Eye / Adnexa (H00-H59) ────────────────────────────────────────────
        ('H25', 'Age-related cataract',                                                         'VII','H25-H28','H25', NULL,  FALSE),
        ('H35', 'Other retinal disorders',                                                      'VII','H30-H36','H35', NULL,  FALSE),
        ('H35.3','Degeneration of macula and posterior pole (AMD)',                             'VII','H30-H36','H35.3','H35', TRUE),
        ('H40', 'Glaucoma',                                                                     'VII','H40-H42','H40', NULL,  FALSE),
        ('H54', 'Visual impairment including blindness',                                        'VII','H53-H54','H54', NULL,  FALSE),
        -- ── Ear (H60-H95) ─────────────────────────────────────────────────────
        -- ── Circulatory system (I00-I99) ──────────────────────────────────────
        ('I10', 'Essential (primary) hypertension',                                             'IX','I10',    'I10', NULL,  FALSE),
        ('I11', 'Hypertensive heart disease',                                                   'IX','I10-I15','I11', NULL,  FALSE),
        ('I20', 'Angina pectoris',                                                              'IX','I20-I25','I20', NULL,  FALSE),
        ('I21', 'Acute myocardial infarction',                                                  'IX','I20-I25','I21', NULL,  FALSE),
        ('I21.9','Acute myocardial infarction, unspecified',                                    'IX','I20-I25','I21.9','I21', TRUE),
        ('I25', 'Chronic ischaemic heart disease',                                              'IX','I20-I25','I25', NULL,  FALSE),
        ('I25.9','Chronic ischaemic heart disease, unspecified',                               'IX','I20-I25','I25.9','I25', TRUE),
        ('I26', 'Pulmonary embolism',                                                           'IX','I26-I28','I26', NULL,  FALSE),
        ('I42', 'Cardiomyopathy',                                                               'IX','I30-I52','I42', NULL,  FALSE),
        ('I48', 'Atrial fibrillation and flutter',                                              'IX','I30-I52','I48', NULL,  FALSE),
        ('I50', 'Heart failure',                                                                'IX','I30-I52','I50', NULL,  FALSE),
        ('I50.9','Heart failure, unspecified',                                                  'IX','I30-I52','I50.9','I50', TRUE),
        ('I63', 'Cerebral infarction',                                                          'IX','I60-I69','I63', NULL,  FALSE),
        ('I64', 'Stroke, not specified as haemorrhage or infarction',                          'IX','I60-I69','I64', NULL,  FALSE),
        ('I65', 'Occlusion and stenosis of precerebral arteries',                              'IX','I60-I69','I65', NULL,  FALSE),
        ('I70', 'Atherosclerosis',                                                              'IX','I70-I79','I70', NULL,  FALSE),
        ('I73', 'Other peripheral vascular diseases',                                           'IX','I70-I79','I73', NULL,  FALSE),
        -- ── Respiratory system (J00-J99) ──────────────────────────────────────
        ('J06', 'Acute upper respiratory infections of multiple and unspecified sites',        'X','J00-J06','J06', NULL,  FALSE),
        ('J12', 'Viral pneumonia, not elsewhere classified',                                    'X','J09-J18','J12', NULL,  FALSE),
        ('J15', 'Unspecified bacterial pneumonia',                                              'X','J09-J18','J15', NULL,  FALSE),
        ('J18', 'Pneumonia, unspecified organism',                                              'X','J09-J18','J18', NULL,  FALSE),
        ('J20', 'Acute bronchitis',                                                             'X','J20-J22','J20', NULL,  FALSE),
        ('J40', 'Bronchitis, not specified as acute or chronic',                               'X','J40-J47','J40', NULL,  FALSE),
        ('J42', 'Unspecified chronic bronchitis',                                               'X','J40-J47','J42', NULL,  FALSE),
        ('J44', 'Other chronic obstructive pulmonary disease',                                  'X','J40-J47','J44', NULL,  FALSE),
        ('J44.1','Chronic obstructive pulmonary disease with acute exacerbation',              'X','J40-J47','J44.1','J44', TRUE),
        ('J44.9','Chronic obstructive pulmonary disease, unspecified',                         'X','J40-J47','J44.9','J44', TRUE),
        ('J45', 'Asthma',                                                                       'X','J40-J47','J45', NULL,  FALSE),
        ('J45.9','Asthma, unspecified',                                                         'X','J40-J47','J45.9','J45', TRUE),
        ('J46', 'Status asthmaticus',                                                           'X','J40-J47','J46', NULL,  FALSE),
        ('J47', 'Bronchiectasis',                                                               'X','J40-J47','J47', NULL,  FALSE),
        ('J70', 'Respiratory conditions due to other external agents',                         'X','J60-J70','J70', NULL,  FALSE),
        ('J84', 'Other interstitial pulmonary diseases',                                        'X','J80-J84','J84', NULL,  FALSE),
        ('J96', 'Respiratory failure, not elsewhere classified',                               'X','J95-J99','J96', NULL,  FALSE),
        -- ── Digestive system (K00-K93) ────────────────────────────────────────
        ('K21', 'Gastro-oesophageal reflux disease',                                           'XI','K20-K31','K21', NULL,  FALSE),
        ('K25', 'Gastric ulcer',                                                                'XI','K25-K28','K25', NULL,  FALSE),
        ('K26', 'Duodenal ulcer',                                                               'XI','K25-K28','K26', NULL,  FALSE),
        ('K50', 'Crohn disease (regional enteritis)',                                           'XI','K50-K52','K50', NULL,  FALSE),
        ('K50.9','Crohn disease, unspecified',                                                  'XI','K50-K52','K50.9','K50', TRUE),
        ('K51', 'Ulcerative colitis',                                                           'XI','K50-K52','K51', NULL,  FALSE),
        ('K51.9','Ulcerative colitis, unspecified',                                             'XI','K50-K52','K51.9','K51', TRUE),
        ('K57', 'Diverticular disease of intestine',                                            'XI','K55-K63','K57', NULL,  FALSE),
        ('K70', 'Alcoholic liver disease',                                                      'XI','K70-K77','K70', NULL,  FALSE),
        ('K74', 'Fibrosis and cirrhosis of liver',                                              'XI','K70-K77','K74', NULL,  FALSE),
        ('K74.6','Other and unspecified cirrhosis of liver',                                   'XI','K70-K77','K74.6','K74', TRUE),
        -- ── Skin (L00-L99) ────────────────────────────────────────────────────
        ('L20', 'Atopic dermatitis',                                                            'XII','L20-L30','L20', NULL,  FALSE),
        ('L20.9','Atopic dermatitis, unspecified',                                              'XII','L20-L30','L20.9','L20', TRUE),
        ('L40', 'Psoriasis',                                                                    'XII','L40-L45','L40', NULL,  FALSE),
        ('L40.0','Psoriasis vulgaris',                                                          'XII','L40-L45','L40.0','L40', TRUE),
        ('L40.5','Arthropathic psoriasis',                                                      'XII','L40-L45','L40.5','L40', TRUE),
        ('L63', 'Alopecia areata',                                                              'XII','L60-L75','L63', NULL,  FALSE),
        ('L93', 'Lupus erythematosus',                                                          'XII','L80-L99','L93', NULL,  FALSE),
        ('L93.0','Discoid lupus erythematosus',                                                 'XII','L80-L99','L93.0','L93', TRUE),
        -- ── Musculoskeletal (M00-M99) ─────────────────────────────────────────
        ('M05', 'Seropositive rheumatoid arthritis',                                            'XIII','M05-M14','M05', NULL,  FALSE),
        ('M05.9','Seropositive rheumatoid arthritis, unspecified',                              'XIII','M05-M14','M05.9','M05', TRUE),
        ('M06', 'Other rheumatoid arthritis',                                                   'XIII','M05-M14','M06', NULL,  FALSE),
        ('M07', 'Psoriatic and enteropathic arthropathies',                                     'XIII','M05-M14','M07', NULL,  FALSE),
        ('M08', 'Juvenile arthritis',                                                           'XIII','M05-M14','M08', NULL,  FALSE),
        ('M10', 'Gout',                                                                          'XIII','M10-M14','M10', NULL,  FALSE),
        ('M10.9','Gout, unspecified',                                                           'XIII','M10-M14','M10.9','M10', TRUE),
        ('M15', 'Polyarthrosis',                                                                'XIII','M15-M19','M15', NULL,  FALSE),
        ('M16', 'Coxarthrosis (arthrosis of hip)',                                              'XIII','M15-M19','M16', NULL,  FALSE),
        ('M17', 'Gonarthrosis (arthrosis of knee)',                                             'XIII','M15-M19','M17', NULL,  FALSE),
        ('M30', 'Polyarteritis nodosa and related conditions',                                  'XIII','M30-M36','M30', NULL,  FALSE),
        ('M45', 'Ankylosing spondylitis',                                                       'XIII','M45-M49','M45', NULL,  FALSE),
        ('M45.9','Ankylosing spondylitis of unspecified sites in spine',                       'XIII','M45-M49','M45.9','M45', TRUE),
        ('M54', 'Dorsalgia (back pain)',                                                        'XIII','M50-M54','M54', NULL,  FALSE),
        ('M54.5','Low back pain',                                                               'XIII','M50-M54','M54.5','M54', TRUE),
        ('M80', 'Osteoporosis with current pathological fracture',                              'XIII','M80-M85','M80', NULL,  FALSE),
        ('M81', 'Osteoporosis without current pathological fracture',                           'XIII','M80-M85','M81', NULL,  FALSE),
        ('M81.0','Postmenopausal osteoporosis',                                                 'XIII','M80-M85','M81.0','M81', TRUE),
        -- ── Genitourinary (N00-N99) ───────────────────────────────────────────
        ('N00', 'Acute nephritic syndrome',                                                     'XIV','N00-N08','N00', NULL,  FALSE),
        ('N03', 'Chronic nephritic syndrome',                                                   'XIV','N00-N08','N03', NULL,  FALSE),
        ('N04', 'Nephrotic syndrome',                                                           'XIV','N00-N08','N04', NULL,  FALSE),
        ('N17', 'Acute kidney failure',                                                         'XIV','N17-N19','N17', NULL,  FALSE),
        ('N18', 'Chronic kidney disease',                                                       'XIV','N17-N19','N18', NULL,  FALSE),
        ('N18.3','Chronic kidney disease, stage 3',                                             'XIV','N17-N19','N18.3','N18', TRUE),
        ('N18.6','End-stage renal disease',                                                     'XIV','N17-N19','N18.6','N18', TRUE),
        ('N18.9','Chronic kidney disease, unspecified',                                         'XIV','N17-N19','N18.9','N18', TRUE),
        ('N20', 'Calculus of kidney and ureter',                                                'XIV','N20-N23','N20', NULL,  FALSE),
        ('N28', 'Other disorders of kidney and ureter',                                         'XIV','N25-N29','N28', NULL,  FALSE),
        ('N39', 'Other disorders of urinary system',                                            'XIV','N30-N39','N39', NULL,  FALSE),
        ('N40', 'Benign prostatic hyperplasia',                                                 'XIV','N40-N51','N40', NULL,  FALSE),
        ('N52', 'Male erectile dysfunction',                                                    'XIV','N40-N51','N52', NULL,  FALSE),
        ('N83', 'Non-inflammatory disorders of ovary, fallopian tube and broad ligament',      'XIV','N80-N98','N83', NULL,  FALSE),
        -- ── Infectious diseases (A00-B99) ─────────────────────────────────────
        ('A00', 'Cholera',                                                                       'I','A00-A09','A00', NULL,  FALSE),
        ('A01', 'Typhoid and paratyphoid fevers',                                               'I','A00-A09','A01', NULL,  FALSE),
        ('A02', 'Other salmonella infections',                                                  'I','A00-A09','A02', NULL,  FALSE),
        ('A09', 'Diarrhoea and gastroenteritis of infectious origin',                          'I','A00-A09','A09', NULL,  FALSE),
        ('A15', 'Respiratory tuberculosis, bacteriologically and histologically confirmed',    'I','A15-A19','A15', NULL,  FALSE),
        ('A30', 'Leprosy (Hansen disease)',                                                     'I','A30-A49','A30', NULL,  FALSE),
        ('A37', 'Whooping cough',                                                               'I','A30-A49','A37', NULL,  FALSE),
        ('A39', 'Meningococcal infection',                                                      'I','A30-A49','A39', NULL,  FALSE),
        ('A40', 'Streptococcal septicaemia',                                                    'I','A40-A41','A40', NULL,  FALSE),
        ('A41', 'Other septicaemia',                                                            'I','A40-A41','A41', NULL,  FALSE),
        ('A80', 'Acute poliomyelitis',                                                          'I','A80-A89','A80', NULL,  FALSE),
        ('A90', 'Dengue fever (classical dengue)',                                              'I','A90-A99','A90', NULL,  FALSE),
        ('B05', 'Measles',                                                                       'I','B05-B09','B05', NULL,  FALSE),
        ('B16', 'Acute hepatitis B',                                                             'I','B15-B19','B16', NULL,  FALSE),
        ('B18', 'Chronic viral hepatitis',                                                      'I','B15-B19','B18', NULL,  FALSE),
        ('B18.2','Chronic viral hepatitis C',                                                   'I','B15-B19','B18.2','B18', TRUE),
        ('B20', 'Human immunodeficiency virus (HIV) disease resulting in infectious and parasitic diseases', 'I','B20-B24','B20', NULL, FALSE),
        ('B24', 'Unspecified human immunodeficiency virus (HIV) disease',                      'I','B20-B24','B24', NULL,  FALSE),
        ('B50', 'Plasmodium falciparum malaria',                                                'I','B50-B64','B50', NULL,  FALSE),
        ('B65', 'Schistosomiasis',                                                              'I','B65-B83','B65', NULL,  FALSE),
        -- ── COVID / Special (U00-U99) ─────────────────────────────────────────
        ('U07', 'COVID-19 (Emergency use code)',                                                'XXII','U00-U85','U07', NULL,  FALSE),
        ('U07.1','COVID-19, virus identified',                                                  'XXII','U00-U85','U07.1','U07', TRUE),
        ('U08', 'Personal history of COVID-19',                                                 'XXII','U00-U85','U08', NULL,  FALSE),
        ('U09', 'Post-COVID-19 condition',                                                      'XXII','U00-U85','U09', NULL,  FALSE)
    ) AS t(icd_code, title, chapter, block_id, category, parent_code, is_leaf)
),

-- ── Pharma-relevant code range lookup ─────────────────────────────────────
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

-- ── Therapeutic area classification ───────────────────────────────────────
classified AS (
    SELECT
        c.icd_code                                                          AS icd10_code,
        c.title                                                             AS icd10_title,
        c.chapter,
        c.block_id,
        c.category,
        c.parent_code,
        c.is_leaf,
        NULL::TEXT[]                                                        AS includes,
        NULL::TEXT[]                                                        AS excludes,
        NULL::TEXT                                                          AS includes_text,
        NULL::TEXT                                                          AS excludes_text,
        'icd10_curated_reference'                                           AS source,
        NOW()                                                               AS source_updated_at,

        CASE
            WHEN c.icd_code ~ '^[AB]'           THEN 'infectious_disease'
            WHEN c.icd_code ~ '^C'              THEN 'oncology'
            WHEN c.icd_code ~ '^D[0-4]'         THEN 'oncology'
            WHEN c.icd_code ~ '^D[5-8]'         THEN 'hematology'
            WHEN c.icd_code ~ '^E[0-8]'         THEN 'endocrinology_metabolic'
            WHEN c.icd_code ~ '^E9'             THEN 'nutrition'
            WHEN c.icd_code ~ '^F'              THEN 'psychiatry_cns'
            WHEN c.icd_code ~ '^G'              THEN 'neurology'
            WHEN c.icd_code ~ '^H[0-5]'         THEN 'ophthalmology'
            WHEN c.icd_code ~ '^H[6-9]'         THEN 'otolaryngology'
            WHEN c.icd_code ~ '^I[0-2]'         THEN 'cardiovascular'
            WHEN c.icd_code ~ '^I[3-5]'         THEN 'cardiovascular'
            WHEN c.icd_code ~ '^I[6-9]'         THEN 'cardiovascular'
            WHEN c.icd_code ~ '^J'              THEN 'respiratory'
            WHEN c.icd_code ~ '^K'              THEN 'gastroenterology'
            WHEN c.icd_code ~ '^L'              THEN 'dermatology'
            WHEN c.icd_code ~ '^M[0-1]'         THEN 'rheumatology'
            WHEN c.icd_code ~ '^M[2-9]'         THEN 'musculoskeletal'
            WHEN c.icd_code ~ '^N'              THEN 'nephrology_urology'
            WHEN c.icd_code ~ '^O'              THEN 'obstetrics_gynecology'
            WHEN c.icd_code ~ '^P'              THEN 'neonatology'
            WHEN c.icd_code ~ '^Q'              THEN 'congenital_disorders'
            WHEN c.icd_code ~ '^R'              THEN 'symptoms_signs'
            WHEN c.icd_code ~ '^[ST]'           THEN 'injury_trauma'
            WHEN c.icd_code ~ '^U'              THEN 'special_purposes'
            WHEN c.icd_code ~ '^[VWX]'          THEN 'external_causes'
            WHEN c.icd_code ~ '^[YZ]'           THEN 'factors_health_status'
            ELSE 'other'
        END                                                                 AS therapeutic_area,

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

        CASE
            WHEN c.icd_code ~ '^[RST]' THEN FALSE
            WHEN c.icd_code ~ '^[VWX]' THEN FALSE
            WHEN c.icd_code ~ '^[YZ]'  THEN FALSE
            ELSE TRUE
        END                                                                 AS is_pharma_relevant,

        REGEXP_REPLACE(
            REGEXP_REPLACE(c.title, '\s*\([^)]*\)', '', 'g'),
            '\s+', ' ', 'g'
        )                                                                   AS indication_name

    FROM code_registry c
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
    g.who_indicators                                                        AS gho_indicator_codes,
    cl.source,
    cl.source_updated_at,
    NOW()                                                                   AS created_at,
    NOW()                                                                   AS updated_at

FROM classified cl
LEFT JOIN gho_crossref g ON g.icd10_code = cl.icd10_code;
