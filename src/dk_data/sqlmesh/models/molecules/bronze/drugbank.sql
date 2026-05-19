-- SQLMesh Model: Bronze DrugBank
-- Transforms Raw DrugBank flat-column records to Bronze typed columns
-- Part of: 012-dk-data-platform
--
-- NOTE: mol_raw.drugbank uses flat columns (not response_body JSONB) because
-- DrugBank is a credential-gated XML download parsed by DrugBankFetcher.
-- The loader (sources/drugbank.py) inserts all parsed fields directly.
-- Columns extended in migration 110 to include structural identifiers,
-- pharmacokinetics, ATC codes, pathways, interactions, and synonyms.
-- There is no response_status / processed_to_bronze / request_timestamp
-- on this table — use _loaded_at for time-range incremental partitioning.

MODEL (
    name mol_bronze.drugbank,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key drugbank_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (drugbank_id)),
        unique_values(columns := (drugbank_id))
    ),
    grain drugbank_id
);

SELECT
    gen_random_uuid() AS id,

    -- DrugBank Identifiers
    drugbank_id::TEXT                       AS drugbank_id,
    cas_number::TEXT                        AS cas_number,

    -- Names
    name::TEXT                              AS name,

    -- Drug Properties
    description::TEXT                       AS description,
    indication::TEXT                        AS indication,
    pharmacodynamics::TEXT                  AS pharmacodynamics,

    -- Structured arrays / JSONB from XML parser
    -- categories: TEXT[] from raw — cast to JSONB array for downstream uniformity
    CASE
        WHEN categories IS NOT NULL
        THEN to_jsonb(categories)
        ELSE '[]'::JSONB
    END                                     AS categories,

    -- targets / enzymes / carriers / transporters: already JSONB from loader
    COALESCE(targets, '[]'::JSONB)          AS targets,
    COALESCE(enzymes, '[]'::JSONB)          AS enzymes,
    COALESCE(carriers, '[]'::JSONB)         AS carriers,
    COALESCE(transporters, '[]'::JSONB)     AS transporters,

    -- Drug classification (from XML <drug type="...">)
    drug_type::TEXT                         AS drug_type,
    -- state extracted by fetcher (migration 111)
    state::TEXT                             AS state,
    -- groups extracted by fetcher (migration 111)
    groups                                  AS groups,
    classification                          AS classification,
    atc_codes                               AS atc_codes,

    -- Pharmacology (all fields extracted in migrations 110 + 111)
    mechanism_of_action::TEXT               AS mechanism_of_action,
    absorption::TEXT                        AS absorption,
    protein_binding::TEXT                   AS protein_binding,
    metabolism::TEXT                        AS metabolism,
    half_life::TEXT                         AS half_life,
    -- route_of_elimination / clearance / volume_of_distribution: columns added in
    -- migration 110; fetcher extraction added in migration 111 work
    route_of_elimination::TEXT              AS route_of_elimination,
    clearance::TEXT                         AS clearance,
    volume_of_distribution::TEXT            AS volume_of_distribution,
    toxicity::TEXT                          AS toxicity,

    -- Structural identifiers (from <calculated-properties>, migration 110)
    smiles::TEXT                            AS smiles,
    inchi::TEXT                             AS inchi,
    inchi_key::TEXT                         AS inchi_key,
    molecular_formula::TEXT                 AS molecular_formula,
    -- molecular_weight stored as TEXT (may include unit suffix like "g/mol")
    -- Cast to NUMERIC, stripping any trailing text
    NULLIF(REGEXP_REPLACE(COALESCE(molecular_weight, ''), '[^0-9.]', '', 'g'), '')::NUMERIC AS average_mass,
    -- monoisotopic_mass from experimental-properties (migration 111)
    NULLIF(REGEXP_REPLACE(COALESCE(monoisotopic_mass, ''), '[^0-9.]', '', 'g'), '')::NUMERIC AS monoisotopic_mass,
    -- unii from external-identifiers (migration 111)
    unii::TEXT                              AS unii,

    -- Molecular properties derived from calculated_properties JSONB blob.
    -- DrugBank <calculated-properties> keys are lowercased+underscored kind names.
    -- COALESCE handles variant key names seen across DrugBank XML versions.
    NULLIF(REGEXP_REPLACE(
        COALESCE(calculated_properties->>'logp', calculated_properties->>'alogp', ''),
        '[^0-9.-]', '', 'g'), '')::NUMERIC                          AS alogp,
    NULLIF(REGEXP_REPLACE(
        COALESCE(calculated_properties->>'h_bond_acceptor_count',
                 calculated_properties->>'hydrogen_bond_acceptor_count', ''),
        '[^0-9]', '', 'g'), '')::INTEGER                            AS hba,
    NULLIF(REGEXP_REPLACE(
        COALESCE(calculated_properties->>'h_bond_donor_count',
                 calculated_properties->>'hydrogen_bond_donor_count', ''),
        '[^0-9]', '', 'g'), '')::INTEGER                            AS hbd,
    NULLIF(REGEXP_REPLACE(
        COALESCE(calculated_properties->>'polar_surface_area_(psa)',
                 calculated_properties->>'polar_surface_area',
                 calculated_properties->>'psa', ''),
        '[^0-9.]', '', 'g'), '')::NUMERIC                           AS psa,
    NULLIF(REGEXP_REPLACE(
        COALESCE(calculated_properties->>'rotatable_bond_count', ''),
        '[^0-9]', '', 'g'), '')::INTEGER                            AS rotatable_bond_count,
    NULLIF(REGEXP_REPLACE(
        COALESCE(calculated_properties->>'heavy_atom_count',
                 calculated_properties->>'number_of_heavy_atoms', ''),
        '[^0-9]', '', 'g'), '')::INTEGER                            AS heavy_atoms,
    NULLIF(REGEXP_REPLACE(
        COALESCE(calculated_properties->>'aromatic_ring_count',
                 calculated_properties->>'number_of_rings', ''),
        '[^0-9]', '', 'g'), '')::INTEGER                            AS aromatic_rings,
    -- isomeric_smiles: DrugBank stores SMILES (canonical) and Isomeric SMILES separately
    COALESCE(calculated_properties->>'isomeric_smiles',
             calculated_properties->>'isomericsmiles')::TEXT        AS isomeric_smiles,

    -- Relational data
    drug_interactions                       AS drug_interactions,
    -- food_interactions extracted by fetcher (migration 111)
    food_interactions                       AS food_interactions,
    pathways                                AS pathways,
    -- external_links: derived from external_identifiers where a URL is present;
    -- external_identifiers stores {resource_key: identifier_value} so there is no
    -- separate URL field — leave NULL (genuine unavailability at this schema level)
    NULL::JSONB                             AS external_links,
    external_identifiers                    AS external_identifiers,
    calculated_properties                   AS calculated_properties,
    experimental_properties                 AS experimental_properties,
    -- fda_label: DrugBank XML does not include full FDA label content
    -- (the API has a label endpoint but DrugBank bulk XML does not); leave NULL
    NULL::JSONB                             AS fda_label,
    -- patents extracted by fetcher (migration 111)
    patents                                 AS patents,
    synonyms                                AS synonyms,
    -- international_brands extracted by fetcher (migration 111)
    international_brands                    AS international_brands,
    -- products: DrugBank <products> element contains thousands of branded product entries;
    -- too large to store per-drug — omitted by design; leave NULL
    NULL::JSONB                             AS products,

    -- Raw source tracking
    -- raw_json: DrugBank uses flat columns (not response_body); full XML blob not stored
    NULL::JSONB                             AS raw_json,
    -- raw_source_id: no request_id concept for flat-column DrugBank table
    NULL::UUID                              AS raw_source_id,
    'drugbank'                              AS source,
    _loaded_at                              AS loaded_at,
    _loaded_at                              AS source_updated_at,
    FALSE                                   AS processed_to_silver,
    NOW()                                   AS created_at

FROM mol_raw.drugbank
WHERE
    drugbank_id IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
