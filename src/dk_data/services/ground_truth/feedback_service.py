"""
User Feedback & Data Quality Monitoring Services.

Implements:
- T183: UserFeedbackService class
- T184: submit_feedback() with auto-triage
- T185: rate_data_quality() for category ratings
- T186: DataQualityMonitoringService class
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from loguru import logger


class FeedbackType(str, Enum):
    """Types of feedback."""
    DATA_ERROR = "data_error"
    MISSING_DATA = "missing_data"
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    GENERAL = "general"
    DATA_QUALITY = "data_quality"


class FeedbackPriority(str, Enum):
    """Feedback priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FeedbackStatus(str, Enum):
    """Feedback status."""
    NEW = "new"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"


class DataCategory(str, Enum):
    """Categories for data quality rating."""
    CLINICAL_TRIALS = "clinical_trials"
    REGULATORY = "regulatory"
    SAFETY = "safety"
    PUBLICATIONS = "publications"
    PRICING = "pricing"
    PATENTS = "patents"
    COMPETITORS = "competitors"
    LIFECYCLE = "lifecycle"


@dataclass
class FeedbackTicket:
    """User feedback ticket."""
    ticket_id: str
    user_id: str
    feedback_type: FeedbackType
    title: str
    description: str
    priority: FeedbackPriority = FeedbackPriority.MEDIUM
    status: FeedbackStatus = FeedbackStatus.NEW
    molecule_id: Optional[str] = None
    data_source: Optional[str] = None
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    screenshot_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ticket_id": self.ticket_id,
            "user_id": self.user_id,
            "feedback_type": self.feedback_type.value,
            "title": self.title,
            "description": self.description[:500] if self.description else None,
            "priority": self.priority.value,
            "status": self.status.value,
            "molecule_id": self.molecule_id,
            "data_source": self.data_source,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class DataQualityRating:
    """User rating of data quality."""
    rating_id: str
    user_id: str
    molecule_id: str
    category: DataCategory
    rating: int  # 1-5
    comment: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rating_id": self.rating_id,
            "user_id": self.user_id,
            "molecule_id": self.molecule_id,
            "category": self.category.value,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class FeedbackAnalytics:
    """Analytics summary for feedback."""
    total_tickets: int
    tickets_by_type: Dict[str, int]
    tickets_by_priority: Dict[str, int]
    tickets_by_status: Dict[str, int]
    avg_resolution_time_hours: Optional[float]
    top_affected_molecules: List[Dict[str, Any]]
    top_data_sources: List[Dict[str, Any]]
    trend_7d: int  # Change from previous 7 days
    avg_quality_rating: Dict[str, float]  # By category


