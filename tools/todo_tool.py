from typing import Dict, Any, List
from tools.base import BaseTool
from theme import console


class TodoTool(BaseTool):
    name = "todo_manager"
    description = "Manages a TODO list during multi-step task execution."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "complete", "clear", "display"],
                "description": (
                    "Action to perform on TODO list. 'list' returns the raw TODO "
                    "data to you (the model) as JSON for your own reasoning. "
                    "'display' renders the current TODO list directly to the user "
                    "in the terminal - use this whenever the user asks to see "
                    "their TODOs/progress, or after meaningful plan changes."
                )
            },
            "task": {
                "type": "string",
                "description": "Task description (required for 'add')."
            },
            "task_id": {
                "type": "integer",
                "description": "Task ID (1-based index, required for 'complete')."
            }
        },
        "required": ["action"]
    }

    def __init__(self):
        self._todos: List[Dict[str, Any]] = []

    def _render(self) -> None:
        """Print the current TODO list to the user via the shared themed console."""
        if not self._todos:
            console.print("[muted]TODO list is empty.[/muted]")
            return

        console.print("\n[label]TODO List:[/label]")
        for item in self._todos:
            if item["completed"]:
                console.print(f"  [success]✔[/success] [muted]{item['id']}. {item['task']}[/muted]")
            else:
                console.print(f"  [warning]○[/warning] [text]{item['id']}. {item['task']}[/text]")

        total = len(self._todos)
        done = sum(1 for i in self._todos if i["completed"])
        console.print(f"[accent]{done}/{total} complete[/accent]\n")

    async def execute(self, action: str, task: str = "", task_id: int = 0) -> Dict[str, Any]:
        action_lower = action.lower()

        if action_lower == "add":
            if not task:
                return {"error": "Task description is required for 'add'."}
            item = {"id": len(self._todos) + 1, "task": task, "completed": False}
            self._todos.append(item)
            return {"status": "added", "task": item}

        elif action_lower == "list":
            return {"todos": self._todos}

        elif action_lower == "display":
            self._render()
            return {"status": "displayed", "todos": self._todos}

        elif action_lower == "complete":
            if task_id <= 0 or task_id > len(self._todos):
                return {"error": f"Invalid task_id {task_id}. Current TODO count: {len(self._todos)}"}
            self._todos[task_id - 1]["completed"] = True
            return {"status": "completed", "task": self._todos[task_id - 1]}

        elif action_lower == "clear":
            self._todos.clear()
            return {"status": "cleared", "message": "TODO list cleared."}

        else:
            return {"error": f"Invalid action '{action}'."}