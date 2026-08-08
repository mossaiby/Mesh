from abc import ABC
from typing import List, Optional
from tools.base import BaseTool


class BaseSkill(ABC):
    name: str
    description: str
    system_instruction: Optional[str] = None
    enabled: bool = True

    def get_tools(self) -> List[BaseTool]:
        """Returns the list of tools supplied by this skill."""
        return []


class DeclarativeSkill(BaseSkill):
    """Skill instantiated dynamically from configuration files like skills.json."""
    def __init__(
        self, 
        name: str, 
        description: str, 
        system_instruction: Optional[str] = None, 
        enabled: bool = True, 
        tools: Optional[List[BaseTool]] = None
    ):
        self.name = name
        self.description = description
        self.system_instruction = system_instruction
        self.enabled = enabled
        self._tools = tools or []

    def get_tools(self) -> List[BaseTool]:
        return self._tools