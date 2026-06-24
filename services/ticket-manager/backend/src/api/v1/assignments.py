from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import UserClaims
from src.core.database import get_db
from src.core.security import get_current_user
from src.schemas.assignment import AssignmentResponse, AssignRequest
from src.services import assignment_service

router = APIRouter(prefix="/tickets", tags=["Assignments"])


@router.post("/{ticket_id}/assignments", response_model=AssignmentResponse, status_code=201)
async def assign_user(
    ticket_id: UUID,
    body: AssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserClaims = Depends(get_current_user),
) -> AssignmentResponse:
    return await assignment_service.assign_user(db, ticket_id, body.user_id, current_user)


@router.delete("/{ticket_id}/assignments/{user_id}", status_code=204)
async def unassign_user(
    ticket_id: UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserClaims = Depends(get_current_user),
) -> None:
    await assignment_service.unassign_user(db, ticket_id, user_id, current_user)
