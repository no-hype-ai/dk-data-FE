"""
Competitive Landscape Graph Builder.

Builds N+2 competitive landscape graphs by:
1. Starting from a core molecule (N)
2. Finding direct competitors (N+1) via indication, MOA, target, class
3. Finding competitors' competitors (N+2)
4. Applying deduplication and scoring rules

Uses inference rules from config/inference_rules.yaml.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from loguru import logger

from ...models.competitive_graph import (
    CompetitiveDimension,
    CompetitiveEdge,
    CompetitiveLandscapeGraph,
    CompetitiveNode,
    DevelopmentStage,
    GraphLevel,
)
from ..external_apis import (
    ClinicalTrialsClient,
    OpenFDAClient,
    RxNormClient,
    UMLSClient,
    get_clinicaltrials_client,
    get_openfda_client,
    get_rxnorm_client,
    get_umls_client,
)


@dataclass
class GraphBuilderConfig:
    """Configuration for graph building."""

    max_depth: int = 2  # N+2
    max_nodes_per_level: int = 100
    min_edge_score: float = 0.20

    # Dimension weights (from scoring_config.yaml)
    dimension_weights: Dict[str, float] = field(default_factory=lambda: {
        "indication": 0.30,
        "moa": 0.25,
        "target": 0.20,
        "class": 0.15,
        "stage": 0.10,
    })

    # Phase weights
    phase_weights: Dict[str, float] = field(default_factory=lambda: {
        "preclinical": 0.05,
        "phase_1": 0.10,
        "phase_1_2": 0.20,
        "phase_2": 0.30,
        "phase_2_3": 0.45,
        "phase_3": 0.60,
        "submitted": 0.80,
        "approved": 1.00,
        "marketed": 1.00,
        "withdrawn": 0.00,
        "discontinued": 0.00,
    })

    # Enabled dimensions
    enabled_dimensions: List[CompetitiveDimension] = field(
        default_factory=lambda: list(CompetitiveDimension)
    )


@dataclass
class DiscoveryPath:
    """Tracks how a competitor was discovered."""

    dimension: CompetitiveDimension
    via_node_id: Optional[str] = None  # ID of node that led to discovery
    evidence: List[str] = field(default_factory=list)
    score: float = 0.0


class GraphBuilder:
    """
    Builds N+2 competitive landscape graphs.

    Usage:
        builder = GraphBuilder()
        await builder.initialize()

        graph = await builder.build_graph(
            core_molecule_id="DB00945",  # Aspirin
            core_molecule_name="Aspirin",
            indications=["M05.79"],  # Rheumatoid arthritis
            moa="Cyclooxygenase inhibitor",
            targets=["Prostaglandin G/H synthase 1"],
        )
    """

    def __init__(self, config: Optional[GraphBuilderConfig] = None):
        self.config = config or GraphBuilderConfig()
        self._umls: Optional[UMLSClient] = None
        self._rxnorm: Optional[RxNormClient] = None
        self._openfda: Optional[OpenFDAClient] = None
        self._clinicaltrials: Optional[ClinicalTrialsClient] = None
        self._inference_rules: Dict[str, Any] = {}

    async def initialize(self) -> None:
        """Initialize API clients and load rules."""
        self._umls = await get_umls_client()
        self._rxnorm = await get_rxnorm_client()
        self._openfda = await get_openfda_client()
        self._clinicaltrials = await get_clinicaltrials_client()

        # Load inference rules
        await self._load_inference_rules()

    async def _load_inference_rules(self) -> None:
        """Load inference rules from config file."""
        try:
            import os
            config_path = os.path.join(
                os.path.dirname(__file__),
                "../../../config/inference_rules.yaml"
            )
            with open(config_path, "r") as f:
                self._inference_rules = yaml.safe_load(f)
            logger.info("Loaded inference rules from config")
        except Exception as e:
            logger.warning(f"Could not load inference rules: {e}, using defaults")
            self._inference_rules = {}

    async def build_graph(
        self,
        core_molecule_id: str,
        core_molecule_name: str,
        indications: Optional[List[str]] = None,
        moa: Optional[str] = None,
        targets: Optional[List[str]] = None,
        atc_codes: Optional[List[str]] = None,
        development_stage: Optional[DevelopmentStage] = None,
        sponsor: Optional[str] = None,
    ) -> CompetitiveLandscapeGraph:
        """
        Build a complete N+2 competitive landscape graph.

        Args:
            core_molecule_id: Unique identifier for the core molecule
            core_molecule_name: Name of the core molecule
            indications: List of ICD-10 codes or indication names
            moa: Mechanism of action
            targets: List of molecular targets
            atc_codes: ATC classification codes
            development_stage: Current development stage
            sponsor: Sponsor/company name

        Returns:
            CompetitiveLandscapeGraph with N+1 and N+2 competitors
        """
        start_time = time.time()

        # Create graph
        graph = CompetitiveLandscapeGraph(
            core_molecule_id=core_molecule_id,
            depth=self.config.max_depth,
            min_score=self.config.min_edge_score,
            dimensions_included=self.config.enabled_dimensions,
        )

        # Create and add core node
        # Use APPROVED as default if development_stage is None (for "all" searches)
        core_stage = development_stage if development_stage is not None else DevelopmentStage.APPROVED
        core_node = CompetitiveNode(
            id=core_molecule_id,
            name=core_molecule_name,
            level=GraphLevel.CORE,
            development_stage=core_stage,
            mechanism_of_action=moa,
            primary_indication=indications[0] if indications else None,
            atc_codes=atc_codes or [],
            targets=targets or [],
            sponsor=sponsor,
        )
        graph.core_molecule = core_node
        graph.add_node(core_node)

        # Build N+1 level (direct competitors)
        logger.info(f"Building N+1 competitors for {core_molecule_name}")
        n_plus_1_discoveries = await self._discover_competitors(
            source_node=core_node,
            target_level=GraphLevel.N_PLUS_1,
            indications=indications,
            moa=moa,
            targets=targets,
            atc_codes=atc_codes,
        )

        # Add N+1 nodes and edges
        for node, paths in n_plus_1_discoveries.items():
            if graph.add_node(node):
                for path in paths:
                    edge = CompetitiveEdge(
                        source_id=core_molecule_id,
                        target_id=node.id,
                        dimension=path.dimension,
                        score=path.score,
                        discovered_via=f"direct_{path.dimension.value}",
                        evidence=path.evidence,
                    )
                    graph.add_edge(edge)

        # Check node limit
        n_plus_1_nodes = graph.get_nodes_at_level(GraphLevel.N_PLUS_1)
        if len(n_plus_1_nodes) > self.config.max_nodes_per_level:
            logger.warning(
                f"N+1 nodes ({len(n_plus_1_nodes)}) exceed limit "
                f"({self.config.max_nodes_per_level}), truncating"
            )
            # Keep highest scoring nodes
            n_plus_1_nodes.sort(key=lambda n: n.threat_score, reverse=True)
            nodes_to_remove = n_plus_1_nodes[self.config.max_nodes_per_level:]
            for node in nodes_to_remove:
                del graph.nodes[node.id]

        # Build N+2 level (competitors' competitors)
        if self.config.max_depth >= 2:
            logger.info(f"Building N+2 competitors")
            await self._build_n_plus_2(graph, n_plus_1_nodes[:self.config.max_nodes_per_level])

        # Calculate build time
        graph.build_time_ms = int((time.time() - start_time) * 1000)
        graph.built_at = datetime.utcnow()

        logger.info(
            f"Graph built: {len(graph.nodes)} nodes, {len(graph.edges)} edges "
            f"in {graph.build_time_ms}ms"
        )

        return graph

    async def _discover_competitors(
        self,
        source_node: CompetitiveNode,
        target_level: GraphLevel,
        indications: Optional[List[str]] = None,
        moa: Optional[str] = None,
        targets: Optional[List[str]] = None,
        atc_codes: Optional[List[str]] = None,
    ) -> Dict[CompetitiveNode, List[DiscoveryPath]]:
        """
        Discover competitors for a node across all dimensions.

        Returns dictionary mapping discovered nodes to their discovery paths.
        """
        discoveries: Dict[str, Tuple[CompetitiveNode, List[DiscoveryPath]]] = {}

        # Run discoveries in parallel
        tasks = []

        if CompetitiveDimension.INDICATION in self.config.enabled_dimensions and indications:
            tasks.append(self._discover_by_indication(source_node, indications, target_level))

        if CompetitiveDimension.MOA in self.config.enabled_dimensions and moa:
            tasks.append(self._discover_by_moa(source_node, moa, target_level))

        if CompetitiveDimension.CLASS in self.config.enabled_dimensions and atc_codes:
            tasks.append(self._discover_by_class(source_node, atc_codes, target_level))

        # Execute all discovery tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Discovery task failed: {result}")
                continue

            for node, paths in result.items():
                if node.id in discoveries:
                    # Merge paths for existing node
                    existing_node, existing_paths = discoveries[node.id]
                    existing_paths.extend(paths)
                else:
                    discoveries[node.id] = (node, paths)

        return {node: paths for node, paths in discoveries.values()}

    async def _discover_by_indication(
        self,
        source_node: CompetitiveNode,
        indications: List[str],
        target_level: GraphLevel,
    ) -> Dict[CompetitiveNode, List[DiscoveryPath]]:
        """Discover competitors treating the same indications."""
        discoveries: Dict[CompetitiveNode, List[DiscoveryPath]] = {}

        for indication in indications:
            try:
                # Search ClinicalTrials.gov for drugs in trials for this indication
                trials = await self._clinicaltrials.search_by_condition(
                    condition=indication,
                    phases=["PHASE2", "PHASE3"],
                    page_size=50,
                )

                # Extract unique drugs from trials
                seen_drugs: Set[str] = set()
                for trial in trials:
                    for intervention in trial.get_drug_interventions():
                        drug_name = intervention.name.lower()

                        # Skip self
                        if drug_name == source_node.name.lower():
                            continue

                        if drug_name in seen_drugs:
                            continue
                        seen_drugs.add(drug_name)

                        # Create competitor node
                        stage = self._trial_phase_to_stage(trial.phase.value)
                        node = CompetitiveNode(
                            id=f"ct_{drug_name.replace(' ', '_')}",
                            name=intervention.name,
                            level=target_level,
                            development_stage=stage,
                            primary_indication=indication,
                            sponsor=trial.lead_sponsor.name if trial.lead_sponsor else None,
                            discovered_via=[f"indication:{indication}"],
                        )

                        # Calculate score
                        phase_weight = self.config.phase_weights.get(stage.value, 0.5)
                        score = 0.30 * 1.0 + 0.70 * phase_weight  # indication_overlap * 1.0

                        path = DiscoveryPath(
                            dimension=CompetitiveDimension.INDICATION,
                            evidence=[f"Trial {trial.nct_id} for {indication}"],
                            score=score,
                        )

                        if node not in discoveries:
                            discoveries[node] = []
                        discoveries[node].append(path)

            except Exception as e:
                logger.error(f"Error discovering by indication {indication}: {e}")

        return discoveries

    async def _discover_by_moa(
        self,
        source_node: CompetitiveNode,
        moa: str,
        target_level: GraphLevel,
    ) -> Dict[CompetitiveNode, List[DiscoveryPath]]:
        """Discover competitors with the same mechanism of action."""
        discoveries: Dict[CompetitiveNode, List[DiscoveryPath]] = {}

        try:
            # Search OpenFDA for drugs with same MOA class
            labels = await self._openfda.search_drug_labels(
                query=moa,
                search_field="openfda.pharm_class_moa",
                limit=50,
            )

            for label in labels:
                if not label.generic_name:
                    continue

                drug_name = label.generic_name.lower()

                # Skip self
                if drug_name == source_node.name.lower():
                    continue

                # Create competitor node
                node = CompetitiveNode(
                    id=f"fda_{label.application_number or drug_name.replace(' ', '_')}",
                    name=label.generic_name,
                    level=target_level,
                    development_stage=DevelopmentStage.APPROVED,
                    mechanism_of_action=moa,
                    sponsor=label.manufacturer_name,
                    discovered_via=[f"moa:{moa}"],
                )

                # Calculate score (approved drugs get high phase weight)
                phase_weight = self.config.phase_weights.get("approved", 1.0)
                score = 0.40 * 1.0 + 0.60 * phase_weight  # moa_similarity * 1.0

                path = DiscoveryPath(
                    dimension=CompetitiveDimension.MOA,
                    evidence=[f"FDA label with MOA: {moa}"],
                    score=score,
                )

                if node not in discoveries:
                    discoveries[node] = []
                discoveries[node].append(path)

        except Exception as e:
            logger.error(f"Error discovering by MOA {moa}: {e}")

        return discoveries

    async def _discover_by_class(
        self,
        source_node: CompetitiveNode,
        atc_codes: List[str],
        target_level: GraphLevel,
    ) -> Dict[CompetitiveNode, List[DiscoveryPath]]:
        """Discover competitors in the same ATC drug class."""
        discoveries: Dict[CompetitiveNode, List[DiscoveryPath]] = {}

        for atc_code in atc_codes:
            try:
                # Get ATC level 4 (first 5 chars) for chemical subgroup
                atc_level_4 = atc_code[:5] if len(atc_code) >= 5 else atc_code

                # Get drugs in this ATC class via RxNorm
                drugs = await self._rxnorm.get_drugs_by_class(
                    class_id=atc_level_4,
                    class_type="ATC",
                )

                for drug in drugs:
                    drug_name = drug.name.lower()

                    # Skip self
                    if drug_name == source_node.name.lower():
                        continue

                    # Create competitor node
                    node = CompetitiveNode(
                        id=f"rxn_{drug.rxcui}",
                        name=drug.name,
                        level=target_level,
                        development_stage=DevelopmentStage.MARKETED,  # RxNorm has marketed drugs
                        atc_codes=[atc_level_4],
                        discovered_via=[f"atc:{atc_level_4}"],
                    )

                    # Calculate score
                    phase_weight = self.config.phase_weights.get("marketed", 1.0)
                    score = 0.25 * 1.0 + 0.75 * phase_weight  # class_similarity * 1.0

                    path = DiscoveryPath(
                        dimension=CompetitiveDimension.CLASS,
                        evidence=[f"ATC class {atc_level_4}"],
                        score=score,
                    )

                    if node not in discoveries:
                        discoveries[node] = []
                    discoveries[node].append(path)

            except Exception as e:
                logger.error(f"Error discovering by ATC class {atc_code}: {e}")

        return discoveries

    async def _build_n_plus_2(
        self,
        graph: CompetitiveLandscapeGraph,
        n_plus_1_nodes: List[CompetitiveNode],
    ) -> None:
        """Build N+2 level by finding competitors of N+1 nodes."""

        # Limit N+1 nodes to process (for performance)
        nodes_to_process = n_plus_1_nodes[:20]  # Top 20 by threat score

        for n1_node in nodes_to_process:
            try:
                # Discover competitors of this N+1 node
                n2_discoveries = await self._discover_competitors(
                    source_node=n1_node,
                    target_level=GraphLevel.N_PLUS_2,
                    indications=[n1_node.primary_indication] if n1_node.primary_indication else None,
                    moa=n1_node.mechanism_of_action,
                    atc_codes=n1_node.atc_codes if n1_node.atc_codes else None,
                )

                # Add N+2 nodes and edges
                for node, paths in n2_discoveries.items():
                    # Skip if already in graph (deduplication)
                    if node.id == graph.core_molecule_id:
                        continue  # Block circular reference

                    # Track discovery path via N+1 node
                    node.discovered_via.append(f"via:{n1_node.id}")

                    if graph.add_node(node):
                        for path in paths:
                            edge = CompetitiveEdge(
                                source_id=n1_node.id,
                                target_id=node.id,
                                dimension=path.dimension,
                                score=path.score * 0.8,  # Decay score for N+2
                                discovered_via=f"indirect_via_{n1_node.id}",
                                evidence=path.evidence,
                            )
                            graph.add_edge(edge)

                # Check N+2 limit
                n_plus_2_count = len(graph.get_nodes_at_level(GraphLevel.N_PLUS_2))
                if n_plus_2_count >= self.config.max_nodes_per_level:
                    logger.info(f"N+2 limit reached ({n_plus_2_count} nodes)")
                    break

            except Exception as e:
                logger.error(f"Error building N+2 for {n1_node.name}: {e}")

    def _trial_phase_to_stage(self, phase: str) -> DevelopmentStage:
        """Convert ClinicalTrials.gov phase to DevelopmentStage."""
        mapping = {
            "EARLY_PHASE1": DevelopmentStage.PHASE_1,
            "PHASE1": DevelopmentStage.PHASE_1,
            "PHASE1/PHASE2": DevelopmentStage.PHASE_1_2,
            "PHASE2": DevelopmentStage.PHASE_2,
            "PHASE2/PHASE3": DevelopmentStage.PHASE_2_3,
            "PHASE3": DevelopmentStage.PHASE_3,
            "PHASE4": DevelopmentStage.MARKETED,
            "NA": DevelopmentStage.PRECLINICAL,
        }
        return mapping.get(phase, DevelopmentStage.PRECLINICAL)


# Singleton instance
_graph_builder: Optional[GraphBuilder] = None


async def get_graph_builder(config: Optional[GraphBuilderConfig] = None) -> GraphBuilder:
    """Get or create the graph builder instance."""
    global _graph_builder

    if _graph_builder is None:
        _graph_builder = GraphBuilder(config)
        await _graph_builder.initialize()

    return _graph_builder
