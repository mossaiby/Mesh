import pytest
from tools.todo_tool import TodoTool


@pytest.mark.asyncio
async def test_todo_workflow_and_dependencies():
    todo = TodoTool()

    # 1. Add sequential & dependent tasks
    r1 = await todo.execute(action="add", task="Initialize project repo")
    assert r1["status"] == "added"
    assert r1["task"]["id"] == 1

    r2 = await todo.execute(action="add", task="Write API tests", depends_on=[1])
    assert r2["status"] == "added"
    assert r2["task"]["id"] == 2

    r3 = await todo.execute(action="add", task="Write documentation")  # Independent
    assert r3["task"]["id"] == 3

    # 2. Query 'next' unblocked tasks
    next_tasks = await todo.execute(action="next")
    ready_ids = {t["id"] for t in next_tasks["ready_tasks"]}
    assert ready_ids == {1, 3}
    assert 2 not in ready_ids  # Task 2 blocked on Task 1

    # 3. Blocked completion error
    comp_blocked = await todo.execute(action="complete", task_id=2)
    assert "error" in comp_blocked
    assert "depends on unfinished task" in comp_blocked["error"]

    # 4. Complete unblocked task with string type coercion
    comp_1 = await todo.execute(action="complete", task_id="1")
    assert comp_1["status"] == "completed"

    # 5. Task 2 should now be unblocked
    next_tasks_2 = await todo.execute(action="next")
    ready_ids_2 = {t["id"] for t in next_tasks_2["ready_tasks"]}
    assert 2 in ready_ids_2


@pytest.mark.asyncio
async def test_todo_cycle_and_invalid_dependencies():
    todo = TodoTool()
    # Cannot depend on non-existent task ID (guarantees DAG without cycles)
    res = await todo.execute(action="add", task="Task with invalid dep", depends_on=[99])
    assert "error" in res
    assert "references unknown task ID" in res["error"]


@pytest.mark.asyncio
async def test_todo_clear():
    todo = TodoTool()
    await todo.execute(action="add", task="Task 1")
    await todo.execute(action="clear")
    listing = await todo.execute(action="list")
    assert len(listing["todos"]) == 0
