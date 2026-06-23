"""PlanningService — orchestrates plan generation, editing, confirmation, and ticket creation."""

from __future__ import annotations

import asyncio
import structlog
import uuid

import httpx
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UpstreamError
from src.repositories.plan_repo import PlanRepository
from src.repositories.session_repo import SessionRepository
from src.schemas.schemas import (
    AgentConfig,
    PlanConfirmResponse,
    PlanContent,
    PlanGenerateResponse,
    PlanResponse,
    PlanStatusResponse,
)
from src.services.llm.planning_llm import generate_agent_config, generate_plan
from src.services.planning.validator import validate_plan
from src.services.ticket_manager.plan_client import TMPlanClient

logger = structlog.get_logger(__name__)


class PlanningService:
    def __init__(self, db: AsyncSession, tm_client: TMPlanClient) -> None:
        self._plan_repo = PlanRepository(db)
        self._session_repo = SessionRepository(db)
        self._tm = tm_client

    async def _get_session_for_user(self, session_id: uuid.UUID, user_id: uuid.UUID):
        session = await self._session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session not found")
        if session.user_id != user_id:
            raise ForbiddenError()
        return session

    async def generate(self, session_id: uuid.UUID, user_id: uuid.UUID) -> PlanGenerateResponse:
        session = await self._get_session_for_user(session_id, user_id)
        if session.status != "approved":
            raise ConflictError(
                f"Session must be in 'approved' state to generate plan, currently: {session.status}"
            )

        await self._plan_repo.delete_by_session_id(session_id)
        await self._session_repo.update(session, status="planning")
        logger.info("plan.generation_triggered session_id=%s user_id=%s", session_id, user_id)

        plan = await self._plan_repo.create(session_id=session_id)

        try:
            iterations = await self._get_latest_refined_prompt(session_id)
            plan_content = await generate_plan(iterations)

            project_id = session.tm_project_id or str(session_id)
            agent_config = await generate_agent_config(iterations, plan_content, project_id)

            plan_dict = plan_content.model_dump()
            agent_config_dict = agent_config.model_dump() if agent_config else None

            plan = await self._plan_repo.update_status(
                plan,
                "ready",
                plan_content=plan_dict,
                agent_config=agent_config_dict,
            )
            await self._session_repo.update(session, status="plan_ready")
            logger.info(
                "plan.generated session_id=%s plan_id=%s user_id=%s",
                session_id, plan.id, user_id,
            )

        except Exception as exc:
            logger.error("Plan generation failed for session %s: %s", session_id, exc)
            await self._session_repo.update(session, status="approved")
            try:
                await self._plan_repo.delete_by_session_id(session_id)
            except Exception:
                pass
            raise

        return PlanGenerateResponse(
            session_id=session_id,
            plan_id=plan.id,
            status="planning",
        )

    async def _get_latest_refined_prompt(self, session_id: uuid.UUID) -> str:
        from src.repositories.session_repo import IterationRepository

        iter_repo = IterationRepository(self._plan_repo._db)
        iterations = await iter_repo.list_for_session(session_id)
        for it in reversed(iterations):
            if it.role == "assistant":
                return it.prompt_text
        return ""

    async def get_plan(self, session_id: uuid.UUID, user_id: uuid.UUID) -> PlanResponse:
        await self._get_session_for_user(session_id, user_id)
        plan = await self._plan_repo.get_by_session_id(session_id)
        if not plan:
            raise NotFoundError("No plan found for this session")
        return PlanResponse.model_validate(plan)

    async def update(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        plan_content_raw: dict,
    ) -> PlanResponse:
        await self._get_session_for_user(session_id, user_id)
        plan = await self._plan_repo.get_by_session_id(session_id)
        if not plan:
            raise NotFoundError("No plan found for this session")
        if plan.status != "ready":
            raise ConflictError(f"Plan cannot be edited in status '{plan.status}'")

        validated, errors = validate_plan(plan_content_raw)
        if validated is None:
            from src.core.exceptions import BadRequestError

            raise BadRequestError(f"Plan validation failed: {'; '.join(errors)}")

        plan = await self._plan_repo.update_content(plan, plan_content_raw)
        return PlanResponse.model_validate(plan)

    async def confirm(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        background_tasks: BackgroundTasks,
    ) -> PlanConfirmResponse:
        session = await self._get_session_for_user(session_id, user_id)
        plan = await self._plan_repo.get_by_session_id(session_id)
        if not plan:
            raise NotFoundError("No plan found for this session")

        # Atomic conditional update: only succeeds if current status is 'ready'.
        # Prevents double-confirmation from concurrent requests (SR-002).
        confirmed_plan = await self._plan_repo.confirm_if_ready(plan.id)
        if confirmed_plan is None:
            # Already confirmed (idempotent retry) — return current status without re-queuing.
            if plan.status == "confirmed":
                return PlanConfirmResponse(
                    session_id=session_id,
                    plan_id=plan.id,
                    status="confirmed",
                )
            raise ConflictError(f"Plan cannot be confirmed in status '{plan.status}'")
        plan = confirmed_plan

        await self._session_repo.update(session, status="plan_confirmed")
        logger.info(
            "plan.confirmed session_id=%s plan_id=%s user_id=%s",
            session_id, plan.id, user_id,
        )

        background_tasks.add_task(self._create_tickets, session_id)

        return PlanConfirmResponse(
            session_id=session_id,
            plan_id=plan.id,
            status="confirmed",
        )

    async def _create_tickets(self, session_id: uuid.UUID) -> None:
        """Background task: create TM tickets for a confirmed plan."""
        try:
            async with asyncio.timeout(120):
                plan = await self._plan_repo.get_by_session_id(session_id)
                if not plan or not plan.plan_content:
                    logger.error(
                        "_create_tickets: plan not found or empty for session %s", session_id
                    )
                    return

                session = await self._session_repo.get_by_id(session_id)
                if not session or not session.tm_project_id:
                    logger.error(
                        "_create_tickets: session/project_id missing for session %s", session_id
                    )
                    return

                project_id = session.tm_project_id
                ticket_id_map: dict[str, str] = dict(plan.ticket_id_map or {})

                plan_content = PlanContent.model_validate(plan.plan_content)

                epic = plan_content.epic
                if plan.tm_epic_id:
                    epic_tm_id = plan.tm_epic_id
                else:
                    epic_tm_id = await self._tm.create_epic(project_id, epic)
                    plan = await self._plan_repo.append_created_ticket(
                        plan, epic.local_id, epic_tm_id
                    )
                    plan = await self._plan_repo.update_status(
                        plan, "confirmed", tm_epic_id=epic_tm_id
                    )
                    ticket_id_map[epic.local_id] = epic_tm_id

                for story in plan_content.stories:
                    if story.local_id in ticket_id_map:
                        story_tm_id = ticket_id_map[story.local_id]
                    else:
                        story_tm_id = await self._tm.create_story(project_id, story, epic_tm_id)
                        plan = await self._plan_repo.append_created_ticket(
                            plan, story.local_id, story_tm_id
                        )
                        ticket_id_map[story.local_id] = story_tm_id

                    for task in story.tasks:
                        if task.local_id in ticket_id_map:
                            continue
                        dep_tm_ids = [
                            ticket_id_map[d] for d in task.depends_on if d in ticket_id_map
                        ]
                        task_tm_id = await self._tm.create_task(
                            project_id, task, story_tm_id, dep_tm_ids
                        )
                        plan = await self._plan_repo.append_created_ticket(
                            plan, task.local_id, task_tm_id
                        )
                        ticket_id_map[task.local_id] = task_tm_id

                plan = await self._plan_repo.update_status(plan, "tickets_created")
                await self._session_repo.update(session, status="tickets_created")
                logger.info(
                    "plan.tickets_created session_id=%s plan_id=%s ticket_count=%d tm_epic_id=%s",
                    session_id, plan.id, len(plan.created_ticket_ids or []), plan.tm_epic_id,
                )

                agent_config_dict = plan.agent_config
                if agent_config_dict:
                    try:
                        agent_config = AgentConfig.model_validate(agent_config_dict)
                        await self._store_agent_config(project_id, agent_config)
                    except Exception as exc:
                        logger.warning("Agent config parse failed: %s", exc)

        except Exception as exc:
            logger.error(
                "_create_tickets failed for session %s: %s", session_id, exc, exc_info=True
            )
            try:
                plan = await self._plan_repo.get_by_session_id(session_id)
                if plan and plan.status == "confirmed":
                    current_errors = list(plan.validation_errors or [])
                    current_errors.append(str(exc))
                    await self._plan_repo.update_status(
                        plan, "confirmed", validation_errors=current_errors
                    )
            except Exception:
                pass

    async def _store_agent_config(self, project_id: str, agent_config: AgentConfig) -> None:
        """Store agent config in ContextDistiller. Best-effort — never raises."""
        try:
            settings = get_settings()
            base = settings.context_distiller_base_url.rstrip("/")
            url = f"{base}/api/v1/memory/{project_id}/agent-config"
            async with httpx.AsyncClient(
                timeout=settings.context_distiller_timeout_seconds
            ) as client:
                resp = await client.post(url, json=agent_config.model_dump())
                if resp.status_code not in (200, 201):
                    logger.warning(
                        "ContextDistiller agent-config store returned %s: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
        except Exception as exc:
            logger.warning("Failed to store agent config in ContextDistiller: %s", exc)

    async def get_creation_status(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> PlanStatusResponse:
        await self._get_session_for_user(session_id, user_id)
        plan = await self._plan_repo.get_by_session_id(session_id)
        if not plan:
            raise NotFoundError("No plan found for this session")

        total = 0
        if plan.plan_content:
            try:
                plan_content = PlanContent.model_validate(plan.plan_content)
                total = (
                    1 + len(plan_content.stories) + sum(len(s.tasks) for s in plan_content.stories)
                )
            except Exception:
                total = 0

        created_count = len(plan.created_ticket_ids or [])
        errors = list(plan.validation_errors or [])

        return PlanStatusResponse(
            status=plan.status,
            created_count=created_count,
            total=total,
            errors=errors,
        )
