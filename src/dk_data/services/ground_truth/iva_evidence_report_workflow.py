"""
IVA Evidence Strengthening Report Workflow.

An Agno-based multi-agent workflow for generating comprehensive IVA Evidence
Strengthening reports similar to IVA_Evidence_Strengthening_2025.md.

Workflow Steps:
1. Publication Retrieval - Pull IVA publications from database
2. Evidence Organization - Organize by indication and CEJ narrative pillar
3. Evidence Table Generation - Create structured evidence tables
4. Evidence Gap Analysis - Compare current evidence vs needs
5. Competitive Coverage Analysis - Build coverage parity matrices
6. Positioning Cautions - Generate warnings based on failed endpoints
7. Report Assembly - Compile final Markdown/PDF report

Usage:
    from iva_evidence_report_workflow import IVAEvidenceReportWorkflow

    workflow = IVAEvidenceReportWorkflow()
    result = await workflow.run(
        drug_name="dupilumab",
        indications=["atopic_dermatitis", "prurigo_nodularis", "chronic_spontaneous_urticaria"],
        include_competitors=True,
    )

    # Access report
    markdown_report = result.markdown_report
    evidence_tables = result.evidence_tables
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4, UUID
from enum import Enum

from loguru import logger

# Try importing Agno
try:
    from agno.agent import Agent
    from agno.models.anthropic import Claude
    from agno.team import Team
    from agno.tools.toolkit import Toolkit
    from agno.tools.function import Function
    AGNO_AVAILABLE = True
except ImportError:
    AGNO_AVAILABLE = False
    logger.warning("Agno framework not installed. Using fallback implementation.")

# Local imports
from .db_utils import get_db_connection
from .clinical_endpoints_loader import get_clinical_endpoints_ontology


# =============================================================================
# Enums and Data Models
# =============================================================================

class CEJNarrativePillar(str, Enum):
    """CEJ (Customer Engagement Journey) narrative pillars."""
    DISEASE_CHRONICITY = "disease_chronicity"  # Disease is chronically active
    CUMULATIVE_BURDEN = "cumulative_burden"  # Cumulative burden and life-course impact
    CHRONIC_STRATEGY = "chronic_strategy"  # Chronic disease requires chronic strategy
    DURABLE_RESULTS = "durable_results"  # Why Dupixent - Durable results
    PROVEN_SAFETY = "proven_safety"  # Why Dupixent - Proven safety


class EvidenceStrength(str, Enum):
    """Evidence strength levels."""
    FDA_LABEL = "fda_label"  # Highest - from FDA label
    RCT = "rct"  # Phase 3 RCT data
    REGISTRY = "registry"  # Registry/RWE data
    META_ANALYSIS = "meta_analysis"
    CASE_SERIES = "case_series"
    EXPERT_OPINION = "expert_opinion"


class GapStatus(str, Enum):
    """Evidence gap status."""
    FULLY_SUPPORTED = "fully_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    GAP = "gap"
    CAUTION = "caution"  # Claim should be avoided


@dataclass
class EvidenceItem:
    """A single piece of evidence."""
    description: str
    data_point: str
    source: str  # PMID, DOI, or FDA Label
    source_url: Optional[str] = None
    year: Optional[int] = None
    indication: Optional[str] = None
    pillar: Optional[CEJNarrativePillar] = None
    strength: EvidenceStrength = EvidenceStrength.RCT
    deployment_guidance: Optional[str] = None


@dataclass
class EvidenceTable:
    """Evidence table for a specific pillar."""
    indication: str
    pillar: CEJNarrativePillar
    pillar_title: str
    narrative: str
    evidence_items: List[EvidenceItem] = field(default_factory=list)
    deployment_guidance: Optional[str] = None


@dataclass
class EvidenceGap:
    """An identified evidence gap."""
    claim: str
    current_support: str
    status: GapStatus
    recommendation: Optional[str] = None


@dataclass
class CompetitorCoverage:
    """Coverage data for a competitor."""
    drug_name: str
    mechanism: str
    indication: str
    endpoints: Dict[str, str]  # endpoint -> value
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)


@dataclass
class CoverageMatrix:
    """Coverage parity matrix comparing drugs."""
    indication: str
    data_category: str
    our_drug: str
    our_coverage: str
    competitors: Dict[str, str]  # drug -> coverage
    parity_status: str  # "Complete", "Gap", "Advantage"


@dataclass
class PositioningCaution:
    """A positioning caution/warning."""
    indication: str
    avoid_claiming: str
    reason: str
    alternative: Optional[str] = None


@dataclass
class WorkflowInputs:
    """Inputs for the IVA Evidence Report workflow."""
    drug_name: str
    indications: List[str] = field(default_factory=lambda: ["atopic_dermatitis"])
    competitors: Optional[List[str]] = None
    include_competitors: bool = True
    include_gap_analysis: bool = True
    include_coverage_matrices: bool = True
    years_back: int = 2  # Include evidence from last N years
    output_format: str = "markdown"  # markdown, html, json


@dataclass
class WorkflowOutputs:
    """Outputs from the IVA Evidence Report workflow."""
    run_id: UUID
    drug_name: str
    indications: List[str]
    generated_at: str

    # Evidence data
    evidence_tables: Dict[str, List[EvidenceTable]] = field(default_factory=dict)  # indication -> tables
    evidence_gaps: Dict[str, List[EvidenceGap]] = field(default_factory=dict)  # indication -> gaps
    coverage_matrices: Dict[str, List[CoverageMatrix]] = field(default_factory=dict)  # indication -> matrices
    competitor_coverage: List[CompetitorCoverage] = field(default_factory=list)
    positioning_cautions: List[PositioningCaution] = field(default_factory=list)

    # Report outputs
    markdown_report: str = ""
    html_report: Optional[str] = None

    # Statistics
    total_evidence_items: int = 0
    evidence_by_pillar: Dict[str, int] = field(default_factory=dict)
    evidence_by_indication: Dict[str, int] = field(default_factory=dict)
    gaps_identified: int = 0
    cautions_identified: int = 0

    # Metadata
    workflow_duration_ms: int = 0
    agents_used: List[str] = field(default_factory=list)


# =============================================================================
# Pillar Configuration
# =============================================================================

PILLAR_CONFIG = {
    "atopic_dermatitis": {
        CEJNarrativePillar.DISEASE_CHRONICITY: {
            "title": "AD Is Chronically Active—Not Episodic",
            "narrative": "AD remains biologically active beyond visible symptoms, with underlying inflammation persisting even when skin appears improved.",
            "keywords": ["flare", "persistent", "chronic", "subclinical", "inflammation"],
        },
        CEJNarrativePillar.CUMULATIVE_BURDEN: {
            "title": "Cumulative Burden and Life-Course Impact Exists",
            "narrative": "Persistent, inadequately controlled AD contributes to cumulative burden over time, affecting multiple dimensions of life.",
            "keywords": ["sleep", "work", "quality of life", "DLQI", "burden", "productivity", "itch"],
        },
        CEJNarrativePillar.CHRONIC_STRATEGY: {
            "title": "Chronic Disease Requires a Chronic Strategy",
            "narrative": "The chronic biology of AD explains why long-term disease management approaches are often needed.",
            "keywords": ["drug survival", "persistence", "retention", "long-term", "maintenance"],
        },
        CEJNarrativePillar.DURABLE_RESULTS: {
            "title": "Why Dupixent—Durable Results",
            "narrative": "Durable control is reflected in patients staying controlled year after year.",
            "keywords": ["EASI", "IGA", "5-year", "sustained", "maintained", "durability"],
        },
        CEJNarrativePillar.PROVEN_SAFETY: {
            "title": "Why Dupixent—Proven Safety",
            "narrative": "In a lifelong disease, safety means confidence over years—not just short-term tolerance.",
            "keywords": ["safety", "discontinuation", "adverse", "tolerability", "retention"],
        },
    },
    "prurigo_nodularis": {
        CEJNarrativePillar.DISEASE_CHRONICITY: {
            "title": "PN Is a Self-Perpetuating Neuro-Immune Disease",
            "narrative": "Treating itch alone does not stop PN from sustaining itself.",
            "keywords": ["neuro-immune", "itch-scratch", "nodule", "dual response"],
        },
        CEJNarrativePillar.CUMULATIVE_BURDEN: {
            "title": "PN Is Complex to Manage with High Disease Burden",
            "narrative": "Delaying effective control allows burden to accumulate.",
            "keywords": ["burden", "QoL", "DLQI", "impaired"],
        },
        CEJNarrativePillar.CHRONIC_STRATEGY: {
            "title": "Chronic PN Requires a Long-Term Control Strategy",
            "narrative": "Episodic treatment does not align with disease biology.",
            "keywords": ["long-term", "sustained", "84-week", "104-week", "maintenance"],
        },
        CEJNarrativePillar.DURABLE_RESULTS: {
            "title": "Why Dupixent—Durable Itch Control",
            "narrative": "Breaking the itch-scratch cycle requires control that lasts.",
            "keywords": ["NRS", "itch", "pruritus", "PP-NRS", "sustained"],
        },
        CEJNarrativePillar.PROVEN_SAFETY: {
            "title": "Why Dupixent—Safety for Long-Term Management",
            "narrative": "When PN persists, treatment must be safe enough to continue.",
            "keywords": ["safety", "retention", "completion", "no new signals"],
        },
    },
    "chronic_spontaneous_urticaria": {
        CEJNarrativePillar.DISEASE_CHRONICITY: {
            "title": "CSU Is Chronic and Unpredictable",
            "narrative": "For many patients, CSU persists for years with an unpredictable course.",
            "keywords": ["chronic", "unpredictable", "persistence", "unmet need"],
        },
        CEJNarrativePillar.CUMULATIVE_BURDEN: {
            "title": "Partial Control Still Carries a High, Ongoing Burden",
            "narrative": "Ongoing itch, hives, and angioedema continue to disrupt sleep, productivity, and emotional well-being.",
            "keywords": ["burden", "partial control", "QoL", "disruption"],
        },
        CEJNarrativePillar.CHRONIC_STRATEGY: {
            "title": "Chronic Inflammation Requires Continuous Disease Control",
            "narrative": "For inadequately controlled patients, guidelines support timely escalation.",
            "keywords": ["antihistamine-refractory", "escalation", "guidelines", "incomplete response"],
        },
        CEJNarrativePillar.DURABLE_RESULTS: {
            "title": "Why Dupixent—Emerging MOA & Durable Disease Control",
            "narrative": "Dupixent targets IL-4/IL-13 signaling—offering differentiated, upstream approach.",
            "keywords": ["UAS7", "ISS7", "IL-4", "IL-13", "IgE", "control"],
        },
        CEJNarrativePillar.PROVEN_SAFETY: {
            "title": "Why Dupixent—Proven Safety & Experience",
            "narrative": "When CSU persists for years, treatment must be suitable for long-term use.",
            "keywords": ["safety", "TEAE", "consistent", "established"],
        },
    },
}


# =============================================================================
# Toolkits
# =============================================================================

if AGNO_AVAILABLE:
    class IVAPublicationToolkit(Toolkit):
        """Toolkit for retrieving IVA publications from database."""

        def __init__(self):
            super().__init__(name="iva_publication_toolkit")
            self.register(self.get_publications)
            self.register(self.get_curated_publications)
            self.register(self.get_publication_stats)

        @Function(
            description="Get IVA publications for a drug filtered by indication and/or pillar",
            parameters={
                "drug_name": {"type": "string", "description": "Drug name to search for"},
                "indication": {"type": "string", "description": "Filter by indication (optional)"},
                "pillar": {"type": "string", "description": "Filter by narrative pillar (optional)"},
                "min_relevance": {"type": "number", "description": "Minimum relevance score (0-1)", "default": 0.3},
                "years_back": {"type": "integer", "description": "Include publications from last N years", "default": 2},
                "limit": {"type": "integer", "description": "Maximum publications to return", "default": 100},
            }
        )
        async def get_publications(
            self,
            drug_name: str,
            indication: Optional[str] = None,
            pillar: Optional[str] = None,
            min_relevance: float = 0.3,
            years_back: int = 2,
            limit: int = 100,
        ) -> List[Dict[str, Any]]:
            """Retrieve IVA publications from database."""
            try:
                async with get_db_connection() as conn:
                    query = """
                        SELECT
                            openalex_id, doi, pmid, title, abstract,
                            publication_date, publication_year, journal,
                            authors, cited_by_count, drug_names,
                            iva_relevance_score, iva_indication,
                            iva_narrative_pillar, iva_evidence_type,
                            study_type, study_population_size,
                            study_duration_weeks, data_source, key_endpoints
                        FROM iva_publications
                        WHERE $1 = ANY(drug_names)
                          AND iva_relevance_score >= $2
                          AND publication_year >= EXTRACT(YEAR FROM CURRENT_DATE) - $3
                    """
                    params = [drug_name.lower(), min_relevance, years_back]
                    param_idx = 4

                    if indication:
                        query += f" AND iva_indication = ${param_idx}"
                        params.append(indication)
                        param_idx += 1

                    if pillar:
                        query += f" AND iva_narrative_pillar = ${param_idx}"
                        params.append(pillar)
                        param_idx += 1

                    query += f" ORDER BY iva_relevance_score DESC, cited_by_count DESC LIMIT ${param_idx}"
                    params.append(limit)

                    rows = await conn.fetch(query, *params)

                    results = []
                    for row in rows:
                        pub = dict(row)
                        # Parse JSON fields
                        if isinstance(pub.get("authors"), str):
                            pub["authors"] = json.loads(pub["authors"])
                        if isinstance(pub.get("key_endpoints"), str):
                            pub["key_endpoints"] = json.loads(pub["key_endpoints"])
                        results.append(pub)

                    return results

            except Exception as e:
                logger.error(f"Failed to get IVA publications: {e}")
                return []

        @Function(
            description="Get curated IVA publications with key findings extracted",
            parameters={
                "drug_name": {"type": "string", "description": "Drug name"},
                "indication": {"type": "string", "description": "Filter by indication (optional)"},
                "limit": {"type": "integer", "description": "Maximum results", "default": 50},
            }
        )
        async def get_curated_publications(
            self,
            drug_name: str,
            indication: Optional[str] = None,
            limit: int = 50,
        ) -> List[Dict[str, Any]]:
            """Get curated publications with key findings."""
            try:
                async with get_db_connection() as conn:
                    query = """
                        SELECT
                            id, drug_name, title, pmid, doi,
                            publication_date, journal, authors,
                            indication, narrative_pillar, evidence_type,
                            key_findings, relevance_score, source_document
                        FROM iva_curated_publications
                        WHERE drug_name = $1
                    """
                    params = [drug_name]

                    if indication:
                        query += " AND indication = $2"
                        params.append(indication)

                    query += f" ORDER BY relevance_score DESC LIMIT ${len(params) + 1}"
                    params.append(limit)

                    rows = await conn.fetch(query, *params)

                    results = []
                    for row in rows:
                        pub = dict(row)
                        if isinstance(pub.get("key_findings"), str):
                            pub["key_findings"] = json.loads(pub["key_findings"])
                        results.append(pub)

                    return results

            except Exception as e:
                logger.error(f"Failed to get curated publications: {e}")
                return []

        @Function(
            description="Get publication statistics by indication and pillar",
            parameters={
                "drug_name": {"type": "string", "description": "Drug name"},
            }
        )
        async def get_publication_stats(self, drug_name: str) -> Dict[str, Any]:
            """Get aggregated publication statistics."""
            try:
                async with get_db_connection() as conn:
                    # By indication
                    indication_rows = await conn.fetch("""
                        SELECT iva_indication, COUNT(*) as cnt
                        FROM iva_publications
                        WHERE $1 = ANY(drug_names) AND iva_indication IS NOT NULL
                        GROUP BY iva_indication
                    """, drug_name.lower())

                    # By pillar
                    pillar_rows = await conn.fetch("""
                        SELECT iva_narrative_pillar, COUNT(*) as cnt
                        FROM iva_publications
                        WHERE $1 = ANY(drug_names) AND iva_narrative_pillar IS NOT NULL
                        GROUP BY iva_narrative_pillar
                    """, drug_name.lower())

                    # By evidence type
                    evidence_rows = await conn.fetch("""
                        SELECT iva_evidence_type, COUNT(*) as cnt
                        FROM iva_publications
                        WHERE $1 = ANY(drug_names) AND iva_evidence_type IS NOT NULL
                        GROUP BY iva_evidence_type
                    """, drug_name.lower())

                    return {
                        "by_indication": {row["iva_indication"]: row["cnt"] for row in indication_rows},
                        "by_pillar": {row["iva_narrative_pillar"]: row["cnt"] for row in pillar_rows},
                        "by_evidence_type": {row["iva_evidence_type"]: row["cnt"] for row in evidence_rows},
                    }

            except Exception as e:
                logger.error(f"Failed to get publication stats: {e}")
                return {}


    class CompetitiveIntelToolkit(Toolkit):
        """Toolkit for competitive intelligence data."""

        def __init__(self):
            super().__init__(name="competitive_intel_toolkit")
            self.register(self.get_competitor_data)
            self.register(self.get_competitive_messages)
            self.register(self.get_head_to_head_data)

        @Function(
            description="Get competitor drug data for an indication",
            parameters={
                "indication": {"type": "string", "description": "Indication to search"},
                "our_drug": {"type": "string", "description": "Our drug name for comparison"},
            }
        )
        async def get_competitor_data(
            self,
            indication: str,
            our_drug: str,
        ) -> List[Dict[str, Any]]:
            """Get competitor data for comparison."""
            # Hardcoded competitor database for now
            # In production, this would query the competitive_intelligence tables
            competitors_db = {
                "atopic_dermatitis": [
                    {
                        "drug_name": "Ebglyss (Lebrikizumab)",
                        "mechanism": "Anti-IL-13",
                        "iga_01_wk16": "33-43%",
                        "easi_75_wk16": "52-59%",
                        "dosing": "Q2W→Q4W SC",
                        "key_differentiator": "Dosing flexibility",
                        "boxed_warning": False,
                        "year_approved": 2024,
                    },
                    {
                        "drug_name": "Rinvoq (Upadacitinib)",
                        "mechanism": "JAK1i",
                        "iga_01_wk16": "40-62%",
                        "easi_75_wk16": "62-80%",
                        "dosing": "Oral QD",
                        "key_differentiator": "Highest efficacy, oral",
                        "boxed_warning": True,
                        "year_approved": 2022,
                    },
                    {
                        "drug_name": "Nemluvio (Nemolizumab)",
                        "mechanism": "Anti-IL-31",
                        "iga_01_wk16": "22-36%",
                        "easi_75_wk16": "36-44%",
                        "dosing": "Q4W SC",
                        "key_differentiator": "Rapid itch onset",
                        "boxed_warning": False,
                        "year_approved": 2024,
                    },
                ],
                "prurigo_nodularis": [
                    {
                        "drug_name": "Nemluvio (Nemolizumab)",
                        "mechanism": "Anti-IL-31",
                        "pp_nrs_4pt": "56-58% (Wk 16)",
                        "iga_01": "26-38% (Wk 16)",
                        "dosing": "Q4W SC",
                        "key_differentiator": "IL-31 targets itch directly",
                        "boxed_warning": False,
                        "year_approved": 2024,
                    },
                ],
                "chronic_spontaneous_urticaria": [
                    {
                        "drug_name": "Xolair (Omalizumab)",
                        "mechanism": "Anti-IgE",
                        "uas7_0": "34-44% (Wk 12)",
                        "uas7_6": "52-66% (Wk 12)",
                        "dosing": "Q4W SC",
                        "key_differentiator": "First-line biologic",
                        "boxed_warning": False,
                        "year_approved": 2014,
                    },
                    {
                        "drug_name": "RHAPSIDO (Remibrutinib)",
                        "mechanism": "BTKi",
                        "uas7_0": "28-31% (Wk 12)",
                        "uas7_6": "47-50% (Wk 12)",
                        "dosing": "Oral BID",
                        "key_differentiator": "Rapid onset (1-2 weeks)",
                        "boxed_warning": False,
                        "year_approved": 2025,
                    },
                ],
            }

            ind_key = indication.lower().replace(" ", "_")
            return competitors_db.get(ind_key, [])

        @Function(
            description="Get competitive messages and claims",
            parameters={
                "competitor_drug": {"type": "string", "description": "Competitor drug name"},
                "indication": {"type": "string", "description": "Indication (optional)"},
            }
        )
        async def get_competitive_messages(
            self,
            competitor_drug: str,
            indication: Optional[str] = None,
        ) -> List[Dict[str, Any]]:
            """Get competitive messages from database."""
            try:
                async with get_db_connection() as conn:
                    query = """
                        SELECT
                            competitor_drug, message_text, message_type,
                            message_category, source_type, source_date,
                            indication, narrative_pillar, targets_our_drug,
                            iva_threat_level
                        FROM gt_competitive_messages
                        WHERE competitor_drug ILIKE $1
                    """
                    params = [f"%{competitor_drug}%"]

                    if indication:
                        query += " AND indication = $2"
                        params.append(indication)

                    query += " ORDER BY source_date DESC LIMIT 50"

                    rows = await conn.fetch(query, *params)
                    return [dict(row) for row in rows]

            except Exception as e:
                logger.error(f"Failed to get competitive messages: {e}")
                return []

        @Function(
            description="Get head-to-head trial data",
            parameters={
                "our_drug": {"type": "string", "description": "Our drug name"},
                "competitor": {"type": "string", "description": "Competitor drug name"},
                "indication": {"type": "string", "description": "Indication"},
            }
        )
        async def get_head_to_head_data(
            self,
            our_drug: str,
            competitor: str,
            indication: str,
        ) -> Dict[str, Any]:
            """Get head-to-head comparison data if available."""
            # Known head-to-head trials
            h2h_data = {
                ("dupilumab", "upadacitinib", "atopic_dermatitis"): {
                    "trial_name": "Heads Up",
                    "our_drug_easi75": "61%",
                    "competitor_easi75": "71%",
                    "p_value": "0.006",
                    "winner": "upadacitinib",
                    "note": "Statistically superior for primary endpoint",
                    "source": "AbbVie Press Release",
                },
            }

            key = (our_drug.lower(), competitor.lower(), indication.lower().replace(" ", "_"))
            return h2h_data.get(key, {})


    class OntologyToolkit(Toolkit):
        """Toolkit for clinical endpoints ontology."""

        def __init__(self):
            super().__init__(name="ontology_toolkit")
            self._ontology = None
            self.register(self.get_endpoints_for_indication)
            self.register(self.get_icd10_codes)
            self.register(self.validate_endpoint)

        def _get_ontology(self):
            if self._ontology is None:
                self._ontology = get_clinical_endpoints_ontology()
            return self._ontology

        @Function(
            description="Get clinical endpoints for an indication",
            parameters={
                "indication": {"type": "string", "description": "Indication name"},
                "primary_only": {"type": "boolean", "description": "Only primary endpoints", "default": False},
            }
        )
        async def get_endpoints_for_indication(
            self,
            indication: str,
            primary_only: bool = False,
        ) -> List[Dict[str, Any]]:
            """Get endpoints from ontology."""
            ontology = self._get_ontology()
            endpoints = ontology.get_endpoints_for_indication(indication)

            if primary_only:
                endpoints = [e for e in endpoints if e.get("is_primary", False)]

            return endpoints

        @Function(
            description="Get ICD-10 codes for an indication",
            parameters={
                "indication": {"type": "string", "description": "Indication name"},
            }
        )
        async def get_icd10_codes(self, indication: str) -> List[Dict[str, Any]]:
            """Get ICD-10 codes."""
            ontology = self._get_ontology()
            return ontology.get_icd10_codes(indication)

        @Function(
            description="Validate if an endpoint is appropriate for an indication",
            parameters={
                "indication": {"type": "string", "description": "Indication"},
                "endpoint": {"type": "string", "description": "Endpoint name"},
            }
        )
        async def validate_endpoint(
            self,
            indication: str,
            endpoint: str,
        ) -> Dict[str, Any]:
            """Validate endpoint."""
            ontology = self._get_ontology()
            is_valid = ontology.is_valid_endpoint(indication, endpoint)
            is_fda = ontology.is_fda_accepted_endpoint(indication, endpoint)
            mcid = ontology.get_mcid(indication, endpoint)

            return {
                "valid": is_valid,
                "fda_accepted": is_fda,
                "mcid": mcid,
            }


# =============================================================================
# Agent Factories
# =============================================================================

if AGNO_AVAILABLE:
    def create_publication_retrieval_agent() -> Agent:
        """Create agent for retrieving IVA publications."""
        return Agent(
            name="IVA Publication Retrieval Agent",
            model=Claude(id="claude-haiku-3-5"),
            instructions="""You are a publication retrieval specialist for IVA evidence strengthening.

