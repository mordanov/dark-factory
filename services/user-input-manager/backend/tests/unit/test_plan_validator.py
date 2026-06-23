"""Unit tests for src.services.planning.validator — PlanValidator."""

import pytest
from src.services.planning.validator import validate_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan(stories=None, epic_overrides=None):
    epic = {
        "local_id": "epic-1",
        "title": "Build auth system",
        "description": "Implement JWT authentication",
        "ticket_type": "epic",
    }
    if epic_overrides:
        epic.update(epic_overrides)
    return {
        "epic": epic,
        "stories": stories if stories is not None else [_make_story()],
    }


def _make_story(index=1, tasks=None, overrides=None):
    story = {
        "local_id": f"story-{index}",
        "title": f"Story {index}",
        "description": f"Description for story {index}",
        "ticket_type": "story",
        "tasks": tasks if tasks is not None else [_make_task(1, index)],
    }
    if overrides:
        story.update(overrides)
    return story


def _make_task(task_idx=1, story_idx=1, depends_on=None, overrides=None):
    task = {
        "local_id": f"task-{story_idx}-{task_idx}",
        "title": f"Task {story_idx}-{task_idx}",
        "description": "Task description",
        "ticket_type": "task",
        "complexity": "M",
        "depends_on": depends_on or [],
    }
    if overrides:
        task.update(overrides)
    return task


# ---------------------------------------------------------------------------
# Valid plan
# ---------------------------------------------------------------------------

def test_valid_plan_passes():
    plan, errors = validate_plan(_make_plan())
    assert errors == []
    assert plan is not None
    assert plan.epic.title == "Build auth system"
    assert len(plan.stories) == 1


def test_valid_plan_with_depends_on():
    tasks = [
        _make_task(1, 1),
        _make_task(2, 1, depends_on=["task-1-1"]),
    ]
    plan, errors = validate_plan(_make_plan(stories=[_make_story(tasks=tasks)]))
    assert errors == []
    assert plan is not None


def test_valid_plan_all_ticket_types():
    tasks = [
        _make_task(1, 1, overrides={"ticket_type": "task"}),
        _make_task(2, 1, overrides={"ticket_type": "implementation"}),
        _make_task(3, 1, overrides={"ticket_type": "investigation"}),
    ]
    plan, errors = validate_plan(_make_plan(stories=[_make_story(tasks=tasks)]))
    assert errors == []


def test_valid_plan_all_complexity_values():
    for i, complexity in enumerate(["S", "M", "L", "XL"], start=1):
        tasks = [_make_task(i, 1, overrides={"complexity": complexity})]
        plan, errors = validate_plan(_make_plan(stories=[_make_story(tasks=tasks)]))
        assert errors == [], f"Complexity {complexity} should be valid"


# ---------------------------------------------------------------------------
# Top-level structural errors
# ---------------------------------------------------------------------------

def test_missing_epic():
    _, errors = validate_plan({"stories": [_make_story()]})
    assert any("epic" in e for e in errors)


def test_missing_stories():
    _, errors = validate_plan({"epic": {
        "local_id": "epic-1", "title": "T", "description": "D", "ticket_type": "epic"
    }})
    assert any("stories" in e for e in errors)


def test_not_a_dict():
    _, errors = validate_plan([1, 2, 3])
    assert any("JSON object" in e for e in errors)


def test_empty_stories_list():
    _, errors = validate_plan(_make_plan(stories=[]))
    assert any("at least one story" in e for e in errors)


# ---------------------------------------------------------------------------
# Epic validation
# ---------------------------------------------------------------------------

def test_epic_wrong_ticket_type():
    _, errors = validate_plan(_make_plan(epic_overrides={"ticket_type": "story"}))
    assert any("ticket_type must be 'epic'" in e for e in errors)


def test_epic_title_too_long():
    _, errors = validate_plan(_make_plan(epic_overrides={"title": "A" * 201}))
    assert any("title exceeds 200" in e for e in errors)


def test_epic_description_too_long():
    _, errors = validate_plan(_make_plan(epic_overrides={"description": "B" * 501}))
    assert any("description exceeds 500" in e for e in errors)


def test_epic_missing_required_fields():
    plan = _make_plan()
    del plan["epic"]["local_id"]
    _, errors = validate_plan(plan)
    assert any("local_id" in e for e in errors)


# ---------------------------------------------------------------------------
# Story count limit
# ---------------------------------------------------------------------------

def test_story_count_exceeds_10():
    stories = [_make_story(i) for i in range(1, 12)]
    _, errors = validate_plan(_make_plan(stories=stories))
    assert any("11 stories" in e for e in errors)


def test_story_count_exactly_10_passes():
    stories = [_make_story(i) for i in range(1, 11)]
    plan, errors = validate_plan(_make_plan(stories=stories))
    assert errors == []
    assert plan is not None


# ---------------------------------------------------------------------------
# Story field validation
# ---------------------------------------------------------------------------

