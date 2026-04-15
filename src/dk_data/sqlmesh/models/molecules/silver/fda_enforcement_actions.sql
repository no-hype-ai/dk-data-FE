-- SQLMesh Model: Silver FDA Enforcement Actions (unified)
-- UNION ALL from 5 bronze enforcement-action sources, normalized to
-- common columns with molecule crosswalk via mol_silver.molecules.
-- Feature: 006-claims-engine-data-gaps (T075)

MODEL (
    name mol_silver.fda_enforcement_actions,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (action_id, action_type))
    ),
    grain (action_id, action_type)
);

WITH unified AS (
    -- Warning Letters
    SELECT
        wl.letter_id                        AS action_id,
        'warning_letter'                    AS action_type,
        wl.letter_date                      AS action_date,
        wl.company_name                     AS company_name,
        wl.subject                          AS subject,
        wl.drug_mentions                    AS drug_mentions,
        wl.full_text                        AS full_text
    FROM mol_bronze.fda_warning_letters wl

    UNION ALL

    -- Untitled Letters
    SELECT
        ul.letter_id                        AS action_id,
        'untitled_letter'                   AS action_type,
        ul.letter_date                      AS action_date,
        ul.company_name                     AS company_name,
        ul.subject                          AS subject,
        ul.drug_mentions                    AS drug_mentions,
        ul.full_text                        AS full_text
    FROM mol_bronze.fda_untitled_letters ul

    UNION ALL

    -- 483 Observations
    SELECT
        obs.observation_id                  AS action_id,
        '483_observation'                   AS action_type,
        obs.inspection_date                 AS action_date,
        obs.company_name                    AS company_name,
        obs.facility                        AS subject,
        obs.drug_mentions                   AS drug_mentions,
        obs.full_text                       AS full_text
    FROM mol_bronze.fda_483_observations obs

    UNION ALL

    -- Dear HCP Letters
    SELECT
        dhcp.letter_id                      AS action_id,
        'dear_hcp'                          AS action_type,
        dhcp.letter_date                    AS action_date,
        dhcp.company_name                   AS company_name,
        dhcp.subject                        AS subject,
        dhcp.drug_mentions                  AS drug_mentions,
        dhcp.full_text                      AS full_text
    FROM mol_bronze.fda_dear_hcp_letters dhcp

    UNION ALL

    -- Complete Response Letters
    SELECT
        crl.crl_id                          AS action_id,
        'crl'                               AS action_type,
        crl.crl_date                        AS action_date,
        crl.company_name                    AS company_name,
        crl.drug_name                       AS subject,
        crl.drug_mentions                   AS drug_mentions,
        crl.full_text                       AS full_text
    FROM mol_bronze.fda_crls crl
)
SELECT
    u.action_id,
    u.action_type,
    u.action_date,
    u.company_name,
    u.subject,
    u.drug_mentions,
    u.full_text,
    -- Molecule crosswalk: attempt to match company_name against mol_silver.molecules
    -- via drug_mentions first element (if available), falling back to subject text
    m.id                                    AS molecule_id,
    NOW()                                   AS created_at
FROM unified u
LEFT JOIN mol_silver.molecules m
    ON LOWER(TRIM(m.name)) = LOWER(TRIM(
        COALESCE(
            u.drug_mentions->>0,
            u.subject
        )
    ));
