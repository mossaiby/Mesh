from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    name: str
    description: str
    parameters: Dict[str, Any]

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
