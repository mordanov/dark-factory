"""PlanRepository — data access for PromptPlan."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import PromptPlan


class PlanRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_session_id(self, session_id: uuid.UUID) -> PromptPlan | None:
        result = await self._db.execute(
            select(PromptPlan).where(PromptPlan.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        session_id: uuid.UUID,
        plan_content: dict | None = None,
        agent_config: dict | None = None,
    ) -> PromptPlan:
        plan = PromptPlan(
            session_id=session_id,
            status="draft",
            plan_content=plan_content,
            agent_config=agent_config,
        )
        self._db.add(plan)
        await self._db.flush()
        await self._db.refresh(plan)
        return plan

    async def update_content(self, plan: PromptPlan, plan_content: dict) -> PromptPlan:
        plan.plan_content = plan_content
        await self._db.flush()
        await self._db.refresh(plan)
        return plan

    async def update_status(self, plan: PromptPlan, status: str, **kwargs) -> PromptPlan:
        plan.status = status
        for k, v in kwargs.items():
            setattr(plan, k, v)
        await self._db.flush()
        await self._db.refresh(plan)
        return plan

    async def confirm_if_ready(self, plan_id: uuid.UUID) -> PromptPlan | None:
        """Atomically transition plan from 'ready' → 'confirmed'.

        Returns the updated plan row if the transition succeeded,
        or None if the plan was not in 'ready' state (race condition guard).
        """
        stmt = (
            update(PromptPlan)
            .where(PromptPlan.id == plan_id, PromptPlan.status == "ready")
            .values(status="confirmed")
            .returning(PromptPlan)
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        await self._db.refresh(row)
        return row

    async def append_created_ticket(
        self, plan: PromptPlan, local_id: str, tm_id: str
    ) -> PromptPlan:
        existing_ids = list(plan.created_ticket_ids or [])
        if tm_id not in existing_ids:
            existing_ids.append(tm_id)

        existing_map = dict(plan.ticket_id_map or {})
        existing_map[local_id] = tm_id

        plan.created_ticket_ids = existing_ids
        plan.ticket_id_map = existing_map
        await self._db.flush()
        await self._db.refresh(plan)
        return plan

    async def delete_by_session_id(self, session_id: uuid.UUID) -> None:
        plan = await self.get_by_session_id(session_id)
        if plan:
            await self._db.delete(plan)
            await self._db.flush()
