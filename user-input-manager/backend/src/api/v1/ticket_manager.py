"""Proxy endpoints for Ticket Manager data the UI needs.

The frontend never calls Ticket Manager directly — it goes through our backend
which owns the service credentials.
"""
from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user
from src.models.models import User
from src.services.ticket_manager.client import TicketManagerClient, get_ticket_manager_client

router = APIRouter(prefix="/ticket-manager", tags=["ticket-manager"])


@router.get("/projects")
async def list_projects(
    _: User = Depends(get_current_user),
    tm: TicketManagerClient = Depends(get_ticket_manager_client),
):
    return await tm.list_projects()


@router.get("/projects/{project_id}/tickets")
async def list_tickets(
    project_id: str,
    _: User = Depends(get_current_user),
    tm: TicketManagerClient = Depends(get_ticket_manager_client),
):
    return await tm.list_tickets(project_id)
