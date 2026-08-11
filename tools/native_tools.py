import os
import glob
import asyncio
from typing import Dict, Any, Optional
from tools.base import BaseTool
from tools.permissions import PermissionManager, default_permission_manager
from file_history import file_history_tracker
from hooks import hook_manager


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Reads text content from a file with optional line range."
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read."},
            "start_line": {"type": "integer", "description": "Optional 1-based start line number."},
            "end_line": {"type": "integer", "description": "Optional 1-based end line number."}
        },
        "required": ["path"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    async def execute(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, path):
            return {"error": f"Permission denied for path '{path}'."}

        if not os.path.exists(path):
            return {"error": f"File '{path}' does not exist."}
        
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            s_idx = (start_line - 1) if start_line and start_line > 0 else 0
            e_idx = end_line if end_line and end_line > 0 else total_lines

            selected_lines = lines[s_idx:e_idx]
            return {
                "path": path,
                "total_lines": total_lines,
                "content": "".join(selected_lines)
            }
        except Exception as e:
            return {"error": f"Failed to read file '{path}': {str(e)}"}


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Writes content to a file (creates parent directories if needed)."
    is_proxied = True
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to write the file."},
            "content": {"type": "string", "description": "File content to write."}
        },
        "required": ["path", "content"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    async def execute(self, path: str, content: str) -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, path):
            return {"error": f"Permission denied for path '{path}'."}

        try:
            diff_text = file_history_tracker.record_edit(path, content, action="write_file")

            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            res = {
                "status": "success",
                "message": f"Wrote {len(content)} characters to '{path}'.",
                "diff": diff_text
            }

            # Trigger post-edit linter hook
            linter_feedback = hook_manager.run_post_edit_hooks(path)
            if linter_feedback:
                res["_linter_feedback"] = linter_feedback

            return res
        except Exception as e:
            return {"error": f"Failed to write file '{path}': {str(e)}"}


class EditFileTool(BaseTool):
    name = "edit_file"
    description = "Edits a file by replacing old string matches with new string."
    is_proxied = True
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit."},
            "old_str": {"type": "string", "description": "Exact target string to be replaced."},
            "new_str": {"type": "string", "description": "New replacement string."}
        },
        "required": ["path", "old_str", "new_str"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    async def execute(self, path: str, old_str: str, new_str: str) -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, path):
            return {"error": f"Permission denied for path '{path}'."}

        if not os.path.exists(path):
            return {"error": f"File '{path}' does not exist."}

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if old_str not in content:
                return {"error": f"Target string 'old_str' not found in '{path}'."}

            updated_content = content.replace(old_str, new_str, 1)

            diff_text = file_history_tracker.record_edit(path, updated_content, action="edit_file")

            with open(path, "w", encoding="utf-8") as f:
                f.write(updated_content)

            res = {
                "status": "success",
                "message": f"Successfully updated '{path}'.",
                "diff": diff_text
            }

            # Trigger post-edit linter hook
            linter_feedback = hook_manager.run_post_edit_hooks(path)
            if linter_feedback:
                res["_linter_feedback"] = linter_feedback

            return res
        except Exception as e:
            return {"error": f"Failed to edit file '{path}': {str(e)}"}


class GlobTool(BaseTool):
    name = "glob_files"
    description = "Finds files matching a glob pattern (e.g., '**/*.py')."
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py')."},
            "root_dir": {"type": "string", "description": "Optional root directory (defaults to current directory)."}
        },
        "required": ["pattern"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    async def execute(self, pattern: str, root_dir: str = ".") -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, root_dir):
            return {"error": f"Permission denied for root directory '{root_dir}'."}

        try:
            search_pattern = os.path.join(root_dir, pattern)
            matches = glob.glob(search_pattern, recursive=True)
            return {"pattern": pattern, "matches": matches[:100], "count": len(matches)}
        except Exception as e:
            return {"error": f"Glob search failed: {str(e)}"}


class ShellTool(BaseTool):
    name = "run_shell_command"
    description = "Runs a shell command in the system environment and returns stdout/stderr."
    is_proxied = True
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute."}
        },
        "required": ["command"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    async def execute(self, command: str) -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, os.getcwd()):
            return {"error": "Permission denied for command execution in current working directory."}

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            return {
                "command": command,
                "exit_code": proc.returncode,
                "stdout": stdout.decode('utf-8', errors='replace').strip(),
                "stderr": stderr.decode('utf-8', errors='replace').strip()
            }
        except asyncio.TimeoutError:
            return {"error": "Command execution timed out after 30 seconds."}
        except Exception as e:
            return {"error": f"Command execution failed: {str(e)}"}