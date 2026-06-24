from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.user import User
from src.schemas.ticket import TokensSpentIncrementRequest, TokensSpentIncrementResponse
from src.services import tokens_spent_service

router = APIRouter(prefix="/tickets", tags=["Tokens Spent"])


@router.post(
    "/{ticket_id}/tokens-spent",
    response_model=TokensSpentIncrementResponse,
    status_code=status.HTTP_200_OK,
)
async def increment_tokens_spent(
    ticket_id: UUID,
    body: TokensSpentIncrementRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TokensSpentIncrementResponse:
    return await tokens_spent_service.increment_tokens_spent(db, ticket_id, body.amount, current_user)
