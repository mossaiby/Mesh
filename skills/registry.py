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
                is_enabled = cfg.get("enabled", True)
                if name in self._skills:
                    # Update existing skill properties from file
                    self._skills[name].enabled = is_enabled
                    if "description" in cfg:
                        self._skills[name].description = cfg["description"]
                    if "system_instruction" in cfg:
                        self._skills[name].system_instruction = cfg["system_instruction"]

                    # Ensure tools in tool_registry match enabled state
                    for tool in self._skills[name].get_tools():
                        if is_enabled:
                            self.tool_registry.register(tool)
                        else:
                            self.tool_registry.unregister(tool.name)
                else:
                    # Instantiate dynamic declarative skill
                    decl_skill = DeclarativeSkill(
                        name=name,
                        description=cfg.get("description", "No description"),
                        system_instruction=cfg.get("system_instruction", None),
                        enabled=is_enabled
                    )
                    self.register(decl_skill)
        except Exception as e:
            print(f"Error loading skills from {self.filepath}: {e}")

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill
        if skill.enabled:
            for tool in skill.get_tools():
                self.tool_registry.register(tool)

    def save_to_file(self) -> None:
        """Persists all currently registered DeclarativeSkills back to skills.json,
        preserving any keys already present in the file (e.g. skills authored
        directly by hand rather than through this registry)."""
        data: Dict = {"skills": {}}
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {"skills": {}}

        data.setdefault("skills", {})
        for name, skill in self._skills.items():
            if isinstance(skill, DeclarativeSkill):
                data["skills"][name] = {
                    "enabled": skill.enabled,
                    "description": skill.description,
                    "system_instruction": skill.system_instruction
                }

        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

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
