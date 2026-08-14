from typing import Dict, Any, List, Optional, Callable
from tools.base import BaseTool


class GoalTool(BaseTool):
    """
    Tracks a single pinned session objective, separate from todo's
    step-by-step task list: a goal is the *why* ("ship a working CLI export
    feature"), while todos are the *how* (the individual steps to get there).
    success_criteria define what "done" actually looks like.

    Unlike todo, this isn't just a tool the model calls - once set,
    the goal (and remaining/completed criteria) is folded directly into the
    system prompt via the on_change callback, so it stays visible to the
    model even after /compact summarizes the conversation, after /switch
    changes models, or after /clear wipes the chat history. A todo list or
    an ordinary chat message would not survive any of those; a pinned goal
    does, by design.
    """

    name = "goal"
    description = (
        "Tracks a single pinned session objective (the overall 'why', as opposed to "
        "todo's step-by-step 'how'), with optional success criteria defining "
        "what 'done' looks like. Once set, the goal stays visible to you in the system "
        "prompt even after the conversation is compacted, the model is switched, or the "
        "chat is cleared - use it to anchor long sessions on what actually matters."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["set", "get", "display", "complete_criterion", "clear"],
                "description": (
                    "Action to perform. 'set' replaces any existing goal. 'get' returns "
                    "the raw goal data as JSON for your own reasoning. 'display' renders "
                    "the goal and its criteria directly to the user in the terminal. "
                    "'complete_criterion' marks one success criterion as met. 'clear' "
                    "removes the current goal entirely."
                )
            },
            "goal": {
                "type": "string",
                "description": "The objective statement (required for 'set')."
            },
            "success_criteria": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of concrete conditions that define 'done' (used with 'set')."
            },
            "criterion_index": {
                "type": "integer",
                "description": "1-based index of the success criterion to mark complete (required for 'complete_criterion')."
            }
        },
        "required": ["action"]
    }
    is_proxied = False  # Small, structured state - no benefit to distillation.

    def __init__(self, on_change: Optional[Callable[[], None]] = None):
        self._on_change = on_change
        self._goal: Optional[str] = None
        self._criteria: List[Dict[str, Any]] = []

    def has_goal(self) -> bool:
        return self._goal is not None

    def as_system_prompt_section(self) -> str:
        """Renders the current goal (if any) as a Markdown section suitable
        for appending to the system prompt. Returns '' when no goal is set."""
        if not self._goal:
            return ""

        lines = [f"## Current Goal\n{self._goal}"]
        if self._criteria:
            lines.append("\nSuccess criteria:")
            for c in self._criteria:
                mark = "[x]" if c["done"] else "[ ]"
                lines.append(f"- {mark} {c['text']}")
        return "\n".join(lines)

    def snapshot(self) -> Dict[str, Any]:
        """Public accessor for the current goal state, for callers like /status
        that want the data without going through execute()."""
        return self._snapshot()

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "goal": self._goal,
            "success_criteria": self._criteria,
            "criteria_complete": sum(1 for c in self._criteria if c["done"]),
            "criteria_total": len(self._criteria)
        }

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

    def render(self, console) -> None:
        """Prints the current goal to the user via the given themed console."""
        if not self._goal:
            console.print("[muted]No goal is currently set.[/muted]")
            return

        console.print(f"\n[label]Current Goal:[/label] {self._goal}")
        if self._criteria:
            console.print("[label]Success Criteria:[/label]")
            for i, c in enumerate(self._criteria, 1):
                if c["done"]:
                    console.print(f"  [success]✔[/success] [muted]{i}. {c['text']}[/muted]")
                else:
                    console.print(f"  [warning]○[/warning] [text]{i}. {c['text']}[/text]")
            done = sum(1 for c in self._criteria if c["done"])
            console.print(f"[accent]{done}/{len(self._criteria)} criteria met[/accent]\n")
        else:
            console.print()

    async def execute(
        self,
        action: str,
        goal: str = "",
        success_criteria: List[str] = None,
        criterion_index: int = 0
    ) -> Dict[str, Any]:
        action_lower = action.lower()
        success_criteria = success_criteria or []

        if action_lower == "set":
            if not goal or not goal.strip():
                return {"error": "A non-empty 'goal' is required for 'set'."}

            self._goal = goal.strip()
            self._criteria = [{"text": c.strip(), "done": False} for c in success_criteria if c and c.strip()]
            self._notify()
            return {"status": "set", **self._snapshot()}

        elif action_lower == "get":
            if not self._goal:
                return {"status": "no_goal"}
            return {"status": "ok", **self._snapshot()}

        elif action_lower == "display":
            return {"status": "displayed", **self._snapshot()}

        elif action_lower == "complete_criterion":
            if not self._goal:
                return {"error": "No goal is currently set."}
            try:
                criterion_index = int(criterion_index)
            except (ValueError, TypeError):
                return {"error": f"Invalid criterion_index '{criterion_index}'. Must be an integer."}

            if criterion_index <= 0 or criterion_index > len(self._criteria):
                return {"error": f"Invalid criterion_index {criterion_index}. Current criteria count: {len(self._criteria)}"}
            self._criteria[criterion_index - 1]["done"] = True
            self._notify()
            return {"status": "criterion_completed", **self._snapshot()}

        elif action_lower == "clear":
            had_goal = self._goal is not None
            self._goal = None
            self._criteria = []
            self._notify()
            return {"status": "cleared" if had_goal else "no_goal_to_clear"}

        else:
            return {"error": f"Invalid action '{action}'."}
