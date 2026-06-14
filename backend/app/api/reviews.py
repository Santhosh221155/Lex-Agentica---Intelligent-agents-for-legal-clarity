from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.services.review_store import list_pending_reviews, decide_review, get_review_request

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


class ReviewDecision(BaseModel):
    reviewer_notes: Optional[str] = Field(default=None, max_length=4000)


@router.get("")
async def pending_reviews(limit: int = Query(50, ge=1, le=200), user: dict = Depends(get_current_user)):
    return await list_pending_reviews(limit=limit)


@router.get("/{review_id}")
async def review_detail(review_id: int, user: dict = Depends(get_current_user)):
    review = await get_review_request(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="not_found")
    return review


@router.post("/{review_id}/approve")
async def approve_review(review_id: int, payload: ReviewDecision, user: dict = Depends(get_current_user)):
    review = await decide_review(review_id, user.get("id"), "approved", payload.reviewer_notes)
    if not review:
        raise HTTPException(status_code=404, detail="not_found")
    return review


@router.post("/{review_id}/reject")
async def reject_review(review_id: int, payload: ReviewDecision, user: dict = Depends(get_current_user)):
    review = await decide_review(review_id, user.get("id"), "rejected", payload.reviewer_notes)
    if not review:
        raise HTTPException(status_code=404, detail="not_found")
    return review