class UserFeedbackService:
    """
    Service for handling user feedback.

    Provides feedback submission, auto-triage, and quality ratings.
    """

    # Auto-triage rules based on keywords
    TRIAGE_RULES = {
        FeedbackPriority.CRITICAL: ["incorrect approval", "wrong indication", "safety error", "death", "fatal"],
        FeedbackPriority.HIGH: ["missing data", "outdated", "wrong company", "incorrect phase"],
        FeedbackPriority.MEDIUM: ["incomplete", "typo", "formatting", "ui bug"],
        FeedbackPriority.LOW: ["suggestion", "improvement", "nice to have", "feature request"],
    }

    # In-memory storage
    _tickets: Dict[str, FeedbackTicket] = {}
    _ratings: Dict[str, List[DataQualityRating]] = {}

    async def submit_feedback(
        self,
        user_id: str,
        feedback_type: str,
        title: str,
        description: str,
        molecule_id: Optional[str] = None,
        data_source: Optional[str] = None,
        expected_value: Optional[str] = None,
        actual_value: Optional[str] = None,
    ) -> FeedbackTicket:
        """
        Submit user feedback with auto-triage.

        Args:
            user_id: User ID
            feedback_type: Type of feedback
            title: Feedback title
            description: Detailed description
            molecule_id: Affected molecule (if applicable)
            data_source: Affected data source (if applicable)
            expected_value: What user expected
            actual_value: What was shown

        Returns:
            FeedbackTicket with assigned priority
        """
        import uuid

        logger.info(f"Submitting feedback: {title}")

        # Parse feedback type
        try:
            fb_type = FeedbackType(feedback_type.lower())
        except ValueError:
            fb_type = FeedbackType.GENERAL

        # Generate ticket ID
        ticket_id = f"FB-{str(uuid.uuid4())[:8].upper()}"

        # Auto-triage priority
        priority = self._auto_triage(title, description)

        # Create ticket
        ticket = FeedbackTicket(
            ticket_id=ticket_id,
            user_id=user_id,
            feedback_type=fb_type,
            title=title,
            description=description,
            priority=priority,
            status=FeedbackStatus.TRIAGED,  # Auto-triaged
            molecule_id=molecule_id,
            data_source=data_source,
            expected_value=expected_value,
            actual_value=actual_value,
            tags=self._extract_tags(title, description),
        )

        # Store ticket
        self._tickets[ticket_id] = ticket

        logger.info(f"Ticket {ticket_id} created with priority {priority.value}")
        return ticket

    def _auto_triage(self, title: str, description: str) -> FeedbackPriority:
        """Auto-assign priority based on content."""
        text = f"{title} {description}".lower()

        for priority, keywords in self.TRIAGE_RULES.items():
            for keyword in keywords:
                if keyword in text:
                    return priority

        return FeedbackPriority.MEDIUM

    def _extract_tags(self, title: str, description: str) -> List[str]:
        """Extract tags from content."""
        tags = []
        text = f"{title} {description}".lower()

        # Data source tags
        sources = ["fda", "ema", "clinicaltrials", "pubmed", "drugbank", "faers"]
        for source in sources:
            if source in text:
                tags.append(source)

        # Category tags
        categories = ["safety", "regulatory", "trial", "pricing", "patent"]
        for cat in categories:
            if cat in text:
                tags.append(cat)

        return tags

    async def rate_data_quality(
        self,
        user_id: str,
        molecule_id: str,
        ratings: Dict[str, int],
        comments: Optional[Dict[str, str]] = None,
    ) -> List[DataQualityRating]:
        """
        Submit data quality ratings for a molecule.

        Args:
            user_id: User ID
            molecule_id: Molecule ID
            ratings: Dict of category -> rating (1-5)
            comments: Optional comments by category

        Returns:
            List of created ratings
        """
        import uuid

        logger.info(f"Rating data quality for {molecule_id}")

        comments = comments or {}
        created_ratings = []

        for category_str, rating_value in ratings.items():
            try:
                category = DataCategory(category_str.lower())
            except ValueError:
                continue

            # Validate rating
            rating_value = max(1, min(5, rating_value))

            rating = DataQualityRating(
                rating_id=str(uuid.uuid4())[:8],
                user_id=user_id,
                molecule_id=molecule_id,
                category=category,
                rating=rating_value,
                comment=comments.get(category_str),
            )

            created_ratings.append(rating)

        # Store ratings
        if molecule_id not in self._ratings:
            self._ratings[molecule_id] = []
        self._ratings[molecule_id].extend(created_ratings)

        return created_ratings

    async def get_ticket(self, ticket_id: str) -> Optional[FeedbackTicket]:
        """Get a feedback ticket by ID."""
        return self._tickets.get(ticket_id)

    async def list_tickets(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        molecule_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[FeedbackTicket]:
        """List feedback tickets with filters."""
        tickets = list(self._tickets.values())

        if user_id:
            tickets = [t for t in tickets if t.user_id == user_id]
        if status:
            tickets = [t for t in tickets if t.status.value == status]
        if molecule_id:
            tickets = [t for t in tickets if t.molecule_id == molecule_id]

        # Sort by priority and created_at
        priority_order = {
            FeedbackPriority.CRITICAL: 0,
            FeedbackPriority.HIGH: 1,
            FeedbackPriority.MEDIUM: 2,
            FeedbackPriority.LOW: 3,
        }
        tickets.sort(key=lambda t: (priority_order[t.priority], t.created_at), reverse=True)

        return tickets[:limit]

    async def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        resolution: Optional[str] = None,
    ) -> Optional[FeedbackTicket]:
        """Update ticket status."""
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None

        try:
            ticket.status = FeedbackStatus(status.lower())
        except ValueError:
            return None

        ticket.updated_at = datetime.utcnow()

        if status in ("resolved", "wont_fix"):
            ticket.resolved_at = datetime.utcnow()
            ticket.resolution = resolution

        return ticket


