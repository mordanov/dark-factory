from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import UserClaims
from src.core.database import get_db
from src.core.security import get_current_user, require_role, require_service_account_or_admin
from src.schemas.orchestrator import (
    AuditEventCreate,
    AuditEventResponse,
    AuditLogResponse,
    PendingTicketsResponse,
)
from src.schemas.ticket import (
    BatchFsmStatusRequest,
    BatchFsmStatusResponse,
    FsmPatchRequest,
    OverrideRequest,
    TagDeltaRequest,
    TagDeltaResponse,
    TicketFsmResponse,
)
from src.services import audit_service, fsm_service, ticket_service

router = APIRouter(prefix="", tags=["Orchestrator"])


@router.get("/orchestrator/pending", response_model=PendingTicketsResponse)
async def get_pending_tickets(
    project_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    after_cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: UserClaims = require_service_account_or_admin,
) -> PendingTicketsResponse:
    return await fsm_service.get_pending_tickets(db, project_id, limit, after_cursor)


@router.patch(
    "/projects/{project_id}/tickets/{ticket_id}/fsm",
    response_model=TicketFsmResponse,
)
async def patch_fsm_fields(
    project_id: UUID,
    ticket_id: UUID,
    body: FsmPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserClaims = require_service_account_or_admin,
) -> TicketFsmResponse:
    return await fsm_service.patch_fsm_fields(db, project_id, ticket_id, body, current_user)


@router.post(
    "/tickets/{ticket_id}/audit",
    response_model=AuditEventResponse,
    status_code=201,
)
async def create_audit_event(
    ticket_id: UUID,
    body: AuditEventCreate,
    db: AsyncSession = Depends(get_db),
    _: UserClaims = require_service_account_or_admin,
) -> AuditEventResponse:
    return await audit_service.create_audit_event(db, ticket_id, body)


@router.get("/tickets/{ticket_id}/audit", response_model=AuditLogResponse)
async def get_audit_log(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(get_current_user),
) -> AuditLogResponse:
    return await audit_service.get_audit_log(db, ticket_id)


@router.post(
    "/projects/{project_id}/tickets/{ticket_id}/override",
    response_model=TicketFsmResponse,
)
async def set_override(
    project_id: UUID,
    ticket_id: UUID,
    body: OverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserClaims = require_role("administrator"),
) -> TicketFsmResponse:
    return await fsm_service.set_override(db, project_id, ticket_id, body, current_user)


@router.post("/tickets/batch-fsm-status", response_model=BatchFsmStatusResponse)
async def batch_fsm_status(
    body: BatchFsmStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserClaims = Depends(get_current_user),
) -> BatchFsmStatusResponse:
    return await ticket_service.batch_fsm_status(db, body.ticket_ids, current_user)


@router.get(
    "/projects/{project_id}/tickets/{ticket_id}/full",
    response_model=TicketFsmResponse,
)
async def get_ticket_full(
    project_id: UUID,
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(get_current_user),
) -> TicketFsmResponse:
    return await fsm_service.get_ticket_full(db, project_id, ticket_id)


@router.post(
    "/projects/{project_id}/tickets/{ticket_id}/tags/delta",
    response_model=TagDeltaResponse,
)
async def apply_tag_delta(
    project_id: UUID,
    ticket_id: UUID,
    body: TagDeltaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserClaims = Depends(get_current_user),
) -> TagDeltaResponse:
    return await ticket_service.apply_tag_delta(db, project_id, ticket_id, body, current_user)
