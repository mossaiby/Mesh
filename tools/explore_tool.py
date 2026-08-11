from typing import Dict, Any, List, Optional
from tools.base import BaseTool
import explore


class ExploreTool(BaseTool):
    name = "explore_branches"
    description = (
        "Runs speculative parallel branch search for complex or ambiguous problems. "
        "Dynamically generates N distinct task strategies, executes sub-agent swarms "
        "in parallel, evaluates their results, and synthesizes the winning solution."
    )
    is_proxied = False
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The complex task or problem description to explore in parallel."
            },
            "num_branches": {
                "type": "integer",
                "description": "Number of parallel strategy branches to generate and explore (2 to 5, default: 3)."
            },
            "strategies": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional explicit list of strategy prompts. If omitted, strategies are generated dynamically by the LLM."
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

    async def execute(
        self,
        task: str,
        num_branches: int = 3,
        strategies: Optional[List[str]] = None,
        max_turns: int = 6
    ) -> Dict[str, Any]:
        debug_mode = getattr(self._tool_registry.subagent_proxy, "debug_mode", False)
        return await explore.explore_branches(
            task=task,
            strategies=strategies,
            tool_registry=self._tool_registry,
            config_mgr=self._config_mgr,
            num_branches=num_branches,
            max_turns=max_turns,
            debug_mode=debug_mode
        )