class DataQualityMonitoringService:
    """
    Service for monitoring data quality.

    Aggregates feedback, ratings, and computes analytics.
    """

    def __init__(
        self,
        feedback_service: Optional[UserFeedbackService] = None,
    ):
        self._feedback = feedback_service or UserFeedbackService()

    async def get_analytics(
        self,
        days: int = 30,
    ) -> FeedbackAnalytics:
        """
        Get feedback analytics summary.

        Args:
            days: Number of days to analyze

        Returns:
            FeedbackAnalytics with aggregated data
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        tickets = await self._feedback.list_tickets(limit=1000)
        recent_tickets = [t for t in tickets if t.created_at >= cutoff]

        # Count by type
        by_type: Dict[str, int] = {}
        for t in recent_tickets:
            by_type[t.feedback_type.value] = by_type.get(t.feedback_type.value, 0) + 1

        # Count by priority
        by_priority: Dict[str, int] = {}
        for t in recent_tickets:
            by_priority[t.priority.value] = by_priority.get(t.priority.value, 0) + 1

        # Count by status
        by_status: Dict[str, int] = {}
        for t in recent_tickets:
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1

        # Average resolution time
        resolved = [t for t in recent_tickets if t.resolved_at]
        avg_resolution = None
        if resolved:
            total_hours = sum(
                (t.resolved_at - t.created_at).total_seconds() / 3600
                for t in resolved
            )
            avg_resolution = total_hours / len(resolved)

        # Top affected molecules
        molecule_counts: Dict[str, int] = {}
        for t in recent_tickets:
            if t.molecule_id:
                molecule_counts[t.molecule_id] = molecule_counts.get(t.molecule_id, 0) + 1
        top_molecules = [
            {"molecule_id": m, "count": c}
            for m, c in sorted(molecule_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        # Top data sources
        source_counts: Dict[str, int] = {}
        for t in recent_tickets:
            if t.data_source:
                source_counts[t.data_source] = source_counts.get(t.data_source, 0) + 1
        top_sources = [
            {"source": s, "count": c}
            for s, c in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        # 7-day trend
        week_ago = datetime.utcnow() - timedelta(days=7)
        two_weeks_ago = datetime.utcnow() - timedelta(days=14)
        last_week = len([t for t in tickets if t.created_at >= week_ago])
        prev_week = len([t for t in tickets if two_weeks_ago <= t.created_at < week_ago])
        trend = last_week - prev_week

        # Average quality ratings by category
        avg_ratings = await self._compute_avg_ratings()

        return FeedbackAnalytics(
            total_tickets=len(recent_tickets),
            tickets_by_type=by_type,
            tickets_by_priority=by_priority,
            tickets_by_status=by_status,
            avg_resolution_time_hours=avg_resolution,
            top_affected_molecules=top_molecules,
            top_data_sources=top_sources,
            trend_7d=trend,
            avg_quality_rating=avg_ratings,
        )

    async def _compute_avg_ratings(self) -> Dict[str, float]:
        """Compute average ratings by category."""
        all_ratings: Dict[str, List[int]] = {}

        for ratings_list in self._feedback._ratings.values():
            for rating in ratings_list:
                cat = rating.category.value
                if cat not in all_ratings:
                    all_ratings[cat] = []
                all_ratings[cat].append(rating.rating)

        return {
            cat: sum(vals) / len(vals) if vals else 0.0
            for cat, vals in all_ratings.items()
        }

    async def get_molecule_quality_score(
        self,
        molecule_id: str,
    ) -> Dict[str, Any]:
        """
        Get quality score for a specific molecule.

        Returns:
            Quality metrics for the molecule
        """
        # Get feedback tickets
        tickets = await self._feedback.list_tickets(molecule_id=molecule_id, limit=100)

        # Get ratings
        ratings = self._feedback._ratings.get(molecule_id, [])

        # Calculate scores
        open_issues = len([t for t in tickets if t.status in (FeedbackStatus.NEW, FeedbackStatus.TRIAGED, FeedbackStatus.IN_PROGRESS)])
        critical_issues = len([t for t in tickets if t.priority == FeedbackPriority.CRITICAL])

        # Compute per-category ratings
        category_ratings: Dict[str, List[int]] = {}
        for r in ratings:
            cat = r.category.value
            if cat not in category_ratings:
                category_ratings[cat] = []
            category_ratings[cat].append(r.rating)

        avg_category_ratings = {
            cat: sum(vals) / len(vals) if vals else None
            for cat, vals in category_ratings.items()
        }

        # Overall quality score (0-100)
        overall_score = 80  # Base score
        overall_score -= open_issues * 2  # Deduct for open issues
        overall_score -= critical_issues * 10  # Deduct more for critical

        # Boost based on ratings
        if ratings:
            avg_rating = sum(r.rating for r in ratings) / len(ratings)
            overall_score += (avg_rating - 3) * 5  # Adjust based on rating (3 is neutral)

        overall_score = max(0, min(100, overall_score))

        return {
            "molecule_id": molecule_id,
            "overall_score": round(overall_score, 1),
            "open_issues": open_issues,
            "critical_issues": critical_issues,
            "total_feedback": len(tickets),
            "category_ratings": avg_category_ratings,
            "rating_count": len(ratings),
        }
