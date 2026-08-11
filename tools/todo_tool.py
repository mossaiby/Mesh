from typing import Dict, Any, List
from tools.base import BaseTool
from theme import console


class TodoTool(BaseTool):
    name = "todo"
    description = (
        "Manages a dependency-aware TODO list during multi-step task execution. "
        "Tasks can declare which other tasks must finish first via depends_on, "
        "so independent branches of work can be tracked and identified separately "
        "from work that's still blocked."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "complete", "clear", "display", "next"],
                "description": (
                    "Action to perform on TODO list. 'list' returns the raw TODO "
                    "data to you (the model) as JSON for your own reasoning. "
                    "'display' renders the current TODO list directly to the user "
                    "in the terminal - use this whenever the user asks to see "
                    "their TODOs/progress, or after meaningful plan changes. "
                    "'next' returns only the tasks that are ready to start right "
                    "now (not completed, and all of their dependencies are already "
                    "completed) - use this to decide what to work on next, or to "
                    "identify independent branches that could be tackled in parallel."
                )
            },
            "task": {
                "type": "string",
                "description": "Task description (required for 'add')."
            },
            "task_id": {
                "type": "integer",
                "description": "Task ID (1-based index, required for 'complete')."
            },
            "depends_on": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Optional list of existing task IDs that must be completed "
                    "before this new task can start (used with 'add'). Every ID "
                    "must already exist - only depend on tasks added earlier."
                )
            }
        },
        "required": ["action"]
    }

    def __init__(self):
        self._todos: List[Dict[str, Any]] = []

    def _is_ready(self, item: Dict[str, Any]) -> bool:
        """A task is ready when it isn't done yet and every task it depends on is."""
        if item["completed"]:
            return False
        done_ids = {t["id"] for t in self._todos if t["completed"]}
        return all(dep_id in done_ids for dep_id in item["depends_on"])

    def _blocking_deps(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Returns the not-yet-completed tasks that are blocking `item`."""
        by_id = {t["id"]: t for t in self._todos}
        return [by_id[dep_id] for dep_id in item["depends_on"] if dep_id in by_id and not by_id[dep_id]["completed"]]

    def _status(self, item: Dict[str, Any]) -> str:
        if item["completed"]:
            return "done"
        return "ready" if self._is_ready(item) else "blocked"

    def _render(self) -> None:
        """Print the current TODO list to the user via the shared themed console."""
        if not self._todos:
            console.print("[muted]TODO list is empty.[/muted]")
            return

        console.print("\n[label]TODO List:[/label]")
        for item in self._todos:
            status = self._status(item)
            deps_str = f" [dim](depends on: {', '.join(str(d) for d in item['depends_on'])})[/dim]" if item["depends_on"] else ""

            if status == "done":
                console.print(f"  [success]✔[/success] [muted]{item['id']}. {item['task']}[/muted]{deps_str}")
            elif status == "ready":
                console.print(f"  [warning]▶[/warning] [text]{item['id']}. {item['task']}[/text]{deps_str}")
            else:
                blockers = self._blocking_deps(item)
                blocked_by = ", ".join(f"#{b['id']}" for b in blockers)
                console.print(f"  [error]⏳[/error] [dim]{item['id']}. {item['task']} — blocked by {blocked_by}[/dim]")

        total = len(self._todos)
        done = sum(1 for i in self._todos if i["completed"])
        console.print(f"[accent]{done}/{total} complete[/accent]\n")

    async def execute(
        self,
        action: str,
        task: str = "",
        task_id: int = 0,
        depends_on: List[int] = None
    ) -> Dict[str, Any]:
        action_lower = action.lower()
        depends_on = depends_on or []

        if action_lower == "add":
            if not task:
                return {"error": "Task description is required for 'add'."}

            existing_ids = {t["id"] for t in self._todos}
            missing = [dep_id for dep_id in depends_on if dep_id not in existing_ids]
            if missing:
                return {
                    "error": (
                        f"Cannot add task: depends_on references unknown task ID(s) {missing}. "
                        "A task can only depend on IDs that already exist (this also guarantees "
                        "the dependency graph can never contain a cycle)."
                    )
                }

            item = {
                "id": len(self._todos) + 1,
                "task": task,
                "completed": False,
                "depends_on": sorted(set(depends_on))
            }
            self._todos.append(item)
            return {"status": "added", "task": item}

        elif action_lower == "list":
            return {"todos": [dict(t, status=self._status(t)) for t in self._todos]}

        elif action_lower == "display":
            self._render()
            return {"status": "displayed", "todos": [dict(t, status=self._status(t)) for t in self._todos]}

        elif action_lower == "next":
            ready = [dict(t, status="ready") for t in self._todos if self._is_ready(t)]
            if not ready:
                remaining = [t for t in self._todos if not t["completed"]]
                if not remaining:
                    return {"status": "all_complete", "ready_tasks": []}
                return {"status": "all_blocked", "ready_tasks": [], "remaining": remaining}
            return {"status": "ok", "ready_tasks": ready}

        elif action_lower == "complete":
            if task_id <= 0 or task_id > len(self._todos):
                return {"error": f"Invalid task_id {task_id}. Current TODO count: {len(self._todos)}"}

            item = self._todos[task_id - 1]
            blockers = self._blocking_deps(item)
            if blockers:
                blocker_desc = [f"#{b['id']} ({b['task']})" for b in blockers]
                return {
                    "error": (
                        f"Cannot complete task #{task_id}: it depends on unfinished task(s) "
                        f"{', '.join(blocker_desc)}. Complete those first."
                    )
                }

            item["completed"] = True
            return {"status": "completed", "task": item}

        elif action_lower == "clear":
            self._todos.clear()
            return {"status": "cleared", "message": "TODO list cleared."}

        else:
            return {"error": f"Invalid action '{action}'."}