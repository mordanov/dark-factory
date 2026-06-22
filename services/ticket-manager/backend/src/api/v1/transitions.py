from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.user import User
from src.schemas.ticket import TicketResponse
from src.schemas.transition import TransitionRequest
from src.services import transition_service

router = APIRouter(prefix="/tickets", tags=["Transitions"])


@router.post("/{ticket_id}/transitions", response_model=TicketResponse)
async def transition_ticket(
    ticket_id: UUID,
    body: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketResponse:
    return await transition_service.transition_ticket(db, ticket_id, body.to_status, current_user)
