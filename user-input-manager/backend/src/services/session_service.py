"""Prompt Session Service — orchestrates the refinement loop.

This is the heart of the application.  It coordinates:
  - DB repositories (sessions + iterations)
  - LLM service (prompt refinement)
  - Ticket Manager client (context + final ticket creation)

Every public method maps to one user action in the UI.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from src.models.models import PromptSession
from src.repositories.session_repo import IterationRepository, SessionRepository
from src.schemas.schemas import (
    ApproveRequest,
    IterationResponse,
    RevertRequest,
    SessionCreate,
    SessionListResponse,
    SessionResponse,
    UserFeedback,
)
from src.services.llm.openai_service import refine_prompt
from src.services.ticket_manager.client import TicketManagerClient


class SessionService:
    def __init__(self, db: AsyncSession, tm_client: TicketManagerClient) -> None:
        self._session_repo = SessionRepository(db)
        self._iter_repo = IterationRepository(db)
        self._tm = tm_client

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_in_progress(self, session: PromptSession) -> None:
        if session.status != "in_progress":
            raise BadRequestError(f"Session is already {session.status}")

    async def _get_session_for_user(
        self, session_id: uuid.UUID, user_id: uuid.UUID, *, admin_allowed: bool = False
    ) -> PromptSession:
        session = await self._session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session not found")
        if session.user_id != user_id and not admin_allowed:
            raise ForbiddenError()
        return session

    async def _build_context(self, session: PromptSession) -> str | None:
        if session.session_type == "existing_project" and session.tm_project_id:
            try:
                return await self._tm.build_project_context(session.tm_project_id)
            except Exception:
                return None  # context is best-effort
        return None

    @staticmethod
    def _iterations_to_history(iterations) -> list[dict]:
        return [
            {
                "role": it.role,
                "iteration_number": it.iteration_number,
                "text": it.prompt_text,
                "questions": it.llm_questions or "",
            }
            for it in iterations
        ]

    # ------------------------------------------------------------------
    # Create session (first user prompt → first LLM refinement)
    # ------------------------------------------------------------------

    async def create_session(self, user_id: uuid.UUID, payload: SessionCreate) -> dict:
        """
        1. Persist the session.
        2. Persist iteration #1 (user role).
        3. Call LLM for refinement.
        4. Persist iteration #2 (assistant role).
        """
        session = await self._session_repo.create(
            user_id=user_id,
            session_type=payload.session_type,
            tm_project_id=payload.tm_project_id,
            tm_project_name=payload.tm_project_name,
        )

        # Iteration 1 — user's raw input
        user_iter = await self._iter_repo.create(
            session_id=session.id,
            iteration_number=1,
            role="user",
            prompt_text=payload.initial_prompt,
        )

        context = await self._build_context(session)

        result = await refine_prompt(
            initial_prompt=payload.initial_prompt,
            iteration_history=[],
            project_context=context,
        )

        # Iteration 2 — LLM refinement
        assistant_iter = await self._iter_repo.create(
            session_id=session.id,
            iteration_number=2,
            role="assistant",
            prompt_text=result.refined_prompt,
            llm_assessment=result.assessment,
            llm_questions=result.questions or None,
            llm_suggested_title=result.suggested_title or None,
        )

        # Update session's suggested title
        await self._session_repo.update(session, tm_ticket_title=result.suggested_title or None)

        return {
            "session": SessionResponse.model_validate(session),
            "latest_iteration": IterationResponse.model_validate(assistant_iter),
        }

    # ------------------------------------------------------------------
    # Submit user feedback → next LLM iteration
    # ------------------------------------------------------------------

    async def submit_feedback(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        feedback: UserFeedback,
    ) -> dict:
        session = await self._get_session_for_user(session_id, user_id)
        self._require_in_progress(session)

        iterations = await self._iter_repo.list_for_session(session_id)
        # last must be an assistant iteration waiting for feedback
        last = iterations[-1] if iterations else None
        if not last or last.role != "assistant" or last.is_approved is not None:
            raise BadRequestError("No pending assistant iteration to respond to")

        if feedback.is_approved:
            # Mark as approved — no new LLM call needed yet
            await self._iter_repo.update(
                last,
                is_approved=True,
                user_comment=feedback.comment,
            )
            return {
                "session": SessionResponse.model_validate(session),
                "latest_iteration": IterationResponse.model_validate(last),
                "awaiting_approval": True,
            }

        # Not approved — record feedback and generate next refinement
        await self._iter_repo.update(
            last,
            is_approved=False,
            user_comment=feedback.comment,
        )

        context = await self._build_context(session)
        initial_prompt = iterations[0].prompt_text  # always the first user iter

        result = await refine_prompt(
            initial_prompt=initial_prompt,
            iteration_history=self._iterations_to_history(iterations),
            project_context=context,
            user_comment=feedback.comment,
        )

        next_number = await self._iter_repo.max_number(session_id) + 1
        new_iter = await self._iter_repo.create(
            session_id=session.id,
            iteration_number=next_number,
            role="assistant",
            prompt_text=result.refined_prompt,
            llm_assessment=result.assessment,
            llm_questions=result.questions or None,
            llm_suggested_title=result.suggested_title or None,
        )

        await self._session_repo.update(session, tm_ticket_title=result.suggested_title or session.tm_ticket_title)

        return {
            "session": SessionResponse.model_validate(session),
            "latest_iteration": IterationResponse.model_validate(new_iter),
            "awaiting_approval": False,
        }

    # ------------------------------------------------------------------
    # Revert to a previous iteration
    # ------------------------------------------------------------------

    async def revert(
        self, session_id: uuid.UUID, user_id: uuid.UUID, payload: RevertRequest
    ) -> dict:
        session = await self._get_session_for_user(session_id, user_id)
        self._require_in_progress(session)

        target = payload.target_iteration_number
        iterations = await self._iter_repo.list_for_session(session_id)
        target_iter = next((it for it in iterations if it.iteration_number == target), None)
        if not target_iter:
            raise NotFoundError(f"Iteration {target} not found")

        # Delete everything after target
        await self._iter_repo.delete_from_number(session_id, target + 1)

        # Reset approval state of target so user can interact with it again
        await self._iter_repo.update(target_iter, is_approved=None, user_comment=None)

        return {
            "session": SessionResponse.model_validate(session),
            "latest_iteration": IterationResponse.model_validate(target_iter),
        }

    # ------------------------------------------------------------------
    # Approve and create ticket
    # ------------------------------------------------------------------

    async def approve_and_create_ticket(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: ApproveRequest,
    ) -> dict:
        session = await self._get_session_for_user(session_id, user_id)
        self._require_in_progress(session)

        iterations = await self._iter_repo.list_for_session(session_id)
        last_assistant = next(
            (it for it in reversed(iterations) if it.role == "assistant"), None
        )
        if not last_assistant:
            raise BadRequestError("No assistant iteration to approve")

        final_prompt = last_assistant.prompt_text

        # 1. Create project if needed
        project_id = session.tm_project_id
        if session.session_type == "new_project":
            project = await self._tm.create_project(
                name=session.tm_project_name or "Untitled Project",
                description=payload.project_description or "",
            )
            project_id = str(project.get("id", ""))
            await self._session_repo.update(session, tm_project_id=project_id)

        # 2. Create ticket
        ticket = await self._tm.create_ticket(
            project_id=project_id,
            title=payload.ticket_title,
            description=final_prompt,
        )
        ticket_id = str(ticket.get("id", ""))

        # 3. Update session
        await self._session_repo.update(
            session,
            status="approved",
            tm_ticket_id=ticket_id,
            tm_ticket_title=payload.ticket_title,
            tm_project_id=project_id,
        )
        await self._iter_repo.update(last_assistant, is_approved=True)

        # Refresh
        session = await self._session_repo.get_by_id(session_id)
        return {
            "session": SessionResponse.model_validate(session),
            "ticket_id": ticket_id,
            "project_id": project_id,
        }

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def list_sessions(self, user_id: uuid.UUID, offset: int, limit: int) -> SessionListResponse:
        sessions, total = await self._session_repo.list_for_user(user_id, offset, limit)
        return SessionListResponse(
            items=[SessionResponse.model_validate(s) for s in sessions],
            total=total,
        )

    async def get_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> SessionResponse:
        session = await self._get_session_for_user(session_id, user_id)
        return SessionResponse.model_validate(session)

    async def get_iterations(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[IterationResponse]:
        session = await self._get_session_for_user(session_id, user_id)
        iterations = await self._iter_repo.list_for_session(session.id)
        return [IterationResponse.model_validate(it) for it in iterations]
