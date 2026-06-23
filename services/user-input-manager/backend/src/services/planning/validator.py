"""PlanValidator — pure validation for plan content. No I/O."""

from __future__ import annotations

from src.schemas.schemas import PlanContent


def validate_plan(data: dict) -> tuple[PlanContent | None, list[str]]:
    """Validate raw plan dict. Returns (PlanContent, []) on success or (None, errors) on failure."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return None, ["Plan must be a JSON object"]

    if "epic" not in data:
        errors.append("Missing required field: epic")
    if "stories" not in data:
        errors.append("Missing required field: stories")

    if errors:
        return None, errors

    epic = data.get("epic", {})
    if not isinstance(epic, dict):
        errors.append("Field 'epic' must be an object")
    else:
        for field in ("local_id", "title", "description", "ticket_type"):
            if field not in epic:
                errors.append(f"Missing required field in epic: {field}")
        title = epic.get("title", "")
        if isinstance(title, str) and len(title) > 200:
            errors.append("Epic title exceeds 200 characters")
        desc = epic.get("description", "")
        if isinstance(desc, str) and len(desc) > 500:
            errors.append("Epic description exceeds 500 characters")
        if epic.get("ticket_type") != "epic":
            errors.append("Epic ticket_type must be 'epic'")

    stories = data.get("stories", [])
    if not isinstance(stories, list):
        errors.append("Field 'stories' must be an array")
        return None, errors

    if len(stories) == 0:
        errors.append("Plan must have at least one story")
    if len(stories) > 10:
        errors.append(f"Plan has {len(stories)} stories; maximum is 10")

    for i, story in enumerate(stories):
        story_prefix = f"Story {i + 1}"
        if not isinstance(story, dict):
            errors.append(f"{story_prefix} must be an object")
            continue

        for field in ("local_id", "title", "description", "ticket_type", "tasks"):
            if field not in story:
                errors.append(f"{story_prefix}: missing required field '{field}'")

        title = story.get("title", "")
        if isinstance(title, str) and len(title) > 200:
            errors.append(f"{story_prefix}: title exceeds 200 characters")
        desc = story.get("description", "")
        if isinstance(desc, str) and len(desc) > 500:
            errors.append(f"{story_prefix}: description exceeds 500 characters")
        if story.get("ticket_type") != "story":
            errors.append(f"{story_prefix}: ticket_type must be 'story'")

        tasks = story.get("tasks", [])
        if not isinstance(tasks, list):
            errors.append(f"{story_prefix}: 'tasks' must be an array")
            continue

        if len(tasks) > 10:
            errors.append(f"{story_prefix}: has {len(tasks)} tasks; maximum is 10")

        task_local_ids = {t.get("local_id") for t in tasks if isinstance(t, dict)}
        allowed_task_types = {"task", "implementation", "investigation"}
        allowed_complexity = {"S", "M", "L", "XL"}

        for j, task in enumerate(tasks):
            task_prefix = f"Story {i + 1} Task {j + 1}"
            if not isinstance(task, dict):
                errors.append(f"{task_prefix}: must be an object")
                continue

            for field in ("local_id", "title", "description", "ticket_type"):
                if field not in task:
                    errors.append(f"{task_prefix}: missing required field '{field}'")

            t_title = task.get("title", "")
            if isinstance(t_title, str) and len(t_title) > 200:
                errors.append(f"{task_prefix}: title exceeds 200 characters")
            t_desc = task.get("description", "")
            if isinstance(t_desc, str) and len(t_desc) > 500:
                errors.append(f"{task_prefix}: description exceeds 500 characters")

            t_type = task.get("ticket_type")
            if t_type not in allowed_task_types:
                errors.append(f"{task_prefix}: ticket_type '{t_type}' not in {allowed_task_types}")

            complexity = task.get("complexity", "M")
            if complexity not in allowed_complexity:
                errors.append(
                    f"{task_prefix}: complexity '{complexity}' not in {allowed_complexity}"
                )

            depends_on = task.get("depends_on", [])
            if not isinstance(depends_on, list):
                errors.append(f"{task_prefix}: depends_on must be an array")
            else:
                for dep in depends_on:
                    if dep not in task_local_ids:
                        errors.append(f"{task_prefix}: depends_on references unknown task '{dep}'")

        if not errors:
            cycle_error = _detect_cycle(tasks)
            if cycle_error:
                errors.append(f"{story_prefix}: {cycle_error}")

    if errors:
        return None, errors

    try:
        plan = PlanContent.model_validate(data)
    except Exception as exc:
        return None, [str(exc)]

    return plan, []


def _detect_cycle(tasks: list[dict]) -> str | None:
    """DFS-based cycle detection in depends_on graph. Returns error message or None."""
    graph: dict[str, list[str]] = {}
    for task in tasks:
        local_id = task.get("local_id", "")
        graph[local_id] = list(task.get("depends_on", []))

    visited: set[str] = set()
    rec_stack: set[str] = set()

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for neighbour in graph.get(node, []):
            if neighbour not in visited:
                if dfs(neighbour):
                    return True
            elif neighbour in rec_stack:
                return True
        rec_stack.discard(node)
        return False

    for node in graph:
        if node not in visited:
            if dfs(node):
                return f"Circular dependency detected involving task '{node}'"

    return None
