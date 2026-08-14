import os
import time
from typing import Optional


class SessionLogger:
    """
    Logs user prompts, assistant responses, tool executions, and system events
    to a clean, formatted Markdown file without terminal ANSI control codes.
    """

    def __init__(self, filepath: str = "session.md", enabled: bool = False):
        self.filepath = filepath
        self.enabled = enabled
        self._initialized_file = False

    def enable(self, filepath: Optional[str] = None):
        if filepath:
            self.filepath = filepath
        self.enabled = True
        self._ensure_header()

    def disable(self):
        self.enabled = False

    def _ensure_header(self):
        if not self.enabled or self._initialized_file:
            return

        dir_name = os.path.dirname(self.filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        if not os.path.exists(self.filepath) or os.path.getsize(self.filepath) == 0:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            header = f"# Mesh Session Log\n\n- **Started**: {timestamp}\n- **Log File**: `{self.filepath}`\n\n---\n\n"
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(header)

        self._initialized_file = True

    def _write_entry(self, entry: str):
        if not self.enabled:
            return
        self._ensure_header()
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(entry + "\n\n")
        except Exception as e:
            print(f"[SessionLogger Error]: Failed to write to '{self.filepath}': {e}")

    def log_user_prompt(self, prompt: str):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"## 👤 User Prompt (`{timestamp}`)\n\n{prompt.strip()}"
        self._write_entry(entry)

    def log_assistant_response(self, response: str, model_name: str = ""):
        timestamp = time.strftime("%H:%M:%S")
        model_str = f" (`{model_name}`)" if model_name else ""
        entry = f"## 🤖 Assistant Response{model_str} (`{timestamp}`)\n\n{response.strip()}"
        self._write_entry(entry)

    def log_tool_call(self, tool_name: str, arguments_json: str, result_str: str):
        timestamp = time.strftime("%H:%M:%S")
        
        args_formatted = arguments_json.strip()
        if not args_formatted:
            args_formatted = "{}"

        res_display = result_str.strip()
        if len(res_display) > 10000:
            res_display = res_display[:10000] + "\n... (truncated log output)"

        entry = (
            f"### ⚡ Tool Execution: **`{tool_name}`** (`{timestamp}`)\n\n"
            f"**Arguments**:\n```json\n{args_formatted}\n```\n\n"
            f"**Result**:\n```json\n{res_display}\n```"
        )
        self._write_entry(entry)

    def log_system_event(self, event_text: str):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"> ℹ️ **System Event** (`{timestamp}`): {event_text.strip()}"
        self._write_entry(entry)
