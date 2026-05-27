"""Composed competitor discovery.

Strategy
--------
1. Build an N+1 competitive graph via CompetitiveGraphService across the
   TARGET / MOA / INDICATION / CLASS dimensions. The graph service already
   fans out to ChEMBL, OpenFDA, ClinicalTrials.gov, and DrugBank.
2. Seed the core node with the caller-supplied MOA + brand + primary
   indication so we skip redundant resolution lookups for the input drug.
3. Project each N+1 node into the response shape, deriving:
     - evidence — distinct upstream sources that surfaced the candidate
     - shared_indications — intersection of caller indications with
       (node.primary_indication ∪ discovered_via "indication:*" tags)
     - approval_status — mapped from the development stage enum
4. Rank by evidence count (more sources = stronger signal), then by name
   for stability; exclude the input molecule; cap at `limit`.
"""

from __future__ import annotations

import logging
from typing import Any

from ...models.competitive_graph import (
    CompetitiveDimension,
    CompetitiveLandscapeGraph,
    CompetitiveNode,
    GraphLevel,
)
from ..ground_truth.competitive_graph_service import (
    CompetitiveGraphService,
    GraphBuildConfig,
)

logger = logging.getLogger(__name__)


_DIMENSION_EVIDENCE: dict[CompetitiveDimension, str] = {
    CompetitiveDimension.TARGET: "chembl",
    CompetitiveDimension.MOA: "openfda",
    CompetitiveDimension.INDICATION: "clinicaltrials",
    CompetitiveDimension.CLASS: "drugbank",
}

_APPROVED_STAGES = {"approved", "marketed"}


class CompetitorSearchService:
    """Compose competitor candidates from multiple ground-truth sources."""

    def __init__(self, graph_service: CompetitiveGraphService | None = None) -> None:
        self._graph = graph_service or CompetitiveGraphService()

    async def find_competitors(
        self,
        molecule_name: str,
        indications: list[dict[str, Any]],
        brand_name: str | None = None,
        mechanism_of_action: str | None = None,
        limit: int = 10,
        db_pool: Any = None,
    ) -> list[dict[str, Any]]:
        """Return up to `limit` competitor dicts shaped for the API response."""
        indication_names = [i["name"] for i in indications if i.get("name")]
        primary_indication = indication_names[0] if indication_names else None
        secondary_indications = indication_names[1:]

        core_node_data: dict[str, Any] = {
            "primary_indication": primary_indication,
            "secondary_indications": secondary_indications,
            "mechanism_of_action": mechanism_of_action,
            "brand_names": [brand_name] if brand_name else [],
        }

        config = GraphBuildConfig(
            depth=1,
            min_score=0.1,
            dimensions=[
                CompetitiveDimension.TARGET,
                CompetitiveDimension.MOA,
                CompetitiveDimension.INDICATION,
                CompetitiveDimension.CLASS,
            ],
            include_preclinical=False,
        )

        core_id = self._synthetic_id(molecule_name)
        graph = await self._graph.build_graph(
            molecule_id=core_id,
            molecule_name=molecule_name,
            config=config,
            core_node_data=core_node_data,
            db_pool=db_pool,
        )

        competitors = [
            n
            for n in graph.get_nodes_at_level(GraphLevel.N_PLUS_1)
            if n.id != core_id
            and not self._is_same_as_input(n, molecule_name, brand_name)
        ]

        results = [
            self._to_result(node, graph, indication_names) for node in competitors
        ]

        # Prefer candidates that share an indication or MOA with the input;
        # fall back to the full set if none match (keeps the response useful
        # when the caller only provided weak hints).
        relevant = [
            r
            for r in results
            if r["shared_indications"]
            or (mechanism_of_action and r["mechanism"] == mechanism_of_action)
        ]
        ranked = relevant or results

        ranked.sort(key=lambda r: (-len(r["evidence"]), r["molecule"].lower()))
        return ranked[:limit]

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _synthetic_id(molecule_name: str) -> str:
        """Stable id for the in-memory graph; not persisted."""
        return f"search:{molecule_name.strip().lower()}"

    @staticmethod
    def _is_same_as_input(
        node: CompetitiveNode, molecule_name: str, brand_name: str | None
    ) -> bool:
        """Exclude the input drug — including biosimilars and combo products
        that share the same INN root.

        e.g. input "adalimumab" matches:
            - "adalimumab"                              (exact)
            - "ADALIMUMAB-ADAZ"                         (biosimilar suffix)
            - "ADALIMUMAB AND HYALURONIDASE-FNJN"       (combo product)
        """
        inputs = {n for n in (molecule_name, brand_name) if n}
        inputs = {n.strip().lower() for n in inputs}

        candidates = {node.name.lower()}
        if node.generic_name:
            candidates.add(node.generic_name.lower())
        candidates.update(b.lower() for b in node.brand_names)

        for inp in inputs:
            for cand in candidates:
                if cand == inp:
                    return True
                # FDA biosimilar 4-letter suffix: "adalimumab-adaz"
                if cand.startswith(inp + "-"):
                    return True
                # Combo product starting with input INN: "adalimumab and ..."
                if cand.startswith(inp + " "):
                    return True
        return False

    def _to_result(
        self,
        node: CompetitiveNode,
        graph: CompetitiveLandscapeGraph,
        input_indications: list[str],
    ) -> dict[str, Any]:
        stage = node.development_stage.value
        approval = "APPROVED" if stage in _APPROVED_STAGES else stage.upper()
        return {
            "molecule": node.generic_name or node.name,
            "brand": node.brand_names[0] if node.brand_names else None,
            "manufacturer": node.sponsor or node.originator,
            "mechanism": node.mechanism_of_action,
            "shared_indications": self._shared_indications(node, input_indications),
            "approval_status": approval,
            "evidence": self._evidence_for(node, graph),
        }

    @staticmethod
    def _evidence_for(
        node: CompetitiveNode, graph: CompetitiveLandscapeGraph
    ) -> list[str]:
        """Distinct upstream sources that surfaced the candidate."""
        seen: set[str] = set()
        sources: list[str] = []
        for edge in graph.edges:
            if node.id not in (edge.source_id, edge.target_id):
                continue
            label = _DIMENSION_EVIDENCE.get(edge.dimension)
            if label and label not in seen:
                seen.add(label)
                sources.append(label)
        return sources

    @staticmethod
    def _shared_indications(
        node: CompetitiveNode, input_indications: list[str]
    ) -> list[str]:
        """Indications the candidate shares with the input molecule.

        The graph service tags indication-derived nodes with
        `discovered_via=["indication:<name>", ...]` (see
        CompetitiveGraphService._find_by_indication) and also records the
        first matched indication on `primary_indication`. We union both
        sources and intersect (case-insensitive) with caller indications.
        """
        candidate: set[str] = set()
        if node.primary_indication:
            candidate.add(node.primary_indication.lower())
        for tag in node.discovered_via:
            if tag.startswith("indication:"):
                candidate.add(tag.split(":", 1)[1].lower())
        return [i for i in input_indications if i.lower() in candidate]
