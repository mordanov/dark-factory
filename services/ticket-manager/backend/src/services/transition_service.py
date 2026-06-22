from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.progress_update import ProgressUpdate
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_assignment import TicketAssignment
from src.models.user import User
from src.schemas.ticket import TicketResponse
from src.schemas.transition import MissingUpdate, TransitionBlockedError
from src.services.event_service import emit_event
from src.services.ticket_service import _load_ticket_response
from src.services.workflow_service import validate_transition


async def transition_ticket(
    session: AsyncSession,
    ticket_id: UUID,
    to_status: TicketStatus,
    actor: User,
) -> TicketResponse:
    # Acquire row lock on ticket first to prevent concurrent transitions racing
    # past the progress gate (security requirement F-TR-04).
    ticket_result = await session.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.deleted_at.is_(None)).with_for_update()
    )
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    # Acquire row locks on all current assignments so the RBAC check and progress
    # gate operate on a consistent snapshot — prevents concurrent unassign+transition
    # from bypassing the gate (F-TR-04).
    all_assignments_result = await session.execute(
        select(TicketAssignment).where(TicketAssignment.ticket_id == ticket_id).with_for_update()
    )
    all_assignments = all_assignments_result.scalars().all()

    assignee_ids = {a.user_id for a in all_assignments}
    if actor.id not in assignee_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only assignees may transition this ticket",
        )

    validate_transition(ticket.status, to_status)

    # Progress gate: uses locked current assignees (Option B per architecture ruling —
    # spec FR-008a says "currently assigned users"; bypass via removal is a documented
    # residual risk mitigated by the immutable audit trail).
    progress_result = await session.execute(
        select(ProgressUpdate).where(ProgressUpdate.ticket_id == ticket_id)
    )
    progress_user_ids = {pu.user_id for pu in progress_result.scalars().all()}

    missing: list[MissingUpdate] = []
    for assignment in all_assignments:
        if assignment.user_id not in progress_user_ids:
            user = await session.get(User, assignment.user_id)
            if user:
                missing.append(MissingUpdate(user_id=assignment.user_id, email=user.email))

    if missing:
        await emit_event(
            session,
            ticket_id,
            "ticket.transition_blocked",
            actor,
            prev_state={"status": ticket.status.value},
            new_state={
                "pending_status": to_status.value,
                "missing_users": [str(m.user_id) for m in missing],
            },
        )
        await session.commit()

        error = TransitionBlockedError(
            detail="Transition blocked: not all assignees have submitted progress updates",
            missing_updates=missing,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=error.model_dump(mode="json"),
        )

    prev_status = ticket.status
    ticket.status = to_status

    await emit_event(
        session,
        ticket_id,
        "ticket.status_changed",
        actor,
        prev_state={"status": prev_status.value},
        new_state={"status": to_status.value},
    )
    await session.commit()
    return await _load_ticket_response(session, ticket)
