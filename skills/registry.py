import json
import os
from typing import Dict
from skills.base import BaseSkill, DeclarativeSkill
from tools.registry import ToolRegistry


class SkillRegistry:
    def __init__(self, tool_registry: ToolRegistry, filepath: str = "skills.json"):
        self._skills: Dict[str, BaseSkill] = {}
        self.tool_registry = tool_registry
        self.filepath = filepath

    def load_from_file(self) -> None:
        """Loads declaratively defined skills from skills.json file."""
        if not os.path.exists(self.filepath):
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            skill_configs = data.get("skills", {})
            for name, cfg in skill_configs.items():
                if name in self._skills:
                    # Update existing skill properties from file
                    self._skills[name].enabled = cfg.get("enabled", True)
                    if "description" in cfg:
                        self._skills[name].description = cfg["description"]
                    if "system_instruction" in cfg:
                        self._skills[name].system_instruction = cfg["system_instruction"]
                else:
                    # Instantiate dynamic declarative skill
                    decl_skill = DeclarativeSkill(
                        name=name,
                        description=cfg.get("description", "No description"),
                        system_instruction=cfg.get("system_instruction", None),
                        enabled=cfg.get("enabled", True)
                    )
                    self.register(decl_skill)
        except Exception as e:
            print(f"Error loading skills from {self.filepath}: {e}")

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill
        if skill.enabled:
            for tool in skill.get_tools():
                self.tool_registry.register(tool)

    def set_skill_state(self, name: str, enabled: bool) -> bool:
        if name not in self._skills:
            return False
        
        skill = self._skills[name]
        skill.enabled = enabled
        
        for tool in skill.get_tools():
            if enabled:
                self.tool_registry.register(tool)
            else:
                self.tool_registry.unregister(tool.name)
        return True

    def get_combined_system_instructions(self) -> str:
        instructions = [
            skill.system_instruction 
            for skill in self._skills.values() 
            if skill.enabled and skill.system_instruction
        ]
        return "\n\n".join(instructions)

    def list_skills(self) -> Dict[str, BaseSkill]:
        return self._skills