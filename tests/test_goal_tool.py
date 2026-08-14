import pytest
from tools.goal_tool import GoalTool


@pytest.mark.asyncio
async def test_goal_lifecycle_and_prompt_injection():
    notified = False

    def on_change():
        nonlocal notified
        notified = True

    goal = GoalTool(on_change=on_change)

    # 1. Set goal with criteria
    res = await goal.execute(
        action="set",
        goal="Ship v1.0 Release",
        success_criteria=["Implement auth", "Write unit tests", "Pass CI"]
    )
    assert res["status"] == "set"
    assert notified is True
    assert goal.has_goal() is True

    # 2. Verify system prompt Markdown section
    section = goal.as_system_prompt_section()
    assert "## Current Goal" in section
    assert "Ship v1.0 Release" in section
    assert "- [ ] Implement auth" in section

    # 3. Complete criterion with string type coercion
    notified = False
    res_comp = await goal.execute(action="complete_criterion", criterion_index="1")
    assert res_comp["status"] == "criterion_completed"
    assert notified is True

    updated_section = goal.as_system_prompt_section()
    assert "- [x] Implement auth" in updated_section
    assert "- [ ] Write unit tests" in updated_section

    # 4. Clear goal
    res_clear = await goal.execute(action="clear")
    assert res_clear["status"] == "cleared"
    assert goal.has_goal() is False
    assert goal.as_system_prompt_section() == ""
