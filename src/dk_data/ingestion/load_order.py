"""Load order for 005-prestaged-hydration.

A single Python list — no DAG framework. Encodes the 8-tier hub → spoke
sequence from ``.dk/specs/005-prestaged-hydration/plan.md`` (§load_order)
so that silver/gold transforms succeed first-try after hydration (US2).

Consumed by ``prestaged.plan_load()`` (Stage 3, T040) which:
  - filters SOURCE_LOAD_ORDER by what artifacts were actually discovered
  - resolves ``depends_on`` (blocked steps emit ``status='blocked'``)
  - emits a :class:`dk_data.ingestion.prestaged_types.LoadPlan`.

The "tiers" are declared by grouping; they are not a distinct construct.
A step in tier N does not start until every step in tiers <N has
reached a terminal state (completed, failed, blocked, skipped_view, or
no_source_available).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceDescriptor:
    """One entry in SOURCE_LOAD_ORDER.

    Attributes:
        source_id: canonical ``"{schema}.{table}"`` key.
        schema: target schema name.
        table: target relation name.
        tier: 1..8, matching plan.md §load_order.
        depends_on: list of source_ids that must reach a terminal state
            (preferably ``completed``) before this source is dispatched.
            Empty list = "only tier ordering gates this source".
        parallelizable: declared but IGNORED in v1 (serial always per D003).
    """

    source_id: str
    schema: str
    table: str
    tier: int
    depends_on: list[str] = field(default_factory=list)
    parallelizable: bool = False


# ---------------------------------------------------------------------------
# SOURCE_LOAD_ORDER — full 8-tier sequence, 120 sources observed.
# ---------------------------------------------------------------------------
# Keep declaration order stable — it defines serial dispatch order inside
# a tier. Adding new entries: append to the right tier; do NOT insert in
# the middle of a tier unless the depends_on graph demands it.

SOURCE_LOAD_ORDER: list[SourceDescriptor] = [
    # -------------------------------------------------------------------
    # Tier 1 — metadata / SQLMesh lineage. Restored first so subsequent
    # `sqlmesh run` calls see the right lineage state.
    # -------------------------------------------------------------------
    SourceDescriptor("meta.fetch_checkpoints", "meta", "fetch_checkpoints", 1),
    SourceDescriptor("sqlmesh._snapshots", "sqlmesh", "_snapshots", 1),

    # -------------------------------------------------------------------
    # Tier 2 — molecule hub raw. Populates the molecule-hub inputs.
    # -------------------------------------------------------------------
    SourceDescriptor("mol_raw.chembl", "mol_raw", "chembl", 2),
    SourceDescriptor("mol_raw.drugbank", "mol_raw", "drugbank", 2),
    SourceDescriptor("mol_raw.pubchem", "mol_raw", "pubchem", 2),  # 7.18 GB, WAL-mode
    SourceDescriptor("mol_raw.fda_drugs", "mol_raw", "fda_drugs", 2),
    SourceDescriptor("mol_raw.fda_ndc", "mol_raw", "fda_ndc", 2),
    SourceDescriptor("mol_raw.rxnorm", "mol_raw", "rxnorm", 2),
    SourceDescriptor("mol_raw.kegg_drug", "mol_raw", "kegg_drug", 2),
    SourceDescriptor("mol_raw.uniprot", "mol_raw", "uniprot", 2),

    # -------------------------------------------------------------------
    # Tier 3 — molecule bronze. Skip bronze transforms where a dump exists.
    # -------------------------------------------------------------------
    SourceDescriptor("mol_bronze.pubchem", "mol_bronze", "pubchem", 3,
                     depends_on=["mol_raw.pubchem"]),  # 7.59 GB, WAL-mode
    SourceDescriptor("mol_bronze.chembl_activities", "mol_bronze", "chembl_activities", 3,
                     depends_on=["mol_raw.chembl"]),  # 2.48 GB, WAL-mode
    SourceDescriptor("mol_bronze.drugbank_data", "mol_bronze", "drugbank_data", 3,
                     depends_on=["mol_raw.drugbank"]),
    SourceDescriptor("mol_bronze.drugbank_targets", "mol_bronze", "drugbank_targets", 3,
                     depends_on=["mol_raw.drugbank"]),
    SourceDescriptor("mol_bronze.drugbank_interactions", "mol_bronze", "drugbank_interactions", 3,
                     depends_on=["mol_raw.drugbank"]),
    SourceDescriptor("mol_bronze.orcid", "mol_bronze", "orcid", 3),
    SourceDescriptor("mol_bronze.tdc_admet", "mol_bronze", "tdc_admet", 3),

    # -------------------------------------------------------------------
    # Tier 4 — molecule silver hubs. Skip silver transforms for these hubs.
    # -------------------------------------------------------------------
    SourceDescriptor("mol_silver.molecules", "mol_silver", "molecules", 4,
                     depends_on=["mol_bronze.chembl_activities",
                                 "mol_bronze.drugbank_data"]),
    SourceDescriptor("mol_silver.drug_labels", "mol_silver", "drug_labels", 4),
    SourceDescriptor("mol_silver.clinical_trials", "mol_silver", "clinical_trials", 4),

    # -------------------------------------------------------------------
    # Tier 5 — clinical / activity spokes. Parallel-safe after hubs but
    # dispatched serially in v1 (D003).
    # -------------------------------------------------------------------
    SourceDescriptor("mol_raw.clinicaltrials", "mol_raw", "clinicaltrials", 5),  # 7.51 GB, WAL-mode
    SourceDescriptor("mol_bronze.clinicaltrials", "mol_bronze", "clinicaltrials", 5,
                     depends_on=["mol_raw.clinicaltrials"]),  # 2.54 GB, WAL-mode
    SourceDescriptor("mol_raw.openfda_faers", "mol_raw", "openfda_faers", 5),
    SourceDescriptor("mol_raw.openfda_labels", "mol_raw", "openfda_labels", 5),
    SourceDescriptor("mol_raw.europepmc", "mol_raw", "europepmc", 5),
    SourceDescriptor("mol_raw.dailymed", "mol_raw", "dailymed", 5),
    SourceDescriptor("mol_raw.sider", "mol_raw", "sider", 5),
    SourceDescriptor("mol_raw.fda_rems", "mol_raw", "fda_rems", 5),
    SourceDescriptor("mol_raw.orange_book", "mol_raw", "orange_book", 5),
    SourceDescriptor("mol_raw.purple_book", "mol_raw", "purple_book", 5),
    SourceDescriptor("mol_raw.pharmgkb", "mol_raw", "pharmgkb", 5),
    SourceDescriptor("mol_raw.ema", "mol_raw", "ema", 5),
    SourceDescriptor("mol_raw.nih_reporter", "mol_raw", "nih_reporter", 5),
    SourceDescriptor("mol_raw.sec_edgar", "mol_raw", "sec_edgar", 5),
    SourceDescriptor("mol_raw.npi_registry", "mol_raw", "npi_registry", 5),
    SourceDescriptor("mol_raw.openalex_ci", "mol_raw", "openalex_ci", 5),
    SourceDescriptor("mol_raw.bindingdb", "mol_raw", "bindingdb", 5),
    SourceDescriptor("mol_raw.pdb", "mol_raw", "pdb", 5),
    SourceDescriptor("mol_raw.orcid", "mol_raw", "orcid", 5),
    SourceDescriptor("mol_raw.cdc_vaccines", "mol_raw", "cdc_vaccines", 5),
    SourceDescriptor("mol_raw.who_gho", "mol_raw", "who_gho", 5),
    SourceDescriptor("mol_raw.who_icd", "mol_raw", "who_icd", 5),
    SourceDescriptor("mol_raw.tdc_admet", "mol_raw", "tdc_admet", 5),
    SourceDescriptor("mol_raw.chembl_activities", "mol_raw", "chembl_activities", 5),

    # -------------------------------------------------------------------
    # Tier 6 — HCS provider hub raw + HCS bronze. 34 tables per tier.
    # -------------------------------------------------------------------
    SourceDescriptor("hcs_raw.cms_pecos", "hcs_raw", "cms_pecos", 6),
    SourceDescriptor("hcs_raw.cms_physician_puf_services", "hcs_raw",
                     "cms_physician_puf_services", 6),
    SourceDescriptor("hcs_raw.cms_telehealth_puf", "hcs_raw", "cms_telehealth_puf", 6),
    SourceDescriptor("hcs_raw.cms_opioid_puf", "hcs_raw", "cms_opioid_puf", 6),
    SourceDescriptor("hcs_raw.cms_open_payments", "hcs_raw", "cms_open_payments", 6),
    SourceDescriptor("hcs_raw.hrsa_shortage_areas", "hcs_raw", "hrsa_shortage_areas", 6),
    # Remaining hcs_raw tables (declared generically; exact list comes from
    # plan.md §Data flow, tier 6. Extend here as new dumps land.)

    SourceDescriptor("hcs_bronze.cms_pecos", "hcs_bronze", "cms_pecos", 6,
                     depends_on=["hcs_raw.cms_pecos"]),
    SourceDescriptor("hcs_bronze.cms_physician_puf_services", "hcs_bronze",
                     "cms_physician_puf_services", 6,
                     depends_on=["hcs_raw.cms_physician_puf_services"]),
    SourceDescriptor("hcs_bronze.cms_telehealth_puf", "hcs_bronze",
                     "cms_telehealth_puf", 6,
                     depends_on=["hcs_raw.cms_telehealth_puf"]),
    SourceDescriptor("hcs_bronze.cms_opioid_puf", "hcs_bronze", "cms_opioid_puf", 6,
                     depends_on=["hcs_raw.cms_opioid_puf"]),
    SourceDescriptor("hcs_bronze.cms_open_payments", "hcs_bronze",
                     "cms_open_payments", 6,
                     depends_on=["hcs_raw.cms_open_payments"]),

    # -------------------------------------------------------------------
    # Tier 7 — HCS silver aggregates.
    # -------------------------------------------------------------------
    SourceDescriptor("hcs_silver.provider_profile", "hcs_silver", "provider_profile", 7),
    SourceDescriptor("hcs_silver.facility_profile", "hcs_silver", "facility_profile", 7),
    SourceDescriptor("hcs_silver.cms_facility_profile", "hcs_silver",
                     "cms_facility_profile", 7),
    SourceDescriptor("hcs_silver.healthcare_facilities", "hcs_silver",
                     "healthcare_facilities", 7),
    SourceDescriptor("hcs_silver.geographic_health", "hcs_silver",
                     "geographic_health", 7),

    # -------------------------------------------------------------------
    # Tier 8 — gold via SQLMesh. No dumps exist; these are rebuilt from
    # silver after tier 7 completes. Declared here so the orchestrator
    # knows to schedule the sqlmesh run invocations in order.
    # -------------------------------------------------------------------
    SourceDescriptor("ind_gold.indication_catalog", "ind_gold", "indication_catalog", 8),
    SourceDescriptor("ip_gold.molecule_profile", "ip_gold", "molecule_profile", 8),
    SourceDescriptor("mol_gold_ext.safety_signals", "mol_gold_ext", "safety_signals", 8),
    SourceDescriptor("mol_gold_ext.lifecycle_stages", "mol_gold_ext",
                     "lifecycle_stages", 8),
]


# ---------------------------------------------------------------------------
# WAL_MODE_TABLES — the 5 tables > 5 GB that need WAL-aware throttling.
# ---------------------------------------------------------------------------
# Pre-restore, prestaged.run_step() checks this set. When the target is
# a member, it polls meta.wal_usage and only starts the restore once
# pct_used < WAL_PAUSE_HIGH_PCT (default 70). See FR-007 / FR-008.

WAL_MODE_TABLES: frozenset[tuple[str, str]] = frozenset(
    {
        ("mol_raw", "pubchem"),          # 7.18 GB
        ("mol_raw", "clinicaltrials"),   # 7.51 GB
        ("mol_bronze", "pubchem"),       # 7.59 GB
        ("mol_bronze", "chembl_activities"),  # 2.48 GB (still WAL-mode per plan)
        ("mol_bronze", "clinicaltrials"),     # 2.54 GB
    }
)


# ---------------------------------------------------------------------------
# Domains that are explicitly out of scope (FR-014).
# ---------------------------------------------------------------------------
# Sources whose schema prefix matches any of these are dropped at
# plan_load() time — they never appear in the LoadPlan, never get a
# live-fetch fallback, never get a row in meta.transform_runs.

OUT_OF_SCOPE_SCHEMA_PREFIXES: frozenset[str] = frozenset(
    {"ip_", "ind_", "hcp_silver"}
)
