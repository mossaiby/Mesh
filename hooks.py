import os
import shutil
import subprocess
from typing import Dict, Any, Optional, List
from theme import console


class HookManager:
    """
    Detects and executes linter/formatter hooks after file edits (write_file/edit_file)
    and attaches feedback directly into tool outputs.
    """
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def _detect_linter_cmd(self, filepath: str) -> Optional[List[str]]:
        """Detects available linter/formatter CLI tools based on file extension."""
        ext = os.path.splitext(filepath)[1].lower()

        if ext == ".py":
            if shutil.which("ruff"):
                return ["ruff", "check", filepath]
            elif shutil.which("flake8"):
                return ["flake8", filepath]
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            if shutil.which("eslint"):
                return ["npx", "eslint", filepath]
        elif ext == ".rs":
            if shutil.which("cargo"):
                return ["cargo", "check"]
        elif ext == ".go":
            if shutil.which("gofmt"):
                return ["gofmt", "-l", filepath]

        return None

    def run_post_edit_hooks(self, filepath: str) -> Optional[str]:
        """
        Runs detected linter/formatter on filepath.
        Returns warning/error feedback string if issues are found, otherwise None.
        """
        if not self.enabled or not os.path.exists(filepath):
            return None

        cmd = self._detect_linter_cmd(filepath)
        if not cmd:
            return None

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=os.getcwd()
            )
            if res.returncode != 0:
                output = (res.stdout + "\n" + res.stderr).strip()
                if output:
                    console.print(f"[warning]⚡ Post-Edit Hook ({cmd[0]}):[/warning] Found warnings in '{filepath}'")
                    return f"[Linter/Hook Feedback from {' '.join(cmd)}]:\n{output[:1000]}"
        except Exception:
            pass

        return None


# Global hook manager instance
hook_manager = HookManager()