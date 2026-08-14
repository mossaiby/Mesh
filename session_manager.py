import os
import json
import time
import copy
from typing import Dict, Any, List, Optional, Tuple
from tools.note_tool import _read_notes, _write_notes
from tools.memory_tool import _load_memory, _save_memory


SESSIONS_DIR = "sessions"


def _ensure_sessions_dir() -> str:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return SESSIONS_DIR


class SessionManager:
    """
    Manages disk-backed session save, resume, list, and delete operations under sessions/.
    Persists messages, goal, todos, notes, memory, active mode, checkpoints, and token metrics.
    """

    def __init__(self, engine_instance: Any):
        self.engine = engine_instance
        self.active_session_name: Optional[str] = None

    def save_session(self, name: Optional[str] = None) -> Tuple[bool, str]:
        session_name = name or self.active_session_name or f"session_{time.strftime('%Y%m%d_%H%M%S')}"
        clean_name = "".join(c for c in session_name if c.isalnum() or c in ("-", "_")).strip()
        if not clean_name:
            clean_name = f"session_{time.strftime('%Y%m%d_%H%M%S')}"

        dir_path = _ensure_sessions_dir()
        filepath = os.path.join(dir_path, f"{clean_name}.json")

        goal_snap = self.engine.goal_tool.snapshot() if hasattr(self.engine, "goal_tool") else {}
        todo_tool = self.engine.tool_registry._tools.get("todo")
        todos_snap = copy.deepcopy(todo_tool._todos) if todo_tool and hasattr(todo_tool, "_todos") else []

        session_data = {
            "session_name": clean_name,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "active_branch": self.engine.checkpoint_mgr.active_branch,
            "current_mode": getattr(self.engine, "current_mode", "build"),
            "active_model": self.engine.config_mgr.config.active_model,
            "tools_enabled": self.engine.tools_enabled,
            "debug_mode": self.engine.debug_mode,
            "session_metrics": {
                "prompt_tokens": self.engine.session_prompt_tokens,
                "completion_tokens": self.engine.session_completion_tokens,
                "cached_tokens": getattr(self.engine, "session_cached_tokens", 0),
                "cost_usd": self.engine.session_cost_usd,
            },
            "goal": copy.deepcopy(goal_snap),
            "todos": todos_snap,
            "notes": _read_notes(),
            "memory": _load_memory(),
            "messages": copy.deepcopy(self.engine.messages),
            "checkpoints": copy.deepcopy(self.engine.checkpoint_mgr.checkpoints)
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)

            self.active_session_name = clean_name
            return True, f"Saved session '[accent]{clean_name}[/accent]' to `{filepath}`."
        except Exception as e:
            return False, f"Failed to save session: {e}"

    def load_session(self, name: str) -> Tuple[bool, str]:
        clean_name = name.removesuffix(".json")
        filepath = os.path.join(SESSIONS_DIR, f"{clean_name}.json")

        if not os.path.exists(filepath):
            return False, f"Session file '{filepath}' does not exist."

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 1. Restore messages
            self.engine.messages = copy.deepcopy(data.get("messages", []))

            # 2. Restore goal
            if hasattr(self.engine, "goal_tool") and data.get("goal"):
                g = data["goal"]
                self.engine.goal_tool._goal = g.get("goal")
                self.engine.goal_tool._criteria = copy.deepcopy(g.get("success_criteria", []))
                self.engine.goal_tool._notify()

            # 3. Restore todo manager
            todo_tool = self.engine.tool_registry._tools.get("todo")
            if todo_tool and hasattr(todo_tool, "_todos"):
                todo_tool._todos = copy.deepcopy(data.get("todos", []))

            # 4. Restore notes and memory
            if "notes" in data:
                _write_notes(data["notes"])
            if "memory" in data:
                _save_memory(data["memory"])

            # 5. Restore checkpoints and branch
            self.engine.checkpoint_mgr.checkpoints = copy.deepcopy(data.get("checkpoints", {}))
            self.engine.checkpoint_mgr.active_branch = data.get("active_branch", "main")

            # 6. Restore modes & models
            mode = data.get("current_mode", "build")
            self.engine.current_mode = mode
            self.engine.tools_enabled = data.get("tools_enabled", True)
            self.engine.debug_mode = data.get("debug_mode", False)

            if "active_model" in data and data["active_model"] in self.engine.config_mgr.config.models or data.get("active_model") == "auto":
                try:
                    self.engine.config_mgr.set_active_model(data["active_model"])
                except Exception:
                    pass

            # 7. Restore metrics
            metrics = data.get("session_metrics", {})
            self.engine.session_prompt_tokens = metrics.get("prompt_tokens", 0)
            self.engine.session_completion_tokens = metrics.get("completion_tokens", 0)
            self.engine.session_cached_tokens = metrics.get("cached_tokens", 0)
            self.engine.session_cost_usd = metrics.get("cost_usd", 0.0)

            self.engine.tool_registry.mode_blocked_tools = (
                __import__("modes").blocked_tools_for_mode(self.engine.current_mode, self.engine.tool_registry)
            )
            self.engine.update_system_message()

            self.active_session_name = clean_name
            return True, f"Loaded session '[accent]{clean_name}[/accent]' ({len(self.engine.messages)} messages restored)."
        except Exception as e:
            return False, f"Failed to load session: {e}"

    def list_sessions(self) -> List[Dict[str, Any]]:
        dir_path = _ensure_sessions_dir()
        sessions = []
        for file in os.listdir(dir_path):
            if file.endswith(".json"):
                path = os.path.join(dir_path, file)
                try:
                    mtime = os.path.getmtime(path)
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    sessions.append({
                        "name": file[:-5],
                        "saved_at": data.get("saved_at", time.ctime(mtime)),
                        "messages_count": len(data.get("messages", [])),
                        "mode": data.get("current_mode", "build"),
                        "model": data.get("active_model", "unknown"),
                        "mtime": mtime
                    })
                except Exception:
                    pass

        sessions.sort(key=lambda s: s["mtime"], reverse=True)
        return sessions

    def get_latest_session_name(self) -> Optional[str]:
        sessions = self.list_sessions()
        return sessions[0]["name"] if sessions else None

    def delete_session(self, name: str) -> Tuple[bool, str]:
        clean_name = name.removesuffix(".json")
        filepath = os.path.join(SESSIONS_DIR, f"{clean_name}.json")
        if not os.path.exists(filepath):
            return False, f"Session file '{filepath}' not found."
        try:
            os.remove(filepath)
            if self.active_session_name == clean_name:
                self.active_session_name = None
            return True, f"Deleted session file '{clean_name}'."
        except Exception as e:
            return False, f"Failed to delete session: {e}"