Your role is to:
1. Query the IVA publications database for relevant evidence
2. Filter by indication and narrative pillar
3. Prioritize high-relevance, recent publications
4. Extract key data points from publication metadata

For each publication, extract:
- Title and source (PMID/DOI)
- Publication year
- Key findings/data points
- Evidence type (RCT, registry, etc.)
- Indication and narrative pillar classification

Return structured data suitable for evidence table generation.""",
            tools=[IVAPublicationToolkit()],
        )

    def create_evidence_organization_agent() -> Agent:
        """Create agent for organizing evidence by pillar."""
        return Agent(
            name="Evidence Organization Agent",
            model=Claude(id="claude-sonnet-4-5"),
            instructions="""You are an evidence organization specialist for medical affairs.

Your role is to:
1. Organize evidence items by indication and CEJ narrative pillar
2. Map each evidence item to the appropriate pillar based on content
3. Ensure pillar assignments align with CEJ messaging strategy
4. Identify the deployment context for each piece of evidence

CEJ Narrative Pillars:
1. Disease Chronicity - Disease is chronically active, not episodic
2. Cumulative Burden - Burden accumulates over time
3. Chronic Strategy - Chronic disease needs chronic management
4. Durable Results - Long-term efficacy data
5. Proven Safety - Long-term safety profile

