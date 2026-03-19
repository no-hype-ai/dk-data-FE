CREATE OR REPLACE FUNCTION silver.run_entity_linking()
RETURNS TABLE(step TEXT, result TEXT) AS $$
DECLARE linked_count INT; total_count INT;
BEGIN
  step := 'Build Lookup'; result := 'mol_silver.molecules'; RETURN NEXT;

  step := 'Link Trials';
  SELECT count(*) INTO total_count FROM bronze.clinicaltrials WHERE nct_id IS NOT NULL;
  INSERT INTO mol_silver.clinical_trials (molecule_id, nct_id, title, phase, status, enrollment_target, sponsor)
  SELECT DISTINCT ON (b.nct_id) m.molecule_id, b.nct_id,
    COALESCE(b.official_title, b.brief_title), b.phases::text, b.overall_status, b.enrollment_count, b.lead_sponsor_name
  FROM bronze.clinicaltrials b CROSS JOIN mol_silver.molecules m
  WHERE m.canonical_name IS NOT NULL AND b.nct_id IS NOT NULL
    AND LOWER(COALESCE(b.official_title, b.brief_title, '')) LIKE '%' || LOWER(m.canonical_name) || '%'
  ON CONFLICT (nct_id) DO UPDATE SET molecule_id = EXCLUDED.molecule_id;
  GET DIAGNOSTICS linked_count = ROW_COUNT;
  result := '+' || linked_count || '/' || total_count || ' trials'; RETURN NEXT;

  step := 'Link FAERS';
  BEGIN
    INSERT INTO mol_silver.adverse_events (source, molecule_id, drug_name_reported, reaction_meddra_pt, seriousness)
    SELECT 'openfda_faers', m.molecule_id, m.canonical_name,
      reaction->>'reactionmeddrapt', b.serious
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
      clinical_studies, effective_date, approval_date
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
      NULL,
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
