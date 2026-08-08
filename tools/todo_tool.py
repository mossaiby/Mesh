from typing import Dict, Any, List
from tools.base import BaseTool


class TodoTool(BaseTool):
    name = "todo_manager"
    description = "Manages a TODO list during multi-step task execution."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "complete", "clear"],
                "description": "Action to perform on TODO list."
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