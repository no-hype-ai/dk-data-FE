"""Load order for 005-prestaged-hydration.

A single Python list — no DAG framework. Encodes the 8-tier hub → spoke
sequence from ``.dk/specs/005-prestaged-hydration/plan.md`` (§load_order)
so that silver/gold transforms succeed first-try after hydration (US2).

Public entry points:
  - :data:`SOURCE_LOAD_ORDER` — the 8-tier descriptor list.
  - :data:`WAL_MODE_TABLES` — the 5 tables >5 GB needing throttle.
  - :data:`OUT_OF_SCOPE_SCHEMA_PREFIXES` — never appear in any plan.
  - :func:`plan_load` — pure function that combines a discovered artifact
    set + the descriptor list into a :class:`LoadPlan`. Used by
    ``prestaged.main()``.
  - :func:`propagate_blocked` — given a set of failed source_ids,
    returns the transitively-blocked downstream steps.

The "tiers" are declared by grouping; they are not a distinct construct.
A step in tier N does not start until every step in tiers <N has
reached a terminal state (completed, failed, blocked, skipped_view, or
no_source_available).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from dk_data.ingestion.prestaged_types import (
    LoadPlan,
    LoadStep,
    PrestagedArtifact,
    SourceKind,
    Tier,
    compute_run_id,
)


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
    #
    # T126 — depends_on declarations: silver aggregates that read from
    # the bronze CMS tables wait for them to be restored. cms_pecos is
    # the foundational provider hub; provider_profile + facility_profile
    # both block on it. The other 3 silver aggregates can run any time
    # after their bronze inputs land (left blocked-only-by-tier).
    # -------------------------------------------------------------------
    SourceDescriptor("hcs_silver.provider_profile", "hcs_silver", "provider_profile", 7,
                     depends_on=["hcs_bronze.cms_pecos"]),
    SourceDescriptor("hcs_silver.facility_profile", "hcs_silver", "facility_profile", 7,
                     depends_on=["hcs_bronze.cms_pecos"]),
    SourceDescriptor("hcs_silver.cms_facility_profile", "hcs_silver",
                     "cms_facility_profile", 7,
                     depends_on=["hcs_bronze.cms_open_payments"]),
    SourceDescriptor("hcs_silver.healthcare_facilities", "hcs_silver",
                     "healthcare_facilities", 7,
                     depends_on=["hcs_bronze.cms_pecos"]),
    SourceDescriptor("hcs_silver.geographic_health", "hcs_silver",
                     "geographic_health", 7,
                     depends_on=["hcs_bronze.cms_opioid_puf"]),

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


# ---------------------------------------------------------------------------
# T040 — plan_load: pure plan construction (no I/O, no DB)
# ---------------------------------------------------------------------------

def plan_load(
    artifacts: Iterable[PrestagedArtifact],
    *,
    cluster_fingerprint: str,
    requested_sources: set[str] | None = None,
    only_tier: int | None = None,
    descriptors: list[SourceDescriptor] | None = None,
) -> LoadPlan:
    """Build a :class:`LoadPlan` from a discovered artifact set.

    Pure function — no DB connection, no filesystem I/O. The ``artifacts``
    parameter must already be validated (magic bytes ok) and hashed
    (``sha256`` populated) by the caller; ``plan_load`` only consults
    metadata, never opens files.

    Selection logic per (schema, table) group:
      - silver dump beats bronze beats raw (FR-003);
      - lower-tier artifacts in the same group are discarded.

    Filters:
      - ``requested_sources``: when not ``None``, only descriptors whose
        ``source_id`` is in the set are emitted.
      - ``only_tier``: when not ``None``, only descriptors with the
        matching ``tier`` are emitted.
      - :data:`OUT_OF_SCOPE_SCHEMA_PREFIXES`: descriptors whose schema
        starts with any prefix are dropped unconditionally (FR-014).

    Args:
        artifacts: validated, hashed PrestagedArtifact instances.
        cluster_fingerprint: stable identifier for the target cluster
            (e.g. ``"host:port/db"``); mixed into ``run_label``.
        requested_sources: optional set of source_ids to keep.
        only_tier: optional tier filter (1..8).
        descriptors: optional override of :data:`SOURCE_LOAD_ORDER`
            (used by tests).

    Returns:
        :class:`LoadPlan` with steps in declared order. Each step's
        ``kind`` is ``"pg_dump"`` if at least one artifact matches its
        ``(schema, table)``, else ``"live_fetch"``. ``wal_mode`` is set
        from :data:`WAL_MODE_TABLES`. ``run_label`` is deterministic
        per the artifact set + cluster.
    """
    descriptors = descriptors if descriptors is not None else SOURCE_LOAD_ORDER

    # Group artifacts by (schema, table) and select highest tier per group
    grouped: dict[tuple[str, str], list[PrestagedArtifact]] = {}
    for art in artifacts:
        grouped.setdefault((art.target_schema, art.target_table), []).append(art)

    table_entries: dict[tuple[str, str], tuple[Tier, list[PrestagedArtifact]]] = {}
    for key, group in grouped.items():
        best_tier: Tier = max(group, key=lambda a: _TIER_RANK[a.tier]).tier
        chosen_all = sorted(
            (a for a in group if a.tier == best_tier),
            key=lambda a: (a.path.parent.name, a.chunk_index),
        )
        # A single (schema, table) can have multiple .dump files — e.g.,
        # `mol_raw.chembl` exists in both the April-14 and April-15 archive
        # batches as full-table snapshots. pg_dump does NOT split tables
        # across files; every .dump is a complete snapshot. Restoring more
        # than one collides on PK. Take the LEXICALLY-LAST artifact
        # (newest archive, by path.parent.name which includes the
        # ISO-8601 timestamp). For genuinely prefixed chunks ('1_foo',
        # 'retry_foo'), 'retry' sorts after numeric so a retry wins —
        # correct.
        chosen = chosen_all[-1:] if chosen_all else []
        table_entries[key] = (best_tier, chosen)

    # Deterministic run label across the selected artifact set
    selected_sha256s = [
        a.sha256 for _, arts in table_entries.values() for a in arts if a.sha256
    ]
    run_label = compute_run_id(selected_sha256s, cluster_fingerprint)

    steps: list[LoadStep] = []
    for d in descriptors:
        if any(d.schema.startswith(p) for p in OUT_OF_SCOPE_SCHEMA_PREFIXES):
            continue
        if only_tier is not None and d.tier != only_tier:
            continue
        if requested_sources is not None and d.source_id not in requested_sources:
            continue

        key = (d.schema, d.table)
        if key in table_entries:
            tier, arts = table_entries[key]
            kind: SourceKind = "pg_dump"
        else:
            tier = "raw"
            arts = []
            kind = "live_fetch"

        steps.append(
            LoadStep(
                source_id=d.source_id,
                target_schema=d.schema,
                target_table=d.table,
                tier=tier,
                kind=kind,
                artifacts=arts,
                depends_on=list(d.depends_on),
                wal_mode=(d.schema, d.table) in WAL_MODE_TABLES,
            )
        )

    # ------------------------------------------------------------------
    # T125 — Auto-merge: any (schema, table) the walker found but that's
    # NOT in SOURCE_LOAD_ORDER gets appended at the tail with empty
    # depends_on. Catches the long-tail spokes (cms_* PUFs, hcs_raw
    # variations) without forcing 122 hand-enumerated SourceDescriptors.
    # ------------------------------------------------------------------
    declared_keys = {(d.schema, d.table) for d in descriptors}
    declared_skipped_by_filter = {
        (d.schema, d.table) for d in descriptors
        if (only_tier is not None and d.tier != only_tier)
        or (requested_sources is not None and d.source_id not in requested_sources)
    }
    for (schema, table), (tier, arts) in table_entries.items():
        if (schema, table) in declared_keys:
            continue  # already emitted above (or filtered out intentionally)
        if any(schema.startswith(p) for p in OUT_OF_SCOPE_SCHEMA_PREFIXES):
            continue
        source_id = f"{schema}.{table}"
        if requested_sources is not None and source_id not in requested_sources:
            continue
        steps.append(
            LoadStep(
                source_id=source_id,
                target_schema=schema,
                target_table=table,
                tier=tier,
                kind="pg_dump",
                artifacts=arts,
                depends_on=[],
                wal_mode=(schema, table) in WAL_MODE_TABLES,
            )
        )
    # Discard the read of declared_skipped_by_filter — kept above only to
    # make the filter intent legible. (Not used; deliberate.)
    _ = declared_skipped_by_filter

    return LoadPlan(
        run_label=run_label,
        sources=steps,
        wal_mode_tables=WAL_MODE_TABLES,
    )


# Internal: tier precedence used by plan_load (silver > bronze > raw, FR-003).
_TIER_RANK: dict[str, int] = {"raw": 0, "bronze": 1, "silver": 2}


# ---------------------------------------------------------------------------
# T041 — propagate_blocked: transitively mark downstream steps as blocked
# ---------------------------------------------------------------------------

def propagate_blocked(
    plan: LoadPlan,
    failed_source_ids: set[str],
) -> dict[str, list[str]]:
    """Compute which steps must be marked ``blocked`` because at least
    one (transitive) ancestor failed or was itself blocked.

    Walks the dependency graph in declared order — since
    :data:`SOURCE_LOAD_ORDER` is already a topological sort by tier and
    by intra-tier declaration order, a single forward pass suffices.

    Args:
        plan: the LoadPlan whose steps to evaluate.
        failed_source_ids: source_ids that already reached a
            non-completed terminal state (failed / no_source_available).

    Returns:
        A mapping from blocked source_id to the list of immediate
        ancestor source_ids that caused the block. Sources without any
        failed ancestor are absent from the mapping.
    """
    blocked: dict[str, list[str]] = {}
    bad: set[str] = set(failed_source_ids)
    for step in plan.sources:
        offenders = [d for d in step.depends_on if d in bad]
        if offenders:
            blocked[step.source_id] = offenders
            bad.add(step.source_id)
    return blocked
