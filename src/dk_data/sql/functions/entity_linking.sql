CREATE OR REPLACE FUNCTION silver.run_entity_linking()
RETURNS TABLE(step TEXT, result TEXT) AS $$
DECLARE linked_count INT; total_count INT;
BEGIN
  step := 'Build Lookup'; result := 'mol_silver.molecules'; RETURN NEXT;

  step := 'Link Trials';
  SELECT count(*) INTO total_count FROM bronze.clinicaltrials WHERE nct_id IS NOT NULL;
  INSERT INTO mol_silver.clinical_trials (
    molecule_id, nct_id, title, brief_summary, detailed_description,
    phase, status, study_type,
    conditions, intervention_names, enrollment_target, start_date, completion_date,
    sponsor, sponsor_type, acronym, eligibility_criteria,
    allocation, intervention_model, masking,
    locations, location_countries, primary_outcomes, secondary_outcomes, other_outcomes, arms,
    has_results, results_section, results_outcome_measures, results_adverse_events,
    fda_regulated_drug, fda_regulated_device, trial_references, ipd_sharing
  )
  SELECT DISTINCT ON (b.nct_id) m.molecule_id, b.nct_id,
    COALESCE(b.official_title, b.brief_title),
    b.brief_summary,
    b.detailed_description,
    b.phases::text,
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
    b.acronym,
    b.eligibility_criteria,
    b.allocation,
    b.intervention_model,
    b.masking,
    b.locations,
    CASE WHEN b.locations IS NOT NULL AND b.locations::text != '[]' AND b.locations::text != 'null'
      THEN ARRAY(SELECT DISTINCT elem->>'country' FROM jsonb_array_elements(b.locations) elem WHERE elem->>'country' IS NOT NULL)
      ELSE NULL END,
    b.primary_outcomes,
    b.secondary_outcomes,
    b.secondary_outcomes, -- other_outcomes: use bronze column when available
    b.arms_groups,
    COALESCE(b.has_results, FALSE),
    b.results_section,
    b.results_section->'outcomeMeasuresModule'->'outcomeMeasures',
    b.results_section->'adverseEventsModule',
    b.fda_regulated_drug,
    b.fda_regulated_device,
    b.references,
    b.ipd_sharing
  FROM bronze.clinicaltrials b CROSS JOIN mol_silver.molecules m
  WHERE m.canonical_name IS NOT NULL AND b.nct_id IS NOT NULL
    AND LOWER(COALESCE(b.official_title, b.brief_title, '')) LIKE '%' || LOWER(m.canonical_name) || '%'
  ON CONFLICT (nct_id) DO UPDATE SET
    molecule_id = EXCLUDED.molecule_id,
    title = COALESCE(EXCLUDED.title, mol_silver.clinical_trials.title),
    brief_summary = COALESCE(EXCLUDED.brief_summary, mol_silver.clinical_trials.brief_summary),
    detailed_description = COALESCE(EXCLUDED.detailed_description, mol_silver.clinical_trials.detailed_description),
    conditions = COALESCE(EXCLUDED.conditions, mol_silver.clinical_trials.conditions),
    intervention_names = COALESCE(EXCLUDED.intervention_names, mol_silver.clinical_trials.intervention_names),
    enrollment_target = COALESCE(EXCLUDED.enrollment_target, mol_silver.clinical_trials.enrollment_target),
    allocation = COALESCE(EXCLUDED.allocation, mol_silver.clinical_trials.allocation),
    intervention_model = COALESCE(EXCLUDED.intervention_model, mol_silver.clinical_trials.intervention_model),
    masking = COALESCE(EXCLUDED.masking, mol_silver.clinical_trials.masking),
    locations = COALESCE(EXCLUDED.locations, mol_silver.clinical_trials.locations),
    location_countries = COALESCE(EXCLUDED.location_countries, mol_silver.clinical_trials.location_countries),
    primary_outcomes = COALESCE(EXCLUDED.primary_outcomes, mol_silver.clinical_trials.primary_outcomes),
    secondary_outcomes = COALESCE(EXCLUDED.secondary_outcomes, mol_silver.clinical_trials.secondary_outcomes),
    arms = COALESCE(EXCLUDED.arms, mol_silver.clinical_trials.arms),
    has_results = COALESCE(EXCLUDED.has_results, mol_silver.clinical_trials.has_results),
    results_section = COALESCE(EXCLUDED.results_section, mol_silver.clinical_trials.results_section),
    results_outcome_measures = COALESCE(EXCLUDED.results_outcome_measures, mol_silver.clinical_trials.results_outcome_measures),
    results_adverse_events = COALESCE(EXCLUDED.results_adverse_events, mol_silver.clinical_trials.results_adverse_events),
    fda_regulated_drug = COALESCE(EXCLUDED.fda_regulated_drug, mol_silver.clinical_trials.fda_regulated_drug),
    trial_references = COALESCE(EXCLUDED.trial_references, mol_silver.clinical_trials.trial_references);
  GET DIAGNOSTICS linked_count = ROW_COUNT;
  result := '+' || linked_count || '/' || total_count || ' trials'; RETURN NEXT;

  step := 'Link FAERS';
  BEGIN
    INSERT INTO mol_silver.adverse_events (
      source, source_report_id, molecule_id, drug_name_reported,
      reaction_meddra_pt, seriousness, outcome,
      patient_age, patient_sex, report_date, country
    )
    SELECT 'openfda_faers', b.safety_report_id, m.molecule_id, m.canonical_name,
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
    FROM bronze.openfda_faers b CROSS JOIN mol_silver.molecules m
    CROSS JOIN LATERAL jsonb_array_elements(b.patient_reaction) AS reaction
    WHERE b.patient_reaction IS NOT NULL AND m.canonical_name IS NOT NULL
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
      application_number, marketing_status, route_of_administration, dosage_forms,
      indications, contraindications, warnings, boxed_warning,
      adverse_reactions, drug_interactions, mechanism_of_action,
      clinical_studies, dosage_and_administration, how_supplied, product_type,
      overdosage, description, storage_and_handling,
      pregnancy, pediatric_use, geriatric_use, use_in_specific_populations,
      pharmacodynamics, pharmacokinetics, clinical_pharmacology,
      dosage_forms_and_strengths,
      effective_date, approval_date
    )
    SELECT DISTINCT ON (b.set_id)
      m.molecule_id, b.set_id, b.spl_id,
      trim(both '"[]' from b.brand_name::text),
      trim(both '"[]' from b.generic_name::text),
      b.manufacturer_name, b.application_number, 'approved',
      CASE WHEN b.route IS NOT NULL AND b.route::text != 'null'
        THEN ARRAY(SELECT jsonb_array_elements_text(b.route))
        ELSE NULL END,
      NULL,
      b.indications_and_usage,
      b.contraindications,
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
    FROM bronze.openfda_labels b
    CROSS JOIN mol_silver.molecules m
    WHERE b.generic_name IS NOT NULL
      AND b.set_id IS NOT NULL
      AND (
        -- Handle both plain text and JSON array ["NAME"] formats
        LOWER(b.generic_name::text) = LOWER(m.canonical_name)
        OR LOWER(trim(both '"[]' from b.generic_name::text)) = LOWER(m.canonical_name)
      )
    ON CONFLICT (set_id) DO UPDATE SET
      molecule_id = EXCLUDED.molecule_id,
      brand_name = COALESCE(EXCLUDED.brand_name, mol_silver.drug_labels.brand_name),
      manufacturer = COALESCE(EXCLUDED.manufacturer, mol_silver.drug_labels.manufacturer),
      indications = COALESCE(EXCLUDED.indications, mol_silver.drug_labels.indications),
      adverse_reactions = COALESCE(EXCLUDED.adverse_reactions, mol_silver.drug_labels.adverse_reactions),
      mechanism_of_action = COALESCE(EXCLUDED.mechanism_of_action, mol_silver.drug_labels.mechanism_of_action),
      route_of_administration = COALESCE(EXCLUDED.route_of_administration, mol_silver.drug_labels.route_of_administration),
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
      approval_date = COALESCE(EXCLUDED.approval_date, mol_silver.drug_labels.approval_date);
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' labels';
  EXCEPTION WHEN OTHERS THEN result := 'Labels: ' || SQLERRM; END;
  RETURN NEXT;

  -- Link DrugBank Targets: bronze.drugbank_targets → mol_silver.targets
  step := 'Link DrugBank Targets';
  BEGIN
    INSERT INTO mol_silver.targets (
      molecule_id, molecule_name, target_name, target_type, action_type,
      gene_symbol, uniprot_accession, source
    )
    SELECT m.molecule_id, m.canonical_name,
      t.target_name, 'protein', array_to_string(t.actions, ', '),
      t.gene_name, t.uniprot_id, 'drugbank'
    FROM bronze.drugbank_targets t
    JOIN bronze.drugbank_data d ON t.drugbank_id = d.drugbank_id
    JOIN mol_silver.molecules m ON LOWER(d.drug_name) = LOWER(m.canonical_name)
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
        LOWER(f.product_name) = LOWER(m.canonical_name)
        OR LOWER(f.product_name) = ANY(SELECT LOWER(unnest(m.brand_names)))
      );
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := '+' || linked_count || ' financial filings';
  EXCEPTION WHEN OTHERS THEN result := 'Financial: ' || SQLERRM; END;
  RETURN NEXT;

  step := 'Refresh Gold';
  BEGIN
    INSERT INTO mol_gold.safety_signals (molecule_id, reaction_meddra_pt, case_count, signal_strength)
    SELECT ae.molecule_id, ae.reaction_meddra_pt, count(*),
      CASE WHEN count(*) > 100 THEN 'strong' WHEN count(*) > 20 THEN 'moderate' ELSE 'weak' END
    FROM mol_silver.adverse_events ae WHERE ae.reaction_meddra_pt IS NOT NULL
    GROUP BY ae.molecule_id, ae.reaction_meddra_pt HAVING count(*) > 1
    ON CONFLICT DO NOTHING;
    UPDATE mol_gold.molecule_profiles mp SET
      trial_count = (SELECT count(*) FROM mol_silver.clinical_trials ct WHERE ct.molecule_id = mp.molecule_id),
      adverse_event_count = (SELECT count(*) FROM mol_silver.adverse_events ae WHERE ae.molecule_id = mp.molecule_id),
      last_updated = now();
    GET DIAGNOSTICS linked_count = ROW_COUNT;
    result := 'Gold refreshed (' || linked_count || ' profiles updated)';
  EXCEPTION WHEN OTHERS THEN result := 'Gold: ' || SQLERRM; END;
  RETURN NEXT;
  RETURN;
END; $$ LANGUAGE plpgsql;
