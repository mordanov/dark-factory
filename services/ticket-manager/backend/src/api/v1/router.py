from fastapi import APIRouter

from src.api.v1 import (
    admin,
    assignments,
    events,
    groups,
    orchestrator,
    progress,
    projects,
    resources,
    tags,
    tickets,
    tokens_spent,
    transitions,
    users,
)

router = APIRouter(prefix="/api/v1")

router.include_router(admin.router)
router.include_router(users.router)
router.include_router(groups.router)
router.include_router(projects.router)
router.include_router(tickets.router)
router.include_router(assignments.router)
router.include_router(progress.router)
router.include_router(transitions.router)
router.include_router(events.router)
router.include_router(tags.router)
router.include_router(resources.router)
router.include_router(tokens_spent.router)
router.include_router(orchestrator.router)
