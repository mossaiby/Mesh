from typing import Dict, Any, Optional
from tools.base import BaseTool
import jobs


class BackgroundShellTool(BaseTool):
    name = "job"
    description = (
        "Spawns a shell command in the background without blocking. Use this for "
        "long-running servers, watchers, or processes (e.g. 'npm run dev', 'pytest --watch'). "
        "Returns a job_id to monitor via /jobs. When sandboxing is available (see /sandbox "
        "status), the command can only write to directories in the permission allow-list and "
        "has no network access unless network: true is set."
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
            },
            "network": {
                "type": "boolean",
                "description": "Whether this command needs network access. Default: false (denied) when the OS-level sandbox is active."
            }
        },
        "required": ["command"]
    }

    async def execute(self, command: str, shell_prefix: Optional[str] = None, network: bool = False) -> Dict[str, Any]:
        return await jobs.job_manager.start_job(command=command, shell_prefix=shell_prefix, network=network)