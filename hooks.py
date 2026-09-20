import asyncio
import json
import os
import re
import shutil
import subprocess
from typing import Dict, Any, Optional, List
from theme import console
from config import default_timeout, APP_ROOT
from glyphs import LIGHTNING


class HookManager:
    """
    Two things live here, both under the same `enabled` switch and the same
    `/hooks` command, but genuinely different in scope:

    1. The original, narrow post-edit linter/formatter hook
       (`run_post_edit_hooks[_async]`) - runs a hardcoded, built-in set of
       linters (ruff/flake8/eslint/cargo/gofmt) after write_file/edit_file/
       hash_edit, based on file extension. Unchanged from before.

    2. A general lifecycle hook system (`run_event`), configured via
       `hooks.json` at the project root, covering five points in Mesh's own
       lifecycle: `session_start`, `session_end`, `user_prompt_submit`,
       `pre_tool_use`, `post_tool_use`. Each hook is an arbitrary shell
       command the user defines - this is the actual general extension
       point #1 was missing, matching what tools like Claude Code expose
       (pre/post tool use, session start/end, user-prompt-submit hooks) -
       Mesh previously only had the one hardcoded linter behavior and
       nothing a user could define themselves.

    hooks.json format:
        {
          "pre_tool_use":  [{"matcher": "shell|job", "command": "..."}],
          "post_tool_use": [{"matcher": "write_file|edit_file", "command": "..."}],
          "user_prompt_submit": [{"command": "..."}],
          "session_start": [{"command": "..."}],
          "session_end": [{"command": "..."}]
        }
    `matcher` is a regex tested against the tool name with `re.fullmatch`
    (ignored/optional for the three non-tool events); omit it to match
    every tool. Each hook command receives a JSON payload on stdin
    describing the event (see `run_event`'s docstring for the exact
    shape) and communicates back via stdout/exit code:

    - Exit code 2: treat as a block (pre_tool_use only - ignored for other
      events, which have nothing to block). The reason shown to the model
      is stderr if non-empty, else stdout. This mirrors Claude Code's own
      hook exit-code convention deliberately, since anyone who already
      knows that convention shouldn't have to learn a different one here.
    - Exit code 0 with JSON on stdout: looks for "block"/"reason" (same
      meaning as above, alternative to the exit-code convention),
      "feedback" (a string appended into the tool result as extra
      context, the same mechanism the linter hook already uses), and
      "modified_prompt" (user_prompt_submit only - replaces the prompt
      before it reaches the model).
    - Exit code 0 with non-JSON stdout: the raw text is used as feedback,
      for simple hooks that just want to print something back.
    - Any other exit code: logged as a warning, does not block anything.
    """

    def __init__(self, enabled: bool = True, config_mgr: Optional[Any] = None, hooks_path: Optional[str] = None):
        self.enabled = enabled
        self._config_mgr = config_mgr
        self._hooks_path = hooks_path or os.path.join(APP_ROOT, "hooks.json")
        self._lifecycle_hooks: Dict[str, List[Dict[str, str]]] = {}
        self.reload_lifecycle_hooks()

    # --- General lifecycle hooks -------------------------------------------------

    def reload_lifecycle_hooks(self) -> Optional[str]:
        """(Re)loads hooks.json. Returns an error string if the file exists
        but couldn't be parsed, else None (including when the file simply
        doesn't exist, which is the common case - lifecycle hooks are
        entirely opt-in)."""
        if not os.path.exists(self._hooks_path):
            self._lifecycle_hooks = {}
            return None
        try:
            with open(self._hooks_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("hooks.json must contain a JSON object mapping event names to hook lists.")
            # Only keep keys that actually look like an event's hook list
            # (a list of dicts) - this lets a hooks.json use "_comment"/
            # "$comment" keys for documentation (as hooks.json.example
            # does) without them leaking into describe_lifecycle_hooks()
            # as a fake event.
            self._lifecycle_hooks = {
                event: hooks for event, hooks in data.items()
                if isinstance(hooks, list) and all(isinstance(h, dict) for h in hooks)
            }
            return None
        except Exception as e:
            self._lifecycle_hooks = {}
            return f"Failed to load {self._hooks_path}: {e}"

    def describe_lifecycle_hooks(self) -> Dict[str, int]:
        """Count of configured hooks per event, for /hooks status display."""
        return {event: len(hooks) for event, hooks in self._lifecycle_hooks.items() if hooks}

    async def run_event(self, event: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Runs every configured hook for `event` whose matcher matches
        context.get("tool_name", "") (events with no tool_name always
        match). Returns {"block": bool, "reason": Optional[str],
        "feedback": List[str], "modified_prompt": Optional[str]}.

        Context shapes by event:
          pre_tool_use:  {"tool_name": str, "arguments": dict}
          post_tool_use: {"tool_name": str, "arguments": dict, "result": Any}
          user_prompt_submit: {"prompt": str}
          session_start: {}
          session_end:   {}
        (the event name itself is always added automatically)
        """
        result: Dict[str, Any] = {"block": False, "reason": None, "feedback": [], "modified_prompt": None}
        if not self.enabled:
            return result

        hooks = self._lifecycle_hooks.get(event, [])
        if not hooks:
            return result

        tool_name = context.get("tool_name", "")
        payload = {"event": event, **context}

        for hook in hooks:
            matcher = hook.get("matcher")
            if matcher and not re.fullmatch(matcher, tool_name):
                continue
            command = hook.get("command")
            if not command:
                continue

            exit_code, stdout, stderr = await self._run_hook_command(command, payload)
            if exit_code is None:
                continue  # hook itself failed to launch/timed out; already logged

            if exit_code == 2 and event == "pre_tool_use":
                result["block"] = True
                result["reason"] = (stderr or stdout or "Blocked by hook.").strip()
                return result

            if exit_code not in (0, 2):
                console.print(f"[warning]{LIGHTNING} Hook '{command}' for {event} exited with code {exit_code}:[/warning] {stderr.strip()[:300]}")
                continue

            if exit_code != 0:
                continue

            parsed = self._try_parse_json(stdout)
            if isinstance(parsed, dict):
                if parsed.get("block") and event == "pre_tool_use":
                    result["block"] = True
                    result["reason"] = str(parsed.get("reason", "Blocked by hook."))
                    return result
                if "feedback" in parsed:
                    result["feedback"].append(str(parsed["feedback"]))
                if event == "user_prompt_submit" and "modified_prompt" in parsed:
                    result["modified_prompt"] = str(parsed["modified_prompt"])
            elif stdout.strip():
                result["feedback"].append(stdout.strip())

        return result

    async def _run_hook_command(self, command: str, payload: Dict[str, Any]):
        """Returns (exit_code, stdout, stderr), or (None, "", "") if the
        hook itself couldn't be run at all (missing interpreter, timeout,
        etc.) - distinguished from a real nonzero exit code so callers
        don't mistake "hook broke" for "hook said no"."""
        timeout_val = self._config_mgr.config.timeouts.hook if self._config_mgr else default_timeout("hook")
        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd(),
            )
            stdin_bytes = json.dumps(payload).encode("utf-8")
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(stdin_bytes), timeout=timeout_val)
            return (
                proc.returncode,
                stdout_bytes.decode("utf-8", errors="replace"),
                stderr_bytes.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            console.print(f"[warning]{LIGHTNING} Hook timed out after {timeout_val}s:[/warning] {command}")
            # asyncio.wait_for abandons the communicate() call on timeout,
            # but the underlying subprocess is NOT killed by that alone -
            # left unhandled it keeps running as an orphan indefinitely.
            if proc is not None:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
                except Exception:
                    pass
            return None, "", ""
        except Exception as e:
            console.print(f"[warning]{LIGHTNING} Hook failed to run:[/warning] {command} ({e})")
            return None, "", ""

    @staticmethod
    def _try_parse_json(text: str) -> Optional[Any]:
        text = text.strip()
        if not text or text[0] not in "{[":
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

    # --- Built-in post-edit linter hook (unchanged from before) -----------------

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

        timeout_val = self._config_mgr.config.timeouts.linter if self._config_mgr else default_timeout("linter")

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_val,
                cwd=os.getcwd()
            )
            if res.returncode != 0:
                output = (res.stdout + "\n" + res.stderr).strip()
                if output:
                    console.print(f"[warning]{LIGHTNING} Post-Edit Hook ({cmd[0]}):[/warning] Found warnings in '{filepath}'")
                    return f"[Linter/Hook Feedback from {' '.join(cmd)}]:\n{output[:1000]}"
        except Exception:
            pass

        return None

    async def run_post_edit_hooks_async(self, filepath: str) -> Optional[str]:
        """Asynchronously runs detected linter/formatter on filepath in a worker thread."""
        return await asyncio.to_thread(self.run_post_edit_hooks, filepath)


# Global hook manager instance
hook_manager = HookManager()
