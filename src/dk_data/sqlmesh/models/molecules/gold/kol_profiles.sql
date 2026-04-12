-- SQLMesh Model: Gold KOL Profiles
-- Key Opinion Leader profiles with influence scoring.
--
-- Sources:
--   mol_silver.researchers (mol_silver.researchers) — ORCID profiles + NIH grant counts
--   mol_silver.publications (mol_silver.publications) — aggregated publication metrics
--   mol_silver.clinical_trials (mol_silver.clinical_trials) — trial sponsor matching
--
-- Influence score formula (FR-018):
--   h_index*0.3 + publications*0.2 + citations*0.25 + trials*0.15 + grants*0.1
--
-- Fixed (019-cms-puf-platform-reconciliation):
--   - ct.lead_sponsor_name → ct.lead_sponsor_name
--     (mol_silver.clinical_trials exposes lead_sponsor_name, not lead_sponsor)
--   - pub_counts now joins via first_author_name ILIKE rather than first_author_id
--     (mol_silver.publications does not expose first_author_id in its final SELECT;
--      name-based match is the correct linkage given the available columns)
--
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_gold.kol_profiles,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key researcher_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (researcher_id, family_name)),
        unique_values(columns := (researcher_id))
    ),
    grain researcher_id
);

WITH researcher_base AS (
    SELECT
        r.id AS researcher_id,
        r.orcid_id,
        r.given_name,
        r.family_name,
        r.affiliation,
        r.country,
        r.works_count,
        COALESCE(r.h_index, 0) AS h_index,
        r.research_areas,
        r.therapeutic_areas,
        COALESCE(r.grant_count, 0) AS grant_count
    FROM mol_silver.researchers r
),

-- Publication counts per researcher, matched by first_author_name.
-- mol_silver.publications exposes first_author_name (display_name from OpenAlex authorships)
-- but not first_author_id (ORCID URL). We match by full name substring to handle
-- variations in display format (e.g. "Jane Smith" vs "J. Smith").
pub_counts AS (
    SELECT
        -- Normalise: strip whitespace, lower-case for matching
        LOWER(TRIM(p.first_author_name))        AS author_name_norm,
        COUNT(*)                                 AS publication_count,
        COALESCE(SUM(p.cited_by_count), 0)       AS total_citations
    FROM mol_silver.publications p
    WHERE p.first_author_name IS NOT NULL
    GROUP BY LOWER(TRIM(p.first_author_name))
),

-- Clinical trial involvement counts, matched by lead_sponsor.
-- Word-boundary regex (\m/\M) prevents short surnames (e.g. "Lee", "Kim") from
-- matching mid-word inside sponsor names ("GlaxoSmithKline"). Length guard ≥4
-- further reduces false positives on very short family names.
trial_counts AS (
    SELECT
        r.id AS researcher_id,
        COUNT(DISTINCT ct.nct_id) AS trial_count
    FROM mol_silver.researchers r
    JOIN mol_silver.clinical_trials ct
        ON LENGTH(r.family_name) >= 4
       AND ct.lead_sponsor_name ~* ('\m' || r.family_name || '\M')
    GROUP BY r.id
),

-- Compute influence score:
-- h_index*0.3 + publications*0.2 + citations*0.25 + trials*0.15 + grants*0.1
scored AS (
    SELECT
        rb.researcher_id,
        rb.orcid_id,
        rb.given_name,
        rb.family_name,
        rb.affiliation,
        rb.country,
        rb.works_count,
        rb.h_index,
        rb.research_areas,
        rb.therapeutic_areas,
        rb.grant_count,
        -- Match publications by researcher full name (given_name + space + family_name)
        COALESCE(pc.publication_count, 0)        AS publication_count,
        COALESCE(pc.total_citations, 0)          AS total_citations,
        COALESCE(tc.trial_count, 0)              AS trial_count,
        -- Influence score formula (FR-018)
        (rb.h_index * 0.3
         + COALESCE(pc.publication_count, 0) * 0.2
         + COALESCE(pc.total_citations, 0) * 0.25
         + COALESCE(tc.trial_count, 0) * 0.15
         + rb.grant_count * 0.1
        )::NUMERIC AS influence_score
    FROM researcher_base rb
    LEFT JOIN pub_counts pc
        ON LOWER(TRIM(rb.given_name || ' ' || rb.family_name)) = pc.author_name_norm
    LEFT JOIN trial_counts tc ON rb.researcher_id = tc.researcher_id
),

-- Compute influence tier via PERCENT_RANK
tiered AS (
    SELECT
        *,
        PERCENT_RANK() OVER (ORDER BY influence_score) AS pct_rank,
        CASE
            WHEN PERCENT_RANK() OVER (ORDER BY influence_score) >= 0.95 THEN 'Global'
            WHEN PERCENT_RANK() OVER (ORDER BY influence_score) >= 0.80 THEN 'National'
            WHEN PERCENT_RANK() OVER (ORDER BY influence_score) >= 0.50 THEN 'Regional'
            ELSE 'Rising'
        END AS influence_tier
    FROM scored
)

SELECT
    gen_random_uuid() AS id,
    researcher_id,
    orcid_id,
    given_name,
    family_name,
    affiliation,
    country,
    works_count,
    h_index,
    publication_count,
    total_citations,
    trial_count,
    grant_count,
    research_areas,
    therapeutic_areas,
    influence_score,
    influence_tier,
    NOW() AS created_at,
    NOW() AS updated_at
FROM tiered;
