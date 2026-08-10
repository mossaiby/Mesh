from typing import Dict, Any, List, Optional
from tools.base import BaseTool
import explore


class ExploreTool(BaseTool):
    name = "explore_branches"
    description = (
        "Runs speculative parallel branch search for complex or ambiguous problems. "
        "Spawns parallel sub-agents with distinct strategies, evaluates their results, "
        "and synthesizes the winning solution."
    )
    is_proxied = False
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The complex task or problem description to explore in parallel."
            },
            "strategies": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of distinct strategy prompts to explore (defaults to 3 auto-generated approaches)."
            },
            "max_turns": {
                "type": "integer",
                "description": "Maximum tool turns per sub-agent branch (default: 6)."
            }
        },
        "required": ["task"]
    }

    def __init__(self, tool_registry, config_mgr):
        self._tool_registry = tool_registry
        self._config_mgr = config_mgr

    async def execute(self, task: str, strategies: Optional[List[str]] = None, max_turns: int = 6) -> Dict[str, Any]:
        return await explore.explore_branches(
            task=task,
            strategies=strategies,
            tool_registry=self._tool_registry,
            config_mgr=self._config_mgr,
            max_turns=max_turns
        )