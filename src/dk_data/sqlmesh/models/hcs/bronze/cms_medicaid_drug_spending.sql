-- SQLMesh Model: Bronze CMS Medicaid Drug Spending
-- Typed pass-through from hcs_raw.cms_medicaid_drug_spending
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_medicaid_drug_spending,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (state_id, drug_name, labeler_name, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (state_id, drug_name, _source_year))
    ),
    grain (state_id, drug_name, labeler_name, _source_year)
);

SELECT
    id,
    state_id,
    state_name,
    drug_name,
    labeler_name,
    units_reimbursed,
    number_of_prescriptions,
    total_amount_reimbursed,
    medicaid_amount_reimbursed,
    non_medicaid_amount_reimbursed,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_medicaid_drug_spending;
