import copy
from typing import Dict, Any, List, Optional
from tools.note_tool import _read_notes, _write_notes
from tools.memory_tool import _load_memory, _save_memory
from theme import console


class CheckpointManager:
    """
    Manages complete snapshots of conversation state, goal state,
    todo graph, notes, memory, and operating mode for branching and rollback.
    """
    def __init__(self):
        self.checkpoints: Dict[str, Dict[str, Any]] = {}
        self.active_branch: str = "main"

    def create_snapshot(
        self,
        tag: str,
        mesh_instance: Any
    ) -> Dict[str, Any]:
        """Captures a complete deep-copy snapshot of Mesh's active state."""
        goal_snap = mesh_instance.goal_tool.snapshot() if hasattr(mesh_instance, "goal_tool") else {}
        
        # Access internal todos list safely
        todo_tool = mesh_instance.tool_registry._tools.get("todo_manager")
        todos_snap = copy.deepcopy(todo_tool._todos) if todo_tool and hasattr(todo_tool, "_todos") else []

        snapshot = {
            "tag": tag,
            "branch": self.active_branch,
            "messages": copy.deepcopy(mesh_instance.messages),
            "goal": copy.deepcopy(goal_snap),
            "todos": todos_snap,
            "notes": _read_notes(),
            "memory": _load_memory(),
            "current_mode": getattr(mesh_instance, "current_mode", "build"),
            "tools_enabled": mesh_instance.tools_enabled,
            "debug_mode": mesh_instance.debug_mode
        }

        self.checkpoints[tag] = snapshot
        return snapshot

    def restore_snapshot(
        self,
        tag: str,
        mesh_instance: Any
    ) -> bool:
        """Restores Mesh's state from a saved snapshot tag."""
        if tag not in self.checkpoints:
            return False

        snap = self.checkpoints[tag]

        # Restore messages
        mesh_instance.messages = copy.deepcopy(snap["messages"])

        # Restore goal
        if hasattr(mesh_instance, "goal_tool") and snap.get("goal"):
            g = snap["goal"]
            mesh_instance.goal_tool._goal = g.get("goal")
            mesh_instance.goal_tool._criteria = copy.deepcopy(g.get("success_criteria", []))
            mesh_instance.goal_tool._notify()

        # Restore todo manager
        todo_tool = mesh_instance.tool_registry._tools.get("todo_manager")
        if todo_tool and hasattr(todo_tool, "_todos"):
            todo_tool._todos = copy.deepcopy(snap["todos"])

        # Restore notes and memory files
        _write_notes(snap["notes"])
        _save_memory(snap["memory"])

        # Restore modes and settings
        mesh_instance.current_mode = snap.get("current_mode", "build")
        mesh_instance.tools_enabled = snap.get("tools_enabled", True)
        mesh_instance.debug_mode = snap.get("debug_mode", False)

        mesh_instance.tool_registry.mode_blocked_tools = (
            __import__("modes").blocked_tools_for_mode(mesh_instance.current_mode, mesh_instance.tool_registry)
        )
        mesh_instance.update_system_message()

        self.active_branch = snap.get("branch", tag)
        return True

    def list_checkpoints(self) -> Dict[str, Any]:
        """Lists all saved checkpoints and current branch info."""
        return {
            "active_branch": self.active_branch,
            "checkpoints": {
                tag: {
                    "branch": snap["branch"],
                    "messages_count": len(snap["messages"]),
                    "mode": snap["current_mode"],
                    "has_goal": snap["goal"].get("goal") is not None
                }
                for tag, snap in self.checkpoints.items()
            }
        }