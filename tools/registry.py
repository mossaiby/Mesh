import json
from typing import Dict, List, Any
from tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> None:
        if tool_name in self._tools:
            del self._tools[tool_name]

    def get_schemas(self) -> List[Dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def execute(self, tool_name: str, arguments_json: str) -> str:
        if tool_name not in self._tools:
            return f"Error: Tool '{tool_name}' not registered."
        
        try:
            kwargs = json.loads(arguments_json) if arguments_json else {}
            result = await self._tools[tool_name].execute(**kwargs)
            return json.dumps(result)
        except Exception as e:
            return f"Error executing tool '{tool_name}': {str(e)}"


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluates basic arithmetic expressions."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression to evaluate (e.g. '12 * 4')"
            }
        },
        "required": ["expression"]
    }

    async def execute(self, expression: str) -> Dict[str, Any]:
        try:
            result = eval(expression, {"__builtins__": None}, {})
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}