-- DEPRECATED: Entity linking is now handled by SilverTransformation (Python) with
-- IdentifierResolver (5-step: direct lookup → structure → API → fuzzy → create new).
-- This SQL function is a legacy fallback. Do not add new linking logic here.
-- All new linking should go through SilverTransformation.process_*() methods.
CREATE OR REPLACE FUNCTION silver.run_entity_linking()
RETURNS TABLE(step TEXT, result TEXT) AS $$
DECLARE linked_count INT; total_count INT;
BEGIN
  step := 'Build Lookup'; result := 'mol_silver.molecules'; RETURN NEXT;

  step := 'Link Trials';
  SELECT count(*) INTO total_count FROM mol_bronze.clinicaltrials WHERE nct_id IS NOT NULL;
  -- mol_bronze.clinicaltrials has: nct_id, brief_title, official_title, overall_status, phase,
  -- study_type, lead_sponsor_name, lead_sponsor_class, enrollment_count, enrollment_type,
  -- start_date, completion_date, interventions, conditions, locations
  -- Additional columns (acronym, outcomes, results, etc.) come from bronze.clinicaltrials (backfill path)
  INSERT INTO mol_silver.clinical_trials (
    molecule_id, nct_id, title, phase, status, study_type,
    conditions, intervention_names, enrollment_target, start_date, completion_date,
    sponsor, sponsor_type, locations, location_countries
  )
  SELECT DISTINCT ON (b.nct_id) m.molecule_id, b.nct_id,
    COALESCE(b.official_title, b.brief_title),
    b.phase,
    b.overall_status,
    b.study_type,
    CASE WHEN b.conditions IS NOT NULL AND b.conditions::text != 'null'
      THEN ARRAY(SELECT jsonb_array_elements_text(b.conditions))
      ELSE NULL END,
    CASE WHEN b.interventions IS NOT NULL AND b.interventions::text != 'null'
      THEN ARRAY(SELECT DISTINCT jsonb_array_elements(b.interventions) ->> 'name')
      ELSE NULL END,
    b.enrollment_count,
    b.start_date,
    b.completion_date,
    b.lead_sponsor_name,
    b.lead_sponsor_class,
    b.locations,
    CASE WHEN b.locations IS NOT NULL AND b.locations::text != '[]' AND b.locations::text != 'null'
      THEN ARRAY(SELECT DISTINCT elem->>'country' FROM jsonb_array_elements(b.locations) elem WHERE elem->>'country' IS NOT NULL)
      ELSE NULL END
  FROM mol_bronze.clinicaltrials b CROSS JOIN mol_silver.molecules m
  WHERE m.pref_name IS NOT NULL AND b.nct_id IS NOT NULL
    AND (
      -- Match by title (original logic)
      LOWER(COALESCE(b.official_title, b.brief_title, '')) LIKE '%' || LOWER(m.pref_name) || '%'
      -- Match by intervention/drug name in the interventions JSON
      OR (b.interventions IS NOT NULL AND b.interventions::text ILIKE '%' || m.pref_name || '%')
      -- Match by brand name in title or interventions
      OR EXISTS (
        SELECT 1 FROM unnest(m.brand_names) bn
        WHERE LOWER(COALESCE(b.official_title, b.brief_title, '')) LIKE '%' || LOWER(bn) || '%'
        OR (b.interventions IS NOT NULL AND b.interventions::text ILIKE '%' || bn || '%')
      )
      -- Match by brief_summary/description
      OR LOWER(COALESCE(b.brief_summary, '')) LIKE '%' || LOWER(m.pref_name) || '%'
      -- Match by FDA label: NCT IDs mentioned in the drug label are authoritative
      OR b.nct_id IN (
        SELECT DISTINCT (regexp_matches(l.clinical_studies, 'NCT\d{7,8}', 'g'))[1]
        FROM mol_silver.drug_labels l
        WHERE l.molecule_id = m.molecule_id
        AND l.clinical_studies IS NOT NULL
      )
    )
  ON CONFLICT (nct_id) DO UPDATE SET
    molecule_id = EXCLUDED.molecule_id,
    title = COALESCE(EXCLUDED.title, mol_silver.clinical_trials.title),
    conditions = COALESCE(EXCLUDED.conditions, mol_silver.clinical_trials.conditions),
    intervention_names = COALESCE(EXCLUDED.intervention_names, mol_silver.clinical_trials.intervention_names),
    enrollment_target = COALESCE(EXCLUDED.enrollment_target, mol_silver.clinical_trials.enrollment_target),
    locations = COALESCE(EXCLUDED.locations, mol_silver.clinical_trials.locations),
    location_countries = COALESCE(EXCLUDED.location_countries, mol_silver.clinical_trials.location_countries);

  -- Enrich from bronze.clinicaltrials (has more columns: acronym, outcomes, results, etc.)
  UPDATE mol_silver.clinical_trials ct SET
    acronym = COALESCE(bc.acronym, ct.acronym),
    eligibility_criteria = COALESCE(bc.eligibility_criteria, ct.eligibility_criteria),
    primary_outcomes = COALESCE(bc.primary_outcomes, ct.primary_outcomes),
    secondary_outcomes = COALESCE(bc.secondary_outcomes, ct.secondary_outcomes),
    arms = COALESCE(bc.arms_groups, ct.arms),
    allocation = COALESCE(bc.allocation, ct.allocation),
    intervention_model = COALESCE(bc.intervention_model, ct.intervention_model),
    masking = COALESCE(bc.masking, ct.masking),
    has_results = COALESCE(bc.has_results, ct.has_results),
    results_section = COALESCE(bc.results_section, ct.results_section),
    results_outcome_measures = COALESCE(bc.results_outcome_measures, ct.results_outcome_measures),
    results_adverse_events = COALESCE(bc.results_adverse_events, ct.results_adverse_events),
    brief_summary = COALESCE(bc.brief_summary, ct.brief_summary),
    why_stopped = COALESCE(bc.why_stopped, ct.why_stopped),
    fda_regulated_drug = COALESCE(bc.fda_regulated_drug, ct.fda_regulated_drug),
    fda_regulated_device = COALESCE(bc.fda_regulated_device, ct.fda_regulated_device),
    trial_references = COALESCE(bc."references", ct.trial_references),
    ipd_sharing = COALESCE(bc.ipd_sharing, ct.ipd_sharing)
  FROM mol_bronze.clinicaltrials bc
  WHERE bc.nct_id = ct.nct_id;
  GET DIAGNOSTICS linked_count = ROW_COUNT;
  result := '+' || linked_count || '/' || total_count || ' trials'; RETURN NEXT;

  step := 'Link FAERS';
  BEGIN
    INSERT INTO mol_silver.adverse_events (
      source, source_report_id, molecule_id, drug_name_reported,
      reaction_meddra_pt, seriousness, outcome,
      patient_age, patient_sex, report_date, country
    )
    SELECT 'openfda_faers', b.safety_report_id, m.molecule_id, m.pref_name,
      reaction->>'reactionmeddrapt',
      CASE WHEN b.serious = 1 THEN
        CASE WHEN b.serious_death = 1 THEN 'death'
             WHEN b.serious_life_threatening = 1 THEN 'life_threatening'
             WHEN b.serious_hospitalization = 1 THEN 'hospitalization'
             WHEN b.serious_disabling = 1 THEN 'disabling'
             ELSE 'other_serious' END
        ELSE 'non_serious' END,
      reaction->>'reactionoutcome',
      b.patient_age::INTEGER,
      CASE WHEN b.patient_sex = '1' THEN 'M' WHEN b.patient_sex = '2' THEN 'F' ELSE NULL END,
      b.receive_date,
      b.occurrence_country
    FROM mol_bronze.openfda_faers b CROSS JOIN mol_silver.molecules m
    CROSS JOIN LATERAL jsonb_array_elements(b.patient_reaction) AS reaction
    WHERE b.patient_reaction IS NOT NULL AND m.pref_name IS NOT NULL
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' AEs';
  EXCEPTION WHEN OTHERS THEN result := 'FAERS: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link Labels: bronze.openfda_labels → mol_silver.drug_labels
  -- Uses ALL fields from bronze — no column dropping
  step := 'Link Labels';
  BEGIN
    INSERT INTO mol_silver.drug_labels (
      molecule_id, set_id, spl_id, brand_name, generic_name, manufacturer,
      application_number, product_type, route, dosage_forms,
      indications_and_usage, contraindications_and_usage, warnings, boxed_warning,
      adverse_reactions, drug_interactions, mechanism_of_action,
      clinical_studies, dosage_and_administration, how_supplied, product_type,
      overdosage, description, storage_and_handling,
      pregnancy, pediatric_use, geriatric_use, use_in_specific_populations,
      pharmacodynamics, pharmacokinetics, clinical_pharmacology,
      dosage_forms_and_strengths,
      effective_date, effective_time
    )
    SELECT DISTINCT ON (b.set_id)
      m.molecule_id, b.set_id, b.spl_id,
      trim(both '"[]' from b.brand_name::text),
      trim(both '"[]' from b.generic_name::text),
      b.manufacturer_name, b.application_number, 'approved',
      b.route,
      NULL,
      b.indications_and_usage,
      b.contraindications_and_usage,
      COALESCE(b.warnings_and_cautions, b.warnings),
      b.boxed_warning,
      b.adverse_reactions,
      b.drug_interactions,
      b.mechanism_of_action,
      b.clinical_studies,
      b.dosage_and_administration,
      b.how_supplied,
      b.product_type,
      b.overdosage,
      b.description,
      b.storage_and_handling,
      b.pregnancy,
      b.pediatric_use,
      b.geriatric_use,
      b.use_in_specific_populations,
      b.pharmacodynamics,
      b.pharmacokinetics,
      b.clinical_pharmacology,
      b.dosage_forms_and_strengths,
      b.effective_time,
      b.effective_time
    FROM mol_bronze.openfda_labels b
    CROSS JOIN mol_silver.molecules m
    WHERE b.generic_name IS NOT NULL
      AND b.set_id IS NOT NULL
      AND (
        -- Handle both plain text and JSON array ["NAME"] formats
        LOWER(b.generic_name::text) = LOWER(m.pref_name)
        OR LOWER(trim(both '"[]' from b.generic_name::text)) = LOWER(m.pref_name)
        -- Match when bronze generic contains canonical name (handles FDA suffixes like -RMBW, -ADAZ)
        OR LOWER(trim(both '"[]' from b.generic_name::text)) LIKE LOWER(m.pref_name) || '%'
        -- Match by brand name
        OR LOWER(trim(both '"[]' from b.brand_name::text)) = ANY(SELECT LOWER(unnest(m.brand_names)))
      )
    ON CONFLICT (set_id) DO UPDATE SET
      molecule_id = EXCLUDED.molecule_id,
      brand_name = COALESCE(EXCLUDED.brand_name, mol_silver.drug_labels.brand_name),
      manufacturer_name = COALESCE(EXCLUDED.manufacturer_name, mol_silver.drug_labels.manufacturer_name_name),
      indications = COALESCE(EXCLUDED.indications_and_usage, mol_silver.drug_labels.indications_and_usage),
      adverse_reactions = COALESCE(EXCLUDED.adverse_reactions, mol_silver.drug_labels.adverse_reactions),
      mechanism_of_action = COALESCE(EXCLUDED.mechanism_of_action, mol_silver.drug_labels.mechanism_of_action),
      route = COALESCE(EXCLUDED.route, mol_silver.drug_labels.route),
      clinical_studies = COALESCE(EXCLUDED.clinical_studies, mol_silver.drug_labels.clinical_studies),
      dosage_and_administration = COALESCE(EXCLUDED.dosage_and_administration, mol_silver.drug_labels.dosage_and_administration),
      how_supplied = COALESCE(EXCLUDED.how_supplied, mol_silver.drug_labels.how_supplied),
      overdosage = COALESCE(EXCLUDED.overdosage, mol_silver.drug_labels.overdosage),
      pregnancy = COALESCE(EXCLUDED.pregnancy, mol_silver.drug_labels.pregnancy),
      pediatric_use = COALESCE(EXCLUDED.pediatric_use, mol_silver.drug_labels.pediatric_use),
      geriatric_use = COALESCE(EXCLUDED.geriatric_use, mol_silver.drug_labels.geriatric_use),
      use_in_specific_populations = COALESCE(EXCLUDED.use_in_specific_populations, mol_silver.drug_labels.use_in_specific_populations),
      pharmacodynamics = COALESCE(EXCLUDED.pharmacodynamics, mol_silver.drug_labels.pharmacodynamics),
      pharmacokinetics = COALESCE(EXCLUDED.pharmacokinetics, mol_silver.drug_labels.pharmacokinetics),
      clinical_pharmacology = COALESCE(EXCLUDED.clinical_pharmacology, mol_silver.drug_labels.clinical_pharmacology),
      effective_time = COALESCE(EXCLUDED.effective_time, mol_silver.drug_labels.effective_time);
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' labels';
  EXCEPTION WHEN OTHERS THEN result := 'Labels: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link DrugBank Targets: bronze.drugbank_targets → mol_silver.targets
  step := 'Link DrugBank Targets';
  BEGIN
    INSERT INTO mol_silver.targets (
      molecule_id, molecule_name, protein_name, target_type, action_type,
      gene_names, primaryaccession, source
    )
    SELECT m.molecule_id, m.pref_name,
      t.protein_name, 'protein', array_to_string(t.actions, ', '),
      t.gene_name, t.uniprot_id, 'drugbank'
    FROM mol_bronze.drugbank_targets t
    JOIN mol_bronze.drugbank_data d ON t.drugbank_id = d.drugbank_id
    JOIN mol_silver.molecules m ON LOWER(d.drug_name) = LOWER(m.pref_name)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' targets';
  EXCEPTION WHEN OTHERS THEN result := 'DrugBank: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link Financial Filings: silver.financial_filings molecule_id via brand name
  step := 'Link Financial Filings';
  BEGIN
    UPDATE mol_silver.financial_filings f
    SET molecule_id = m.molecule_id
    FROM mol_silver.molecules m
    WHERE f.molecule_id IS NULL
      AND (
        LOWER(f.product_name) = LOWER(m.pref_name)
        OR LOWER(f.product_name) = ANY(SELECT LOWER(unnest(m.brand_names)))
      );
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' financial filings';
  EXCEPTION WHEN OTHERS THEN result := 'Financial: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link UniProt protein targets → mol_silver.protein_targets
  -- Sources: (1) mol_silver.targets has primaryaccession from DrugBank/ChEMBL,
  --          (2) bronze.uniprot has full protein records from UniProt API
  step := 'Link UniProt Targets';
  BEGIN
    -- Method 1: From existing mol_silver.targets (DrugBank-sourced)
    INSERT INTO mol_silver.protein_targets (
      molecule_id, primaryaccession, protein_name, gene_name, source
    )
    SELECT DISTINCT m.molecule_id, t.primaryaccession, t.protein_name, t.gene_names, 'uniprot'
    FROM mol_silver.targets t
    JOIN mol_silver.molecules m ON t.molecule_id = m.molecule_id
    WHERE t.primaryaccession IS NOT NULL
    ON CONFLICT (molecule_id, primaryaccession) DO NOTHING;

    -- Method 2: Enrich with bronze.uniprot data (function, subcellular location)
    UPDATE mol_silver.protein_targets pt SET
      protein_function = COALESCE(bu.function_description::TEXT, pt.protein_function),
      subcellular_location = COALESCE(bu.subcellular_location::TEXT, pt.subcellular_location)
    FROM mol_bronze.uniprot bu
    WHERE bu.accession = pt.primaryaccession
      AND pt.protein_function IS NULL;

    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' protein targets';
  EXCEPTION WHEN OTHERS THEN result := 'UniProt: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link FDA Drugs@FDA approvals → mol_silver.regulatory_timeline
  step := 'Link FDA Approvals';
  BEGIN
    INSERT INTO mol_silver.regulatory_timeline (
      molecule_id, milestone_type, event_name, event_date, event_date_precision,
      region, review_priority, source, source_detail, confidence
    )
    SELECT m.molecule_id,
      CASE WHEN fa.submission_type = 'ORIG' THEN 'approval'
           WHEN fa.submission_class_description ILIKE '%efficacy%' THEN 'approval'
           ELSE 'submission' END,
      CASE WHEN fa.submission_type = 'ORIG' THEN 'Original BLA Approval (NME)'
           ELSE 'sBLA ' || fa.submission_number || ' — ' || COALESCE(fa.submission_class_description, 'Supplement')
           END,
      fa.submission_status_date, 'exact', 'US (FDA)',
      fa.review_priority, 'fda_drugsfda',
      fa.application_number || ' ' || fa.submission_type || ' ' || fa.submission_number,
      1.0
    FROM mol_bronze.fda_drugsfda fa
    JOIN mol_silver.molecules m ON (
      LOWER(fa.generic_name) = LOWER(m.pref_name)
      OR LOWER(fa.generic_name) LIKE LOWER(m.pref_name) || '%'
      OR LOWER(fa.brand_name) = ANY(SELECT LOWER(unnest(m.brand_names)))
    )
    WHERE fa.submission_status = 'AP'
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' FDA milestones';
  EXCEPTION WHEN OTHERS THEN result := 'FDA Approvals: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link NICE HTA decisions → mol_silver.hta_decisions
  step := 'Link NICE HTA';
  BEGIN
    INSERT INTO mol_silver.hta_decisions (
      molecule_id, agency, guidance_id, title, indication, decision, decision_date, icer_value, source, url
    )
    SELECT m.molecule_id, n.guidance_type, n.guidance_id, n.title, n.indication,
           n.decision, n.decision_date, n.icer_value, 'nice', n.url
    FROM mol_bronze.nice_hta n
    JOIN mol_silver.molecules m ON LOWER(n.drug_name) = LOWER(m.pref_name)
    WHERE n.guidance_id IS NOT NULL
    ON CONFLICT (molecule_id, agency, guidance_id) DO UPDATE SET
      indication = COALESCE(EXCLUDED.indication, mol_silver.hta_decisions.indication),
      decision = COALESCE(EXCLUDED.decision, mol_silver.hta_decisions.decision),
      decision_date = COALESCE(EXCLUDED.decision_date, mol_silver.hta_decisions.decision_date),
      icer_value = COALESCE(EXCLUDED.icer_value, mol_silver.hta_decisions.icer_value);
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' HTA decisions';
  EXCEPTION WHEN OTHERS THEN result := 'NICE HTA: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link Reactome pathways → mol_silver.pathways
  -- Strategy: link ALL bronze.reactome pathways to molecules that have matching protein targets.
  -- Two-pronged: (1) direct UniProt cross-ref match, (2) pathway name contains target gene name.
  step := 'Link Reactome Pathways';
  BEGIN
    INSERT INTO mol_silver.pathways (
      molecule_id, pathway_source, pathway_external_id, pathway_name, target_gene, source
    )
    -- Method 1: Direct match via UniProt reactome_ids cross-references
    SELECT DISTINCT t.molecule_id, 'reactome', r.stable_id, r.pathway_name, t.gene_name, 'reactome'
    FROM mol_bronze.reactome r
    JOIN mol_silver.protein_targets t ON t.reactome_ids IS NOT NULL AND r.stable_id = ANY(t.reactome_ids)
    UNION
    -- Method 2: Pathway name mentions the target gene (e.g. "PD-L1", "CD274", "PDCD1")
    SELECT DISTINCT t.molecule_id, 'reactome', r.stable_id, r.pathway_name, t.gene_name, 'reactome'
    FROM mol_bronze.reactome r
    JOIN mol_silver.protein_targets t ON (
      r.pathway_name ILIKE '%' || t.gene_name || '%'
      OR r.pathway_name ILIKE '%PD-L1%' AND t.gene_name = 'CD274'
      OR r.pathway_name ILIKE '%PD-1%' AND t.gene_name = 'PDCD1'
      OR r.pathway_name ILIKE '%immune checkpoint%'
    )
    WHERE t.molecule_id IS NOT NULL
    UNION
    -- Method 3: All pathways fetched for this molecule (searched by drug target)
    -- Link all bronze.reactome entries to any molecule that has a protein_target
    SELECT DISTINCT t.molecule_id, 'reactome', r.stable_id, r.pathway_name, NULL, 'reactome'
    FROM mol_bronze.reactome r
    CROSS JOIN (SELECT DISTINCT molecule_id FROM mol_silver.protein_targets) t
    WHERE r.pathway_name ILIKE '%immun%' OR r.pathway_name ILIKE '%checkpoint%' OR r.pathway_name ILIKE '%PD-%'
    ON CONFLICT (molecule_id, pathway_source, pathway_external_id) DO NOTHING;
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' pathways';
  EXCEPTION WHEN OTHERS THEN result := 'Reactome: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link KEGG pathways → mol_silver.pathways
  -- Links by drug_name match to molecule canonical_name or brand_names
  step := 'Link KEGG Pathways';
  BEGIN
    INSERT INTO mol_silver.pathways (
      molecule_id, pathway_source, pathway_external_id, pathway_name, source
    )
    SELECT m.molecule_id, 'kegg', kp.key, kp.value, 'kegg'
    FROM mol_bronze.kegg_drugs k
    CROSS JOIN LATERAL jsonb_each_text(k.pathways) AS kp
    JOIN mol_silver.molecules m ON (
      LOWER(k.drug_name) = LOWER(m.pref_name)
      OR LOWER(k.drug_name) = ANY(SELECT LOWER(unnest(m.brand_names)))
    )
    ON CONFLICT (molecule_id, pathway_source, pathway_external_id) DO NOTHING;
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' KEGG pathways';
  EXCEPTION WHEN OTHERS THEN result := 'KEGG: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link NIH grants → mol_silver.research_grants
  step := 'Link NIH Grants';
  BEGIN
    INSERT INTO mol_silver.research_grants (
      molecule_id, project_number, project_title, pi_name, pi_institution,
      award_amount, fiscal_year, source
    )
    SELECT m.molecule_id, g.project_number, g.project_title, g.pi_name,
      g.pi_institution, g.award_amount, g.fiscal_year, 'nih_reporter'
    FROM mol_bronze.nih_grants g
    JOIN mol_silver.molecules m ON (
      LOWER(g.project_title) LIKE '%' || LOWER(m.pref_name) || '%'
      OR LOWER(g.terms) LIKE '%' || LOWER(m.pref_name) || '%'
    )
    ON CONFLICT (molecule_id, project_number, fiscal_year) DO NOTHING;
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' NIH grants';
  EXCEPTION WHEN OTHERS THEN result := 'NIH Grants: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link CMS Medicare spending → mol_silver.drug_spending
  step := 'Link Medicare Spending';
  BEGIN
    INSERT INTO mol_silver.drug_spending (
      molecule_id, brand_name, generic_name, program, year,
      total_claims, total_beneficiaries, total_spending, avg_cost_per_claim, source
    )
    SELECT m.molecule_id, s.brand_name, s.generic_name, s.program, s.year,
      s.total_claims, s.total_beneficiaries, s.total_spending, s.avg_cost_per_claim, 'cms_medicare'
    FROM mol_bronze.cms_medicare_spending s
    JOIN mol_silver.molecules m ON (
      LOWER(s.brand_name) = ANY(SELECT LOWER(unnest(m.brand_names)))
      OR LOWER(s.generic_name) = LOWER(m.pref_name)
    )
    ON CONFLICT (molecule_id, program, year) DO NOTHING;
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' Medicare spending records';
  EXCEPTION WHEN OTHERS THEN result := 'Medicare: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link CMS Open Payments → mol_silver.physician_payments
  -- Links by manufacturer name matching the molecule's label manufacturer
  step := 'Link Open Payments';
  BEGIN
    INSERT INTO mol_silver.physician_payments (
      molecule_id, physician_npi, physician_name, physician_specialty,
      manufacturer_name, payment_amount, payment_nature, payment_year, source
    )
    SELECT DISTINCT m.molecule_id, p.physician_npi,
      COALESCE(p.physician_first_name || ' ' || p.physician_last_name, 'Unknown'),
      p.physician_specialty, p.manufacturer_name,
      p.payment_amount, p.payment_nature, p.payment_year, 'cms_open_payments'
    FROM mol_bronze.cms_open_payments p
    CROSS JOIN mol_silver.molecules m
    JOIN mol_silver.drug_labels dl ON dl.molecule_id = m.molecule_id
    WHERE LOWER(p.manufacturer_name) LIKE '%' || LOWER(SPLIT_PART(dl.manufacturer_name, ' ', 1)) || '%'
      AND p.payment_amount >= 1000
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' physician payments';
  EXCEPTION WHEN OTHERS THEN result := 'Open Payments: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link NPI Registry → mol_silver.physician_profiles
  -- Copies provider records from bronze (not molecule-specific, reference table)
  step := 'Link NPI Profiles';
  BEGIN
    INSERT INTO mol_silver.physician_profiles (
      npi, first_name, last_name, credential, primary_specialty,
      practice_state, practice_city, source
    )
    SELECT n.npi, n.first_name, n.last_name, n.credential,
      n.primary_taxonomy_desc, n.practice_address_state, n.practice_address_city, 'npi_registry'
    FROM mol_bronze.npi_registry n
    ON CONFLICT (npi) DO NOTHING;
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' physician profiles';
  EXCEPTION WHEN OTHERS THEN result := 'NPI: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link Orange Book Patents & Exclusivities → mol_silver.patent_exclusivities
  step := 'Link Orange Book Patents';
  BEGIN
    INSERT INTO mol_silver.patent_exclusivities (
      molecule_id, patent_number, patent_expiry_date, patent_type,
      exclusivity_code, exclusivity_date, application_number, trade_name
    )
    SELECT DISTINCT ON (m.molecule_id, ob.patent_number)
      m.molecule_id,
      ob.patent_number,
      ob.patent_expiration,
      CASE
        WHEN ob.drug_substance_patent = true THEN 'drug_substance'
        WHEN ob.drug_product_patent = true THEN 'drug_product'
        WHEN ob.patent_use_code IS NOT NULL AND ob.patent_use_code != '' THEN 'method_of_use'
        ELSE 'unknown'
      END,
      ob.exclusivity_code,
      ob.exclusivity_date,
      ob.application_number,
      ob.trade_name
    FROM mol_bronze.orange_book ob
    JOIN mol_silver.molecules m ON LOWER(ob.ingredient) = LOWER(m.pref_name)
    WHERE ob.patent_number IS NOT NULL
      AND ob.patent_number != ''
    ON CONFLICT (molecule_id, patent_number) DO UPDATE SET
      patent_expiry_date = COALESCE(EXCLUDED.patent_expiry_date, mol_silver.patent_exclusivities.patent_expiry_date),
      patent_type = COALESCE(EXCLUDED.patent_type, mol_silver.patent_exclusivities.patent_type),
      exclusivity_code = COALESCE(EXCLUDED.exclusivity_code, mol_silver.patent_exclusivities.exclusivity_code),
      exclusivity_date = COALESCE(EXCLUDED.exclusivity_date, mol_silver.patent_exclusivities.exclusivity_date),
      trade_name = COALESCE(EXCLUDED.trade_name, mol_silver.patent_exclusivities.trade_name);
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' patent exclusivities';
  EXCEPTION WHEN OTHERS THEN result := 'Orange Book: ' || SQLERRM; END;
  RETURN NEXT;

  step := 'Refresh Gold';
  BEGIN
    -- Safety signals aggregation
    INSERT INTO mol_gold.safety_signals (molecule_id, reaction_meddra_pt, case_count, signal_strength)
    SELECT ae.molecule_id, ae.reaction_meddra_pt, count(*),
      CASE WHEN count(*) > 100 THEN 'strong' WHEN count(*) > 20 THEN 'moderate' ELSE 'weak' END
    FROM mol_silver.adverse_events ae WHERE ae.reaction_meddra_pt IS NOT NULL
    GROUP BY ae.molecule_id, ae.reaction_meddra_pt HAVING count(*) > 1
    ON CONFLICT DO NOTHING;

    -- Ensure molecule_profile entries exist for all molecules (INSERT missing ones)
    INSERT INTO mol_gold.molecule_profile (molecule_id, inchi_key, canonical_name)
    SELECT m.molecule_id, m.inchi_key, m.pref_name
    FROM mol_silver.molecules m
    WHERE NOT EXISTS (SELECT 1 FROM mol_gold.molecule_profile mp WHERE mp.molecule_id = m.molecule_id)
    ON CONFLICT (molecule_id) DO NOTHING;

    -- Molecule profiles — aggregate ALL silver counts
    UPDATE mol_gold.molecule_profile mp SET
      trial_count = (SELECT count(*) FROM mol_silver.clinical_trials ct WHERE ct.molecule_id = mp.molecule_id),
      active_trial_count = (SELECT count(*) FROM mol_silver.clinical_trials ct WHERE ct.molecule_id = mp.molecule_id AND ct.status IN ('RECRUITING','ACTIVE_NOT_RECRUITING','NOT_YET_RECRUITING')),
      label_count = (SELECT count(*) FROM mol_silver.drug_labels dl WHERE dl.molecule_id = mp.molecule_id),
      adverse_event_count = (SELECT count(*) FROM mol_silver.adverse_events ae WHERE ae.molecule_id = mp.molecule_id),
      serious_ae_count = (SELECT count(*) FROM mol_silver.adverse_events ae WHERE ae.molecule_id = mp.molecule_id AND ae.seriousness IS NOT NULL AND ae.seriousness != 'non_serious'),
      publication_count = (SELECT count(*) FROM mol_silver.molecule_publications pub WHERE pub.molecule_id = mp.molecule_id),
      indication_count = (SELECT count(DISTINCT rm.indication) FROM mol_silver.regulatory_timeline rm WHERE rm.molecule_id = mp.molecule_id AND rm.milestone_type = 'approval' AND rm.indication IS NOT NULL),
      first_effective_time = (SELECT MIN(rm.event_date) FROM mol_silver.regulatory_timeline rm WHERE rm.molecule_id = mp.molecule_id AND rm.milestone_type = 'approval' AND rm.source = 'fda_drugsfda'),
      last_updated = now();

    -- Regulatory summary
    INSERT INTO mol_gold.regulatory_timeline (molecule_id, first_effective_time, latest_effective_time, total_approvals, total_indications_and_usage, priority_review_count, pipeline_milestone_count, next_pipeline_date, next_pipeline_event)
    SELECT m.molecule_id,
      MIN(rm.event_date) FILTER (WHERE rm.milestone_type = 'approval'),
      MAX(rm.event_date) FILTER (WHERE rm.milestone_type = 'approval'),
      count(*) FILTER (WHERE rm.milestone_type = 'approval'),
      count(DISTINCT rm.indication) FILTER (WHERE rm.milestone_type = 'approval' AND rm.indication IS NOT NULL),
      count(*) FILTER (WHERE rm.review_priority = 'PRIORITY'),
      count(*) FILTER (WHERE rm.milestone_type = 'pipeline'),
      MIN(rm.event_date) FILTER (WHERE rm.milestone_type = 'pipeline' AND rm.event_date > CURRENT_DATE),
      (SELECT rm2.event_name FROM mol_silver.regulatory_timeline rm2 WHERE rm2.molecule_id = m.molecule_id AND rm2.milestone_type = 'pipeline' AND rm2.event_date > CURRENT_DATE ORDER BY rm2.event_date LIMIT 1)
    FROM mol_silver.molecules m
    LEFT JOIN mol_silver.regulatory_timeline rm ON rm.molecule_id = m.molecule_id
    GROUP BY m.molecule_id
    ON CONFLICT (molecule_id) DO UPDATE SET
      first_effective_time = EXCLUDED.first_effective_time,
      latest_effective_time = EXCLUDED.latest_effective_time,
      total_approvals = EXCLUDED.total_approvals,
      total_indications = EXCLUDED.total_indications_and_usage,
      priority_review_count = EXCLUDED.priority_review_count,
      pipeline_milestone_count = EXCLUDED.pipeline_milestone_count,
      next_pipeline_date = EXCLUDED.next_pipeline_date,
      next_pipeline_event = EXCLUDED.next_pipeline_event,
      last_updated = now();

    -- Target summary
    INSERT INTO mol_gold.target_summary_deprecated (molecule_id, target_count, primary_target_gene, primary_protein_name, primary_target_uniprot, pdb_structure_count, pathway_count, reactome_pathway_count, kegg_pathway_count)
    SELECT m.molecule_id,
      (SELECT count(*) FROM mol_silver.protein_targets pt WHERE pt.molecule_id = m.molecule_id),
      (SELECT pt.gene_name FROM mol_silver.protein_targets pt WHERE pt.molecule_id = m.molecule_id LIMIT 1),
      (SELECT pt.protein_name FROM mol_silver.protein_targets pt WHERE pt.molecule_id = m.molecule_id LIMIT 1),
      (SELECT pt.primaryaccession FROM mol_silver.protein_targets pt WHERE pt.molecule_id = m.molecule_id LIMIT 1),
      (SELECT COALESCE(SUM(array_length(pt.pdb_ids, 1)), 0) FROM mol_silver.protein_targets pt WHERE pt.molecule_id = m.molecule_id),
      (SELECT count(*) FROM mol_silver.pathways pw WHERE pw.molecule_id = m.molecule_id),
      (SELECT count(*) FROM mol_silver.pathways pw WHERE pw.molecule_id = m.molecule_id AND pw.pathway_source = 'reactome'),
      (SELECT count(*) FROM mol_silver.pathways pw WHERE pw.molecule_id = m.molecule_id AND pw.pathway_source = 'kegg')
    FROM mol_silver.molecules m
    ON CONFLICT (molecule_id) DO UPDATE SET
      target_count = EXCLUDED.target_count,
      primary_target_gene = EXCLUDED.primary_target_gene,
      primary_protein_name = EXCLUDED.primary_protein_name,
      primary_target_uniprot = EXCLUDED.primary_target_uniprot,
      pdb_structure_count = EXCLUDED.pdb_structure_count,
      pathway_count = EXCLUDED.pathway_count,
      reactome_pathway_count = EXCLUDED.reactome_pathway_count,
      kegg_pathway_count = EXCLUDED.kegg_pathway_count,
      last_updated = now();

    -- Market summary
    INSERT INTO mol_gold.market_summary (molecule_id, latest_annual_revenue, revenue_year, revenue_growth_pct, medicare_spending, medicare_beneficiaries, medicare_year, hta_decision_count, hta_favorable_count)
    SELECT m.molecule_id,
      (SELECT ff.revenue FROM mol_silver.financial_filings ff WHERE ff.molecule_id = m.molecule_id ORDER BY ff.period DESC LIMIT 1),
      (SELECT CASE WHEN ff.period LIKE 'annual_%' THEN SUBSTRING(ff.period FROM 'annual_(\d+)')::INTEGER ELSE NULL END FROM mol_silver.financial_filings ff WHERE ff.molecule_id = m.molecule_id ORDER BY ff.period DESC LIMIT 1),
      (SELECT CASE WHEN ff2.revenue > 0 THEN ((ff1.revenue - ff2.revenue) / ff2.revenue * 100)::NUMERIC(5,2) ELSE NULL END
       FROM mol_silver.financial_filings ff1
       JOIN mol_silver.financial_filings ff2 ON ff1.molecule_id = ff2.molecule_id AND ff1.period > ff2.period
       WHERE ff1.molecule_id = m.molecule_id ORDER BY ff1.period DESC LIMIT 1),
      (SELECT ds.total_spending FROM mol_silver.drug_spending ds WHERE ds.molecule_id = m.molecule_id ORDER BY ds.year DESC LIMIT 1),
      (SELECT ds.total_beneficiaries FROM mol_silver.drug_spending ds WHERE ds.molecule_id = m.molecule_id ORDER BY ds.year DESC LIMIT 1),
      (SELECT ds.year FROM mol_silver.drug_spending ds WHERE ds.molecule_id = m.molecule_id ORDER BY ds.year DESC LIMIT 1),
      (SELECT count(*) FROM mol_silver.hta_decisions hta WHERE hta.molecule_id = m.molecule_id),
      (SELECT count(*) FROM mol_silver.hta_decisions hta WHERE hta.molecule_id = m.molecule_id AND hta.decision IN ('Recommended', 'Approved', 'Positive'))
    FROM mol_silver.molecules m
    ON CONFLICT (molecule_id) DO UPDATE SET
      latest_annual_revenue = EXCLUDED.latest_annual_revenue,
      revenue_year = EXCLUDED.revenue_year,
      revenue_growth_pct = EXCLUDED.revenue_growth_pct,
      medicare_spending = EXCLUDED.medicare_spending,
      medicare_beneficiaries = EXCLUDED.medicare_beneficiaries,
      medicare_year = EXCLUDED.medicare_year,
      hta_decision_count = EXCLUDED.hta_decision_count,
      hta_favorable_count = EXCLUDED.hta_favorable_count,
      last_updated = now();

    -- KOL summary (top physicians by total payments)
    INSERT INTO mol_gold.kol_summary (molecule_id, physician_name, physician_npi, specialty, total_payments, payment_count, sources)
    SELECT pp.molecule_id, pp.physician_name, pp.physician_npi, pp.physician_specialty,
      SUM(pp.payment_amount), count(*),
      ARRAY_AGG(DISTINCT pp.source)
    FROM mol_silver.physician_payments pp
    WHERE pp.payment_amount >= 500
    GROUP BY pp.molecule_id, pp.physician_name, pp.physician_npi, pp.physician_specialty
    ON CONFLICT (molecule_id, physician_npi) DO UPDATE SET
      total_payments = EXCLUDED.total_payments,
      payment_count = EXCLUDED.payment_count,
      last_updated = now();

    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := 'Gold refreshed (' || linked_count || ' records)';
  EXCEPTION WHEN OTHERS THEN result := 'Gold: ' || SQLERRM; END;
  RETURN NEXT;
  RETURN;
END; $$ LANGUAGE plpgsql;
