from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.user import User
from src.schemas.ticket import (
    FollowUpTicketCreate,
    TagAddRequest,
    TicketResponse,
    TicketUpdate,
)
from src.services import ticket_service

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TicketResponse:
    return await ticket_service.get_ticket(db, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: UUID,
    body: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketResponse:
    return await ticket_service.update_ticket(db, ticket_id, body, current_user)


@router.delete("/{ticket_id}", status_code=204)
async def delete_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await ticket_service.delete_ticket(db, ticket_id, current_user)


@router.post("/{ticket_id}/follow-ups", response_model=TicketResponse, status_code=201)
async def create_follow_up(
    ticket_id: UUID,
    body: FollowUpTicketCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketResponse:
    return await ticket_service.create_follow_up(db, ticket_id, body, current_user)


@router.post("/{ticket_id}/tags", response_model=TicketResponse)
async def add_tag(
    ticket_id: UUID,
    body: TagAddRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketResponse:
    return await ticket_service.add_tag(db, ticket_id, body.name, current_user)


@router.delete("/{ticket_id}/tags/{tag_name}", response_model=TicketResponse)
async def remove_tag(
    ticket_id: UUID,
    tag_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketResponse:
    return await ticket_service.remove_tag(db, ticket_id, tag_name, current_user)
