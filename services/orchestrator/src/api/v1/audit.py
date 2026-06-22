from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.db.postgres import get_db
from src.repositories.audit_repo import AuditRepository
from src.schemas.schemas import AuditListResponse, AuditLogResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/{ticket_id}", response_model=AuditListResponse)
async def get_audit_for_ticket(
    ticket_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = AuditRepository(db)
    entries, total = await repo.list_for_ticket(ticket_id, offset=offset, limit=limit)
    return AuditListResponse(
        items=[AuditLogResponse.model_validate(e) for e in entries],
        total=total,
    )
