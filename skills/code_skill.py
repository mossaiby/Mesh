import sys
import subprocess
from typing import Dict, Any, List, Optional
from tools.base import BaseTool
from skills.base import BaseSkill


class PythonExecutionTool(BaseTool):
    name = "execute_python"
    description = "Executes Python code snippet in a subprocess and returns stdout/stderr."
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code script to execute."
            }
        },
        "required": ["code"]
    }

    def __init__(self, config_mgr: Optional[Any] = None):
        self._config_mgr = config_mgr

    async def execute(self, code: str) -> Dict[str, Any]:
        timeout_val = self._config_mgr.config.timeouts.python if self._config_mgr else 10.0
        try:
            res = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_val
            )
            return {
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode
            }
        except Exception as e:
            return {"error": str(e)}


class PythonCodingSkill(BaseSkill):
    name = "python_coding"
    description = "Provides Python code execution and developer-focused reasoning guidelines."
    system_instruction = (
        "You possess the Python Coding Skill. When writing code, prefer concise, "
        "idiomatic Python. You can execute snippets directly using the execute_python tool."
    )

    def __init__(self, config_mgr: Optional[Any] = None):
        self._config_mgr = config_mgr

    def get_tools(self) -> List[BaseTool]:
        return [PythonExecutionTool(self._config_mgr)]
