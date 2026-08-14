from modes import MODES, blocked_tools_for_mode
from tools.registry import ToolRegistry
from tools.native_tools import ReadFileTool, WriteFileTool, ShellTool
from tools.todo_tool import TodoTool
from tools.web_tools import WebSearchTool, WebFetchTool
from tools.advisor_tool import AdvisorTool
from tools.memory_tool import MemoryTool


def test_modes_blocked_tools():
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ShellTool())
    registry.register(TodoTool())
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())
    registry.register(AdvisorTool(None))
    registry.register(MemoryTool())

    # Build Mode: No blocked tools
    assert len(blocked_tools_for_mode("build", registry)) == 0

    # Plan Mode: Blocks mutating tools (write_file, shell, delegate_task)
    plan_blocked = blocked_tools_for_mode("plan", registry)
    assert "write_file" in plan_blocked
    assert "shell" in plan_blocked
    assert "read_file" not in plan_blocked

    # Chat Mode: Permits ONLY allowed_tools (web_search, web_fetch, calculator, consult_advisor, memory)
    chat_blocked = blocked_tools_for_mode("chat", registry)
    assert "read_file" in chat_blocked
    assert "write_file" in chat_blocked
    assert "shell" in chat_blocked
    assert "todo" in chat_blocked
    assert "web_search" not in chat_blocked
    assert "web_fetch" not in chat_blocked
    assert "consult_advisor" not in chat_blocked
    assert "memory" not in chat_blocked
