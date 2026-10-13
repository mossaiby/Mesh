import uuid
from typing import Dict, Any, Optional
from tools.base import BaseTool


class WaitForEventTool(BaseTool):
    """Deliberately minimal: execute() just returns the correctly-shaped
    {"status": "pending", ...} dict. Registering it with the event registry
    (and starting a file watcher if watch_file was given) happens
    generically in tools/registry.py for ANY tool returning this shape.
    This tool gives the model an explicit, self-describing way to reach
    for that mechanism."""

    name = "wait_for_event"
    description = (
        "Ends your turn waiting on something that happens OUTSIDE this conversation - "
        "an MCP server asking the user to finish an OAuth flow in their browser, a build "
        "or long-running process finishing, or anything else external you need before "
        "continuing. Call this, tell the user what they need to do in your reply (not just "
        "in this tool call), and then stop - do not call another tool or keep talking this "
        "turn. You will be automatically resumed with a message describing what happened as "
        "soon as the event fires (via /resume, an automatic file watcher if you provided "
        "watch_file, or anything else that triggers it) - the user does not need to say "
        "'continue'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "What you're waiting for, in plain language - shown to the user now and to you again when you resume."
            },
            "event_id": {
                "type": "string",
                "description": "A short, stable identifier for this wait (e.g. 'oauth-callback'). Auto-generated if omitted; provide your own if the user might need to reference it, e.g. to run /resume <event_id>."
            },
            "watch_file": {
                "type": "string",
                "description": "Optional absolute path. If given, Mesh automatically resumes this wait the moment the path exists, with no manual /resume needed - use whenever the external process can plausibly write a marker/output file when it finishes."
            }
        },
        "required": ["message"]
    }

    async def execute(self, message: str, event_id: Optional[str] = None, watch_file: Optional[str] = None) -> Dict[str, Any]:
        event_id = event_id or f"wait-{uuid.uuid4().hex[:8]}"
        result: Dict[str, Any] = {"status": "pending", "event_id": event_id, "message": message}
        if watch_file:
            result["watch_file"] = watch_file
        return result
