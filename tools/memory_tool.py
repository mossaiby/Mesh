import json
import os
from typing import Dict, Any
from tools.base import BaseTool

MEMORY_FILE = "memory.json"


def _load_memory() -> Dict[str, Any]:
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_memory(data: Dict[str, Any]) -> None:
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class MemoryTool(BaseTool):
    name = "memory"
    description = "Saves, retrieves, lists, or deletes persistent memory key-value pairs across sessions."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "get", "list", "delete"],
                "description": "Action to perform on persistent memory."
            },
            "key": {
                "type": "string",
                "description": "Memory key name (required for save, get, delete)."
            },
            "value": {
                "type": "string",
                "description": "Value to store (required for save)."
            }
        },
        "required": ["action"]
    }

    async def execute(self, action: str, key: str = "", value: str = "") -> Dict[str, Any]:
        mem = _load_memory()
        action_lower = action.lower()

        if action_lower == "save":
            if not key:
                return {"error": "Key is required for save action."}
            mem[key] = value
            _save_memory(mem)
            return {"status": "success", "message": f"Saved memory key '{key}'."}

        elif action_lower == "get":
            if not key:
                return {"error": "Key is required for get action."}
            if key in mem:
                return {"key": key, "value": mem[key]}
            return {"error": f"Memory key '{key}' not found."}

        elif action_lower == "list":
            return {"memories": mem}

        elif action_lower == "delete":
            if not key:
                return {"error": "Key is required for delete action."}
            if key in mem:
                del mem[key]
                _save_memory(mem)
                return {"status": "success", "message": f"Deleted memory key '{key}'."}
            return {"error": f"Memory key '{key}' not found."}

        else:
            return {"error": f"Invalid action '{action}'. Use save, get, list, or delete."}