For each pillar, identify:
- Supporting evidence items
- Key data points with sources
- Deployment guidance (how to use in messaging)

Return organized evidence tables by indication and pillar.""",
            tools=[IVAPublicationToolkit(), OntologyToolkit()],
            reasoning=True,
        )

    def create_gap_analysis_agent() -> Agent:
        """Create agent for evidence gap analysis."""
        return Agent(
            name="Evidence Gap Analysis Agent",
            model=Claude(id="claude-sonnet-4-5"),
            instructions="""You are an evidence gap analyst for IVA materials.

Your role is to:
1. Compare current evidence against CEJ messaging needs
2. Identify gaps where claims lack supporting evidence
3. Flag claims that should be avoided (CAUTION)
4. Assess evidence strength for each claim

For each CEJ claim, determine:
- Current Support: What evidence exists
- Status: FULLY_SUPPORTED, PARTIALLY_SUPPORTED, GAP, or CAUTION
- Recommendation: How to address the gap

Evidence Strength Hierarchy:
1. FDA Label (highest)
2. Phase 3 RCT
3. Registry/RWE
4. Meta-analysis
5. Case series
6. Expert opinion (lowest)

Be conservative - only mark as FULLY_SUPPORTED when strong evidence exists.
Mark CAUTION for claims that could be challenged or have contradictory data.""",
            tools=[IVAPublicationToolkit(), OntologyToolkit()],
            reasoning=True,
        )

    def create_competitive_coverage_agent() -> Agent:
        """Create agent for competitive coverage analysis."""
        return Agent(
            name="Competitive Coverage Agent",
            model=Claude(id="claude-sonnet-4-5"),
            instructions="""You are a competitive intelligence analyst for pharmaceutical products.

