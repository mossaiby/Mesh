from typing import Dict, Any
from tools.base import BaseTool
import tool_synthesis


class SynthesizeTool(BaseTool):
    name = "synthesize_tool"
    description = (
        "Synthesizes a new deterministic Python tool on the fly, saves it to custom_tools/, "
        "and registers it dynamically into Mesh's tool registry without restarting."
    )
    is_proxied = False
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short snake_case name for the tool module (e.g. 'json_csv_converter')."
            },
            "code": {
                "type": "string",
                "description": (
                    "Complete Python source code defining a subclass of BaseTool. Must import "
                    "BaseTool from tools.base and implement name, description, parameters, and async execute()."
                )
            }
        },
        "required": ["name", "code"]
    }

    def __init__(self, tool_registry):
        self._tool_registry = tool_registry

    async def execute(self, name: str, code: str) -> Dict[str, Any]:
        success, message = tool_synthesis.register_synthesized_tool(
            name=name,
            code=code,
            tool_registry=self._tool_registry
        )
        if success:
            return {"status": "success", "message": message, "tool_name": name}
        else:
            return {"status": "error", "error": message}