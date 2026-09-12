import json
import os
from typing import Dict, Any
from tools.base import BaseTool
from config import APP_ROOT
import memory_search

MEMORY_FILE = os.path.join(APP_ROOT, "memory.json")


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
        "sharing any words with it.\n\n"
        "'search' has two engines, chosen with the 'method' parameter:\n"
        "- 'embedding' (local, instant, free): word/character overlap over the store, computed "
        "in-process with no model call. Good for most lookups and for large stores, but purely "
        "lexical - it won't connect a query to a memory that shares no words or word-fragments "
        "with it (e.g. it won't match 'continuous integration tool' to a key/value about "
        "'GitHub Actions').\n"
        "- 'llm' (a real model call): understands paraphrases and synonyms with no lexical "
        "overlap at all, at the cost of latency and tokens, and it stops scaling once the "
        "store is too large to fit in one prompt.\n"
        "- 'auto' (default): tries 'embedding' first; if that comes back empty, automatically "
        "falls back to 'llm'. Override explicitly with 'embedding' to save tokens on a query "
        "you expect to be lexically close to the stored key/value, or with 'llm' directly if "
        "the query is a heavy paraphrase or the store is small enough that the cost doesn't "
        "matter."
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
            },
            "method": {
                "type": "string",
                "enum": ["auto", "embedding", "llm"],
                "description": "Search engine to use for 'search' (default: 'auto'). See the tool description for the trade-offs between 'embedding' (local, instant, lexical) and 'llm' (a model call, understands paraphrases). 'auto' tries embedding first and falls back to llm if nothing is found."
            }
        },
        "required": ["action"]
    }

    def __init__(self, config_mgr=None):
        # config_mgr is only needed for the 'search' action's 'llm' engine
        # (see memory_search.py); the 'embedding' engine (local_search.py)
        # needs no provider/config at all.
        self._config_mgr = config_mgr

    def is_read_only(self, action: str = "", **kwargs) -> bool:
        return str(action).lower() in ("get", "list", "search")

    async def execute(self, action: str, key: str = "", value: str = "", query: str = "", method: str = "auto") -> Dict[str, Any]:
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

            method_lower = (method or "auto").lower()
            if method_lower not in ("auto", "embedding", "llm"):
                return {"error": f"Invalid method '{method}'. Use auto, embedding, or llm."}

            if method_lower in ("embedding", "auto"):
                local_result = memory_search.local_memory_search(query, mem)
                if method_lower == "embedding" or local_result.get("matches"):
                    return local_result
                # 'auto' and the local pass came back empty - fall through to the LLM engine below.

            if self._config_mgr is None:
                return {"error": "The 'llm' search method is unavailable: memory tool was not given a config manager."}
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
