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

  step := 'Link Labels';
  SELECT count(*) INTO linked_count FROM mol_silver.drug_labels WHERE molecule_id IS NOT NULL;
  result := linked_count || ' labels'; RETURN NEXT;

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
    result := 'Gold refreshed';
  EXCEPTION WHEN OTHERS THEN result := 'Gold: ' || SQLERRM; END;
  RETURN NEXT;
  RETURN;
END; $$ LANGUAGE plpgsql;
