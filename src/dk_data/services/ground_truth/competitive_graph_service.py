"""
Competitive Graph Service.

Implements T033-T044: CompetitiveGraphService for N+1/N+2 competitive landscape building.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Any
from loguru import logger

from ...models.competitive_graph import (
    CompetitiveNode,
    CompetitiveEdge,
    CompetitiveLandscapeGraph,
    CompetitiveDimension,
    GraphLevel,
    DevelopmentStage,
)
from ..external_apis.openfda_client import OpenFDAClient
from ..external_apis.clinicaltrials_client import ClinicalTrialsClient, ClinicalTrial
from ..external_apis.rxnorm_client import RxNormClient
from ..external_apis.umls_client import UMLSClient


@dataclass
class GraphBuildConfig:
    """Configuration for building competitive graphs."""
    depth: int = 1  # 1 = N+1 only, 2 = N+2
    min_score: float = 0.1
    dimensions: List[CompetitiveDimension] = field(
        default_factory=lambda: [
            CompetitiveDimension.INDICATION,
            CompetitiveDimension.MOA,
            CompetitiveDimension.TARGET,
        ]
    )
    max_competitors_per_dimension: int = 50
    include_preclinical: bool = False
    queue_failed_requests: bool = True


@dataclass
class FailedRequest:
    """A failed API request to retry later."""
    source: str
    query: str
    dimension: CompetitiveDimension
    error: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    retry_count: int = 0


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
        CompetitiveDimension.STAGE: 0.05,
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
        openfda_client: Optional[OpenFDAClient] = None,
        clinicaltrials_client: Optional[ClinicalTrialsClient] = None,
        rxnorm_client: Optional[RxNormClient] = None,
        umls_client: Optional[UMLSClient] = None,
        dimension_weights: Optional[Dict[CompetitiveDimension, float]] = None,
    ):
        self._openfda = openfda_client or OpenFDAClient()
        self._clinicaltrials = clinicaltrials_client or ClinicalTrialsClient()
        self._rxnorm = rxnorm_client or RxNormClient()
        self._umls = umls_client
        self._dimension_weights = dimension_weights or self.DEFAULT_DIMENSION_WEIGHTS
        self._failed_requests: List[FailedRequest] = []

    async def build_graph(
        self,
        molecule_id: str,
        molecule_name: str,
        config: Optional[GraphBuildConfig] = None,
        core_node_data: Optional[Dict[str, Any]] = None,
    ) -> CompetitiveLandscapeGraph:
        """
        Build a competitive landscape graph for a molecule.

        Args:
            molecule_id: Unique identifier for the molecule
            molecule_name: Name of the molecule (INN or brand)
            config: Build configuration
            core_node_data: Optional pre-populated data for core node

        Returns:
            CompetitiveLandscapeGraph with N+1 (and optionally N+2) competitors
        """
        config = config or GraphBuildConfig()
        start_time = time.time()

        logger.info(f"Building competitive graph for {molecule_name} (depth={config.depth})")

        # Initialize graph
        graph = CompetitiveLandscapeGraph(
            core_molecule_id=molecule_id,
            depth=config.depth,
            min_score=config.min_score,
            dimensions_included=config.dimensions,
        )

        # Create and add core node
        core_node = await self._create_core_node(
            molecule_id, molecule_name, core_node_data
        )
        graph.core_molecule = core_node
        graph.add_node(core_node)

        # Find N+1 competitors
        n_plus_1_nodes = await self._find_competitors(
            core_node, GraphLevel.N_PLUS_1, config
        )

        for node, edges in n_plus_1_nodes:
            if graph.add_node(node):
                for edge in edges:
                    graph.add_edge(edge)

        logger.info(f"Found {len(n_plus_1_nodes)} N+1 competitors")

        # Find N+2 competitors if depth=2
        if config.depth >= 2:
            n_plus_1_list = graph.get_nodes_at_level(GraphLevel.N_PLUS_1)
            n_plus_2_tasks = []

            for n1_node in n_plus_1_list:
                n_plus_2_tasks.append(
                    self._find_competitors(n1_node, GraphLevel.N_PLUS_2, config)
                )

            n_plus_2_results = await asyncio.gather(*n_plus_2_tasks, return_exceptions=True)

            for result in n_plus_2_results:
                if isinstance(result, Exception):
                    logger.error(f"N+2 search failed: {result}")
                    continue
                for node, edges in result:
                    if graph.add_node(node):
                        for edge in edges:
                            graph.add_edge(edge)

            logger.info(f"Found {len(graph.get_nodes_at_level(GraphLevel.N_PLUS_2))} N+2 competitors")

        # Calculate threat scores for all competitors
        await self._calculate_threat_scores(graph)

        # Enrich nodes with generic and brand names
        await self._enrich_graph_with_names(graph)

        # Record build time
        graph.build_time_ms = int((time.time() - start_time) * 1000)
        graph.built_at = datetime.utcnow()

        logger.info(
            f"Graph built in {graph.build_time_ms}ms: "
            f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
        )

        return graph

    async def _create_core_node(
        self,
        molecule_id: str,
        molecule_name: str,
        data: Optional[Dict[str, Any]] = None,
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
            atc_codes=data.get("atc_codes", []),
            targets=data.get("targets", []),
            level=GraphLevel.CORE,
            sponsor=data.get("sponsor"),
            originator=data.get("originator"),
        )

    async def _find_competitors(
        self,
        source_node: CompetitiveNode,
        target_level: GraphLevel,
        config: GraphBuildConfig,
    ) -> List[tuple[CompetitiveNode, List[CompetitiveEdge]]]:
        """
        Find competitors for a node across all configured dimensions.

        Returns list of (node, edges) tuples.
        """
        competitors: Dict[str, tuple[CompetitiveNode, List[CompetitiveEdge]]] = {}

        # Run searches in parallel for each dimension
        search_tasks = []

        if CompetitiveDimension.INDICATION in config.dimensions:
            search_tasks.append(
                self._find_by_indication(source_node, target_level, config)
            )

        if CompetitiveDimension.MOA in config.dimensions:
            search_tasks.append(
                self._find_by_moa(source_node, target_level, config)
            )

        if CompetitiveDimension.TARGET in config.dimensions:
            search_tasks.append(
                self._find_by_target(source_node, target_level, config)
            )

        if CompetitiveDimension.CLASS in config.dimensions:
            search_tasks.append(
                self._find_by_class(source_node, target_level, config)
            )

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
    ) -> List[tuple[CompetitiveNode, List[CompetitiveEdge]]]:
        """
        Find competitors by shared indication.

        Uses ClinicalTrials.gov to find drugs in trials for the same condition.
        """
        results = []
        indication = source_node.primary_indication

        if not indication:
            return results

        try:
            # Search ClinicalTrials.gov for trials with same condition
            trials = await self._clinicaltrials.search_by_condition(
                condition=indication,
                page_size=config.max_competitors_per_dimension,
            )

            if not trials:
                return results

            # Extract unique interventions
            seen_drugs: Set[str] = set()

            for trial in trials:
                for intervention in trial.interventions:
                    # Check for drug or biological interventions
                    if intervention.intervention_type not in ["DRUG", "BIOLOGICAL"]:
                        continue

                    drug_name = intervention.name.strip()
                    if not drug_name or drug_name.lower() == source_node.name.lower():
                        continue
                    if drug_name in seen_drugs:
                        continue

                    seen_drugs.add(drug_name)

                    # Get sponsor name
                    sponsor_name = trial.lead_sponsor.name if trial.lead_sponsor else None

                    # Build trial link data
                    trial_link = {
                        "nct_id": trial.nct_id,
                        "title": trial.brief_title if hasattr(trial, 'brief_title') else trial.official_title,
                        "phase": trial.phase.value if trial.phase else None,
                        "status": trial.overall_status.value if trial.overall_status else None,
                        "url": f"https://clinicaltrials.gov/study/{trial.nct_id}",
                    }

                    # Create competitor node with linked data
                    node = CompetitiveNode(
                        id=f"drug_{drug_name.lower().replace(' ', '_')}",
                        name=drug_name,
                        level=target_level,
                        primary_indication=indication,
                        development_stage=self._trial_phase_to_stage(
                            trial.phase.value if trial.phase else ""
                        ),
                        sponsor=sponsor_name,
                        discovered_via=[f"indication:{indication}"],
                        metadata={
                            "linked_trials": [trial_link],
                            "external_links": {
                                "clinicaltrials_gov": f"https://clinicaltrials.gov/search?term={drug_name.replace(' ', '+')}",
                            },
                        },
                    )

                    # Create edge
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

                    if len(results) >= config.max_competitors_per_dimension:
                        break

        except Exception as e:
            logger.error(f"Indication search failed: {e}")
            self._queue_failed_request(
                "clinicaltrials", indication, CompetitiveDimension.INDICATION,
                str(e), config
            )

        return results

    async def _find_by_moa(
        self,
        source_node: CompetitiveNode,
        target_level: GraphLevel,
        config: GraphBuildConfig,
    ) -> List[tuple[CompetitiveNode, List[CompetitiveEdge]]]:
        """
        Find competitors by shared mechanism of action.

        Uses OpenFDA pharm_class_moa field.
        """
        results = []
        moa = source_node.mechanism_of_action

        if not moa:
            return results

        try:
            # Search OpenFDA for drugs with same MOA
            fda_response = await self._openfda.search_by_pharm_class(
                pharm_class=moa,
                class_type="moa",
                limit=config.max_competitors_per_dimension,
            )

            if not fda_response.success:
                self._queue_failed_request(
                    "openfda", moa, CompetitiveDimension.MOA,
                    fda_response.error or "Unknown error", config
                )
                return results

            drugs = fda_response.data.get("drugs", [])
            seen_drugs: Set[str] = set()

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
                    "openfda": f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{drug_name}\"",
                    "dailymed": f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?query={drug_name.replace(' ', '+')}",
                }

                node = CompetitiveNode(
                    id=f"drug_{drug_name.lower().replace(' ', '_')}",
                    name=drug_name,
                    generic_name=drug.get("generic_name"),
                    brand_names=[drug.get("brand_name")] if drug.get("brand_name") else [],
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
    ) -> List[tuple[CompetitiveNode, List[CompetitiveEdge]]]:
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
                seen_drugs: Set[str] = set()

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
    ) -> List[tuple[CompetitiveNode, List[CompetitiveEdge]]]:
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
            seen_drugs: Set[str] = set()

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
            dimension_scores: Dict[CompetitiveDimension, float] = {}
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

    def _calculate_indication_score(
        self,
        trial: Dict,
        source: CompetitiveNode,
        target: CompetitiveNode,
    ) -> float:
        """Calculate competitive score based on indication match (dict-based trial)."""
        base_score = 0.7  # Base score for same indication

        # Boost for same phase or later
        target_phase = self._trial_phase_to_stage(trial.get("phase", ""))
        if target_phase.value >= source.development_stage.value:
            base_score += 0.1

        # Boost for recruiting trials (active competition)
        if trial.get("status") == "RECRUITING":
            base_score += 0.1

        return min(1.0, base_score)

    def _calculate_indication_score_from_trial(
        self,
        trial: "ClinicalTrial",
        source: CompetitiveNode,
        target: CompetitiveNode,
    ) -> float:
        """Calculate competitive score based on indication match (ClinicalTrial object)."""
        from ..external_apis.clinicaltrials_client import TrialStatus

        base_score = 0.7  # Base score for same indication

        # Boost for same phase or later
        if target.development_stage.value >= source.development_stage.value:
            base_score += 0.1

        # Boost for recruiting trials (active competition)
        if trial.overall_status in [TrialStatus.RECRUITING, TrialStatus.ACTIVE_NOT_RECRUITING]:
            base_score += 0.1

        return min(1.0, base_score)

    def _calculate_moa_score(
        self,
        drug: Dict,
        source: CompetitiveNode,
        target: CompetitiveNode,
    ) -> float:
        """Calculate competitive score based on MOA match."""
        base_score = 0.6  # Base score for same MOA

        # Approved drugs are higher threat
        if target.development_stage in [DevelopmentStage.APPROVED, DevelopmentStage.MARKETED]:
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

    async def _get_moa_from_openfda(self, drug_name: str) -> Optional[str]:
        """Look up MOA from OpenFDA."""
        try:
            moas = await self._openfda.get_mechanism_of_action(drug_name)
            if moas:
                return moas[0]
        except Exception as e:
            logger.warning(f"Failed to get MOA for {drug_name}: {e}")
        return None

    async def _get_primary_indication(self, drug_name: str) -> Optional[str]:
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

    def get_failed_requests(self) -> List[FailedRequest]:
        """Get list of failed requests."""
        return self._failed_requests

    def clear_failed_requests(self) -> None:
        """Clear failed requests queue."""
        self._failed_requests = []

    async def get_competitors(
        self,
        molecule_id: str,
        level: Optional[GraphLevel] = None,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Get competitors for a molecule from cached graph.

        For production, this would load from database/cache.
        """
        # This would typically load from database
        # Placeholder implementation
        return []

    async def _resolve_drug_names(
        self,
        drug_name: str,
    ) -> tuple[Optional[str], List[str]]:
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
            node for node in graph.nodes.values()
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
            existing_app_nums = {lbl.get("application_number") for lbl in existing_labels if lbl}
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
            path for path in new_node.discovered_via
            if path not in existing_node.discovered_via
        )

        # Update generic/brand names if not already set
        if not existing_node.generic_name and new_node.generic_name:
            existing_node.generic_name = new_node.generic_name
        if not existing_node.brand_names and new_node.brand_names:
            existing_node.brand_names = new_node.brand_names
