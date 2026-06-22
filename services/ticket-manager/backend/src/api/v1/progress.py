from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.user import User
from src.schemas.progress import ProgressListResponse, ProgressUpdateRequest, ProgressUpdateResponse
from src.services import progress_service

router = APIRouter(prefix="/tickets", tags=["Progress"])


@router.get("/{ticket_id}/progress", response_model=ProgressListResponse)
async def list_progress(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProgressListResponse:
    return await progress_service.list_updates(db, ticket_id, current_user)


@router.put("/{ticket_id}/progress", response_model=ProgressUpdateResponse)
async def submit_progress(
    ticket_id: UUID,
    body: ProgressUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProgressUpdateResponse:
    return await progress_service.submit_update(db, ticket_id, current_user, body.content)
