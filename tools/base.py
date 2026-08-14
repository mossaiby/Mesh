import copy
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    name: str
    description: str
    parameters: Dict[str, Any]
    is_distilled: bool = False  # Set to True for heavy tools that benefit from sub-agent distillation
    requires_guard: bool = False  # Set to True for tools whose calls should be risk-assessed
                                   # by the SafetyGuard before executing (shell, file writes, MCP tools)

    @property
    def is_proxied(self) -> bool:
        """Backward-compatibility property alias for is_distilled."""
        return self.is_distilled

    @is_proxied.setter
    def is_proxied(self, value: bool) -> None:
        self.is_distilled = value

    def is_read_only(self, **kwargs) -> bool:
        """
        Returns True if the tool invocation is read-only (side-effect free)
        and safe to execute concurrently with other read-only tool calls.
        Subclasses with action parameters (e.g. MemoryTool, NoteTool) override
        this method to inspect the specific action being performed.
        """
        return not self.requires_guard

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute tool logic and return result as serializable dict/str."""
        pass

    def to_openai_schema(self, inject_intent: bool = True) -> Dict[str, Any]:
        schema_params = copy.deepcopy(self.parameters)
        
        # Ensure _intent is explicitly purged when intent injection is disabled
        if "properties" in schema_params and "_intent" in schema_params["properties"]:
            del schema_params["properties"]["_intent"]
        if "required" in schema_params and "_intent" in schema_params["required"]:
            schema_params["required"].remove("_intent")

        # Inject required _intent parameter ONLY if tool is distilled AND intent injection is enabled
        if self.is_distilled and inject_intent:
            props = schema_params.get("properties", {})
            props["_intent"] = {
                "type": "string",
                "description": "The exact goal, purpose, or reason for this tool call and what specific information you need."
            }
            schema_params["properties"] = props
            required = schema_params.get("required", [])
            if "_intent" not in required:
                required.append("_intent")
            schema_params["required"] = required

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema_params
            }
        }