Your role is to:
1. Build coverage parity matrices comparing our drug vs competitors
2. Identify competitive advantages and disadvantages
3. Assess data coverage gaps relative to competitors
4. Generate competitive positioning recommendations

Coverage Categories to Analyze:
- Week 16 Efficacy (IGA, EASI, etc.)
- Week 52 Efficacy
- Long-term data (3-5 year)
- Drug survival/persistence
- QoL measures (DLQI, etc.)
- Safety profile
- Speed of onset

For each category, determine:
- Our coverage status
- Competitor coverage
- Parity status: Complete, Gap, or Advantage

Highlight areas where we have data advantages over competitors.""",
            tools=[CompetitiveIntelToolkit(), OntologyToolkit()],
            reasoning=True,
        )

    def create_positioning_cautions_agent() -> Agent:
        """Create agent for identifying positioning cautions."""
        return Agent(
            name="Positioning Cautions Agent",
            model=Claude(id="claude-sonnet-4-5"),
            instructions="""You are a regulatory and medical affairs compliance specialist.

Your role is to:
1. Identify claims that should be AVOIDED in messaging
2. Flag incorrect or outdated data points
3. Highlight areas where competitors have advantages we shouldn't challenge
4. Ensure compliance with FDA label claims

Generate cautions for:
- Failed endpoints in trials (e.g., CUPID B for omalizumab-refractory)
- Head-to-head losses (e.g., Heads Up vs Rinvoq)
- Unsupported superiority claims
- Data that has been superseded or corrected
- Competitive claims we cannot substantiate

