import os
from typing import Dict, Any
from tools.base import BaseTool

NOTES_FILE = "notes.md"


def _read_notes() -> str:
    if not os.path.exists(NOTES_FILE):
        return ""
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _write_notes(content: str) -> None:
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def _append_notes(content: str) -> None:
    existing = _read_notes()
    separator = "\n\n" if existing and not existing.endswith("\n\n") else ""
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(separator + content)


class NoteTool(BaseTool):
    name = "note"
    description = "Keeps, updates, appends to, or reads persistent project/session notes in Markdown format."
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "append", "clear"],
                "description": "Action to perform on the Markdown notes file (notes.md)."
            },
            "content": {
                "type": "string",
                "description": "Markdown content to write or append (required for 'write' and 'append')."
            }
        },
        "required": ["action"]
    }

    async def execute(self, action: str, content: str = "") -> Dict[str, Any]:
        action_lower = action.lower()

        if action_lower == "read":
            notes = _read_notes()
            return {"notes": notes if notes else "<notes.md is empty>"}

        elif action_lower == "write":
            _write_notes(content)
            return {"status": "success", "message": "Updated notes.md with new content."}

        elif action_lower == "append":
            if not content:
                return {"error": "Content is required for 'append' action."}
            _append_notes(content)
            return {"status": "success", "message": "Appended content to notes.md."}

        elif action_lower == "clear":
            _write_notes("")
            return {"status": "success", "message": "Cleared notes.md."}

        else:
            return {"error": f"Invalid action '{action}'. Use read, write, append, or clear."}