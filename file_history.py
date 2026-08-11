import difflib
import os
from typing import List, Dict, Any, Optional, Tuple
from theme import console


class FileHistoryTracker:
    """
    Intercepts write_file and edit_file executions before disk mutation,
    computes colorized unified diffs, and maintains a session undo stack.
    """
    def __init__(self):
        # Stack of {path, old_content, new_content, action, timestamp}
        self.undo_stack: List[Dict[str, Any]] = []

    def record_edit(self, path: str, new_content: str, action: str = "edit") -> str:
        """
        Reads old file content (if exists), records entry to undo stack,
        and returns a colorized Rich unified diff string.
        """
        old_content = ""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    old_content = f.read()
            except Exception:
                old_content = ""

        self.undo_stack.append({
            "path": path,
            "old_content": old_content,
            "new_content": new_content,
            "action": action,
            "existed": os.path.exists(path)
        })

        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3
        ))

        return "".join(diff_lines)

    def get_last_diff(self) -> Optional[Dict[str, Any]]:
        """Returns the diff info of the most recent file edit."""
        if not self.undo_stack:
            return None

        entry = self.undo_stack[-1]
        diff_lines = list(difflib.unified_diff(
            entry["old_content"].splitlines(keepends=True),
            entry["new_content"].splitlines(keepends=True),
            fromfile=f"a/{entry['path']}",
            tofile=f"b/{entry['path']}",
            n=3
        ))

        return {
            "path": entry["path"],
            "action": entry["action"],
            "diff_text": "".join(diff_lines)
        }

    def undo_last(self) -> Tuple[bool, str]:
        """
        Reverts the last file modification on disk and pops from the stack.
        Returns (success, message).
        """
        if not self.undo_stack:
            return False, "Undo stack is empty - no file edits to revert."

        entry = self.undo_stack.pop()
        path = entry["path"]

        try:
            if not entry["existed"] and not entry["old_content"]:
                # File was newly created by tool - delete it to revert
                if os.path.exists(path):
                    os.remove(path)
                return True, f"Reverted edit: Deleted newly created file '{path}'."
            else:
                # File existed previously - restore old content
                dir_name = os.path.dirname(path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(entry["old_content"])
                return True, f"Reverted last edit to '{path}' ({len(entry['old_content'])} bytes restored)."
        except Exception as e:
            return False, f"Failed to undo edit on '{path}': {str(e)}"


# Global tracker instance
file_history_tracker = FileHistoryTracker()