For each caution:
- Indication: Where this applies
- Avoid Claiming: The specific claim to avoid
- Reason: Why it should be avoided
- Alternative: What to say instead (if applicable)

Be thorough - missing cautions can lead to regulatory or legal issues.""",
            tools=[CompetitiveIntelToolkit(), IVAPublicationToolkit()],
            reasoning=True,
        )

    def create_report_assembly_agent() -> Agent:
        """Create agent for assembling the final report."""
        return Agent(
            name="Report Assembly Agent",
            model=Claude(id="claude-sonnet-4-5"),
            instructions="""You are a medical writing specialist for IVA evidence reports.

Your role is to:
1. Assemble evidence tables, gap analyses, and competitive data into a cohesive report
2. Follow the exact structure of IVA Evidence Strengthening documents
3. Generate clear, actionable deployment guidance
4. Include proper citations and source attributions

Report Structure:
1. Executive Summary
   - Document Overview
   - Key Evidence Updates table
   - Positioning Cautions table

2. Per-Indication Sections
   - Target Belief Shift
   - Pillar 1-5 with evidence tables
   - Evidence Gap Analysis

3. Competitive Landscape
   - Competitor Summary tables
   - Competitive Positioning tables

4. CEJ Narrative Alignment
   - Structure tables per indication

5. Appendices
   - Data Source Methodology
   - FDA Label Comparison Tables
   - Coverage Parity Matrices
   - References

