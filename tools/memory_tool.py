import json
import os
from typing import Dict, Any
from tools.base import BaseTool
import memory_search

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
    description = (
        "Saves, retrieves, lists, searches, or deletes persistent memory key-value pairs "
        "across sessions. Use 'get' when you know the exact key. Use 'search' when you "
        "don't know the exact key and want to recall something by meaning - e.g. 'what CI "
        "system does this project use' will find a key like ci_provider even without "
        "sharing any words with it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "get", "list", "search", "delete"],
                "description": "Action to perform on persistent memory."
            },
            "key": {
                "type": "string",
                "description": "Memory key name (required for save, get, delete)."
            },
            "value": {
                "type": "string",
                "description": "Value to store (required for save)."
            },
            "query": {
                "type": "string",
                "description": "Natural-language description of what you're trying to recall (required for 'search')."
            }
        },
        "required": ["action"]
    }

    def __init__(self, config_mgr=None):
        # config_mgr is only needed for the 'search' action, which runs a
        # small dedicated sub-agent call (see memory_search.py) rather than
        # an embedding/cosine-similarity index.
        self._config_mgr = config_mgr

    async def execute(self, action: str, key: str = "", value: str = "", query: str = "") -> Dict[str, Any]:
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

        elif action_lower == "search":
            if not query:
                return {"error": "Query is required for search action."}
            if self._config_mgr is None:
                return {"error": "Semantic search is unavailable: memory tool was not given a config manager."}
            return await memory_search.semantic_memory_search(query, mem, self._config_mgr)

        elif action_lower == "delete":
            if not key:
                return {"error": "Key is required for delete action."}
            if key in mem:
                del mem[key]
                _save_memory(mem)
                return {"status": "success", "message": f"Deleted memory key '{key}'."}
            return {"error": f"Memory key '{key}' not found."}

        else:
            return {"error": f"Invalid action '{action}'. Use save, get, list, search, or delete."}