def test_story_wrong_ticket_type():
    story = _make_story(overrides={"ticket_type": "task"})
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("ticket_type must be 'story'" in e for e in errors)


def test_story_title_too_long():
    story = _make_story(overrides={"title": "X" * 201})
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("title exceeds 200" in e for e in errors)


def test_story_description_too_long():
    story = _make_story(overrides={"description": "Y" * 501})
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("description exceeds 500" in e for e in errors)


def test_story_missing_required_field():
    story = _make_story()
    del story["title"]
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("title" in e for e in errors)


# ---------------------------------------------------------------------------
# Task count limit
# ---------------------------------------------------------------------------

def test_task_count_exceeds_10():
    tasks = [_make_task(i, 1) for i in range(1, 12)]
    story = _make_story(tasks=tasks)
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("11 tasks" in e for e in errors)


def test_task_count_exactly_10_passes():
    tasks = [_make_task(i, 1) for i in range(1, 11)]
    story = _make_story(tasks=tasks)
    plan, errors = validate_plan(_make_plan(stories=[story]))
    assert errors == []


# ---------------------------------------------------------------------------
# Task field validation
# ---------------------------------------------------------------------------

def test_task_invalid_ticket_type():
    task = _make_task(overrides={"ticket_type": "epic"})
    story = _make_story(tasks=[task])
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("ticket_type" in e for e in errors)


def test_task_invalid_complexity():
    task = _make_task(overrides={"complexity": "XS"})
    story = _make_story(tasks=[task])
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("complexity" in e for e in errors)


def test_task_title_too_long():
    task = _make_task(overrides={"title": "Z" * 201})
    story = _make_story(tasks=[task])
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("title exceeds 200" in e for e in errors)


def test_task_description_too_long():
    task = _make_task(overrides={"description": "W" * 501})
    story = _make_story(tasks=[task])
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("description exceeds 500" in e for e in errors)


def test_task_missing_required_field():
    task = _make_task()
    del task["local_id"]
    story = _make_story(tasks=[task])
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("local_id" in e for e in errors)


# ---------------------------------------------------------------------------
# depends_on validation
# ---------------------------------------------------------------------------

def test_depends_on_unknown_task():
    task = _make_task(1, 1, depends_on=["task-1-99"])
    story = _make_story(tasks=[task])
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("task-1-99" in e for e in errors)


def test_depends_on_cross_story_task_rejected():
    """A task in story-1 must not reference a task from story-2."""
    task = _make_task(1, 1, depends_on=["task-2-1"])
    story = _make_story(tasks=[task])
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("task-2-1" in e for e in errors)


def test_depends_on_not_a_list():
    task = _make_task(overrides={"depends_on": "task-1-1"})
    story = _make_story(tasks=[task])
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("depends_on must be an array" in e for e in errors)


# ---------------------------------------------------------------------------
# Circular dependency detection
# ---------------------------------------------------------------------------

def test_simple_cycle_detected():
    tasks = [
        _make_task(1, 1, depends_on=["task-1-2"]),
        _make_task(2, 1, depends_on=["task-1-1"]),
    ]
    story = _make_story(tasks=tasks)
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("Circular dependency" in e for e in errors)


def test_self_cycle_detected():
    tasks = [_make_task(1, 1, depends_on=["task-1-1"])]
    story = _make_story(tasks=tasks)
    _, errors = validate_plan(_make_plan(stories=[story]))
    # self-reference is caught as unknown dep (local_id not in other tasks) or as cycle
    assert len(errors) > 0


def test_three_task_cycle_detected():
    tasks = [
        _make_task(1, 1, depends_on=["task-1-3"]),
        _make_task(2, 1, depends_on=["task-1-1"]),
        _make_task(3, 1, depends_on=["task-1-2"]),
    ]
    story = _make_story(tasks=tasks)
    _, errors = validate_plan(_make_plan(stories=[story]))
    assert any("Circular dependency" in e for e in errors)


def test_diamond_dependency_no_cycle():
    """A→B, A→C, B→D, C→D is a valid diamond shape with no cycle."""
    tasks = [
        _make_task(1, 1),                                 # A
        _make_task(2, 1, depends_on=["task-1-1"]),        # B depends on A
        _make_task(3, 1, depends_on=["task-1-1"]),        # C depends on A
        _make_task(4, 1, depends_on=["task-1-2", "task-1-3"]),  # D depends on B, C
    ]
    story = _make_story(tasks=tasks)
    plan, errors = validate_plan(_make_plan(stories=[story]))
    assert errors == []


# ---------------------------------------------------------------------------
# Return-value contract
# ---------------------------------------------------------------------------

def test_returns_none_plan_on_error():
    plan, errors = validate_plan({"epic": "not a dict", "stories": []})
    assert plan is None
    assert len(errors) > 0


def test_returns_plan_content_object_on_success():
    from src.schemas.schemas import PlanContent
    plan, errors = validate_plan(_make_plan())
    assert isinstance(plan, PlanContent)
    assert errors == []
