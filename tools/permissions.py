import os
from pathlib import Path
from typing import List
from tools.ask_tool import AskUserTool
from theme import console



class PermissionManager:
    def __init__(self):
        # Default allowed directory is current working directory
        self.allowed_dirs: List[str] = [str(Path.cwd().resolve())]
        # Set by /mode (YOLO mode forces this True for its duration, and
        # restores the prior value on leaving) - when True, out-of-bounds
        # path requests are approved automatically without an interactive
        # prompt, but NOT persisted to allowed_dirs, so it's a per-call
        # convenience rather than a permanent widening of the allow-list.
        self.auto_approve: bool = False

    def add_dir(self, path: str) -> str:
        resolved = str(Path(path).resolve())
        if resolved not in self.allowed_dirs:
            self.allowed_dirs.append(resolved)
        return resolved

    def remove_dir(self, path: str) -> bool:
        resolved = str(Path(path).resolve())
        if resolved in self.allowed_dirs:
            self.allowed_dirs.remove(resolved)
            return True
        return False

    def is_path_allowed(self, target_path: str) -> bool:
        try:
            resolved_target = Path(target_path).resolve()
            for allowed in self.allowed_dirs:
                resolved_allowed = Path(allowed).resolve()
                if resolved_target == resolved_allowed or resolved_target.is_relative_to(resolved_allowed):
                    return True
            return False
        except Exception:
            return False

    async def check_and_request_permission(self, tool_name: str, target_path: str) -> bool:
        if self.is_path_allowed(target_path):
            return True

        if self.auto_approve:
            console.print(f"[warning]Auto-approved path access for '{tool_name}' (YOLO mode):[/warning] '{target_path}'")
            return True

        resolved_target = str(Path(target_path).resolve())
        target_path_obj = Path(resolved_target)
        # A target is treated as a directory only if it actually exists and is one.
        # (Using a file's suffix as a stand-in for "is a directory" incorrectly
        # classified extensionless existing files, e.g. Makefile/LICENSE/Dockerfile,
        # as directories, causing "Always Allow" to add the file itself instead of
        # its parent directory to the allow-list.)
        target_dir = str(target_path_obj if target_path_obj.is_dir() else target_path_obj.parent)

        question = (
            f"Tool '{tool_name}' requested access to a path outside allowed directories:\n"
            f"  Target: '{resolved_target}'"
        )
        options = [
            f"Always Allow (Add directory '{target_dir}' to allowed list)",
            "Allow Once",
            "Deny"
        ]

        ask_tool = AskUserTool()
        res = await ask_tool.execute(question=question, options=options, allow_custom=False)
        choice = res.get("user_response", "Deny")

        if choice.startswith("Always Allow"):
            self.add_dir(target_dir)
            console.print(f"[success]Added '{target_dir}' to allowed directories.[/success]")
            return True
        elif choice == "Allow Once":
            console.print(f"[warning]Allowed access once for '{resolved_target}'.[/warning]")
            return True
        else:
            console.print(f"[error]Permission denied for '{resolved_target}'.[/error]")
            return False


# Global default instance
default_permission_manager = PermissionManager()