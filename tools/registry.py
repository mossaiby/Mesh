import json
from typing import Dict, List, Any, Optional
from tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self.subagent_proxy: Optional[Any] = None

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> None:
        if tool_name in self._tools:
            del self._tools[tool_name]

    def get_schemas(self, inject_intent: bool = True) -> List[Dict[str, Any]]:
        use_intent = inject_intent and (
            self.subagent_proxy is not None and self.subagent_proxy.enabled
        )
        return [tool.to_openai_schema(inject_intent=use_intent) for tool in self._tools.values()]

    async def execute(self, tool_name: str, arguments_json: str) -> str:
        if tool_name not in self._tools:
            return json.dumps({"error": f"Tool '{tool_name}' not registered."})
        
        tool = self._tools[tool_name]

        try:
            kwargs = json.loads(arguments_json) if arguments_json else {}
            
            # Extract and strip _intent parameter if present
            intent = kwargs.pop("_intent", "").strip()

            # Execute underlying tool
            raw_result = await tool.execute(**kwargs)
            result_str = json.dumps(raw_result) if not isinstance(raw_result, str) else raw_result

            # Route through SubAgentProxy if tool is proxied and sub-agent is enabled
            if (
                tool.is_proxied 
                and self.subagent_proxy is not None 
                and self.subagent_proxy.enabled 
                and intent
            ):
                return await self.subagent_proxy.distill_tool_result(
                    tool_name=tool_name, 
                    intent=intent, 
                    raw_result=result_str
                )

            # Ensure valid JSON string returned for non-proxied tools or when proxy is disabled
            if not (result_str.startswith("{") or result_str.startswith("[")):
                return json.dumps({"result": result_str})

            return result_str
        except Exception as e:
            return json.dumps({"error": f"Error executing tool '{tool_name}': {str(e)}"})


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluates basic arithmetic expressions."
    is_proxied = False  # Direct execution
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