import os
import sys
from typing import List, Optional, Any, Tuple
from tools.memory_tool import _load_memory
import jobs
from theme import console

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.styles import Style
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


def get_path_completions(partial_path: str, prefix: str = "") -> List[Tuple[str, str, str]]:
    """
    Generates relative file and directory completions matching partial_path.
    Returns list of (full_completion_text, display_name, meta_type).
    """
    raw_path = partial_path
    if prefix and raw_path.startswith(prefix):
        raw_path = raw_path[len(prefix):]

    expanded_path = os.path.expanduser(raw_path)
    dirname, basename = os.path.split(expanded_path)
    orig_dirname, _ = os.path.split(raw_path)

    search_dir = dirname if dirname else "."
    if not (os.path.exists(search_dir) and os.path.isdir(search_dir)):
        return []

    completions = []
    try:
        entries = sorted(os.listdir(search_dir))
        for entry in entries:
            if entry.startswith(".") and not basename.startswith("."):
                continue
            if entry.lower().startswith(basename.lower()):
                full_path = os.path.join(search_dir, entry)
                is_dir = os.path.isdir(full_path)

                if orig_dirname:
                    rel_completion = os.path.join(orig_dirname, entry)
                else:
                    rel_completion = entry

                if is_dir:
                    rel_completion += "/"

                final_text = f"{prefix}{rel_completion}"
                display = f"{entry}/" if is_dir else entry
                meta = "Directory" if is_dir else "File"
                completions.append((final_text, display, meta))
    except Exception:
        pass
    return completions


