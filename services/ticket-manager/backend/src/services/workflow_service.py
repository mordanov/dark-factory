from fastapi import HTTPException, status

from src.models.ticket import TicketStatus

WORKFLOW_TRANSITIONS: dict[TicketStatus, list[TicketStatus]] = {
    TicketStatus.OPEN: [TicketStatus.IN_PROGRESS],
    TicketStatus.IN_PROGRESS: [TicketStatus.IN_REVIEW],
    TicketStatus.IN_REVIEW: [TicketStatus.DONE, TicketStatus.IN_PROGRESS],
    TicketStatus.DONE: [TicketStatus.CLOSED, TicketStatus.IN_PROGRESS],
    TicketStatus.CLOSED: [],
}


def validate_transition(from_status: TicketStatus, to_status: TicketStatus) -> None:
    allowed = WORKFLOW_TRANSITIONS.get(from_status, [])
    if to_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transition from {from_status.value} to {to_status.value} is not allowed",
        )
