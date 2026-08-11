import os
import sys
from typing import List, Optional, Any
from theme import console

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.styles import Style
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


class MeshCompleter(Completer if PROMPT_TOOLKIT_AVAILABLE else object):
    """
    Custom completion engine for Mesh: autocomplete slash commands,
    model keys, operating modes, and local workspace file paths (including @file mentions).
    """
    def __init__(self, mesh_instance: Any):
        self.mesh = mesh_instance

    def get_completions(self, document, complete_event):
        if not PROMPT_TOOLKIT_AVAILABLE:
            return

        text = document.text_before_cursor
        words = text.lstrip().split()

        # 1. Complete Slash Commands
        if text.startswith("/") and len(words) <= 1:
            cmd_list = list(self.mesh.cmd_registry.list_commands().keys())
            for cmd in cmd_list:
                if cmd.startswith(text.lower()):
                    desc = self.mesh.cmd_registry.list_commands().get(cmd, "")
                    yield Completion(cmd, start_position=-len(text), display_meta=desc[:40])
            return

        # 2. Complete Model Keys for /switch, /models, /guard model, /agent advisor model
        if len(words) >= 2 and words[0].lower() in ("/switch", "/models", "/guard"):
            prefix = words[-1].lower() if len(words) > 1 else ""
            model_keys = list(self.mesh.config_mgr.config.models.keys())
            for key in model_keys:
                if key.lower().startswith(prefix):
                    yield Completion(key, start_position=-len(prefix))
            return

        # 3. Complete Operating Modes for /mode
        if len(words) >= 2 and words[0].lower() == "/mode":
            prefix = words[-1].lower()
            modes_dict = __import__("modes").MODES
            for m_key in modes_dict.keys():
                if m_key.startswith(prefix):
                    yield Completion(m_key, start_position=-len(prefix), display_meta=modes_dict[m_key].description[:35])
            return

        # 4. Complete Agent Workflows for /agent
        if len(words) >= 2 and words[0].lower() == "/agent":
            prefix = words[1].lower() if len(words) == 2 else ""
            agent_subs = ["explore", "squad", "consensus", "delegate", "advisor"]
            for sub in agent_subs:
                if sub.startswith(prefix):
                    yield Completion(sub, start_position=-len(prefix))
            return

        # 5. Complete Config Toggles for /config
        if len(words) >= 2 and words[0].lower() == "/config":
            prefix = words[1].lower() if len(words) == 2 else ""
            cfg_subs = ["proxy", "repair", "hooks", "compact"]
            for sub in cfg_subs:
                if sub.startswith(prefix):
                    yield Completion(sub, start_position=-len(prefix))
            return

        # 6. Complete Git Subcommands for /git
        if len(words) >= 2 and words[0].lower() == "/git":
            prefix = words[1].lower() if len(words) == 2 else ""
            git_subs = ["status", "diff", "commit", "push", "branch"]
            for sub in git_subs:
                if sub.startswith(prefix):
                    yield Completion(sub, start_position=-len(prefix))
            return

        # 7. Complete @file Mentions anywhere in prompt
        if "@" in text:
            at_idx = text.rfind("@")
            partial = text[at_idx + 1:]
            dirname, basename = os.path.split(partial)
            search_dir = dirname if dirname else "."
            if os.path.exists(search_dir) and os.path.isdir(search_dir):
                try:
                    for entry in os.listdir(search_dir):
                        if entry.startswith(basename) and not entry.startswith(".git"):
                            full_rel = os.path.join(dirname, entry) if dirname else entry
                            display = entry + ("/" if os.path.isdir(os.path.join(search_dir, entry)) else "")
                            yield Completion(f"@{full_rel}", start_position=-len(partial) - 1, display=display)
                except Exception:
                    pass
            return

        # 8. File Path Completion for /script, /dirs, /checkpoint
        if len(words) >= 2 and words[0].lower() in ("/script", "/dirs", "/checkpoint"):
            partial_path = words[-1]
            dirname, basename = os.path.split(partial_path)
            search_dir = dirname if dirname else "."
            if os.path.exists(search_dir) and os.path.isdir(search_dir):
                try:
                    for entry in os.listdir(search_dir):
                        if entry.startswith(basename):
                            full_rel = os.path.join(dirname, entry) if dirname else entry
                            display = entry + ("/" if os.path.isdir(os.path.join(search_dir, entry)) else "")
                            yield Completion(full_rel, start_position=-len(partial_path), display=display)
                except Exception:
                    pass
            return


class MeshPromptSession:
    """
    Wraps prompt_toolkit.PromptSession for styled prompt input and tab completion,
    falling back cleanly to console.input() if prompt_toolkit is missing.
    Uses prompt_async() to integrate safely with Mesh's active asyncio event loop.
    """
    def __init__(self, mesh_instance: Any):
        self.mesh = mesh_instance
        if PROMPT_TOOLKIT_AVAILABLE:
            self.completer = MeshCompleter(mesh_instance)
            self.style = Style.from_dict({
                "prompt": "bold #5f87ff",  # Matches Rich bold blue / [info]
            })
            self.session = PromptSession(
                completer=self.completer,
                style=self.style,
                complete_while_typing=True
            )
        else:
            self.session = None

    async def get_input_async(self) -> str:
        """Asynchronously reads input on the active asyncio event loop."""
        if PROMPT_TOOLKIT_AVAILABLE and sys.stdin.isatty() and self.session:
            try:
                result = await self.session.prompt_async([("class:prompt", "User > ")])
                return result.strip()
            except KeyboardInterrupt:
                raise KeyboardInterrupt()
            except EOFError:
                raise EOFError()
        else:
            return console.input("[info]User[/info] > ").strip()

    def get_input(self) -> str:
        """Fallback synchronous input reader for non-async contexts."""
        return console.input("[info]User[/info] > ").strip()