class MeshCompleter(Completer if PROMPT_TOOLKIT_AVAILABLE else object):
    """
    Context-aware completion engine for Mesh: autocompletes slash commands,
    positional subcommands, model keys, operating modes, background jobs,
    memory keys, session names, config parameters, and local filesystem paths.
    """
    def __init__(self, mesh_instance: Any):
        self.mesh = mesh_instance

    def get_completions(self, document, complete_event):
        if not PROMPT_TOOLKIT_AVAILABLE:
            return

        text = document.text_before_cursor
        if not text:
            return

        ends_with_space = text.endswith(" ")
        raw_words = text.lstrip().split()

        if ends_with_space:
            current_word = ""
            current_arg_index = len(raw_words)
            typed_words = raw_words
        else:
            current_word = raw_words[-1] if raw_words else ""
            current_arg_index = len(raw_words) - 1 if raw_words else 0
            typed_words = raw_words[:-1]

        cmd0 = raw_words[0].lower() if raw_words else ""

        # -------------------------------------------------------------
        # 1. `@` Mention Path Completion
        # -------------------------------------------------------------
        if "@" in text:
            at_idx = text.rfind("@")
            partial_at = text[at_idx:]
            for full_text, display, meta in get_path_completions(partial_at, prefix="@"):
                yield Completion(
                    full_text,
                    start_position=-len(partial_at),
                    display=display,
                    display_meta=meta
                )
            return

        # -------------------------------------------------------------
        # 2. Command Name Completion
        # -------------------------------------------------------------
        if current_arg_index == 0:
            if current_word.startswith("/"):
                cmd_dict = self.mesh.cmd_registry.list_commands()
                for cmd, desc in cmd_dict.items():
                    if cmd.lower().startswith(current_word.lower()):
                        yield Completion(
                            cmd,
                            start_position=-len(current_word),
                            display_meta=desc[:40]
                        )
            return

        # -------------------------------------------------------------
        # 3. Context-Aware Subcommand & Argument Completions
        # -------------------------------------------------------------

        # --- /log ---
        if cmd0 == "/log":
            if current_arg_index == 1:
                subs = [
                    ("on", "Enable Markdown session logging"),
                    ("off", "Disable Markdown session logging"),
                    ("status", "Show logging status and file path")
                ]
                for sub, meta in subs:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)

                for full_text, display, meta in get_path_completions(current_word):
                    yield Completion(full_text, start_position=-len(current_word), display=display, display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 == "on":
                    for full_text, display, meta in get_path_completions(current_word):
                        yield Completion(full_text, start_position=-len(current_word), display=display, display_meta=meta)
            return

        # --- /session ---
        if cmd0 == "/session":
            if current_arg_index == 1:
                subs = [
                    ("save", "Save state to disk under sessions/"),
                    ("load", "Load state from disk"),
                    ("list", "List all saved disk sessions"),
                    ("delete", "Delete saved disk session")
                ]
                for sub, meta in subs:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 in ("load", "restore", "delete"):
                    sessions = self.mesh.session_manager.list_sessions()
                    for s in sessions:
                        s_name = s["name"]
                        if s_name.lower().startswith(current_word.lower()):
                            yield Completion(s_name, start_position=-len(current_word), display_meta=f"{s['messages_count']} msgs ({s['saved_at']})")
            return

        # --- /debug ---
        if cmd0 == "/debug":
            if current_arg_index == 1:
                for opt in ("on", "off"):
                    if opt.startswith(current_word.lower()):
                        yield Completion(opt, start_position=-len(current_word))
            return

        # --- /agent ---
        if cmd0 == "/agent":
            if current_arg_index == 1:
                subs = [
                    ("explore", "Parallel speculative strategy exploration"),
                    ("squad", "4-stage pipeline (Architect->Coder->Tester->Auditor)"),
                    ("consensus", "Adversarial multi-model audit"),
                    ("delegate", "Hand task to autonomous sub-agent"),
                    ("advisor", "Consult second opinion or change advisor model")
                ]
                for sub, meta in subs:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 == "advisor":
                    if "model".startswith(current_word.lower()):
                        yield Completion("model", start_position=-len(current_word), display_meta="Configure advisor model")
                elif word1 == "delegate":
                    if "depth".startswith(current_word.lower()):
                        yield Completion("depth", start_position=-len(current_word), display_meta="Set delegation recursion depth")
            elif current_arg_index == 3:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                word2 = typed_words[2].lower() if len(typed_words) > 2 else ""
                if word1 == "advisor" and word2 == "model":
                    models = list(self.mesh.config_mgr.config.models.keys()) + ["clear", "reset"]
                    for m in models:
                        if m.lower().startswith(current_word.lower()):
                            yield Completion(m, start_position=-len(current_word))
            return

        # --- /models ---
        if cmd0 == "/models":
            if current_arg_index == 1:
                subs = [
                    ("discover", "Query provider endpoints for offered models"),
                    ("add", "Add models: /models add <provider> [<pattern>] [<context_window>]")
                ]
                for sub, meta in subs:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 in ("discover", "add"):
                    providers = list(self.mesh.config_mgr.config.providers.keys())
                    for p in providers:
                        if p.lower().startswith(current_word.lower()):
                            yield Completion(p, start_position=-len(current_word))
            elif current_arg_index == 3:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 == "add":
                    patterns = [
                        ("*", "All available models"),
                        ("*free*", "Free tier models"),
                        ("*coding*", "Coding models"),
                        ("*reasoning*", "Reasoning / thinking models"),
                        ("*vision*", "Vision-capable models")
                    ]
                    for pat, meta in patterns:
                        if pat.startswith(current_word.lower()):
                            yield Completion(pat, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 4:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 == "add":
                    sizes = ["8192", "16384", "32768", "65536", "128000", "200000", "262144", "524288", "1000000", "2097152"]
                    for sz in sizes:
                        if sz.startswith(current_word):
                            yield Completion(sz, start_position=-len(current_word), display_meta=f"{int(sz):,} tokens")
            return

        # --- /switch ---
        if cmd0 == "/switch":
            if current_arg_index == 1:
                subs = [
                    ("auto", "Enable sticky model auto-routing mode"),
                    ("router", "View or configure the model router model")
                ]
                for sub, meta in subs:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)

                models = list(self.mesh.config_mgr.config.models.keys())
                for m in models:
                    if m.lower().startswith(current_word.lower()):
                        cfg = self.mesh.config_mgr.config.models[m]
                        yield Completion(m, start_position=-len(current_word), display_meta=cfg.name)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 == "router":
                    models = list(self.mesh.config_mgr.config.models.keys()) + ["clear", "reset"]
                    for m in models:
                        if m.lower().startswith(current_word.lower()):
                            yield Completion(m, start_position=-len(current_word))
            return

        # --- /config ---
        if cmd0 == "/config":
            if current_arg_index == 1:
                subs = [
                    ("set", "Set timeout, budget, turns, repair, & compaction parameters"),
                    ("distill", "Toggle sub-agent tool output distillation"),
                    ("proxy", "View or configure global network HTTP/HTTPS/SOCKS proxy"),
                    ("repair", "Toggle self-repair tool recovery"),
                    ("hooks", "Toggle post-edit linter hooks"),
                    ("compact", "Toggle auto-compaction"),
                    ("thinking", "Toggle extended thinking/reasoning mode"),
                    ("effort", "Set reasoning effort level (low|medium|high)"),
                    ("tokens", "Toggle turn token count display"),
                    ("cost", "Toggle turn and session USD cost display"),
                    ("statistics", "Toggle TTFT and tok/s performance statistics display")
                ]
                for sub, meta in subs:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 in ("distill", "repair", "hooks", "tokens", "cost", "statistics", "thinking"):
                    for opt in ("on", "off"):
                        if opt.startswith(current_word.lower()):
                            yield Completion(opt, start_position=-len(current_word))
                elif word1 == "effort":
                    for opt in ("low", "medium", "high"):
                        if opt.startswith(current_word.lower()):
                            yield Completion(opt, start_position=-len(current_word))
                elif word1 == "proxy":
                    for opt in ("clear", "off"):
                        if opt.startswith(current_word.lower()):
                            yield Completion(opt, start_position=-len(current_word))
                elif word1 == "compact":
                    for opt in ("on", "off", "threshold"):
                        if opt.startswith(current_word.lower()):
                            yield Completion(opt, start_position=-len(current_word))
                elif word1 == "set":
                    from commands.system_commands import CONFIG_SET_MAP
                    for cat in CONFIG_SET_MAP.keys():
                        if cat.startswith(current_word.lower()):
                            yield Completion(cat, start_position=-len(current_word), display_meta=f"{cat} parameters")
            elif current_arg_index == 3:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                word2 = typed_words[2].lower() if len(typed_words) > 2 else ""
                if word1 == "set":
                    from commands.system_commands import CONFIG_SET_MAP
                    if word2 in CONFIG_SET_MAP:
                        params = CONFIG_SET_MAP[word2]
                        for p_name, (_, _, _, desc) in params.items():
                            if p_name.startswith(current_word.lower()):
                                yield Completion(p_name, start_position=-len(current_word), display_meta=desc[:40])
            return

        # --- /mode ---
        if cmd0 == "/mode":
            if current_arg_index == 1:
                modes_dict = __import__("modes").MODES
                for m_key, mode_def in modes_dict.items():
                    if m_key.startswith(current_word.lower()):
                        yield Completion(m_key, start_position=-len(current_word), display_meta=mode_def.description[:35])
            return

        # --- /guard ---
        if cmd0 == "/guard":
            if current_arg_index == 1:
                subs = [
                    ("on", "Enable Safety Guard"),
                    ("off", "Disable Safety Guard"),
                    ("mode", "Set autonomy mode (supervised|autonomous)"),
                    ("model", "Set guard risk assessment model"),
                    ("trust", "Trust tool for current session")
                ]
                for sub, meta in subs:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 == "mode":
                    for mode in ("supervised", "autonomous"):
                        if mode.startswith(current_word.lower()):
                            yield Completion(mode, start_position=-len(current_word))
                elif word1 == "model":
                    models = list(self.mesh.config_mgr.config.models.keys())
                    for m in models:
                        if m.lower().startswith(current_word.lower()):
                            yield Completion(m, start_position=-len(current_word))
                elif word1 == "trust":
                    tools = list(self.mesh.tool_registry._tools.keys())
                    for t in tools:
                        if t.lower().startswith(current_word.lower()):
                            yield Completion(t, start_position=-len(current_word))
            return

        # --- /jobs ---
        if cmd0 == "/jobs":
            if current_arg_index == 1:
                subs = [
                    ("log", "View recent logs for background job"),
                    ("stop", "Stop running background job"),
                    ("clear", "Clear stopped/completed job entries")
                ]
                for sub, meta in subs:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 in ("log", "stop"):
                    job_list = jobs.job_manager.list_jobs()
                    for j in job_list:
                        jid_str = str(j["job_id"])
                        if jid_str.startswith(current_word):
                            yield Completion(jid_str, start_position=-len(current_word), display_meta=f"PID {j['pid']}: {j['command'][:30]}")
            return

        # --- /git ---
        if cmd0 == "/git":
            if current_arg_index == 1:
                subs = [
                    ("status", "Show Git repository status"),
                    ("diff", "Show Git unified diff"),
                    ("commit", "Create Git commit (AI auto-message if omitted)"),
                    ("push", "Push active branch to remote"),
                    ("branch", "Create or switch feature branch")
                ]
                for sub, meta in subs:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 == "diff":
                    if "staged".startswith(current_word.lower()):
                        yield Completion("staged", start_position=-len(current_word), display_meta="Show staged (--cached) diff")
                elif word1 == "push":
                    for remote in ("origin", "upstream"):
                        if remote.startswith(current_word.lower()):
                            yield Completion(remote, start_position=-len(current_word))
            return

        # --- /diff ---
        if cmd0 == "/diff":
            if current_arg_index == 1:
                if "undo".startswith(current_word.lower()):
                    yield Completion("undo", start_position=-len(current_word), display_meta="Revert last file edit")
            return

        # --- /project ---
        if cmd0 == "/project":
            if current_arg_index == 1:
                for sub, meta in [("map", "Display repository architecture map"), ("reload", "Reload project rules and repo map")]:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            return

        # --- /checkpoint ---
        if cmd0 == "/checkpoint":
            if current_arg_index == 1:
                for sub, meta in [
                    ("save", "Save snapshot tag"),
                    ("fork", "Fork new session branch"),
                    ("restore", "Restore session state tag/branch"),
                    ("list", "List all saved checkpoints")
                ]:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 in ("restore", "checkout"):
                    checkpoints = self.mesh.checkpoint_mgr.checkpoints.keys()
                    for tag in checkpoints:
                        if tag.lower().startswith(current_word.lower()):
                            yield Completion(tag, start_position=-len(current_word))
            return

        # --- /goal ---
        if cmd0 == "/goal":
            if current_arg_index == 1:
                for sub, meta in [("done", "Mark criterion complete"), ("clear", "Clear active session goal")]:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            return

        # --- /note ---
        if cmd0 == "/note":
            if current_arg_index == 1:
                for sub, meta in [("append", "Append text to notes.md"), ("clear", "Clear notes.md")]:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            return

        # --- /memory ---
        if cmd0 == "/memory":
            if current_arg_index == 1:
                for sub, meta in [
                    ("save", "Save key-value memory"),
                    ("get", "Get memory value by key"),
                    ("list", "List all saved memory keys"),
                    ("search", "Semantic natural-language search"),
                    ("delete", "Delete memory key"),
                    ("clear", "Clear all memory")
                ]:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 in ("get", "delete"):
                    mem_keys = list(_load_memory().keys())
                    for k in mem_keys:
                        if k.lower().startswith(current_word.lower()):
                            yield Completion(k, start_position=-len(current_word))
            return

        # --- /reflexion ---
        if cmd0 == "/reflexion":
            if current_arg_index == 1:
                for sub, meta in [("distill", "Distill error logs into rules"), ("clear", "Clear reflexion journal")]:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            return

        # --- /system ---
        if cmd0 == "/system":
            if current_arg_index == 1:
                if "clear".startswith(current_word.lower()):
                    yield Completion("clear", start_position=-len(current_word), display_meta="Clear system prompt from context")
            return

        # --- /tools ---
        if cmd0 == "/tools":
            if current_arg_index == 1:
                for opt in ("on", "off"):
                    if opt.startswith(current_word.lower()):
                        yield Completion(opt, start_position=-len(current_word))
            return

        # --- /skills ---
        if cmd0 == "/skills":
            if current_arg_index == 1:
                for sub in ("enable", "disable"):
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word))
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 in ("enable", "disable"):
                    skills = list(self.mesh.skill_registry.list_skills().keys())
                    for s in skills:
                        if s.lower().startswith(current_word.lower()):
                            yield Completion(s, start_position=-len(current_word))
            return

        # --- /dirs ---
        if cmd0 == "/dirs":
            if current_arg_index == 1:
                for sub, meta in [("add", "Add allowed directory"), ("remove", "Remove allowed directory"), ("clear", "Reset to current CWD")]:
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word), display_meta=meta)
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 == "remove":
                    allowed_dirs = self.mesh.permission_manager.allowed_dirs
                    for d in allowed_dirs:
                        if d.lower().startswith(current_word.lower()):
                            yield Completion(d, start_position=-len(current_word))
                elif word1 == "add":
                    for full_text, display, meta in get_path_completions(current_word):
                        yield Completion(full_text, start_position=-len(current_word), display=display, display_meta=meta)
            return

        # --- /mcps ---
        if cmd0 == "/mcps":
            if current_arg_index == 1:
                for sub in ("on", "off", "enable", "disable"):
                    if sub.startswith(current_word.lower()):
                        yield Completion(sub, start_position=-len(current_word))
            elif current_arg_index == 2:
                word1 = typed_words[1].lower() if len(typed_words) > 1 else ""
                if word1 in ("enable", "disable"):
                    mcps = list(self.mesh.mcp_manager.sessions.keys())
                    for m in mcps:
                        if m.lower().startswith(current_word.lower()):
                            yield Completion(m, start_position=-len(current_word))
            return

        # --- /help ---
        if cmd0 == "/help":
            if current_arg_index == 1:
                cmds = list(self.mesh.cmd_registry.list_commands().keys())
                for c in cmds:
                    clean_c = c.lstrip("/")
                    if clean_c.lower().startswith(current_word.lower().lstrip("/")):
                        yield Completion(clean_c, start_position=-len(current_word))
            return

        # --- Path-based Commands ---
        if cmd0 in ("/cd", "/script", "/shell", "!", "/python", "#", "/loop") or current_word.startswith(("./", "../", "/", "~")):
            for full_text, display, meta in get_path_completions(current_word):
                yield Completion(
                    full_text,
                    start_position=-len(current_word),
                    display=display,
                    display_meta=meta
                )
            return

        if "/" in current_word or "\\" in current_word:
            for full_text, display, meta in get_path_completions(current_word):
                yield Completion(
                    full_text,
                    start_position=-len(current_word),
                    display=display,
                    display_meta=meta
                )


class MeshPromptSession:
    """
    Wraps prompt_toolkit.PromptSession for styled prompt input and tab completion,
    falling back cleanly to console.input() if prompt_toolkit is missing.
    Uses 'bold ansiblue' to match Rich's [info] theme color identically.
    Uses prompt_async() to integrate safely with Mesh's active asyncio event loop.
    """
    def __init__(self, mesh_instance: Any):
        self.mesh = mesh_instance
        if PROMPT_TOOLKIT_AVAILABLE:
            self.completer = MeshCompleter(mesh_instance)
            self.style = Style.from_dict({
                "prompt": "bold ansiblue",
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
            return console.input("[info]User >[/info] ").strip()

    def get_input(self) -> str:
        """Fallback synchronous input reader for non-async contexts."""
        return console.input("[info]User >[/info] ").strip()
