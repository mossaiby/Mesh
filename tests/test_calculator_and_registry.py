import pytest
from tools.registry import ToolRegistry, CalculatorTool
from tools.base import BaseTool


class MockMutatingTool(BaseTool):
    name = "mutating_tool"
    description = "A tool that modifies state"
    requires_guard = True
    parameters = {"type": "object", "properties": {}}

    async def execute(self):
        return {"status": "mutated"}


@pytest.mark.asyncio
async def test_calculator_tool_eval_and_safety():
    calc = CalculatorTool()

    # Valid arithmetic
    assert (await calc.execute("2 + 2")) == {"result": 4}
    assert (await calc.execute("10 * (5 - 3) / 2")) == {"result": 10.0}
    assert (await calc.execute("2 ** 8")) == {"result": 256}

    # Division by zero
    assert "error" in (await calc.execute("10 / 0"))

    # Security: AST block code injection and imports
    res_inj = await calc.execute("__import__('os').system('ls')")
    assert "error" in res_inj
    assert "disallowed construct" in res_inj["error"]


@pytest.mark.asyncio
async def test_tool_registry_mode_blocking_and_fuzzy_matching():
    registry = ToolRegistry()
    calc = CalculatorTool()
    mut = MockMutatingTool()
    registry.register(calc)
    registry.register(mut)

    # 1. Fuzzy match typo correction ('calculatr' -> 'calculator')
    res_fuzzy = await registry.execute("calculatr", '{"expression": "5 + 5"}')
    assert "10" in res_fuzzy

    # 2. Mode blocking
    registry.mode_blocked_tools.add("mutating_tool")
    res_blocked = await registry.execute("mutating_tool", "{}")
    assert "error" in res_blocked
    assert "not available in the current mode" in res_blocked
