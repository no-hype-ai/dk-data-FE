"""CompetitiveGraphService — N+1/N+2 competitive landscape builder.

Discovers competitors across INDICATION (ClinicalTrials.gov), MOA (OpenFDA),
TARGET (RxNorm), and CLASS (OpenFDA pharm_class_epc) dimensions, then ranks
by threat score.

Auxiliary modules:
- ``normalizer``       — CT.gov intervention-name cleanup
- ``moa_enrichment``   — caller-MOA → FDA pharm_class / targets / ATC mapping
- ``config``           — ``GraphBuildConfig``, ``FailedRequest`` dataclasses
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

from loguru import logger

from....models.competitive_graph import (
    CompetitiveDimension,
    CompetitiveEdge,
    CompetitiveLandscapeGraph,
    CompetitiveNode,
    DevelopmentStage,
    GraphLevel,
)
from ...external_apis.clinicaltrials_client import ClinicalTrial, ClinicalTrialsClient
from ...external_apis.openfda_client import OpenFDAClient
from ...external_apis.rxnorm_client import RxNormClient
from .config import FailedRequest, GraphBuildConfig
from .moa_enrichment import lookup_moa
from .normalizer import normalize_intervention_name


class CompetitiveGraphService:
    """
    Service for building N+1 and N+2 competitive landscape graphs.

    Discovers competitors through multiple dimensions:
    - Indication (same disease/condition)
    - Mechanism of Action (same MOA)
    - Molecular Target (same target)
    - Drug Class (same ATC class)
    """

    # Dimension weights for scoring (from config in production)
    DEFAULT_DIMENSION_WEIGHTS = {
        CompetitiveDimension.INDICATION: 0.35,
        CompetitiveDimension.MOA: 0.30,
        CompetitiveDimension.TARGET: 0.20,
        CompetitiveDimension.CLASS: 0.10,
    }

    # Phase weights for threat scoring
    PHASE_WEIGHTS = {
        DevelopmentStage.APPROVED: 1.0,
        DevelopmentStage.MARKETED: 1.0,
        DevelopmentStage.SUBMITTED: 0.9,
        DevelopmentStage.PHASE_3: 0.8,
        DevelopmentStage.PHASE_2_3: 0.7,
        DevelopmentStage.PHASE_2: 0.6,
        DevelopmentStage.PHASE_1_2: 0.5,
        DevelopmentStage.PHASE_1: 0.4,
        DevelopmentStage.PRECLINICAL: 0.2,
        DevelopmentStage.WITHDRAWN: 0.1,
        DevelopmentStage.DISCONTINUED: 0.05,
    }

    def __init__(
        self,
        openfda_client: OpenFDAClient | None = None,
        clinicaltrials_client: ClinicalTrialsClient | None = None,
        rxnorm_client: RxNormClient | None = None,
        dimension_weights: dict[CompetitiveDimension, float] | None = None,
    ):
        self._openfda = openfda_client or OpenFDAClient()
        self._clinicaltrials = clinicaltrials_client or ClinicalTrialsClient()
        self._rxnorm = rxnorm_client or RxNormClient()
        self._dimension_weights = dimension_weights or self.DEFAULT_DIMENSION_WEIGHTS
        self._failed_requests: list[FailedRequest] = []

    async def build_graph(
        self,
        molecule_id: str,
        molecule_name: str,
        config: GraphBuildConfig | None = None,
        core_node_data: dict[str, Any] | None = None,
        db_pool: Any = None,
    ) -> CompetitiveLandscapeGraph:
        """Build a competitive landscape graph for a molecule.

        Recipe (each step is one named action):
            1. init empty graph
            2. populate core node (N)
            3. populate direct competitors (N+1)
            4. populate competitors-of-competitors (N+2) if depth=2
            5. score threats across all nodes
            6. enrich nodes with generic / brand names
            7. stamp build time
        """
        config = config or GraphBuildConfig()
        start_time = time.time()
        logger.info(f"Building competitive graph for {molecule_name} (depth={config.depth})")

        graph = self._init_graph(molecule_id, config)
        await self._populate_core(
            graph, molecule_id, molecule_name, core_node_data, db_pool
        )
        await self._populate_n_plus_1(graph, config)
        if config.depth >= 2:
            await self._populate_n_plus_2(graph, config)
        await self._calculate_threat_scores(graph)
        await self._enrich_graph_with_names(graph)
        self._stamp_build_time(graph, start_time)
        return graph

    # ── recipe steps ────────────────────────────────────────────────────────

    def _init_graph(
        self, molecule_id: str, config: GraphBuildConfig
    ) -> CompetitiveLandscapeGraph:
        return CompetitiveLandscapeGraph(
            core_molecule_id=molecule_id,
            depth=config.depth,
            min_score=config.min_score,
            dimensions_included=config.dimensions,
        )

    async def _populate_core(
        self,
        graph: CompetitiveLandscapeGraph,
        molecule_id: str,
        molecule_name: str,
        core_node_data: dict[str, Any] | None,
        db_pool: Any = None,
    ) -> None:
        core_node = await self._create_core_node(
            molecule_id, molecule_name, core_node_data, db_pool
        )
        graph.core_molecule = core_node
        graph.add_node(core_node)

    async def _populate_n_plus_1(
        self, graph: CompetitiveLandscapeGraph, config: GraphBuildConfig
    ) -> None:
        competitors = await self._find_competitors(
            graph.core_molecule, GraphLevel.N_PLUS_1, config
        )
        self._absorb_competitors(graph, competitors)
        logger.info(f"Found {len(competitors)} N+1 competitors")

    async def _populate_n_plus_2(
        self, graph: CompetitiveLandscapeGraph, config: GraphBuildConfig
    ) -> None:
        n1_nodes = graph.get_nodes_at_level(GraphLevel.N_PLUS_1)
        results = await asyncio.gather(
            *[self._find_competitors(n, GraphLevel.N_PLUS_2, config) for n in n1_nodes],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"N+2 search failed: {result}")
                continue
            self._absorb_competitors(graph, result)
        logger.info(
            f"Found {len(graph.get_nodes_at_level(GraphLevel.N_PLUS_2))} N+2 competitors"
        )

    def _absorb_competitors(
        self,
        graph: CompetitiveLandscapeGraph,
        competitors: list[tuple],
    ) -> None:
        """Add competitor nodes + their edges into the graph, dedup-safe."""
        for node, edges in competitors:
            if graph.add_node(node):
                for edge in edges:
                    graph.add_edge(edge)

    def _stamp_build_time(
        self, graph: CompetitiveLandscapeGraph, start_time: float
    ) -> None:
        graph.build_time_ms = int((time.time() - start_time) * 1000)
        graph.built_at = datetime.utcnow()
        logger.info(
            f"Graph built in {graph.build_time_ms}ms: "
            f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
        )

    async def _create_core_node(
        self,
        molecule_id: str,
        molecule_name: str,
        data: dict[str, Any] | None = None,
        db_pool: Any = None,
    ) -> CompetitiveNode:
        """Create the core node for the graph."""
        data = data or {}

        # Try to enrich with external data if not provided
        if not data.get("mechanism_of_action"):
            moa = await self._get_moa_from_openfda(molecule_name)
            if moa:
                data["mechanism_of_action"] = moa

        if not data.get("primary_indication"):
            indication = await self._get_primary_indication(molecule_name)
            if indication:
                data["primary_indication"] = indication

        # Resolve generic and brand names if not provided
        generic_name = data.get("generic_name")
        brand_names = data.get("brand_names", [])
        if not generic_name:
            generic_name, brand_names = await self._resolve_drug_names(molecule_name)

        # MOA-driven enrichment: when caller passes a recognized MOA but no
        # targets / ATC codes, fill them in so the TARGET and CLASS fan-out
        # branches have inputs to work with. Also stash an FDA pharm_class
        # hint in metadata for `_find_by_moa` to use instead of the
        # caller's free-text MOA (which OpenFDA's strict label match rejects).
        targets = data.get("targets", []) or []
        atc_codes = data.get("atc_codes", []) or []
        metadata = data.get("metadata", {}) or {}
        moa_enrich = await lookup_moa(
            data.get("mechanism_of_action"),
            db_pool=db_pool,
            openfda_client=self._openfda,
        )
        if moa_enrich:
            if not targets and moa_enrich.targets:
                targets = list(moa_enrich.targets)
            if not atc_codes and moa_enrich.atc_prefix:
                atc_codes = [moa_enrich.atc_prefix]
            if moa_enrich.fda_pharm_class_epc:
                metadata.setdefault(
                    "fda_pharm_class_epc", moa_enrich.fda_pharm_class_epc
                )
            if moa_enrich.fda_pharm_class_moa:
                metadata.setdefault(
                    "fda_pharm_class_moa", moa_enrich.fda_pharm_class_moa
                )

        return CompetitiveNode(
            id=molecule_id,
            name=molecule_name,
            generic_name=generic_name,
            brand_names=brand_names,
            drugbank_id=data.get("drugbank_id"),
            chembl_id=data.get("chembl_id"),
            development_stage=DevelopmentStage(
                data.get("development_stage", "preclinical")
            ),
            mechanism_of_action=data.get("mechanism_of_action"),
            primary_indication=data.get("primary_indication"),
            secondary_indications=data.get("secondary_indications", []),
            atc_codes=atc_codes,
            targets=targets,
            level=GraphLevel.CORE,
            sponsor=data.get("sponsor"),
            originator=data.get("originator"),
            metadata=metadata,
        )

    async def _find_competitors(
        self,
        source_node: CompetitiveNode,
        target_level: GraphLevel,
        config: GraphBuildConfig,
    ) -> list[tuple[CompetitiveNode, list[CompetitiveEdge]]]:
        """
        Find competitors for a node across all configured dimensions.

        Returns list of (node, edges) tuples.
        """
        competitors: dict[str, tuple[CompetitiveNode, list[CompetitiveEdge]]] = {}

        # Run searches in parallel for each dimension
        search_tasks = []

        if CompetitiveDimension.INDICATION in config.dimensions:
            search_tasks.append(
                self._find_by_indication(source_node, target_level, config)
            )

        if CompetitiveDimension.MOA in config.dimensions:
            search_tasks.append(self._find_by_moa(source_node, target_level, config))

        if CompetitiveDimension.TARGET in config.dimensions:
            search_tasks.append(self._find_by_target(source_node, target_level, config))

        if CompetitiveDimension.CLASS in config.dimensions:
            search_tasks.append(self._find_by_class(source_node, target_level, config))

        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Merge results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Dimension search failed: {result}")
                continue

            for node, edges in result:
                if node.id in competitors:
                    # Merge edges and metadata for existing competitor
                    existing_node, existing_edges = competitors[node.id]
                    existing_edges.extend(edges)
                    # Merge metadata
                    self._merge_node_metadata(existing_node, node)
                else:
                    competitors[node.id] = (node, edges)

        return list(competitors.values())

    async def _find_by_indication(
        self,
        source_node: CompetitiveNode,
        target_level: GraphLevel,
        config: GraphBuildConfig,
    ) -> list[tuple[CompetitiveNode, list[CompetitiveEdge]]]:
        """
        Find competitors by shared indication.

        Iterates over `primary_indication` + `secondary_indications`, queries
        ClinicalTrials.gov per indication, normalizes intervention strings
        into INN candidates, validates each via RxNorm, drops trials below
        the configured phase floor, and dedupes across indications.
        """
        indications = [
            i
            for i in (
                [source_node.primary_indication] + source_node.secondary_indications
            )
            if i
        ]
        if not indications:
            return []

        min_rank = config.min_trial_phase.rank
        source_name_lc = source_node.name.lower()
        source_generic_lc = (source_node.generic_name or "").lower()
        per_dim_cap = config.max_competitors_per_dimension

        # Scale per-indication page size by indication count so total trial
        # volume stays bounded. Floor at 5 to keep each indication useful.
        per_ind_pages = max(5, per_dim_cap // max(1, len(indications)))

        # ── 1. Fan out CT.gov queries in parallel, one per indication ──
        trial_lists = await asyncio.gather(
            *[
                self._clinicaltrials.search_by_condition(
                    condition=ind,
                    page_size=per_ind_pages,
                )
                for ind in indications
            ],
            return_exceptions=True,
        )

        # ── 2. Flatten (indication, trial) pairs, apply phase floor ──
        pairs: list[tuple[str, Any, DevelopmentStage]] = []
        for indication, trials in zip(indications, trial_lists):
            if isinstance(trials, Exception):
                logger.error(f"Indication search failed ({indication}): {trials}")
                self._queue_failed_request(
                    "clinicaltrials",
                    indication,
                    CompetitiveDimension.INDICATION,
                    str(trials),
                    config,
                )
                continue
            for trial in trials or []:
                trial_stage = self._trial_phase_to_stage(
                    trial.phase.value if trial.phase else ""
                )
                if trial_stage.rank < min_rank:
                    continue
                pairs.append((indication, trial, trial_stage))

        # ── 3. Collect unique normalized drug candidates (first-seen wins) ──
        # Map[drug_lc] -> (original_name, indication, trial, stage)
        candidates: dict[str, tuple[str, str, Any, DevelopmentStage]] = {}
        for indication, trial, trial_stage in pairs:
            for intervention in trial.interventions:
                if intervention.intervention_type not in ("DRUG", "BIOLOGICAL"):
                    continue
                for drug_name in normalize_intervention_name(intervention.name):
                    drug_lc = drug_name.lower()
                    if drug_lc in (source_name_lc, source_generic_lc):
                        continue
                    if drug_lc not in candidates:
                        candidates[drug_lc] = (
                            drug_name,
                            indication,
                            trial,
                            trial_stage,
                        )

        if not candidates:
            return []

        # Pre-trim candidates before paying RxNorm cost. Keep a 3x buffer so
        # validation failures still leave enough survivors to hit per_dim_cap.
        if len(candidates) > per_dim_cap * 3:
            candidates = dict(list(candidates.items())[: per_dim_cap * 3])

        # ── 4. Fan out RxNorm validation in parallel ──
        if config.validate_intervention_names:
            items = list(candidates.items())
            rxcuis = await asyncio.gather(
                *[self._rxnorm.get_rxcui(drug_name) for _, (drug_name, *_) in items],
                return_exceptions=True,
            )
            candidates = {
                key: ctx
                for (key, ctx), rxcui in zip(items, rxcuis)
                if not isinstance(rxcui, Exception) and rxcui
            }

        # ── 5. Build nodes + edges (insertion-ordered, capped) ──
        results: list[tuple[CompetitiveNode, list[CompetitiveEdge]]] = []
        for drug_lc, (drug_name, indication, trial, trial_stage) in candidates.items():
            if len(results) >= per_dim_cap:
                break
            sponsor_name = trial.lead_sponsor.name if trial.lead_sponsor else None
            trial_link = {
                "nct_id": trial.nct_id,
                "title": getattr(trial, "brief_title", None) or trial.official_title,
                "phase": trial.phase.value if trial.phase else None,
                "status": (
                    trial.overall_status.value if trial.overall_status else None
                ),
                "url": f"https://clinicaltrials.gov/study/{trial.nct_id}",
            }
            node = CompetitiveNode(
                id=f"drug_{drug_lc.replace(' ', '_')}",
                name=drug_name,
                level=target_level,
                primary_indication=indication,
                development_stage=trial_stage,
                sponsor=sponsor_name,
                discovered_via=[f"indication:{indication}"],
                metadata={
                    "linked_trials": [trial_link],
                    "external_links": {
                        "clinicaltrials_gov": (
                            "https://clinicaltrials.gov/search?term="
                            f"{drug_name.replace(' ', '+')}"
                        ),
                    },
                },
            )
            edge = CompetitiveEdge(
                source_id=source_node.id,
                target_id=node.id,
                dimension=CompetitiveDimension.INDICATION,
                score=self._calculate_indication_score_from_trial(
                    trial, source_node, node
                ),
                discovered_via=f"ClinicalTrials.gov:{trial.nct_id}",
                evidence=[f"Trial: {trial.nct_id}"],
            )
            results.append((node, [edge]))

        return results

    async def _find_by_moa(
        self,
        source_node: CompetitiveNode,
        target_level: GraphLevel,
        config: GraphBuildConfig,
    ) -> list[tuple[CompetitiveNode, list[CompetitiveEdge]]]:
        """
        Find competitors by shared mechanism of action.

        OpenFDA's pharm_class_moa / pharm_class_epc fields require strict
        label strings (e.g. "Tumor Necrosis Factor Blocker [EPC]"), not
        free-text MOA. Prefer the enriched pharm_class from `lookup_moa`
        stashed in `source_node.metadata` over the caller's raw MOA.
        """
        results = []
        moa = source_node.mechanism_of_action
        meta = source_node.metadata or {}
        pharm_class = meta.get("fda_pharm_class_epc") or meta.get("fda_pharm_class_moa")
        class_type = "epc" if meta.get("fda_pharm_class_epc") else "moa"
        query = pharm_class or moa

        if not query:
            return results

        try:
            fda_response = await self._openfda.search_by_pharm_class(
                pharm_class=query,
                class_type=class_type,
                limit=config.max_competitors_per_dimension,
            )

            if not fda_response.success:
                self._queue_failed_request(
                    "openfda",
                    moa,
                    CompetitiveDimension.MOA,
                    fda_response.error or "Unknown error",
                    config,
                )
                return results

            drugs = fda_response.data.get("drugs", [])
            seen_drugs: set[str] = set()

            for drug in drugs:
                drug_name = drug.get("generic_name") or drug.get("brand_name", "")
                if not drug_name or drug_name.lower() == source_node.name.lower():
                    continue
                if drug_name in seen_drugs:
                    continue

                seen_drugs.add(drug_name)

                # Build FDA label link data
                application_number = drug.get("application_number")
                fda_link = None
                if application_number:
                    fda_link = {
                        "application_number": application_number,
                        "generic_name": drug.get("generic_name"),
                        "brand_name": drug.get("brand_name"),
                        "manufacturer_name": drug.get("manufacturer_name"),
                        "url": f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={application_number.replace('NDA', '').replace('BLA', '').replace('ANDA', '')}",
                    }

                # Build external links
                external_links = {
                    "openfda": f'https://api.fda.gov/drug/label.json?search=openfda.generic_name:"{drug_name}"',
                    "dailymed": f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?query={drug_name.replace(' ', '+')}",
                }

                node = CompetitiveNode(
                    id=f"drug_{drug_name.lower().replace(' ', '_')}",
                    name=drug_name,
                    generic_name=drug.get("generic_name"),
                    brand_names=[drug.get("brand_name")]
                    if drug.get("brand_name")
                    else [],
                    level=target_level,
                    mechanism_of_action=moa,
                    development_stage=DevelopmentStage.APPROVED,  # OpenFDA = approved
                    discovered_via=[f"moa:{moa}"],
                    sponsor=drug.get("manufacturer_name"),
                    metadata={
                        "fda_labels": [fda_link] if fda_link else [],
                        "external_links": external_links,
                    },
                )

                edge = CompetitiveEdge(
                    source_id=source_node.id,
                    target_id=node.id,
                    dimension=CompetitiveDimension.MOA,
                    score=self._calculate_moa_score(drug, source_node, node),
                    discovered_via="OpenFDA:pharm_class_moa",
                    evidence=[f"MOA: {moa}"],
                )

                results.append((node, [edge]))

                if len(results) >= config.max_competitors_per_dimension:
                    break

        except Exception as e:
            logger.error(f"MOA search failed: {e}")
            self._queue_failed_request(
                "openfda", moa, CompetitiveDimension.MOA, str(e), config
            )

        return results

    async def _find_by_target(
        self,
        source_node: CompetitiveNode,
        target_level: GraphLevel,
        config: GraphBuildConfig,
    ) -> list[tuple[CompetitiveNode, list[CompetitiveEdge]]]:
        """
        Find competitors by shared molecular target.

        Uses RxNorm and UMLS to find drugs targeting same protein.
        """
        results = []
        targets = source_node.targets

        if not targets:
            return results

        try:
            for target in targets[:3]:  # Limit to top 3 targets
                # Search RxNorm for related drugs
                rxnorm_response = await self._rxnorm.search_by_ingredient_class(
                    target, limit=config.max_competitors_per_dimension // 3
                )

                if not rxnorm_response.success:
                    continue

                drugs = rxnorm_response.data.get("drugs", [])
                seen_drugs: set[str] = set()

                for drug in drugs:
                    drug_name = drug.get("name", "")
                    if not drug_name or drug_name.lower() == source_node.name.lower():
                        continue
                    if drug_name in seen_drugs:
                        continue

                    seen_drugs.add(drug_name)

                    node = CompetitiveNode(
                        id=f"drug_{drug_name.lower().replace(' ', '_')}",
                        name=drug_name,
                        level=target_level,
                        targets=[target],
                        discovered_via=[f"target:{target}"],
                    )

                    edge = CompetitiveEdge(
                        source_id=source_node.id,
                        target_id=node.id,
                        dimension=CompetitiveDimension.TARGET,
                        score=self._calculate_target_score(target, source_node, node),
                        discovered_via="RxNorm:ingredient_class",
                        evidence=[f"Target: {target}"],
                    )

                    results.append((node, [edge]))

        except Exception as e:
            logger.error(f"Target search failed: {e}")
            self._queue_failed_request(
                "rxnorm", str(targets), CompetitiveDimension.TARGET, str(e), config
            )

        return results

    async def _find_by_class(
        self,
        source_node: CompetitiveNode,
        target_level: GraphLevel,
        config: GraphBuildConfig,
    ) -> list[tuple[CompetitiveNode, list[CompetitiveEdge]]]:
        """
        Find competitors by shared ATC drug class.

        Uses OpenFDA pharm_class_epc field.
        """
        results = []
        atc_codes = source_node.atc_codes

        if not atc_codes:
            return results

        try:
            # Use first ATC code at level 3 (pharmacological subgroup)
            atc_prefix = atc_codes[0][:4] if atc_codes else None
            if not atc_prefix:
                return results

            fda_response = await self._openfda.search_by_pharm_class(
                pharm_class=atc_prefix,
                class_type="epc",
                limit=config.max_competitors_per_dimension,
            )

            if not fda_response.success:
                return results

            drugs = fda_response.data.get("drugs", [])
            seen_drugs: set[str] = set()

            for drug in drugs:
                drug_name = drug.get("generic_name") or drug.get("brand_name", "")
                if not drug_name or drug_name.lower() == source_node.name.lower():
                    continue
                if drug_name in seen_drugs:
                    continue

                seen_drugs.add(drug_name)

                node = CompetitiveNode(
                    id=f"drug_{drug_name.lower().replace(' ', '_')}",
                    name=drug_name,
                    level=target_level,
                    atc_codes=[atc_prefix],
                    development_stage=DevelopmentStage.APPROVED,
                    discovered_via=[f"class:{atc_prefix}"],
                )

                edge = CompetitiveEdge(
                    source_id=source_node.id,
                    target_id=node.id,
                    dimension=CompetitiveDimension.CLASS,
                    score=0.5,  # Default class score
                    discovered_via="OpenFDA:pharm_class_epc",
                    evidence=[f"ATC: {atc_prefix}"],
                )

                results.append((node, [edge]))

                if len(results) >= config.max_competitors_per_dimension:
                    break

        except Exception as e:
            logger.error(f"Class search failed: {e}")

        return results

    async def _calculate_threat_scores(self, graph: CompetitiveLandscapeGraph) -> None:
        """Calculate threat scores for all competitors in the graph."""
        for node in graph.nodes.values():
            if node.level == GraphLevel.CORE:
                continue

            # Get edges for this node
            edges = graph.get_edges_for_node(node.id)

            # Calculate dimension-weighted score
            dimension_scores: dict[CompetitiveDimension, float] = {}
            for edge in edges:
                if edge.dimension not in dimension_scores:
                    dimension_scores[edge.dimension] = edge.score
                else:
                    dimension_scores[edge.dimension] = max(
                        dimension_scores[edge.dimension], edge.score
                    )

            # Weighted average
            weighted_sum = 0.0
            weight_sum = 0.0
            for dim, score in dimension_scores.items():
                weight = self._dimension_weights.get(dim, 0.1)
                weighted_sum += score * weight
                weight_sum += weight

            base_score = weighted_sum / weight_sum if weight_sum > 0 else 0.0

            # Apply phase multiplier
            phase_multiplier = self.PHASE_WEIGHTS.get(node.development_stage, 0.5)
            node.threat_score = round(base_score * phase_multiplier, 3)

    def _calculate_indication_score_from_trial(
        self,
        trial: "ClinicalTrial",
        source: CompetitiveNode,
        target: CompetitiveNode,
    ) -> float:
        """Calculate competitive score based on indication match (ClinicalTrial object)."""
        from ...external_apis.clinicaltrials_client import TrialStatus

        base_score = 0.7  # Base score for same indication

        # Boost for same phase or later
        if target.development_stage.rank >= source.development_stage.rank:
            base_score += 0.1

        # Boost for recruiting trials (active competition)
        if trial.overall_status in [
            TrialStatus.RECRUITING,
            TrialStatus.ACTIVE_NOT_RECRUITING,
        ]:
            base_score += 0.1

        return min(1.0, base_score)

    def _calculate_moa_score(
        self,
        drug: dict,
        source: CompetitiveNode,
        target: CompetitiveNode,
    ) -> float:
        """Calculate competitive score based on MOA match."""
        base_score = 0.6  # Base score for same MOA

        # Approved drugs are higher threat
        if target.development_stage in [
            DevelopmentStage.APPROVED,
            DevelopmentStage.MARKETED,
        ]:
            base_score += 0.2

        return min(1.0, base_score)

    def _calculate_target_score(
        self,
        target: str,
        source: CompetitiveNode,
        target_node: CompetitiveNode,
    ) -> float:
        """Calculate competitive score based on target match."""
        return 0.5  # Base score for target match

    async def _get_moa_from_openfda(self, drug_name: str) -> str | None:
        """Look up MOA from OpenFDA."""
        try:
            moas = await self._openfda.get_mechanism_of_action(drug_name)
            if moas:
                return moas[0]
        except Exception as e:
            logger.warning(f"Failed to get MOA for {drug_name}: {e}")
        return None

    async def _get_primary_indication(self, drug_name: str) -> str | None:
        """Look up primary indication."""
        try:
            indications = await self._openfda.get_indications(drug_name)
            if indications:
                # Return first indication, truncated to reasonable length
                return indications[0][:300] if indications[0] else None
        except Exception as e:
            logger.warning(f"Failed to get indication for {drug_name}: {e}")
        return None

    def _trial_phase_to_stage(self, phase: str) -> DevelopmentStage:
        """Convert ClinicalTrials.gov phase to DevelopmentStage."""
        phase_map = {
            "EARLY_PHASE1": DevelopmentStage.PHASE_1,
            "PHASE1": DevelopmentStage.PHASE_1,
            "PHASE1/PHASE2": DevelopmentStage.PHASE_1_2,
            "PHASE2": DevelopmentStage.PHASE_2,
            "PHASE2/PHASE3": DevelopmentStage.PHASE_2_3,
            "PHASE3": DevelopmentStage.PHASE_3,
            "PHASE4": DevelopmentStage.MARKETED,
            "NA": DevelopmentStage.PRECLINICAL,
        }
        return phase_map.get(phase, DevelopmentStage.PRECLINICAL)

    def _queue_failed_request(
        self,
        source: str,
        query: str,
        dimension: CompetitiveDimension,
        error: str,
        config: GraphBuildConfig,
    ) -> None:
        """Queue a failed request for retry."""
        if not config.queue_failed_requests:
            return

        self._failed_requests.append(
            FailedRequest(
                source=source,
                query=query,
                dimension=dimension,
                error=error,
            )
        )

    async def _resolve_drug_names(
        self,
        drug_name: str,
    ) -> tuple[str | None, list[str]]:
        """
        Resolve generic and brand names for a drug using RxNorm.

        Args:
            drug_name: The drug name to look up

        Returns:
            Tuple of (generic_name, list of brand_names)
        """
        generic_name = None
        brand_names = []

        try:
            # Get RXCUI for the drug
            rxcui = await self._rxnorm.get_rxcui(drug_name)
            if not rxcui:
                # Name might already be the generic name
                return drug_name, []

            # Get concept to determine if brand or generic
            concept = await self._rxnorm.get_concept(rxcui)
            if concept:
                name = concept.name

                # SBD = Semantic Branded Drug, SCD = Semantic Clinical Drug
                # BN = Brand Name, IN = Ingredient (generic)
                if concept.is_brand():
                    # This is a brand name, get related generic (ingredients)
                    brand_names.append(name)
                    ingredients = await self._rxnorm.get_ingredients(rxcui)
                    if ingredients:
                        generic_name = ingredients[0].name
                elif concept.is_ingredient() or concept.is_clinical_drug():
                    # This is a generic name, get brand names
                    generic_name = name
                    brands = await self._rxnorm.get_brands(rxcui)
                    brand_names = [b.name for b in brands[:5] if b.name]
                else:
                    # Unknown type, treat as-is and try to get brands
                    generic_name = name
                    brands = await self._rxnorm.get_brands(rxcui)
                    brand_names = [b.name for b in brands[:5] if b.name]

        except Exception as e:
            logger.debug(f"Name resolution failed for {drug_name}: {e}")
            # If resolution fails, use the original name as generic
            generic_name = drug_name

        return generic_name, brand_names

    async def _enrich_node_with_names(self, node: CompetitiveNode) -> None:
        """
        Enrich a competitor node with generic and brand names.

        Modifies the node in place.
        """
        try:
            generic_name, brand_names = await self._resolve_drug_names(node.name)
            if generic_name:
                node.generic_name = generic_name
            if brand_names:
                node.brand_names = brand_names
        except Exception as e:
            logger.debug(f"Failed to enrich names for {node.name}: {e}")

    async def _enrich_graph_with_names(
        self,
        graph: CompetitiveLandscapeGraph,
        max_concurrent: int = 10,
    ) -> None:
        """
        Enrich all nodes in the graph with generic and brand names.

        Uses concurrent requests with rate limiting.
        """
        import asyncio

        nodes_to_enrich = [
            node
            for node in graph.nodes.values()
            if node.level != GraphLevel.CORE  # Skip core node (already has names)
        ]

        if not nodes_to_enrich:
            return

        logger.info(f"Enriching {len(nodes_to_enrich)} nodes with generic/brand names")

        # Use semaphore for rate limiting
        semaphore = asyncio.Semaphore(max_concurrent)

        async def enrich_with_limit(node: CompetitiveNode) -> None:
            async with semaphore:
                await self._enrich_node_with_names(node)

        # Run enrichment concurrently
        await asyncio.gather(
            *[enrich_with_limit(node) for node in nodes_to_enrich],
            return_exceptions=True,
        )

        logger.info("Finished enriching nodes with names")

    def _merge_node_metadata(
        self,
        existing_node: CompetitiveNode,
        new_node: CompetitiveNode,
    ) -> None:
        """
        Merge metadata from a new node into an existing node.

        This is called when the same competitor is discovered via multiple dimensions.
        Merges linked trials, FDA labels, and external links.
        """
        if not new_node.metadata:
            return

        if not existing_node.metadata:
            existing_node.metadata = {}

        # Merge linked trials
        existing_trials = existing_node.metadata.get("linked_trials", [])
        new_trials = new_node.metadata.get("linked_trials", [])
        if new_trials:
            existing_nct_ids = {t.get("nct_id") for t in existing_trials}
            for trial in new_trials:
                if trial.get("nct_id") not in existing_nct_ids:
                    existing_trials.append(trial)
            existing_node.metadata["linked_trials"] = existing_trials

        # Merge FDA labels
        existing_labels = existing_node.metadata.get("fda_labels", [])
        new_labels = new_node.metadata.get("fda_labels", [])
        if new_labels:
            existing_app_nums = {
                lbl.get("application_number") for lbl in existing_labels if lbl
            }
            for label in new_labels:
                if label and label.get("application_number") not in existing_app_nums:
                    existing_labels.append(label)
            existing_node.metadata["fda_labels"] = existing_labels

        # Merge external links
        existing_links = existing_node.metadata.get("external_links", {})
        new_links = new_node.metadata.get("external_links", {})
        if new_links:
            for key, url in new_links.items():
                if key not in existing_links:
                    existing_links[key] = url
            existing_node.metadata["external_links"] = existing_links

        # Merge discovered_via paths
        existing_node.discovered_via.extend(
            path
            for path in new_node.discovered_via
            if path not in existing_node.discovered_via
        )

        # Update generic/brand names if not already set
        if not existing_node.generic_name and new_node.generic_name:
            existing_node.generic_name = new_node.generic_name
        if not existing_node.brand_names and new_node.brand_names:
            existing_node.brand_names = new_node.brand_names

    # ════════════════════════════════════════════════════════════════════════
    # ▼▼▼ PARKED — not used by the competitor-search endpoint ▼▼▼
    #
    # The methods below are kept only to satisfy the contract of legacy
    # consumers (currently the unmounted `/api/v1/graph/*` routes in
    # `api/routes/graph.py`). They are NOT exercised by any live endpoint
    # in this PR and have not been validated. Treat as scaffolding —
    # don't extend, don't take their return value at face value.
    # ════════════════════════════════════════════════════════════════════════

    async def get_competitors(
        self,
        molecule_id: str,
        level: GraphLevel | None = None,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Placeholder — returns []. Would load from DB/cache in production."""
        return []
