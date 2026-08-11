from typing import Dict, Any, Optional
from tools.base import BaseTool
import jobs


class BackgroundShellTool(BaseTool):
    name = "job"
    description = (
        "Spawns a shell command in the background without blocking. Use this for "
        "long-running servers, watchers, or processes (e.g. 'npm run dev', 'pytest --watch'). "
        "Returns a job_id to monitor via /jobs."
    )
    is_proxied = False
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to run in the background."
            },
            "shell_prefix": {
                "type": "string",
                "description": "Optional shell wrapper prefix (e.g. 'powershell -Command', 'cmd /c', 'wsl')."
            }
        },
        "required": ["command"]
    }

    async def execute(self, command: str, shell_prefix: Optional[str] = None) -> Dict[str, Any]:
        return await jobs.job_manager.start_job(command=command, shell_prefix=shell_prefix)