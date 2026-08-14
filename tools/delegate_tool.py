from typing import Dict, Any
from tools.base import BaseTool
import delegation


class DelegateTaskTool(BaseTool):
    name = "delegate_task"
    description = (
        "Delegates a self-contained task to an autonomous sub-agent that runs its own "
        "multi-step tool loop (it can read/write files, run shell commands, search the "
        "web, manage notes/memory, etc.) and reports back a single final summary. Use "
        "this for tasks whose intermediate steps you don't need to see one-by-one - e.g. "
        "'investigate why the build is failing and report what's wrong', or 'find and "
        "summarize every TODO comment in this repo'. Do NOT use it for tasks that need "
        "the user's input mid-way (the sub-agent cannot ask questions), or for trivial "
        "single-step actions that are just as easy to do directly. If a task genuinely "
        "splits into independent sub-tasks, the sub-agent may itself delegate those "
        "further (up to a configured recursion depth) - calling delegate_task several "
        "times in one turn runs those sub-tasks in parallel rather than one at a time."
    )
    is_proxied = False  # This tool manages its own tool loop and returns a final
                         # summary already; it should not also be routed through
                         # SubAgentProxy distillation.
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "A clear, self-contained description of the task for the sub-agent "
                    "to complete. Include all context it needs - it cannot ask you or "
                    "the user follow-up questions."
                )
            },
            "max_turns": {
                "type": "integer",
                "description": (
                    "Maximum number of tool-call turns the sub-agent may take before "
                    "giving up (default 6, hard cap 10). The effective cap tapers down "
                    "automatically at deeper recursion levels."
                )
            }
        },
        "required": ["task"]
    }

    def __init__(self, tool_registry, config_mgr):
        # References to the live registry/config rather than copies, so the
        # sub-agent always sees the current tool set and active model.
        self._tool_registry = tool_registry
        self._config_mgr = config_mgr

    def is_read_only(self, **kwargs) -> bool:
        return False

    async def execute(self, task: str, max_turns: int = 6) -> Dict[str, Any]:
        try:
            max_turns = int(max_turns)
        except (TypeError, ValueError):
            max_turns = 6
        max_turns = max(1, min(max_turns, delegation.HARD_MAX_TURNS_CAP))

        # The current depth is read from context, not passed as a visible
        # parameter, since this same tool instance is shared by every level
        # of delegation - each nested call needs to know how deep *it* is
        # being invoked from right now (see CURRENT_DELEGATION_DEPTH).
        current_depth = delegation.CURRENT_DELEGATION_DEPTH.get()
        child_depth = current_depth + 1

        max_depth = getattr(self._config_mgr.config, "max_delegation_depth", 2)
        if child_depth > max_depth:
            # Defensive: shouldn't normally be reachable, since delegate_task
            # is excluded from a sub-agent's own schema once it's at the
            # deepest allowed level - but guard against it directly in case
            # of a future direct call that bypasses schema-based exclusion.
            return {
                "error": (
                    f"Maximum delegation depth ({max_depth}) reached - cannot delegate "
                    f"further from depth {current_depth}. Complete this task directly instead."
                )
            }

        max_turns = delegation.max_turns_for_depth(max_turns, child_depth)

        return await delegation.run_delegated_task(
            task=task,
            tool_registry=self._tool_registry,
            config_mgr=self._config_mgr,
            max_turns=max_turns,
            depth=child_depth,
            max_depth=max_depth,
        )
