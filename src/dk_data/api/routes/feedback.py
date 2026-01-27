"""
User Feedback API routes.

Implements:
- T189: POST /api/v1/feedback
- T190: POST /api/v1/feedback/rate/{molecule_id}
- T191: GET /api/v1/feedback/analytics
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

from ...services.ground_truth.feedback_service import (
    UserFeedbackService,
    DataQualityMonitoringService,
)


router = APIRouter(prefix="/feedback", tags=["feedback"])


# Request Models
class FeedbackSubmitRequest(BaseModel):
    """Request to submit feedback."""
    user_id: str
    feedback_type: str = Field(
        ...,
        description="Type: data_error, missing_data, feature_request, bug_report, general"
    )
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    molecule_id: Optional[str] = None
    data_source: Optional[str] = None
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None


class DataQualityRatingRequest(BaseModel):
    """Request to rate data quality."""
    user_id: str
    ratings: Dict[str, int] = Field(
        ...,
        description="Category -> rating (1-5). Categories: clinical_trials, regulatory, safety, publications, pricing, patents, competitors, lifecycle"
    )
    comments: Optional[Dict[str, str]] = None


class TicketUpdateRequest(BaseModel):
    """Request to update ticket status."""
    status: str = Field(
        ...,
        description="Status: new, triaged, in_progress, resolved, wont_fix"
    )
    resolution: Optional[str] = None


# Response Models
class FeedbackResponse(BaseModel):
    """Response for feedback submission."""
    success: bool
    ticket_id: str
    title: str
    priority: str
    status: str
    message: str
    timestamp: str


class RatingResponse(BaseModel):
    """Response for data quality rating."""
    success: bool
    molecule_id: str
    ratings_submitted: int
    categories_rated: List[str]
    timestamp: str


class AnalyticsResponse(BaseModel):
    """Response for feedback analytics."""
    success: bool
    total_tickets: int
    tickets_by_type: Dict[str, int]
    tickets_by_priority: Dict[str, int]
    tickets_by_status: Dict[str, int]
    avg_resolution_time_hours: Optional[float]
    top_affected_molecules: List[Dict[str, Any]]
    top_data_sources: List[Dict[str, Any]]
    trend_7d: int
    avg_quality_rating: Dict[str, float]
    timestamp: str


# Service instances
_feedback_service: Optional[UserFeedbackService] = None
_quality_service: Optional[DataQualityMonitoringService] = None


def get_feedback_service() -> UserFeedbackService:
    global _feedback_service
    if _feedback_service is None:
        _feedback_service = UserFeedbackService()
    return _feedback_service


def get_quality_service() -> DataQualityMonitoringService:
    global _quality_service, _feedback_service
    if _quality_service is None:
        _quality_service = DataQualityMonitoringService(
            feedback_service=get_feedback_service()
        )
    return _quality_service


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackSubmitRequest):
    """
    Submit user feedback with auto-triage.

    Automatically assigns priority based on content analysis.
    """
    try:
        service = get_feedback_service()

        ticket = await service.submit_feedback(
            user_id=request.user_id,
            feedback_type=request.feedback_type,
            title=request.title,
            description=request.description,
            molecule_id=request.molecule_id,
            data_source=request.data_source,
            expected_value=request.expected_value,
            actual_value=request.actual_value,
        )

        return FeedbackResponse(
            success=True,
            ticket_id=ticket.ticket_id,
            title=ticket.title,
            priority=ticket.priority.value,
            status=ticket.status.value,
            message=f"Feedback submitted successfully. Assigned priority: {ticket.priority.value}",
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rate/{molecule_id}", response_model=RatingResponse)
async def rate_data_quality(
    molecule_id: str,
    request: DataQualityRatingRequest,
):
    """
    Submit data quality ratings for a molecule.

    Rate different categories (1-5) to help improve data quality.
    """
    try:
        service = get_feedback_service()

        ratings = await service.rate_data_quality(
            user_id=request.user_id,
            molecule_id=molecule_id,
            ratings=request.ratings,
            comments=request.comments,
        )

        return RatingResponse(
            success=True,
            molecule_id=molecule_id,
            ratings_submitted=len(ratings),
            categories_rated=[r.category.value for r in ratings],
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error rating data quality: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_feedback_analytics(
    days: int = Query(30, ge=1, le=365, description="Days to analyze"),
):
    """
    Get feedback analytics summary.

    Returns aggregated statistics about feedback and data quality.
    """
    try:
        service = get_quality_service()

        analytics = await service.get_analytics(days=days)

        return AnalyticsResponse(
            success=True,
            total_tickets=analytics.total_tickets,
            tickets_by_type=analytics.tickets_by_type,
            tickets_by_priority=analytics.tickets_by_priority,
            tickets_by_status=analytics.tickets_by_status,
            avg_resolution_time_hours=analytics.avg_resolution_time_hours,
            top_affected_molecules=analytics.top_affected_molecules,
            top_data_sources=analytics.top_data_sources,
            trend_7d=analytics.trend_7d,
            avg_quality_rating=analytics.avg_quality_rating,
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_feedback_tickets(
    user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    molecule_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List feedback tickets with filters.
    """
    try:
        service = get_feedback_service()

        tickets = await service.list_tickets(
            user_id=user_id,
            status=status,
            molecule_id=molecule_id,
            limit=limit,
        )

        return {
            "success": True,
            "tickets_count": len(tickets),
            "tickets": [t.to_dict() for t in tickets],
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error listing tickets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticket_id}")
async def get_feedback_ticket(ticket_id: str):
    """
    Get a specific feedback ticket.
    """
    try:
        service = get_feedback_service()

        ticket = await service.get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

        return {
            "success": True,
            "ticket": ticket.to_dict(),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ticket: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{ticket_id}")
async def update_feedback_ticket(
    ticket_id: str,
    request: TicketUpdateRequest,
):
    """
    Update feedback ticket status.
    """
    try:
        service = get_feedback_service()

        ticket = await service.update_ticket_status(
            ticket_id=ticket_id,
            status=request.status,
            resolution=request.resolution,
        )

        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

        return {
            "success": True,
            "ticket": ticket.to_dict(),
            "message": f"Ticket status updated to {ticket.status.value}",
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating ticket: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/{molecule_id}")
async def get_molecule_quality_score(molecule_id: str):
    """
    Get data quality score for a specific molecule.

    Returns quality metrics and issue summary.
    """
    try:
        service = get_quality_service()

        score = await service.get_molecule_quality_score(molecule_id)

        return {
            "success": True,
            **score,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting quality score: {e}")
        raise HTTPException(status_code=500, detail=str(e))
