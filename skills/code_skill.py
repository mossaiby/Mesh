import asyncio
import os
import shlex
import sys
import tempfile
from typing import Dict, Any, List, Optional
from tools.base import BaseTool
from skills.base import BaseSkill
from config import default_timeout
import sandbox
import windows_sandbox


class PythonExecutionTool(BaseTool):
    name = "execute_python"
    description = (
        "Executes Python code snippet in a subprocess and returns stdout/stderr. When "
        "sandboxing is available (see /sandbox status), the code can only write to directories "
        "in the permission allow-list and has no network access unless network: true is set. "
        "Remember to prune .venv/node_modules/__pycache__/.git when walking directories - see "
        "the general tool-use guidance."
    )
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code script to execute."
            },
            "network": {
                "type": "boolean",
                "description": "Whether this code needs network access (e.g. urllib/requests calls). Default: false (denied) when the OS-level sandbox is active."
            }
        },
        "required": ["code"]
    }

    def __init__(self, config_mgr: Optional[Any] = None, permission_manager: Optional[Any] = None):
        self._config_mgr = config_mgr
        self._permission_manager = permission_manager

    def is_read_only(self, **kwargs) -> bool:
        return False

    def _sandboxed(self) -> bool:
        return (self._config_mgr is None or self._config_mgr.config.sandbox_enabled) and sandbox.detect_backend() != "none"

    def _windows_experimental(self) -> bool:
        return (
            windows_sandbox.is_available()
            and self._config_mgr is not None
            and getattr(self._config_mgr.config, "sandbox_windows_experimental", False)
        )

    async def execute(self, code: str, network: bool = False) -> Dict[str, Any]:
        timeout_val = self._config_mgr.config.timeouts.python if self._config_mgr else default_timeout("python")

        if self._windows_experimental():
            # Deliberately not passing `code` inline on the command line:
            # _run_write_restricted_sync wraps commands as `cmd.exe /c
            # "<command>"`, and cmd.exe's quoting rules have nothing to do
            # with shlex (which is POSIX-only) - embedding arbitrary Python
            # source with its own quotes/newlines directly into a cmd.exe
            # command line is a correctness minefield for no reason, when
            # writing it to a temp file and running `python <path>` sidesteps
            # the whole problem. The temp file only needs to be *read*, which
            # the sandbox's write-restriction never affects.
            allowed_dirs = self._permission_manager.allowed_dirs if self._permission_manager else [os.getcwd()]
            fd, tmp_path = tempfile.mkstemp(suffix=".py")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(code)
                inner = f'"{sys.executable}" "{tmp_path}"'
                return await windows_sandbox.run_write_restricted(inner, allowed_dirs, cwd=os.getcwd(), timeout=timeout_val)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        sandboxed = self._sandboxed()
        if sandboxed:
            allowed_dirs = self._permission_manager.allowed_dirs if self._permission_manager else [os.getcwd()]
            # sandbox.wrap_command expects a shell command string; quote the interpreter
            # invocation the same way subprocess would have run it directly.
            inner = " ".join([shlex.quote(sys.executable), "-c", shlex.quote(code)])
            argv = sandbox.wrap_command(inner, allowed_dirs, allow_network=network, cwd=os.getcwd())
        else:
            argv = [sys.executable, "-c", code]

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_val)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return {"error": f"Command '{[sys.executable, '-c', code]}' timed out after {timeout_val} seconds"}

            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode,
                "_sandbox": sandbox.detect_backend() if sandboxed else "none"
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

    def __init__(self, config_mgr: Optional[Any] = None, permission_manager: Optional[Any] = None):
        self._config_mgr = config_mgr
        self._permission_manager = permission_manager

    def get_tools(self) -> List[BaseTool]:
        return [PythonExecutionTool(self._config_mgr, self._permission_manager)]
