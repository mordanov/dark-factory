"""TMPlanClient — creates Epic/Story/Task tickets for plan hierarchies.

TM API constraints (verified against live API):
- Field is `ticket_type`, not `type`.
- Allowed ticket_type values: bug, feature, improvement, investigation,
  discovery, reporting, testing, analysis, other.  Epic/story/task are NOT valid.
- Hierarchy is expressed via the follow-ups endpoint:
    POST /api/v1/tickets/{parent_id}/follow-ups
  (not via a `parent_id` field on the create-ticket body).
- There is no `depends_on` field; task dependencies are expressed via tags.

Mapping:
  plan epic  → ticket_type="feature"  + tag "plan-epic"
  plan story → follow-up of epic      + ticket_type="feature"  + tag "plan-story"
  plan task  → follow-up of story     + ticket_type={investigation|feature|improvement|other}
               + tag "complexity-{S|M|L|XL}" + tags "depends-on-{tm_id}" per dependency
"""

from __future__ import annotations

import structlog

from src.schemas.schemas import PlanEpic, PlanStory, PlanTask
from src.services.ticket_manager.client import TicketManagerClient

logger = structlog.get_logger(__name__)

# Maps plan ticket_type values to valid TM ticket_type values.
_TASK_TYPE_MAP: dict[str, str] = {
    "task": "other",
    "implementation": "improvement",
    "investigation": "investigation",
}


class TMPlanClient(TicketManagerClient):
    async def create_epic(self, project_id: str, epic: PlanEpic) -> str:
        result = await self._request(
            "POST",
            f"/api/v1/projects/{project_id}/tickets",
            json={
                "title": epic.title,
                "description": epic.description,
                "ticket_type": "feature",
                "ticket_spec": "architecture",
                "tags": ["plan-epic"],
            },
        )
        return str(result["id"])

    async def create_story(self, project_id: str, story: PlanStory, epic_tm_id: str) -> str:
        # Stories are created as follow-ups of the epic ticket for hierarchy.
        result = await self._request(
            "POST",
            f"/api/v1/tickets/{epic_tm_id}/follow-ups",
            json={
                "title": story.title,
                "description": story.description,
                "ticket_type": "feature",
                "ticket_spec": "architecture",
                "tags": ["plan-story"],
            },
        )
        return str(result["id"])

    async def create_task(
        self,
        project_id: str,
        task: PlanTask,
        story_tm_id: str,
        dep_tm_ids: list[str],
    ) -> str:
        tm_type = _TASK_TYPE_MAP.get(task.ticket_type, "other")
        tags = [f"complexity-{task.complexity}", "plan-task"]
        # Encode dependencies as tags since TM has no depends_on field.
        tags.extend(f"depends-on-{tid[:8]}" for tid in dep_tm_ids)

        result = await self._request(
            "POST",
            f"/api/v1/tickets/{story_tm_id}/follow-ups",
            json={
                "title": task.title,
                "description": task.description,
                "ticket_type": tm_type,
                "ticket_spec": "architecture",
                "tags": tags,
            },
        )
        return str(result["id"])