Format tables using Markdown pipe syntax.
Include PMID/DOI links for all sources.
Use clear headers and consistent formatting.""",
            reasoning=True,
        )


# =============================================================================
# Team Definitions
# =============================================================================

if AGNO_AVAILABLE:
    def create_data_gathering_team() -> Team:
        """Create team for parallel data gathering."""
        return Team(
            name="Data Gathering Team",
            description="Gathers publications and competitive intelligence in parallel",
            agents=[
                create_publication_retrieval_agent(),
            ],
            mode="parallel",
        )

    def create_analysis_team() -> Team:
        """Create team for sequential analysis pipeline."""
        return Team(
            name="Analysis Team",
            description="Analyzes evidence through sequential pipeline",
            agents=[
                create_evidence_organization_agent(),
                create_gap_analysis_agent(),
                create_competitive_coverage_agent(),
                create_positioning_cautions_agent(),
            ],
            mode="sequential",
        )


# =============================================================================
# Main Workflow Class
# =============================================================================

class IVAEvidenceReportWorkflow:
    """
    Orchestrates the IVA Evidence Strengthening Report generation workflow.

    Uses a multi-agent pipeline:
    1. Data Gathering (parallel)
    2. Evidence Organization (sequential)
    3. Gap Analysis (sequential)
    4. Competitive Coverage (sequential)
    5. Positioning Cautions (sequential)
    6. Report Assembly (final)
    """

    def __init__(self):
        """Initialize the workflow."""
        self._ontology = get_clinical_endpoints_ontology()

        if AGNO_AVAILABLE:
            self.data_gathering_team = create_data_gathering_team()
            self.analysis_team = create_analysis_team()
            self.report_agent = create_report_assembly_agent()
            logger.info("IVA Evidence Report Workflow initialized with Agno agents")
        else:
            logger.info("IVA Evidence Report Workflow initialized with fallback mode")

    async def run(self, inputs: WorkflowInputs) -> WorkflowOutputs:
        """
        Execute the IVA Evidence Report workflow.

        Args:
            inputs: Workflow input parameters

        Returns:
            WorkflowOutputs with evidence tables, gap analysis, and final report
        """
        run_id = uuid4()
        start_time = datetime.now()

        logger.info(f"Starting IVA Evidence Report workflow {run_id} for {inputs.drug_name}")

        if AGNO_AVAILABLE:
            return await self._run_agno(inputs, run_id, start_time)
        else:
            return await self._run_fallback(inputs, run_id, start_time)

    async def _run_agno(
        self,
        inputs: WorkflowInputs,
        run_id: UUID,
        start_time: datetime,
    ) -> WorkflowOutputs:
        """Run workflow using Agno agents."""
        agents_used = []

        # Initialize output containers
        all_evidence_tables: Dict[str, List[EvidenceTable]] = {}
        all_evidence_gaps: Dict[str, List[EvidenceGap]] = {}
        all_coverage_matrices: Dict[str, List[CoverageMatrix]] = {}
        all_competitor_coverage: List[CompetitorCoverage] = []
        all_cautions: List[PositioningCaution] = []

        total_evidence_items = 0
        evidence_by_pillar: Dict[str, int] = {}
        evidence_by_indication: Dict[str, int] = {}

        # Process each indication
        for indication in inputs.indications:
            logger.info(f"Processing indication: {indication}")

            # Step 1: Gather publications
            try:
                pub_result = await self.data_gathering_team.arun(
                    message=f"Retrieve IVA publications for {inputs.drug_name} in {indication} from the last {inputs.years_back} years. Include all narrative pillars.",
                    context={
                        "drug_name": inputs.drug_name,
                        "indication": indication,
                        "years_back": inputs.years_back,
                    }
                )
                agents_used.append("IVA Publication Retrieval Agent")
            except Exception as e:
                logger.error(f"Data gathering failed: {e}")
                continue

            # Step 2-5: Run analysis pipeline
            try:
                await self.analysis_team.arun(
                    message=f"Analyze evidence for {inputs.drug_name} in {indication}. Organize by CEJ pillar, identify gaps, analyze competitive coverage, and flag positioning cautions.",
                    context={
                        "drug_name": inputs.drug_name,
                        "indication": indication,
                        "publications": pub_result.output if hasattr(pub_result, 'output') else [],
                        "include_competitors": inputs.include_competitors,
                        "pillar_config": PILLAR_CONFIG.get(indication.lower().replace(" ", "_"), {}),
                    }
                )
                agents_used.extend([
                    "Evidence Organization Agent",
                    "Evidence Gap Analysis Agent",
                    "Competitive Coverage Agent",
                    "Positioning Cautions Agent",
                ])
            except Exception as e:
                logger.error(f"Analysis pipeline failed: {e}")
                continue

            # Extract results from analysis
            # In a real implementation, we'd parse the agent outputs
            # For now, use fallback data generation
            evidence_tables = await self._generate_evidence_tables_fallback(
                inputs.drug_name, indication
            )
            all_evidence_tables[indication] = evidence_tables

            # Count evidence
            for table in evidence_tables:
                total_evidence_items += len(table.evidence_items)
                pillar_key = table.pillar.value
                evidence_by_pillar[pillar_key] = evidence_by_pillar.get(pillar_key, 0) + len(table.evidence_items)

            evidence_by_indication[indication] = sum(len(t.evidence_items) for t in evidence_tables)

            # Generate gap analysis
            if inputs.include_gap_analysis:
                gaps = await self._generate_gaps_fallback(inputs.drug_name, indication)
                all_evidence_gaps[indication] = gaps

            # Generate coverage matrices
            if inputs.include_coverage_matrices:
                matrices = await self._generate_coverage_matrices_fallback(
                    inputs.drug_name, indication
                )
                all_coverage_matrices[indication] = matrices

        # Generate positioning cautions
        cautions = await self._generate_cautions_fallback(inputs.drug_name, inputs.indications)
        all_cautions = cautions

        # Step 6: Assemble final report
        try:
            report_context = {
                "drug_name": inputs.drug_name,
                "indications": inputs.indications,
                "evidence_tables": all_evidence_tables,
                "evidence_gaps": all_evidence_gaps,
                "coverage_matrices": all_coverage_matrices,
                "positioning_cautions": all_cautions,
                "generated_at": datetime.now().isoformat(),
            }

            report_result = await self.report_agent.arun(
                message="Assemble the final IVA Evidence Strengthening Report using all the gathered data.",
                context=report_context,
            )
            agents_used.append("Report Assembly Agent")

            markdown_report = report_result.output if hasattr(report_result, 'output') else ""
        except Exception as e:
            logger.error(f"Report assembly failed: {e}")
            markdown_report = await self._generate_report_fallback(
                inputs.drug_name,
                inputs.indications,
                all_evidence_tables,
                all_evidence_gaps,
                all_coverage_matrices,
                all_cautions,
            )

        # If report is empty, use fallback
        if not markdown_report:
            markdown_report = await self._generate_report_fallback(
                inputs.drug_name,
                inputs.indications,
                all_evidence_tables,
                all_evidence_gaps,
                all_coverage_matrices,
                all_cautions,
            )

        # Calculate duration
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return WorkflowOutputs(
            run_id=run_id,
            drug_name=inputs.drug_name,
            indications=inputs.indications,
            generated_at=datetime.now().isoformat(),
            evidence_tables=all_evidence_tables,
            evidence_gaps=all_evidence_gaps,
            coverage_matrices=all_coverage_matrices,
            competitor_coverage=all_competitor_coverage,
            positioning_cautions=all_cautions,
            markdown_report=markdown_report,
            total_evidence_items=total_evidence_items,
            evidence_by_pillar=evidence_by_pillar,
            evidence_by_indication=evidence_by_indication,
            gaps_identified=sum(len(g) for g in all_evidence_gaps.values()),
            cautions_identified=len(all_cautions),
            workflow_duration_ms=duration_ms,
            agents_used=list(set(agents_used)),
        )

    async def _run_fallback(
        self,
        inputs: WorkflowInputs,
        run_id: UUID,
        start_time: datetime,
    ) -> WorkflowOutputs:
        """Run workflow using fallback implementation (no Agno)."""
        logger.info("Running IVA Evidence Report workflow in fallback mode")

        all_evidence_tables: Dict[str, List[EvidenceTable]] = {}
        all_evidence_gaps: Dict[str, List[EvidenceGap]] = {}
        all_coverage_matrices: Dict[str, List[CoverageMatrix]] = {}
        all_cautions: List[PositioningCaution] = []

        total_evidence_items = 0
        evidence_by_pillar: Dict[str, int] = {}
        evidence_by_indication: Dict[str, int] = {}

        for indication in inputs.indications:
            # Generate evidence tables
            evidence_tables = await self._generate_evidence_tables_fallback(
                inputs.drug_name, indication
            )
            all_evidence_tables[indication] = evidence_tables

            for table in evidence_tables:
                total_evidence_items += len(table.evidence_items)
                pillar_key = table.pillar.value
                evidence_by_pillar[pillar_key] = evidence_by_pillar.get(pillar_key, 0) + len(table.evidence_items)

            evidence_by_indication[indication] = sum(len(t.evidence_items) for t in evidence_tables)

            if inputs.include_gap_analysis:
                gaps = await self._generate_gaps_fallback(inputs.drug_name, indication)
                all_evidence_gaps[indication] = gaps

            if inputs.include_coverage_matrices:
                matrices = await self._generate_coverage_matrices_fallback(
                    inputs.drug_name, indication
                )
                all_coverage_matrices[indication] = matrices

        cautions = await self._generate_cautions_fallback(inputs.drug_name, inputs.indications)
        all_cautions = cautions

        markdown_report = await self._generate_report_fallback(
            inputs.drug_name,
            inputs.indications,
            all_evidence_tables,
            all_evidence_gaps,
            all_coverage_matrices,
            all_cautions,
        )

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return WorkflowOutputs(
            run_id=run_id,
            drug_name=inputs.drug_name,
            indications=inputs.indications,
            generated_at=datetime.now().isoformat(),
            evidence_tables=all_evidence_tables,
            evidence_gaps=all_evidence_gaps,
            coverage_matrices=all_coverage_matrices,
            positioning_cautions=all_cautions,
            markdown_report=markdown_report,
            total_evidence_items=total_evidence_items,
            evidence_by_pillar=evidence_by_pillar,
            evidence_by_indication=evidence_by_indication,
            gaps_identified=sum(len(g) for g in all_evidence_gaps.values()),
            cautions_identified=len(all_cautions),
            workflow_duration_ms=duration_ms,
            agents_used=["Fallback Implementation"],
        )

    async def _generate_evidence_tables_fallback(
        self,
        drug_name: str,
        indication: str,
    ) -> List[EvidenceTable]:
        """Generate evidence tables using fallback (database query)."""
        tables = []
        ind_key = indication.lower().replace(" ", "_")
        pillar_config = PILLAR_CONFIG.get(ind_key, {})

        # Query publications from database
        publications = []
        try:
            async with get_db_connection() as conn:
                rows = await conn.fetch("""
                    SELECT
                        title, doi, pmid, publication_year,
                        iva_narrative_pillar, iva_evidence_type,
                        key_endpoints, data_source
                    FROM iva_publications
                    WHERE $1 = ANY(drug_names)
                      AND iva_indication = $2
                    ORDER BY iva_relevance_score DESC
                    LIMIT 50
                """, drug_name.lower(), indication)

                for row in rows:
                    publications.append(dict(row))
        except Exception as e:
            logger.warning(f"Could not query publications: {e}")

        # Create evidence table for each pillar
        for pillar, config in pillar_config.items():
            evidence_items = []

            # Filter publications for this pillar
            pillar_pubs = [
                p for p in publications
                if p.get("iva_narrative_pillar") == pillar.value
            ]

            for pub in pillar_pubs[:5]:  # Limit to 5 per pillar
                # Build source reference
                source = ""
                if pub.get("pmid"):
                    source = f"PMID {pub['pmid']}"
                elif pub.get("doi"):
                    source = f"DOI {pub['doi']}"

                # Extract key endpoint data
                endpoints = pub.get("key_endpoints", [])
                if isinstance(endpoints, str):
                    try:
                        endpoints = json.loads(endpoints)
                    except Exception:
                        endpoints = []

                data_point = pub.get("title", "")[:100]
                if endpoints and len(endpoints) > 0:
                    ep = endpoints[0]
                    data_point = f"{ep.get('endpoint', '')}: {ep.get('value', '')}"

                evidence_items.append(EvidenceItem(
                    description=pub.get("title", "")[:100],
                    data_point=data_point,
                    source=source,
                    year=pub.get("publication_year"),
                    indication=indication,
                    pillar=pillar,
                    strength=EvidenceStrength.RCT if pub.get("iva_evidence_type") == "rct" else EvidenceStrength.REGISTRY,
                ))

            tables.append(EvidenceTable(
                indication=indication,
                pillar=pillar,
                pillar_title=config.get("title", pillar.value),
                narrative=config.get("narrative", ""),
                evidence_items=evidence_items,
                deployment_guidance=f"Use to support \"{config.get('title', '')}\" messaging.",
            ))

        return tables

    async def _generate_gaps_fallback(
        self,
        drug_name: str,
        indication: str,
    ) -> List[EvidenceGap]:
        """Generate evidence gaps using fallback."""

        # Standard gap analysis based on indication
        gap_templates = {
            "atopic_dermatitis": [
                EvidenceGap(
                    claim="80% maintained response at 1 year",
                    current_support="SOLO-CONTINUE, PROSE 2-yr data",
                    status=GapStatus.FULLY_SUPPORTED,
                ),
                EvidenceGap(
                    claim="5-year real-world control",
                    current_support="BioDay cited",
                    status=GapStatus.FULLY_SUPPORTED,
                ),
            ],
            "prurigo_nodularis": [
                EvidenceGap(
                    claim="70% achieved itch or nodule clearance at Week 24",
                    current_support="58.8% itch + 46.4% skin",
                    status=GapStatus.FULLY_SUPPORTED,
                ),
                EvidenceGap(
                    claim="Long-term durability",
                    current_support="84-week and 104-week data",
                    status=GapStatus.FULLY_SUPPORTED,
                ),
            ],
            "chronic_spontaneous_urticaria": [
                EvidenceGap(
                    claim="Improved itch and hives vs placebo at Week 24",
                    current_support="CUPID A/C with P-values",
                    status=GapStatus.FULLY_SUPPORTED,
                ),
                EvidenceGap(
                    claim="Long-term efficacy",
                    current_support="Limited to 24 weeks",
                    status=GapStatus.GAP,
                    recommendation="Monitor for extension study data",
                ),
                EvidenceGap(
                    claim="Omalizumab-refractory efficacy",
                    current_support="CUPID B failed",
                    status=GapStatus.CAUTION,
                    recommendation="Do not claim efficacy in this population",
                ),
            ],
        }

        ind_key = indication.lower().replace(" ", "_")
        return gap_templates.get(ind_key, [])

    async def _generate_coverage_matrices_fallback(
        self,
        drug_name: str,
        indication: str,
    ) -> List[CoverageMatrix]:
        """Generate coverage parity matrices using fallback."""

        # Standard coverage categories
        coverage_templates = {
            "atopic_dermatitis": [
                CoverageMatrix(
                    indication=indication,
                    data_category="Week 16 Efficacy",
                    our_drug=drug_name,
                    our_coverage="SOLO/CHRONOS",
                    competitors={"Ebglyss": "ADvocate", "Rinvoq": "Measure Up", "Nemluvio": "ARCADIA"},
                    parity_status="Complete",
                ),
                CoverageMatrix(
                    indication=indication,
                    data_category="5-Year Data",
                    our_drug=drug_name,
                    our_coverage="BioDay 78-92% EASI≤7",
                    competitors={"Ebglyss": "3yr only (50%)", "Rinvoq": "No 5yr", "Nemluvio": "No 5yr"},
                    parity_status="Advantage",
                ),
                CoverageMatrix(
                    indication=indication,
                    data_category="Drug Survival",
                    our_drug=drug_name,
                    our_coverage="74% @ 5yr",
                    competitors={"Ebglyss": "Limited", "Rinvoq": "48% @ 18mo", "Nemluvio": "Limited"},
                    parity_status="Advantage",
                ),
            ],
            "chronic_spontaneous_urticaria": [
                CoverageMatrix(
                    indication=indication,
                    data_category="Week 12 Efficacy",
                    our_drug=drug_name,
                    our_coverage="UAS7≤6: 35.3%",
                    competitors={"Xolair": "UAS7=0: 34-44%", "RHAPSIDO": "UAS7=0: 28-31%"},
                    parity_status="Complete",
                ),
                CoverageMatrix(
                    indication=indication,
                    data_category="Week 52 Efficacy",
                    our_drug=drug_name,
                    our_coverage="No data",
                    competitors={"Xolair": "Established", "RHAPSIDO": "~48% UAS7=0"},
                    parity_status="Gap",
                ),
            ],
        }

        ind_key = indication.lower().replace(" ", "_")
        return coverage_templates.get(ind_key, [])

    async def _generate_cautions_fallback(
        self,
        drug_name: str,
        indications: List[str],
    ) -> List[PositioningCaution]:
        """Generate positioning cautions using fallback."""
        cautions = [
            PositioningCaution(
                indication="Atopic Dermatitis",
                avoid_claiming="SOLO-CONTINUE '20%/48%' flare data",
                reason="INCORRECT - Use verified: 10% flare (dupilumab) vs 37% (placebo)",
                alternative="Cite correct SOLO-CONTINUE flare prevention data",
            ),
            PositioningCaution(
                indication="Chronic Spontaneous Urticaria",
                avoid_claiming="Efficacy in omalizumab-refractory",
                reason="CUPID B did not meet primary endpoints",
                alternative="Position for antihistamine-refractory, not biologic-refractory",
            ),
            PositioningCaution(
                indication="Chronic Spontaneous Urticaria",
                avoid_claiming="Superiority vs omalizumab",
                reason="No head-to-head data",
                alternative="Position based on Type 2 comorbidities and MOA differentiation",
            ),
            PositioningCaution(
                indication="Prurigo Nodularis",
                avoid_claiming="Faster itch relief than Nemluvio",
                reason="IL-31 mechanism may provide faster onset",
                alternative="Emphasize comprehensive disease control (IGA 0/1) advantage",
            ),
        ]

        # Filter by requested indications
        filtered = []
        for caution in cautions:
            for ind in indications:
                if ind.lower().replace("_", " ") in caution.indication.lower():
                    filtered.append(caution)
                    break

        return filtered if filtered else cautions

    async def _generate_report_fallback(
        self,
        drug_name: str,
        indications: List[str],
        evidence_tables: Dict[str, List[EvidenceTable]],
        evidence_gaps: Dict[str, List[EvidenceGap]],
        coverage_matrices: Dict[str, List[CoverageMatrix]],
        positioning_cautions: List[PositioningCaution],
    ) -> str:
        """Generate the final Markdown report using fallback."""
        lines = []

        # Header
        drug_display = drug_name.title()
        lines.append(f"# {drug_display} IVA Evidence Strengthening Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Executive Summary
        lines.append("# Executive Summary")
        lines.append("")
        lines.append("## Document Overview")
        lines.append("")
        lines.append(f"This document provides evidence support for {drug_display} IVA materials organized by indication and CEJ narrative pillar.")
        lines.append("")

        # Key Evidence Updates table
        lines.append("## Key Evidence Updates")
        lines.append("")
        lines.append("| Indication | Key Update | Impact |")
        lines.append("|------------|-----------|--------|")

        for indication in indications:
            ind_tables = evidence_tables.get(indication, [])
            if ind_tables:
                for table in ind_tables[:1]:  # Just first pillar as example
                    if table.evidence_items:
                        item = table.evidence_items[0]
                        lines.append(f"| **{indication.replace('_', ' ').title()}** | {item.data_point[:50]} | {table.pillar_title} |")

        lines.append("")

        # Positioning Cautions
        lines.append("## Positioning Cautions")
        lines.append("")
        lines.append("| Indication | Avoid Claiming | Reason |")
        lines.append("|------------|---------------|--------|")

        for caution in positioning_cautions:
            lines.append(f"| **{caution.indication}** | {caution.avoid_claiming} | {caution.reason} |")

        lines.append("")
        lines.append("---")
        lines.append("")

        # Per-Indication Sections
        for idx, indication in enumerate(indications, 1):
            ind_display = indication.replace("_", " ").title()
            lines.append(f"# Part {idx}: {ind_display}")
            lines.append("")

            ind_key = indication.lower().replace(" ", "_")
            pillar_config = PILLAR_CONFIG.get(ind_key, {})

            # Target Belief Shift
            if pillar_config:
                lines.append("## Target Belief Shift")
                lines.append("")
                lines.append("> [Insert target belief shift from CEJ]")
                lines.append("")

            # Evidence tables by pillar
            ind_tables = evidence_tables.get(indication, [])
            for table in ind_tables:
                lines.append(f"### {table.pillar_title}")
                lines.append("")
                lines.append(f"**Narrative:** {table.narrative}")
                lines.append("")

                if table.evidence_items:
                    lines.append("| New Evidence | Data Point | Source | Year |")
                    lines.append("|-------------|------------|--------|------|")

                    for item in table.evidence_items:
                        year_str = str(item.year) if item.year else "-"
                        lines.append(f"| {item.description[:40]} | {item.data_point[:40]} | {item.source} | {year_str} |")

                    lines.append("")

                if table.deployment_guidance:
                    lines.append(f"**Deployment:** {table.deployment_guidance}")
                    lines.append("")

                lines.append("---")
                lines.append("")

            # Evidence Gap Analysis
            ind_gaps = evidence_gaps.get(indication, [])
            if ind_gaps:
                lines.append(f"### {ind_display} Evidence Gap Analysis")
                lines.append("")
                lines.append("| CEJ Claim | Current Support | Status |")
                lines.append("|-----------|----------------|--------|")

                for gap in ind_gaps:
                    status_display = gap.status.value.replace("_", " ").title()
                    if gap.status == GapStatus.CAUTION:
                        status_display = "**CAUTION**"
                    elif gap.status == GapStatus.GAP:
                        status_display = "**GAP**"
                    lines.append(f"| {gap.claim} | {gap.current_support} | {status_display} |")

                lines.append("")
                lines.append("---")
                lines.append("")

        # Coverage Matrices
        has_matrices = any(coverage_matrices.values())
        if has_matrices:
            lines.append("# Appendix: Coverage Parity Matrices")
            lines.append("")

            for indication in indications:
                ind_matrices = coverage_matrices.get(indication, [])
                if ind_matrices:
                    ind_display = indication.replace("_", " ").title()
                    lines.append(f"## {ind_display} Coverage Matrix")
                    lines.append("")

                    # Get all competitor names
                    all_competitors = set()
                    for matrix in ind_matrices:
                        all_competitors.update(matrix.competitors.keys())

                    # Header
                    comp_headers = " | ".join(all_competitors)
                    lines.append(f"| Data Category | {drug_display} | {comp_headers} | Parity |")
                    lines.append("|" + "---|" * (3 + len(all_competitors)))

                    for matrix in ind_matrices:
                        comp_values = " | ".join(matrix.competitors.get(c, "-") for c in all_competitors)
                        lines.append(f"| **{matrix.data_category}** | {matrix.our_coverage} | {comp_values} | {matrix.parity_status} |")

                    lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append(f"*Document generated by IVA Evidence Report Workflow | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)


# =============================================================================
# Convenience Function
# =============================================================================

async def generate_iva_evidence_report(
    drug_name: str,
    indications: Optional[List[str]] = None,
    include_competitors: bool = True,
    include_gap_analysis: bool = True,
    include_coverage_matrices: bool = True,
    years_back: int = 2,
    output_format: str = "markdown",
) -> WorkflowOutputs:
    """
    Convenience function to generate an IVA Evidence Strengthening Report.

    Args:
        drug_name: Name of the drug (e.g., "dupilumab")
        indications: List of indications to include
        include_competitors: Include competitive analysis
        include_gap_analysis: Include evidence gap analysis
        include_coverage_matrices: Include coverage parity matrices
        years_back: Include evidence from last N years
        output_format: Output format (markdown, html, json)

    Returns:
        WorkflowOutputs with the complete report and structured data
    """
    if indications is None:
        indications = ["atopic_dermatitis"]

    workflow = IVAEvidenceReportWorkflow()

    inputs = WorkflowInputs(
        drug_name=drug_name,
        indications=indications,
        include_competitors=include_competitors,
        include_gap_analysis=include_gap_analysis,
        include_coverage_matrices=include_coverage_matrices,
        years_back=years_back,
        output_format=output_format,
    )

    return await workflow.run(inputs)
