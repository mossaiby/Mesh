import sys
import subprocess
from typing import Dict, Any, List
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

    async def execute(self, code: str) -> Dict[str, Any]:
        try:
            res = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=10
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

    def get_tools(self) -> List[BaseTool]:
        return [PythonExecutionTool()]