from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.user import User
from src.schemas.resource import TicketResourceIncrementRequest, TicketResourceIncrementResponse
from src.services import resource_service

router = APIRouter(prefix="/tickets", tags=["Resources"])


@router.post(
    "/{ticket_id}/resources", response_model=TicketResourceIncrementResponse, status_code=200
)
async def increment_ticket_resources(
    ticket_id: UUID,
    body: TicketResourceIncrementRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketResourceIncrementResponse:
    if body.time_spent_delta == 0 and body.tokens_consumed_delta == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of time_spent_delta or tokens_consumed_delta must be > 0",
        )
    return await resource_service.increment_resources(
        db, ticket_id, current_user, body.time_spent_delta, body.tokens_consumed_delta
    )
