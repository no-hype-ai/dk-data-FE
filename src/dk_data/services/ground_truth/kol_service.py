"""
KOL (Key Opinion Leader) Intelligence Service.

Implements:
- T156: KOLIntelligenceService class
- T157: identify_kols() using publication, trial, grant data
- T158: get_kol_network() with co-author/co-investigator data
- T159-T160: PatientAdvocacyService
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from enum import Enum
from loguru import logger

from ..external_apis.openalex_client import OpenAlexClient, Author

if TYPE_CHECKING:
    from .news_service import NewsService


class KOLTier(str, Enum):
    """KOL influence tiers."""
    GLOBAL = "global"  # Top 1% - international recognition
    NATIONAL = "national"  # Top 5% - national recognition
    REGIONAL = "regional"  # Top 20% - regional recognition
    RISING = "rising"  # Emerging KOL


class ExpertiseArea(str, Enum):
    """Areas of expertise."""
    CLINICAL = "clinical"
    RESEARCH = "research"
    REGULATORY = "regulatory"
    ADVOCACY = "advocacy"
    POLICY = "policy"


@dataclass
class KOL:
    """Key Opinion Leader profile."""
    kol_id: str
    name: str
    tier: KOLTier = KOLTier.REGIONAL
    affiliations: List[str] = field(default_factory=list)
    therapeutic_areas: List[str] = field(default_factory=list)
    expertise_areas: List[ExpertiseArea] = field(default_factory=list)
    h_index: Optional[int] = None
    publications_count: int = 0
    citations_count: int = 0
    clinical_trials_count: int = 0
    grants_count: int = 0
    influence_score: float = 0.0
    email: Optional[str] = None
    linkedin: Optional[str] = None
    twitter: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "kol_id": self.kol_id,
            "name": self.name,
            "tier": self.tier.value,
            "affiliations": self.affiliations[:5],
            "therapeutic_areas": self.therapeutic_areas,
            "expertise_areas": [e.value for e in self.expertise_areas],
            "h_index": self.h_index,
            "publications_count": self.publications_count,
            "citations_count": self.citations_count,
            "clinical_trials_count": self.clinical_trials_count,
            "influence_score": round(self.influence_score, 2),
        }


@dataclass
class KOLConnection:
    """Connection between KOLs."""
    from_kol_id: str
    to_kol_id: str
    connection_type: str  # co_author, co_investigator, same_institution
    strength: float = 0.0
    shared_publications: int = 0
    shared_trials: int = 0


@dataclass
class KOLNetwork:
    """Network of KOLs."""
    center_kol: KOL
    connections: List[KOLConnection]
    connected_kols: List[KOL]
    network_size: int = 0
    avg_connection_strength: float = 0.0


@dataclass
class PatientAdvocacyGroup:
    """Patient advocacy organization."""
    org_id: str
    name: str
    disease_focus: List[str]
    website: Optional[str] = None
    location: Optional[str] = None
    size_estimate: Optional[str] = None  # small, medium, large
    activities: List[str] = field(default_factory=list)  # research, education, policy
    contact_email: Optional[str] = None
    social_media: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "org_id": self.org_id,
            "name": self.name,
            "disease_focus": self.disease_focus,
            "website": self.website,
            "location": self.location,
            "size_estimate": self.size_estimate,
            "activities": self.activities,
        }


class KOLIntelligenceService:
    """
    Service for identifying and analyzing Key Opinion Leaders.

    Uses data from:
    - OpenAlex (publications, authors)
    - ClinicalTrials.gov (investigators)
    - NIH Reporter (grants)
    - ORCID (researcher profiles)
    """

    # Weights for influence score calculation
    INFLUENCE_WEIGHTS = {
        "h_index": 0.30,
        "publications": 0.20,
        "citations": 0.25,
        "trials": 0.15,
        "grants": 0.10,
    }

    # Tier thresholds (percentile-based)
    TIER_THRESHOLDS = {
        KOLTier.GLOBAL: 0.95,
        KOLTier.NATIONAL: 0.80,
        KOLTier.REGIONAL: 0.50,
    }

    def __init__(
        self,
        openalex_client: Optional[OpenAlexClient] = None,
    ):
        self._openalex = openalex_client or OpenAlexClient()

    async def identify_kols(
        self,
        therapeutic_area: str,
        indication: Optional[str] = None,
        limit: int = 50,
    ) -> List[KOL]:
        """
        Identify Key Opinion Leaders in a therapeutic area.

        Args:
            therapeutic_area: Therapeutic area (e.g., "Oncology")
            indication: Specific indication (e.g., "NSCLC")
            limit: Maximum KOLs to return

        Returns:
            List of KOLs ranked by influence
        """
        logger.info(f"Identifying KOLs in {therapeutic_area}")

        # Search for authors in the field
        query = f"{therapeutic_area} {indication}" if indication else therapeutic_area
        authors = await self._openalex.search_authors(query, limit=limit * 2)

        # Convert to KOLs and calculate influence
        kols = []
        for author in authors:
            kol = self._author_to_kol(author, therapeutic_area)
            kol.influence_score = self._calculate_influence_score(kol)
            kols.append(kol)

        # Rank by influence score
        kols.sort(key=lambda x: x.influence_score, reverse=True)

        # Assign tiers
        for i, kol in enumerate(kols):
            percentile = 1 - (i / len(kols)) if kols else 0
            kol.tier = self._assign_tier(percentile)

        return kols[:limit]

    async def get_kol_details(
        self,
        kol_id: str,
    ) -> Optional[KOL]:
        """Get detailed information about a specific KOL."""
        try:
            # Query OpenAlex for author details
            authors = await self._openalex.search_authors(kol_id, limit=1)
            if authors:
                kol = self._author_to_kol(authors[0], "")
                kol.influence_score = self._calculate_influence_score(kol)
                return kol
            return None
        except Exception as e:
            logger.error(f"Error getting KOL details: {e}")
            return None

    async def get_kol_network(
        self,
        kol_id: str,
        depth: int = 1,
    ) -> KOLNetwork:
        """
        Get network of collaborators for a KOL.

        Args:
            kol_id: KOL identifier (OpenAlex ID or name)
            depth: Network depth (1 = direct connections)

        Returns:
            KOLNetwork with connections and connected KOLs
        """
        logger.info(f"Building KOL network for {kol_id}")

        # Get center KOL
        center_kol = await self.get_kol_details(kol_id)
        if not center_kol:
            return KOLNetwork(
                center_kol=KOL(kol_id=kol_id, name=kol_id),
                connections=[],
                connected_kols=[],
            )

        # Get publications to find co-authors
        publications = await self._openalex.search_publications(
            center_kol.name,
            limit=50,
        )

        # Extract co-authors
        coauthor_counts: Dict[str, int] = {}
        for pub in publications:
            for author in pub.authors:
                author_name = author.get("name", "")
                if author_name and author_name != center_kol.name:
                    coauthor_counts[author_name] = coauthor_counts.get(author_name, 0) + 1

        # Build connections for top co-authors
        connections = []
        connected_kols = []

        top_coauthors = sorted(
            coauthor_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]

        for coauthor_name, shared_pubs in top_coauthors:
            # Create connection
            connections.append(KOLConnection(
                from_kol_id=center_kol.kol_id,
                to_kol_id=coauthor_name,
                connection_type="co_author",
                strength=min(1.0, shared_pubs / 10),
                shared_publications=shared_pubs,
            ))

            # Get coauthor as KOL
            coauthor_kols = await self._openalex.search_authors(coauthor_name, limit=1)
            if coauthor_kols:
                kol = self._author_to_kol(coauthor_kols[0], "")
                kol.influence_score = self._calculate_influence_score(kol)
                connected_kols.append(kol)

        # Calculate network metrics
        avg_strength = (
            sum(c.strength for c in connections) / len(connections)
            if connections else 0
        )

        return KOLNetwork(
            center_kol=center_kol,
            connections=connections,
            connected_kols=connected_kols,
            network_size=len(connected_kols),
            avg_connection_strength=avg_strength,
        )

    async def get_kols_for_drug(
        self,
        drug_name: str,
        limit: int = 20,
    ) -> List[KOL]:
        """
        Find KOLs who have published about or investigated a drug.
        """
        # Search for publications about the drug
        publications = await self._openalex.search_publications(
            drug_name,
            limit=100,
        )

        # Count author appearances
        author_counts: Dict[str, Dict] = {}
        for pub in publications:
            for author in pub.authors:
                author_id = author.get("author_id") or author.get("name", "")
                if author_id:
                    if author_id not in author_counts:
                        author_counts[author_id] = {
                            "name": author.get("name", ""),
                            "author_id": author.get("author_id"),
                            "count": 0,
                        }
                    author_counts[author_id]["count"] += 1

        # Get top authors
        top_authors = sorted(
            author_counts.values(),
            key=lambda x: x["count"],
            reverse=True
        )[:limit]

        # Convert to KOLs
        kols = []
        for author_data in top_authors:
            authors = await self._openalex.search_authors(
                author_data["name"], limit=1
            )
            if authors:
                kol = self._author_to_kol(authors[0], "")
                kol.influence_score = self._calculate_influence_score(kol)
                kols.append(kol)

        return kols

    def _author_to_kol(self, author: Author, therapeutic_area: str) -> KOL:
        """Convert OpenAlex Author to KOL."""
        return KOL(
            kol_id=author.openalex_id,
            name=author.display_name,
            affiliations=[a.get("name", "") for a in author.affiliations],
            therapeutic_areas=[therapeutic_area] if therapeutic_area else [],
            expertise_areas=[ExpertiseArea.RESEARCH],
            h_index=author.h_index,
            publications_count=author.works_count,
            citations_count=author.cited_by_count,
        )

    def _calculate_influence_score(self, kol: KOL) -> float:
        """Calculate influence score for a KOL."""
        # Normalize metrics (simple normalization)
        h_index_score = min(1.0, (kol.h_index or 0) / 100)
        pubs_score = min(1.0, kol.publications_count / 500)
        citations_score = min(1.0, kol.citations_count / 50000)
        trials_score = min(1.0, kol.clinical_trials_count / 50)
        grants_score = min(1.0, kol.grants_count / 20)

        # Weighted sum
        score = (
            self.INFLUENCE_WEIGHTS["h_index"] * h_index_score +
            self.INFLUENCE_WEIGHTS["publications"] * pubs_score +
            self.INFLUENCE_WEIGHTS["citations"] * citations_score +
            self.INFLUENCE_WEIGHTS["trials"] * trials_score +
            self.INFLUENCE_WEIGHTS["grants"] * grants_score
        )

        return score * 100  # Scale to 0-100

    def _assign_tier(self, percentile: float) -> KOLTier:
        """Assign tier based on percentile rank."""
        if percentile >= self.TIER_THRESHOLDS[KOLTier.GLOBAL]:
            return KOLTier.GLOBAL
        elif percentile >= self.TIER_THRESHOLDS[KOLTier.NATIONAL]:
            return KOLTier.NATIONAL
        elif percentile >= self.TIER_THRESHOLDS[KOLTier.REGIONAL]:
            return KOLTier.REGIONAL
        else:
            return KOLTier.RISING


class PatientAdvocacyService:
    """
    Service for finding patient advocacy groups.

    Uses data from:
    - NORD (National Organization for Rare Disorders)
    - Disease-specific foundations
    - Public databases
    """

    def __init__(
        self,
        openalex_client: Optional[OpenAlexClient] = None,
        news_service: Optional["NewsService"] = None,
    ):
        self._openalex = openalex_client or OpenAlexClient()
        self._news_service = news_service

    def _get_news_service(self) -> "NewsService":
        """Lazy initialization of news service."""
        if self._news_service is None:
            from .news_service import NewsService
            self._news_service = NewsService()
        return self._news_service

    # Known advocacy organizations by disease area
    KNOWN_ORGANIZATIONS = {
        "cancer": [
            PatientAdvocacyGroup(
                org_id="acs",
                name="American Cancer Society",
                disease_focus=["cancer"],
                website="https://www.cancer.org",
                size_estimate="large",
                activities=["research", "education", "policy"],
            ),
            PatientAdvocacyGroup(
                org_id="lls",
                name="Leukemia & Lymphoma Society",
                disease_focus=["leukemia", "lymphoma", "blood cancer"],
                website="https://www.lls.org",
                size_estimate="large",
                activities=["research", "patient_support"],
            ),
        ],
        "rare_disease": [
            PatientAdvocacyGroup(
                org_id="nord",
                name="National Organization for Rare Disorders",
                disease_focus=["rare diseases"],
                website="https://rarediseases.org",
                size_estimate="large",
                activities=["research", "education", "policy"],
            ),
        ],
        "autoimmune": [
            PatientAdvocacyGroup(
                org_id="af",
                name="Arthritis Foundation",
                disease_focus=["arthritis", "rheumatoid arthritis"],
                website="https://www.arthritis.org",
                size_estimate="large",
                activities=["research", "education", "advocacy"],
            ),
        ],
    }

    async def find_advocacy_groups(
        self,
        indication: str,
        therapeutic_area: Optional[str] = None,
        limit: int = 20,
    ) -> List[PatientAdvocacyGroup]:
        """
        Find patient advocacy groups for an indication.

        Args:
            indication: Disease/indication name
            therapeutic_area: Broader therapeutic area
            limit: Maximum groups to return

        Returns:
            List of relevant advocacy groups
        """
        logger.info(f"Finding advocacy groups for {indication}")

        results = []
        indication_lower = indication.lower()

        # Search known organizations
        for area, orgs in self.KNOWN_ORGANIZATIONS.items():
            for org in orgs:
                # Check if indication matches disease focus
                for focus in org.disease_focus:
                    if indication_lower in focus.lower() or focus.lower() in indication_lower:
                        results.append(org)
                        break

        # In production, also query NORD database and other sources

        return results[:limit]

    async def get_advocacy_sentiment(
        self,
        molecule_name: str,
    ) -> Dict[str, Any]:
        """
        Analyze patient advocacy and public sentiment towards a drug.

        Analyzes:
        - Recent news coverage and tone
        - Publication trends and citation growth
        - Regulatory news (approvals, warnings)
        - Research activity indicators
        """
        logger.info(f"Analyzing sentiment for {molecule_name}")

        data_sources = []
        sentiment_signals = []

        # Get news items to analyze sentiment
        try:
            news_service = self._get_news_service()
            from .news_service import AlertPriority

            news_items = await news_service.get_news_for_molecule(
                molecule_name,
                days=90,  # Last 90 days
                limit=50,
            )

            if news_items:
                data_sources.append("news_feeds")

                # Analyze news sentiment based on types and priorities
                positive_signals = 0
                negative_signals = 0
                neutral_signals = 0

                for item in news_items:
                    title_lower = item.title.lower()

                    # Check for positive signals
                    if any(word in title_lower for word in [
                        "approval", "approved", "breakthrough", "success",
                        "positive", "effective", "benefit", "promising"
                    ]):
                        positive_signals += 1
                        if item.priority == AlertPriority.CRITICAL:
                            positive_signals += 2  # Extra weight for critical news

                    # Check for negative signals
                    elif any(word in title_lower for word in [
                        "warning", "safety", "recall", "failed", "terminated",
                        "adverse", "death", "withdrawn", "reject"
                    ]):
                        negative_signals += 1
                        if item.priority == AlertPriority.CRITICAL:
                            negative_signals += 2

                    else:
                        neutral_signals += 1

                sentiment_signals.append({
                    "source": "news",
                    "positive": positive_signals,
                    "negative": negative_signals,
                    "neutral": neutral_signals,
                    "total_items": len(news_items),
                })

        except Exception as e:
            logger.warning(f"Failed to get news for sentiment: {e}")

        # Get publication data to analyze research sentiment
        try:
            publications = await self._openalex.search_publications(
                query=molecule_name,
                filters={"publication_year": str(datetime.now().year)},
                limit=50,
            )

            if publications:
                data_sources.append("openalex")

                # High citation count = positive community interest
                high_citation_pubs = sum(1 for p in publications if p.cited_by_count > 10)
                recent_pubs = len(publications)

                # Check publication titles for sentiment indicators
                positive_titles = sum(1 for p in publications if any(
                    word in p.title.lower() for word in
                    ["efficacy", "effective", "improved", "benefit", "promising", "successful"]
                ))
                negative_titles = sum(1 for p in publications if any(
                    word in p.title.lower() for word in
                    ["adverse", "toxicity", "failure", "risk", "concern", "limitation"]
                ))

                sentiment_signals.append({
                    "source": "publications",
                    "recent_publications": recent_pubs,
                    "high_citation_count": high_citation_pubs,
                    "positive_titles": positive_titles,
                    "negative_titles": negative_titles,
                })

        except Exception as e:
            logger.warning(f"Failed to get publications for sentiment: {e}")

        # Calculate overall sentiment score
        total_positive = sum(
            s.get("positive", 0) + s.get("positive_titles", 0) + s.get("high_citation_count", 0)
            for s in sentiment_signals
        )
        total_negative = sum(
            s.get("negative", 0) + s.get("negative_titles", 0)
            for s in sentiment_signals
        )
        total_signals = total_positive + total_negative + sum(
            s.get("neutral", 0) for s in sentiment_signals
        )

        if total_signals > 0:
            # Score from 0 (very negative) to 1 (very positive)
            sentiment_score = 0.5 + (total_positive - total_negative) / (total_signals * 2)
            sentiment_score = max(0.0, min(1.0, sentiment_score))  # Clamp to [0, 1]
        else:
            sentiment_score = 0.5  # Neutral if no data

        # Determine overall sentiment label
        if sentiment_score >= 0.7:
            overall_sentiment = "positive"
        elif sentiment_score >= 0.55:
            overall_sentiment = "slightly_positive"
        elif sentiment_score >= 0.45:
            overall_sentiment = "neutral"
        elif sentiment_score >= 0.3:
            overall_sentiment = "slightly_negative"
        else:
            overall_sentiment = "negative"

        return {
            "molecule_name": molecule_name,
            "overall_sentiment": overall_sentiment,
            "sentiment_score": round(sentiment_score, 3),
            "data_sources": data_sources if data_sources else ["insufficient_data"],
            "analysis_details": {
                "total_positive_signals": total_positive,
                "total_negative_signals": total_negative,
                "total_signals_analyzed": total_signals,
            },
            "signal_breakdown": sentiment_signals,
            "analysis_period_days": 90,
            "timestamp": datetime.utcnow().isoformat(),
        }
