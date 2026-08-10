import asyncio
import sys
import os
from typing import Optional
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
from render.stream_renderer import StreamRenderer
from tools import (
    ToolRegistry,
    CalculatorTool,
    MemoryTool,
    NoteTool,
    AskUserTool,
    TodoTool,
    PermissionManager,
    WebSearchTool,
    WebFetchTool,
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    GlobTool,
    ShellTool,
    DelegateTaskTool,
    GoalTool,
    AdvisorTool,
    ExploreTool,
    SynthesizeTool,
    ConsensusTool,
)
import delegation
import memory_search
import advisor
import explore
import consensus
import tool_synthesis
from guard import SafetyGuard
from tools.ask_tool import _read_single_key
from tools.note_tool import _read_notes, _write_notes, _append_notes
from tools.memory_tool import _load_memory, _save_memory
from commands.registry import CommandRegistry
from mcp.client import MCPManager
from skills import SkillRegistry, PythonCodingSkill, DeclarativeSkill
from compaction import compact_messages, maybe_auto_compact, estimate_tokens
from dream import dream_extract
from subagent import SubAgentProxy
from self_heal import SelfHealer
import modes
from theme import console
from version import __version__


class Mesh:
    def __init__(self):
        self.config_mgr = ConfigManager()
        self.renderer = StreamRenderer()
        self.tool_registry = ToolRegistry()
        self.subagent_proxy = SubAgentProxy(self.config_mgr)
        self.tool_registry.subagent_proxy = self.subagent_proxy
        self.self_healer = SelfHealer(self.config_mgr)
        self.tool_registry.self_healer = self.self_healer
        self.safety_guard = SafetyGuard(self.config_mgr, enabled=self.config_mgr.config.guard_enabled)
        self.tool_registry.safety_guard = self.safety_guard
        
        self.permission_manager = PermissionManager()
        self.skill_registry = SkillRegistry(self.tool_registry)
        self.cmd_registry = CommandRegistry()
        self.mcp_manager = MCPManager()
        self.debug_mode: bool = False
        self.subagent_proxy.debug_mode = self.debug_mode
        self.tools_enabled: bool = True
        self.current_mode: str = modes.DEFAULT_MODE
        # Saved so YOLO mode can restore whatever the user had explicitly
        # set before entering it, rather than resetting to hardcoded defaults.
        self._pre_yolo_guard_autonomy: Optional[str] = None
        self._pre_yolo_permission_auto_approve: Optional[bool] = None

        self.setup_defaults()
        self.tool_registry.mode_blocked_tools = modes.blocked_tools_for_mode(self.current_mode, self.tool_registry)
        self.update_system_message(self.config_mgr.config.system_prompt)

    def update_system_message(self, base_prompt: str = None):
        if not base_prompt:
            base_prompt = self.config_mgr.config.system_prompt or "You are a helpful text-based AI assistant."

        skill_instructions = self.skill_registry.get_combined_system_instructions()
        full_sys = base_prompt
        if skill_instructions:
            full_sys += f"\n\nActive Skills Instructions:\n{skill_instructions}"

        goal_section = self.goal_tool.as_system_prompt_section() if hasattr(self, "goal_tool") else ""
        if goal_section:
            full_sys += f"\n\n{goal_section}"

        if hasattr(self, "current_mode"):
            mode_def = modes.MODES.get(self.current_mode, modes.MODES[modes.DEFAULT_MODE])
            full_sys += f"\n\n## Current Mode: {mode_def.label}\n{mode_def.system_note}"

        sys_idx = next((i for i, m in enumerate(self.messages) if m.get("role") == "system"), None) if hasattr(self, "messages") else None
        
        if sys_idx is not None:
            self.messages[sys_idx]["content"] = full_sys
        else:
            self.messages = [{"role": "system", "content": full_sys}]

    def setup_defaults(self):
        # 1. Register Base Tools with PermissionManager
        self.tool_registry.register(CalculatorTool())
        self.tool_registry.register(MemoryTool(self.config_mgr))
        self.tool_registry.register(NoteTool())
        self.tool_registry.register(AskUserTool())
        self.tool_registry.register(TodoTool())
        self.tool_registry.register(WebSearchTool())
        self.tool_registry.register(WebFetchTool())
        self.tool_registry.register(ReadFileTool(self.permission_manager))
        self.tool_registry.register(WriteFileTool(self.permission_manager))
        self.tool_registry.register(EditFileTool(self.permission_manager))
        self.tool_registry.register(GlobTool(self.permission_manager))
        self.tool_registry.register(ShellTool(self.permission_manager))
        self.tool_registry.register(DelegateTaskTool(self.tool_registry, self.config_mgr))
        self.goal_tool = GoalTool(on_change=lambda: self.update_system_message())
        self.tool_registry.register(self.goal_tool)
        self.tool_registry.register(AdvisorTool(self.config_mgr))
        self.tool_registry.register(ExploreTool(self.tool_registry, self.config_mgr))
        self.tool_registry.register(SynthesizeTool(self.tool_registry))
        self.tool_registry.register(ConsensusTool(self.config_mgr))
        
        # Load any existing dynamic tools from custom_tools/
        tool_synthesis.load_all_custom_tools(self.tool_registry)

        # 2. Register Skills & Load skills.json
        self.skill_registry.register(PythonCodingSkill())
        self.skill_registry.load_from_file()

        # 3. Slash Commands
        self.cmd_registry.register("help", "Show available slash commands", self.cmd_help)
        self.cmd_registry.register("status", "Show current Mesh status overview", self.cmd_status)
        self.cmd_registry.register("models", "List configured models and providers", self.cmd_models)
        self.cmd_registry.register("switch", "Switch active model interactively, or directly: /switch <model_key>", self.cmd_switch)
        self.cmd_registry.register("clear", "Clear the conversation context window", self.cmd_clear)
        self.cmd_registry.register("compact", "Semantically summarize older conversation context", self.cmd_compact)
        self.cmd_registry.register("autocompact", "View or set auto-compaction: /autocompact on | /autocompact off | /autocompact threshold <0-100>", self.cmd_autocompact)
        self.cmd_registry.register("dream", "Analyze the conversation and extract candidate notes, memory facts, and skills", self.cmd_dream)
        self.cmd_registry.register("delegate", "Delegate a self-contained task to an autonomous sub-agent: /delegate <task description> | /delegate depth [<n>]", self.cmd_delegate)
        self.cmd_registry.register("explore", "Run parallel speculative branch exploration: /explore <task description>", self.cmd_explore)
        self.cmd_registry.register("consensus", "Run an adversarial multi-model consensus audit: /consensus <question> | <proposal>", self.cmd_consensus)
        self.cmd_registry.register("goal", "View, set, or manage the pinned session goal: /goal <text> [| criterion 1 | criterion 2 ...] | /goal done <criterion #> | /goal clear", self.cmd_goal)
        self.cmd_registry.register("advisor", "Consult the advisor for a second opinion: /advisor <question>", self.cmd_advisor)
        self.cmd_registry.register("guard", "View or configure the tool-call safety guard: /guard [on|off] | /guard mode [supervised|autonomous] | /guard model [<key>] | /guard trust <tool>", self.cmd_guard)
        self.cmd_registry.register("mode", "View or switch operating mode: /mode [plan|build|review|yolo]", self.cmd_mode)
        self.cmd_registry.register("retry", "Retry the last LLM response turn", self.cmd_retry)
        self.cmd_registry.register("context", "Display context window, tool schemas, and MCP status", self.cmd_context)
        self.cmd_registry.register("system", "Show the system prompt, or set it: /system <text> | /system clear", self.cmd_system)
        self.cmd_registry.register("note", "View notes, or edit them: /note append <text> | /note clear", self.cmd_note)
        self.cmd_registry.register("memory", "View memory, or edit it: /memory save <key> <value> | /memory get <key> | /memory search <query> | /memory delete <key> | /memory clear", self.cmd_memory)
        self.cmd_registry.register("skills", "List skills, or toggle one: /skills enable <name> | /skills disable <name>", self.cmd_skills)
        self.cmd_registry.register("tools", "List registered tools, or toggle inclusion: /tools on | /tools off", self.cmd_tools)
        self.cmd_registry.register("proxy", "Toggle sub-agent tool proxy distillation: /proxy on | /proxy off", self.cmd_proxy)
        self.cmd_registry.register("selfheal", "Toggle automatic tool-error recovery: /selfheal on | /selfheal off", self.cmd_selfheal)
        self.cmd_registry.register("dirs", "List allowed directories, or edit them: /dirs add <path> | /dirs remove <path> | /dirs clear", self.cmd_dirs)
        self.cmd_registry.register("mcps", "List MCP servers, or toggle them: /mcps on | /mcps off | /mcps enable <server> | /mcps disable <server>", self.cmd_mcps)
        self.cmd_registry.register("debug", "Toggle debug mode (CoT & tool traces): /debug on | /debug off", self.cmd_debug)
        self.cmd_registry.register("version", "Show the current Mesh version", self.cmd_version)
        self.cmd_registry.register("exit", "Exit Mesh", self.cmd_exit)

    async def cmd_help(self, args):
        console.print("\n[success]Available Slash Commands:[/success]\n")

        table = Table(show_header=False, box=None, padding=(0, 1, 0, 2))
        table.add_column("Command", style="label", no_wrap=True)
        # Descriptions are rendered as plain Text (not markup) so literal
        # characters like [key] or <path> in usage hints are shown exactly
        # as written instead of being parsed as Rich style tags and dropped.
        table.add_column("Description")

        for cmd, desc in self.cmd_registry.list_commands().items():
            table.add_row(cmd, Text(desc))

        console.print(table)
        console.print()

    async def cmd_version(self, args):
        console.print(f"[brand]Mesh[/brand] version [accent]{__version__}[/accent]")

    async def cmd_status(self, args):
        model_cfg, provider_cfg = self.config_mgr.get_active_model_and_provider()
        sys_idx = next((i for i, m in enumerate(self.messages) if m.get("role") == "system"), None)
        sys_prompt = self.messages[sys_idx]["content"] if sys_idx is not None else "None"
        
        console.print(f"\n[success]=== MESH STATUS (v{__version__}) ===[/success]\n")
        console.print(f"• [label]Active Model:[/label] {model_cfg.name} ({self.config_mgr.config.active_model})")
        console.print(f"  [dim]Provider: {provider_cfg.name} | Base URL: {provider_cfg.base_url} | Model ID: {model_cfg.model_id}[/dim]")
        
        tools_state = "[success]ENABLED[/success]" if self.tools_enabled else "[error]DISABLED[/error]"
        proxy_state = "[success]ON[/success]" if self.subagent_proxy.enabled else "[error]OFF[/error]"
        selfheal_state = "[success]ON[/success]" if self.self_healer.enabled else "[error]OFF[/error]"
        debug_state = "[success]ON[/success]" if self.debug_mode else "[error]OFF[/error]"
        
        schemas = self.tool_registry.get_schemas()
        console.print(f"• [label]Tools:[/label] {tools_state} ({len(schemas)} active schemas)")
        console.print(f"• [label]Sub-Agent Proxy Distillation:[/label] {proxy_state}")
        console.print(f"• [label]Self-Healing Tool-Error Recovery:[/label] {selfheal_state}")
        console.print(f"• [label]Delegation Recursion Depth:[/label] {self.config_mgr.config.max_delegation_depth}")
        guard_state = "[success]ON[/success]" if self.safety_guard.enabled else "[error]OFF[/error]"
        guard_model_str = self.config_mgr.config.guard_model or f"{self.config_mgr.config.active_model} (active)"
        console.print(
            f"• [label]Safety Guard:[/label] {guard_state} "
            f"(mode: {self.config_mgr.config.guard_autonomy}, model: {guard_model_str})"
        )
        advisor_model_str = self.config_mgr.config.advisor_model or f"{self.config_mgr.config.active_model} (active)"
        console.print(f"• [label]Advisor Model:[/label] {advisor_model_str}")
        console.print(f"• [label]Mode:[/label] {modes.MODES[self.current_mode].label}")
        console.print(f"• [label]Debug Mode:[/label] {debug_state}")
        
        skills = self.skill_registry.list_skills()
        active_skills_count = sum(1 for s in skills.values() if s.enabled)
        console.print(f"• [label]Skills:[/label] {active_skills_count}/{len(skills)} active")
        
        mcp_info = self.mcp_manager.get_server_info()
        connected_mcp_count = sum(1 for details in mcp_info.values() if details["connected"])
        global_mcp_state = "[success]ENABLED[/success]" if self.mcp_manager.global_enabled else "[error]DISABLED[/error]"
        console.print(f"• [label]MCP Servers:[/label] {global_mcp_state} ({connected_mcp_count}/{len(mcp_info)} connected)")
        
        console.print(f"• [label]Allowed Directories:[/label] {len(self.permission_manager.allowed_dirs)} directories")

        est_tokens = estimate_tokens(self.messages)
        window = max(1, model_cfg.context_window)
        usage_pct = int((est_tokens / window) * 100)
        autocompact_state = "[success]ON[/success]" if self.config_mgr.config.auto_compact else "[error]OFF[/error]"
        console.print(
            f"• [label]Context Window:[/label] {len(self.messages)} messages, "
            f"~{est_tokens}/{window} est. tokens ({usage_pct}%)"
        )
        console.print(
            f"• [label]Auto-Compaction:[/label] {autocompact_state} "
            f"(triggers at {int(self.config_mgr.config.auto_compact_threshold * 100)}%)"
        )
        console.print(f"• [label]System Prompt Length:[/label] {len(sys_prompt)} chars (~{len(sys_prompt.split())} words)")

        if self.goal_tool.has_goal():
            snapshot = self.goal_tool.snapshot()
            crit_str = f", {snapshot['criteria_complete']}/{snapshot['criteria_total']} criteria met" if snapshot["criteria_total"] else ""
            console.print(f"• [label]Goal:[/label] {snapshot['goal']}{crit_str}\n")
        else:
            console.print("• [label]Goal:[/label] [muted]none set[/muted]\n")

    async def cmd_models(self, args):
        active = self.config_mgr.config.active_model
        console.print("[success]Configured Models:[/success]")
        for key, model_cfg in self.config_mgr.config.models.items():
            provider_cfg = self.config_mgr.config.providers.get(model_cfg.provider)
            provider_name = provider_cfg.name if provider_cfg else model_cfg.provider
            
            mark = "[accent]*[/accent]" if key == active else " "
            console.print(
                f"{mark} [label]{key}[/label] -> {model_cfg.name} via "
                f"[brand]{provider_name}[/brand] ([dim]{model_cfg.model_id}[/dim]) "
                f"[dim]— {model_cfg.context_window} token context window[/dim]"
            )

    async def cmd_switch(self, args):
        models_dict = self.config_mgr.config.models
        if not models_dict:
            console.print("[error]No models configured in models.json.[/error]")
            return

        model_keys = list(models_dict.keys())

        if args:
            target_key = args[0]
            if target_key not in models_dict:
                console.print(f"[error]Model key '{target_key}' not found in models.json.[/error]")
                return
            selected_key = target_key
        else:
            active_key = self.config_mgr.config.active_model
            current_idx = model_keys.index(active_key) if active_key in model_keys else 0

            def render_switch_menu(selected_idx: int):
                lines = ["\n[success]Select a Model to Switch to:[/success]", "[dim]Use ↑/↓ Arrow Keys to navigate, Enter to select:[/dim]\n"]
                for idx, key in enumerate(model_keys):
                    cfg = models_dict[key]
                    provider_cfg = self.config_mgr.config.providers.get(cfg.provider)
                    p_name = provider_cfg.name if provider_cfg else cfg.provider
                    
                    is_active = (key == active_key)
                    active_tag = " [accent](active)[/accent]" if is_active else ""
                    
                    item_text = f"{cfg.name} ({key}) via {p_name}{active_tag}"
                    
                    if idx == selected_idx:
                        lines.append(f"  [accent]❯ 🔘 {item_text}[/accent]")
                    else:
                        lines.append(f"    [dim]⚪ {item_text}[/dim]")
                return Text.from_markup("\n".join(lines))

            def interactive_switch():
                if not sys.stdin.isatty():
                    console.print("[accent]Available Models:[/accent]")
                    for idx, k in enumerate(model_keys, 1):
                        console.print(f"  {idx}. {k}")
                    raw = input("Choice > ").strip()
                    if raw.isdigit() and 1 <= int(raw) <= len(model_keys):
                        return model_keys[int(raw) - 1]
                    return raw

                nonlocal current_idx
                with Live(render_switch_menu(current_idx), console=console, auto_refresh=False, vertical_overflow="visible") as live:
                    while True:
                        live.update(render_switch_menu(current_idx), refresh=True)
                        try:
                            key = _read_single_key()
                        except Exception:
                            break

                        if key == "up":
                            current_idx = (current_idx - 1) % len(model_keys)
                        elif key == "down":
                            current_idx = (current_idx + 1) % len(model_keys)
                        elif key == "enter":
                            break

                return model_keys[current_idx]

            loop = asyncio.get_running_loop()
            selected_key = await loop.run_in_executor(None, interactive_switch)

        try:
            self.config_mgr.set_active_model(selected_key)
            model_cfg, provider_cfg = self.config_mgr.get_active_model_and_provider()
            console.print(f"[success]Switched active model to: [label]{selected_key}[/label] ({model_cfg.name} via {provider_cfg.name})[/success]")
        except Exception as e:
            console.print(f"[error]Error switching model: {e}[/error]")

    async def cmd_clear(self, args):
        self.update_system_message()
        console.print("[warning]Conversation context cleared (system prompt and skills preserved).[/warning]")

    async def cmd_compact(self, args):
        console.print("[warning]Analyzing and compacting conversation history...[/warning]")
        new_messages, success, details = await compact_messages(self.messages, self.config_mgr)
        if success:
            self.messages = new_messages
            console.print(f"[success]Compaction Successful![/success] {details}")
        else:
            console.print(f"[warning]{details}[/warning]")

    async def cmd_autocompact(self, args):
        cfg = self.config_mgr.config

        if not args:
            state_str = "[success]ON[/success]" if cfg.auto_compact else "[error]OFF[/error]"
            try:
                model_cfg, _ = self.config_mgr.get_active_model_and_provider()
                window_info = f" (active model context window: {model_cfg.context_window} tokens)"
            except Exception:
                window_info = ""
            console.print(
                f"Auto-compaction is currently {state_str}, triggering at "
                f"[accent]{int(cfg.auto_compact_threshold * 100)}%[/accent] of the active model's "
                f"context window{window_info}."
            )
            console.print("Usage: [warning]/autocompact on[/warning] | [warning]/autocompact off[/warning] | [warning]/autocompact threshold <0-100>[/warning]")
            return

        action = args[0].lower()
        if action == "on":
            cfg.auto_compact = True
            console.print("[success]Auto-compaction ENABLED.[/success]")
        elif action == "off":
            cfg.auto_compact = False
            console.print("[warning]Auto-compaction DISABLED.[/warning]")
        elif action == "threshold" and len(args) > 1:
            try:
                pct = float(args[1])
            except ValueError:
                console.print("[error]Threshold must be a number between 0 and 100.[/error]")
                return
            if not (0 < pct <= 100):
                console.print("[error]Threshold must be between 0 and 100.[/error]")
                return
            cfg.auto_compact_threshold = pct / 100.0
            console.print(f"[success]Auto-compaction threshold set to {pct:.0f}% of the context window.[/success]")
        else:
            console.print("[error]Usage: /autocompact on | /autocompact off | /autocompact threshold <0-100>[/error]")

    async def cmd_dream(self, args):
        console.print("[brand]💤 Dreaming...[/brand] [dim]Analyzing the conversation for reusable notes, memories, and skills.[/dim]")

        extraction, error = await dream_extract(self.messages, self.config_mgr)
        if error:
            console.print(f"[warning]{error}[/warning]")
            return

        notes = extraction["notes"]
        memory_items = extraction["memory"]
        skills = extraction["skills"]

        if not notes and not memory_items and not skills:
            console.print("[dim]Nothing worth extracting from this conversation.[/dim]")
            return

        def prompt_selection() -> str:
            try:
                return input("Selection > ").strip()
            except (EOFError, KeyboardInterrupt):
                return ""

        def resolve_indices(raw: str, count: int) -> set:
            raw = raw.lower().strip()
            if raw in ("all", "a", "y", "yes"):
                return set(range(count))
            if raw in ("none", "n", "no", "", "skip"):
                return set()
            indices = set()
            for part in raw.replace(" ", "").split(","):
                if part.isdigit():
                    idx = int(part) - 1
                    if 0 <= idx < count:
                        indices.add(idx)
            return indices

        loop = asyncio.get_running_loop()
        applied_notes = applied_memory = applied_skills = 0

        if notes:
            console.print(f"\n[label]📝 Candidate Notes ({len(notes)}):[/label]")
            for i, n in enumerate(notes, 1):
                console.print(f"  {i}. {n}")
            console.print("[dim]Enter numbers to save (e.g. 1,3), 'all', or 'none':[/dim]")
            raw = await loop.run_in_executor(None, prompt_selection)
            chosen = resolve_indices(raw, len(notes))
            for i in sorted(chosen):
                _append_notes(f"- {notes[i]}")
            applied_notes = len(chosen)

        if memory_items:
            console.print(f"\n[label]🧠 Candidate Memory Facts ({len(memory_items)}):[/label]")
            for i, m in enumerate(memory_items, 1):
                console.print(f"  {i}. [accent]{m['key']}[/accent] = {m['value']}")
            console.print("[dim]Enter numbers to save (e.g. 1,3), 'all', or 'none':[/dim]")
            raw = await loop.run_in_executor(None, prompt_selection)
            chosen = resolve_indices(raw, len(memory_items))
            if chosen:
                mem = _load_memory()
                for i in chosen:
                    mem[memory_items[i]["key"]] = memory_items[i]["value"]
                _save_memory(mem)
            applied_memory = len(chosen)

        if skills:
            console.print(f"\n[label]🛠️ Candidate Skills ({len(skills)}):[/label]")
            existing_names = set(self.skill_registry.list_skills().keys())
            for i, s in enumerate(skills, 1):
                dup_tag = " [warning](exists - will be overwritten)[/warning]" if s["name"] in existing_names else ""
                console.print(f"  {i}. [accent]{s['name']}[/accent]{dup_tag} - {s['description']}")
            console.print("[dim]Enter numbers to save (e.g. 1,3), 'all', or 'none':[/dim]")
            raw = await loop.run_in_executor(None, prompt_selection)
            chosen = resolve_indices(raw, len(skills))
            for i in chosen:
                s = skills[i]
                decl = DeclarativeSkill(
                    name=s["name"],
                    description=s["description"] or "Skill extracted via /dream.",
                    system_instruction=s["system_instruction"],
                    enabled=True
                )
                self.skill_registry.register(decl)
            if chosen:
                self.skill_registry.save_to_file()
                self.update_system_message()
            applied_skills = len(chosen)

        console.print(
            f"\n[success]Dream complete.[/success] Saved {applied_notes} note(s), "
            f"{applied_memory} memory fact(s), and {applied_skills} skill(s)."
        )

    async def cmd_delegate(self, args):
        if not args:
            console.print("[error]Usage: /delegate <task description> | /delegate depth [<n>][/error]")
            return

        if args[0].lower() == "depth":
            if len(args) == 1:
                console.print(
                    f"Delegation recursion depth is currently [accent]{self.config_mgr.config.max_delegation_depth}[/accent] "
                    f"(1 = no recursion beyond the first sub-agent).\nUsage: [warning]/delegate depth <n>[/warning]"
                )
                return
            try:
                n = int(args[1])
            except ValueError:
                console.print("[error]Usage: /delegate depth <n> (n must be a positive integer)[/error]")
                return
            if n < 1:
                console.print("[error]Depth must be at least 1.[/error]")
                return
            self.config_mgr.config.max_delegation_depth = n
            console.print(f"[success]Delegation recursion depth set to {n}.[/success]")
            return

        task = " ".join(args)
        result = await delegation.run_delegated_task(
            task=task,
            tool_registry=self.tool_registry,
            config_mgr=self.config_mgr,
        )

        status = result.get("status")
        turns_used = result.get("turns_used", 0)
        n_calls = len(result.get("tool_calls", []))

        if status == "success":
            console.print(
                f"\n[success]Sub-agent report[/success] "
                f"[dim]({turns_used} turn(s), {n_calls} tool call(s)):[/dim]\n{result['report']}\n"
            )
        elif status == "max_turns_reached":
            console.print(
                f"\n[warning]{result['report']}[/warning] "
                f"[dim]({n_calls} tool call(s) made)[/dim]\n"
            )
        else:
            console.print(f"\n[error]Delegation failed:[/error] {result.get('error', 'Unknown error')}\n")

    async def cmd_explore(self, args):
        if not args:
            console.print("[error]Usage: /explore <task description>[/error]")
            return

        task = " ".join(args)
        result = await explore.explore_branches(
            task=task,
            strategies=None,
            tool_registry=self.tool_registry,
            config_mgr=self.config_mgr
        )

        if result["status"] == "success":
            console.print(f"\n[success]🌲 Exploration Swarm Synthesis:[/success]\n\n{result['synthesis']}\n")
        else:
            console.print(f"[error]Exploration failed:[/error] {result.get('error', 'Unknown error')}")

    async def cmd_consensus(self, args):
        if not args:
            console.print("[error]Usage: /consensus <question/task> | <proposed solution>[/error]")
            return

        raw = " ".join(args)
        if "|" in raw:
            parts = raw.split("|", 1)
            question, proposal = parts[0].strip(), parts[1].strip()
        else:
            question = raw
            proposal = "Evaluate the optimal technical solution for this task."

        result = await consensus.get_consensus(
            question=question,
            proposal=proposal,
            config_mgr=self.config_mgr
        )

        if result["status"] == "success":
            console.print(f"\n[label]Auditor Critique ({result['auditor_model']}):[/label]\n{result['critique']}\n")
            console.print(f"[success]⚖️ Verified Consensus Recommendation ({result['proposer_model']}):[/success]\n{result['consensus_recommendation']}\n")
        else:
            console.print(f"[error]Consensus audit failed:[/error] {result.get('error', 'Unknown error')}")

    async def cmd_goal(self, args):
        if not args:
            self.goal_tool.render(console)
            return

        subcmd = args[0].lower()

        if subcmd == "clear":
            await self.goal_tool.execute("clear")
            console.print("[warning]Goal cleared.[/warning]")

        elif subcmd == "done" and len(args) >= 2:
            try:
                idx = int(args[1])
            except ValueError:
                console.print("[error]Usage: /goal done <criterion number>[/error]")
                return
            result = await self.goal_tool.execute("complete_criterion", criterion_index=idx)
            if "error" in result:
                console.print(f"[error]{result['error']}[/error]")
            else:
                console.print(f"[success]Marked criterion #{idx} complete.[/success]")
                self.goal_tool.render(console)

        else:
            # Anything else is treated as the goal text itself, optionally
            # followed by success criteria separated by '|', e.g.
            # /goal Ship the export feature | CSV export works | Tests pass
            raw = " ".join(args)
            parts = [p.strip() for p in raw.split("|")]
            goal_text, criteria = parts[0], [p for p in parts[1:] if p]

            result = await self.goal_tool.execute("set", goal=goal_text, success_criteria=criteria)
            if "error" in result:
                console.print(f"[error]{result['error']}[/error]")
            else:
                self.goal_tool.render(console)

    async def cmd_advisor(self, args):
        if not args:
            console.print("[error]Usage: /advisor <question>[/error]")
            return

        question = " ".join(args)
        console.print(f"[brand]🧭 Consulting advisor:[/brand] {question}")

        result = await advisor.get_advice(question=question, config_mgr=self.config_mgr)
        if result["status"] == "error":
            console.print(f"[error]{result['error']}[/error]")
        else:
            console.print(f"\n[success]Advice[/success] [dim](from {result['advisor_model']}):[/dim]\n{result['advice']}\n")

    async def cmd_guard(self, args):
        cfg = self.config_mgr.config

        if not args:
            state_str = "[success]ON[/success]" if self.safety_guard.enabled else "[error]OFF[/error]"
            model_str = cfg.guard_model or f"{cfg.active_model} (active model)"
            trusted = ", ".join(sorted(self.safety_guard.get_session_trusted_tools())) or "none"
            console.print(
                f"Safety Guard is currently {state_str}, mode [accent]{cfg.guard_autonomy}[/accent], "
                f"using model [accent]{model_str}[/accent].\n"
                f"Session-trusted tools: [dim]{trusted}[/dim]\n"
                f"Usage: [warning]/guard on[/warning] | [warning]/guard off[/warning] | "
                f"[warning]/guard mode supervised[/warning] | [warning]/guard mode autonomous[/warning] | "
                f"[warning]/guard model <key>[/warning] | [warning]/guard trust <tool_name>[/warning]"
            )
            return

        sub = args[0].lower()

        if sub == "on":
            self.safety_guard.enabled = True
            console.print("[success]Safety Guard ENABLED.[/success]")
        elif sub == "off":
            self.safety_guard.enabled = False
            console.print("[warning]Safety Guard DISABLED - guarded tool calls will run unchecked.[/warning]")
        elif sub == "mode" and len(args) >= 2:
            mode = args[1].lower()
            if mode not in ("supervised", "autonomous"):
                console.print("[error]Usage: /guard mode supervised | /guard mode autonomous[/error]")
                return
            cfg.guard_autonomy = mode
            if self.current_mode == "yolo":
                self._pre_yolo_guard_autonomy = mode
            console.print(f"[success]Safety Guard mode set to '{mode}'.[/success]")
        elif sub == "model":
            if len(args) == 1:
                cfg.guard_model = None
                console.print("[success]Safety Guard model reset to the active model.[/success]")
                return
            key = args[1]
            if key not in cfg.models:
                console.print(f"[error]Unknown model key '{key}'. See /models for valid keys.[/error]")
                return
            cfg.guard_model = key
            console.print(f"[success]Safety Guard model set to '{key}'.[/success]")
        elif sub == "trust" and len(args) >= 2:
            tool_name = args[1]
            self.safety_guard.trust_tool_for_session(tool_name)
            console.print(f"[success]'{tool_name}' will no longer be guard-checked for the rest of this session.[/success]")
        else:
            console.print(
                "[error]Usage: /guard [on|off] | /guard mode [supervised|autonomous] | "
                "/guard model [<key>] | /guard trust <tool_name>[/error]"
            )

    async def cmd_mode(self, args):
        if not args:
            current = modes.MODES[self.current_mode]
            console.print(f"Current mode: [accent]{current.label}[/accent] - {current.description}\n")
            console.print("[label]Available modes:[/label]")
            for key, mode_def in modes.MODES.items():
                marker = "[accent]*[/accent]" if key == self.current_mode else " "
                console.print(f"  {marker} [label]{key}[/label] - {mode_def.description}")
            console.print("\nUsage: [warning]/mode <name>[/warning]")
            return

        requested = args[0].lower()
        if requested not in modes.MODES:
            valid = ", ".join(modes.MODES.keys())
            console.print(f"[error]Unknown mode '{requested}'. Valid modes: {valid}[/error]")
            return

        if requested == self.current_mode:
            console.print(f"[dim]Already in {modes.MODES[requested].label} mode.[/dim]")
            return

        leaving_yolo = self.current_mode == "yolo" and requested != "yolo"
        entering_yolo = requested == "yolo" and self.current_mode != "yolo"

        if entering_yolo:
            # Remember whatever the user had explicitly set, so leaving
            # YOLO restores their actual prior choice rather than a
            # hardcoded default.
            self._pre_yolo_guard_autonomy = self.config_mgr.config.guard_autonomy
            self._pre_yolo_permission_auto_approve = self.permission_manager.auto_approve
            self.config_mgr.config.guard_autonomy = "autonomous"
            self.permission_manager.auto_approve = True
        elif leaving_yolo:
            if self._pre_yolo_guard_autonomy is not None:
                self.config_mgr.config.guard_autonomy = self._pre_yolo_guard_autonomy
            if self._pre_yolo_permission_auto_approve is not None:
                self.permission_manager.auto_approve = self._pre_yolo_permission_auto_approve
            self._pre_yolo_guard_autonomy = None
            self._pre_yolo_permission_auto_approve = None

        self.current_mode = requested
        self.tool_registry.mode_blocked_tools = modes.blocked_tools_for_mode(requested, self.tool_registry)
        self.update_system_message()

        mode_def = modes.MODES[requested]
        console.print(f"[success]Switched to {mode_def.label} Mode.[/success] {mode_def.description}")
        if self.tool_registry.mode_blocked_tools:
            blocked_str = ", ".join(sorted(self.tool_registry.mode_blocked_tools))
            console.print(f"[dim]Unavailable in this mode: {blocked_str}[/dim]")

    async def cmd_retry(self, args):
        last_user_idx = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                last_user_idx = i
                break

        if last_user_idx is None:
            console.print("[warning]No user message found in context to retry.[/warning]")
            return

        self.messages = self.messages[:last_user_idx + 1]
        console.print("[warning]Retrying last completion turn...[/warning]")
        await self.process_inference()

    async def cmd_note(self, args):
        if not args:
            notes = _read_notes()
            if not notes.strip():
                console.print("[dim]notes.md is currently empty.[/dim]")
            else:
                console.print("\n[success]=== Current Notes (notes.md) ===[/success]\n")
                console.print(Markdown(notes))
                console.print()
            console.print("Usage: [warning]/note[/warning], [warning]/note append <text>[/warning], or [warning]/note clear[/warning]\n")
            return

        subcmd = args[0].lower()
        if subcmd == "clear":
            _write_notes("")
            console.print("[warning]notes.md cleared.[/warning]")
        elif subcmd == "append":
            text_to_append = " ".join(args[1:]).strip()
            if not text_to_append:
                console.print("[error]Usage: /note append <text>[/error]")
                return
            _append_notes(text_to_append)
            console.print("[success]Appended text to notes.md.[/success]")
        else:
            text_to_append = " ".join(args).strip()
            _append_notes(text_to_append)
            console.print("[success]Appended text to notes.md.[/success]")

    async def cmd_memory(self, args):
        mem = _load_memory()

        if not args:
            console.print("\n[success]=== Saved Memory Items (memory.json) ===[/success]\n")
            if not mem:
                console.print("  [dim]No memory keys saved.[/dim]")
            else:
                for k, v in mem.items():
                    console.print(f"  • [label]{k}[/label]: {v}")
            console.print("\nUsage: [warning]/memory[/warning], [warning]/memory save <key> <value>[/warning], [warning]/memory get <key>[/warning], [warning]/memory search <query>[/warning], [warning]/memory delete <key>[/warning], or [warning]/memory clear[/warning]\n")
            return

        subcmd = args[0].lower()

        if subcmd == "save" and len(args) >= 3:
            key = args[1]
            val = " ".join(args[2:]).strip()
            mem[key] = val
            _save_memory(mem)
            console.print(f"[success]Saved memory key '{key}'.[/success]")

        elif subcmd == "get" and len(args) >= 2:
            key = args[1]
            if key in mem:
                console.print(f"[label]{key}:[/label] {mem[key]}")
            else:
                console.print(f"[error]Memory key '{key}' not found.[/error]")

        elif subcmd == "search" and len(args) >= 2:
            query = " ".join(args[1:]).strip()
            result = await memory_search.semantic_memory_search(query, mem, self.config_mgr, verbose=True)

            if result["status"] == "empty":
                console.print("[dim]Memory is empty - nothing to search.[/dim]")
            elif result["status"] == "error":
                console.print(f"[error]Search failed:[/error] {result.get('error', 'Unknown error')}")
            else:
                matches = result["matches"]
                if result.get("answer"):
                    console.print(f"\n[success]Answer:[/success] {result['answer']}")
                if matches:
                    console.print("\n[label]Matching memory entries:[/label]")
                    for m in matches:
                        console.print(f"  • [accent]{m['key']}[/accent]: {m['value']}  [dim]({m['why']})[/dim]")
                elif not result.get("answer"):
                    console.print("[dim]No relevant memory entries found.[/dim]")

        elif subcmd == "delete" and len(args) >= 2:
            key = args[1]
            if key in mem:
                del mem[key]
                _save_memory(mem)
                console.print(f"[warning]Deleted memory key '{key}'.[/warning]")
            else:
                console.print(f"[error]Memory key '{key}' not found.[/error]")

        elif subcmd == "clear":
            _save_memory({})
            console.print("[warning]Cleared all persistent memories from memory.json.[/warning]")

        else:
            console.print("[error]Usage: /memory save <key> <value> | /memory get <key> | /memory search <query> | /memory delete <key> | /memory clear[/error]")

    async def cmd_skills(self, args):
        skills = self.skill_registry.list_skills()
        if not args:
            console.print("\n[success]Registered Skills:[/success]")
            if not skills:
                console.print("  [dim]No skills registered.[/dim]")
            for name, skill in skills.items():
                status = "[success]ENABLED[/success]" if skill.enabled else "[error]DISABLED[/error]"
                console.print(f"• [label]{name}[/label] ({status}): {escape(skill.description)}")
                tools = skill.get_tools()
                if tools:
                    tool_names = ", ".join([t.name for t in tools])
                    console.print(f"  [dim]Tools provided: {tool_names}[/dim]")
            console.print("\nUsage: [warning]/skills enable <name>[/warning] or [warning]/skills disable <name>[/warning]\n")
            return

        action = args[0].lower()
        if action in ["enable", "disable"] and len(args) > 1:
            target = args[1]
            enable_flag = (action == "enable")
            success = self.skill_registry.set_skill_state(target, enable_flag)
            if success:
                self.update_system_message()
                console.print(f"[success]Skill '{target}' set to {action}d.[/success]")
            else:
                console.print(f"[error]Skill '{target}' not found.[/error]")
        else:
            console.print("[error]Usage: /skills enable <name> or /skills disable <name>[/error]")

    async def cmd_dirs(self, args):
        if not args:
            console.print("\n[success]Currently Allowed Directories:[/success]")
            for d in self.permission_manager.allowed_dirs:
                console.print(f"  • [label]{d}[/label]")
            console.print("\nUsage: [warning]/dirs add <path>[/warning] or [warning]/dirs remove <path>[/warning] or [warning]/dirs clear[/warning]\n")
            return

        action = args[0].lower()
        if action == "add" and len(args) > 1:
            target_path = " ".join(args[1:])
            added = self.permission_manager.add_dir(target_path)
            console.print(f"[success]Added directory to allowed list:[/success] {added}")
        elif action == "remove" and len(args) > 1:
            target_path = " ".join(args[1:])
            removed = self.permission_manager.remove_dir(target_path)
            if removed:
                console.print(f"[warning]Removed directory from allowed list:[/warning] {target_path}")
            else:
                console.print(f"[error]Directory not found in allowed list:[/error] {target_path}")
        elif action == "clear":
            self.permission_manager.allowed_dirs = [str(os.getcwd())]
            console.print("[warning]Reset allowed directories to Current Working Directory.[/warning]")
        else:
            console.print("[error]Usage: /dirs add <path> | /dirs remove <path> | /dirs clear[/error]")

    async def cmd_proxy(self, args):
        if not args:
            state_str = "[success]ON[/success]" if self.subagent_proxy.enabled else "[error]OFF[/error]"
            console.print(f"Sub-agent tool proxy distillation is currently {state_str}.\nUsage: [warning]/proxy on[/warning] or [warning]/proxy off[/warning]")
            return

        arg = args[0].lower()
        if arg == "on":
            self.subagent_proxy.enabled = True
            console.print("[success]Sub-agent tool proxy distillation ENABLED.[/success]")
        elif arg == "off":
            self.subagent_proxy.enabled = False
            console.print("[warning]Sub-agent tool proxy distillation DISABLED.[/warning]")
        else:
            console.print("[error]Invalid option. Use '/proxy on' or '/proxy off'.[/error]")

    async def cmd_selfheal(self, args):
        if not args:
            state_str = "[success]ON[/success]" if self.self_healer.enabled else "[error]OFF[/error]"
            console.print(
                f"Self-healing tool-error recovery is currently {state_str} "
                f"(mechanical retries: {self.self_healer.mechanical_retries}).\n"
                f"Usage: [warning]/selfheal on[/warning] or [warning]/selfheal off[/warning]"
            )
            return

        arg = args[0].lower()
        if arg == "on":
            self.self_healer.enabled = True
            console.print("[success]Self-healing tool-error recovery ENABLED.[/success]")
        elif arg == "off":
            self.self_healer.enabled = False
            console.print("[warning]Self-healing tool-error recovery DISABLED.[/warning]")
        else:
            console.print("[error]Invalid option. Use '/selfheal on' or '/selfheal off'.[/error]")

    async def cmd_context(self, args):
        console.print(f"\n[success]=== CONTEXT MESSAGES ({len(self.messages)} Messages) ===[/success]\n")
        for idx, msg in enumerate(self.messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", None)
            tool_call_id = msg.get("tool_call_id", None)

            header = f"[{idx}] Role: [label]{role}[/label]"
            if tool_call_id:
                header += f" | Tool Call ID: [dim]{tool_call_id}[/dim]"

            console.print(header)

            if content:
                console.print(f"  {content}")
            if tool_calls:
                console.print(f"  [dim italic]Tool Calls: {tool_calls}[/dim italic]")
            if not content and not tool_calls:
                console.print("  [dim]<empty>[/dim]")

            console.print()

        tools_state = "[success]ENABLED[/success]" if self.tools_enabled else "[error]DISABLED[/error]"
        proxy_state = "[success]ON[/success]" if self.subagent_proxy.enabled else "[error]OFF[/error]"
        console.print(f"[success]=== ACTIVE TOOL SCHEMAS ({tools_state} | Proxy Distillation: {proxy_state}) ===[/success]\n")
        if self.tools_enabled:
            schemas = self.tool_registry.get_schemas()
            if schemas:
                for s in schemas:
                    fn = s.get("function", {})
                    name = fn.get("name", "unnamed")
                    desc = fn.get("description", "No description")
                    params = fn.get("parameters", {}).get("properties", {})
                    param_keys = ", ".join(params.keys()) if params else "none"
                    console.print(f"• [label]{name}[/label]: {escape(desc)}")
                    console.print(f"  [dim]Parameters: ({param_keys})[/dim]")
            else:
                console.print("  [dim]No tools currently registered.[/dim]")
        else:
            console.print("  [dim]Tools are disabled (/tools off). No schemas are sent to the model.[/dim]")
        console.print()

        global_mcp_str = "[success]ENABLED[/success]" if self.mcp_manager.global_enabled else "[error]DISABLED[/error]"
        console.print(f"[success]=== MCP SERVERS & TOOLS (Global MCP: {global_mcp_str}) ===[/success]\n")
        mcp_info = self.mcp_manager.get_server_info()
        if mcp_info:
            for name, details in mcp_info.items():
                status = "[success]CONNECTED[/success]" if details["connected"] else "[error]DISCONNECTED[/error]"
                enabled_str = "[success]ENABLED[/success]" if details["enabled"] else "[error]DISABLED[/error]"
                cmd_str = f"{details['command']} {' '.join(details['args'])}" if details['command'] else "N/A"
                console.print(f"• [label]{name}[/label] ({status}) ({enabled_str}) — [dim]{escape(cmd_str)}[/dim]")
                
                tools = details.get("tools", [])
                if tools:
                    for t in tools:
                        t_name = t.get("name", "unnamed")
                        t_desc = t.get("description", "No description")
                        t_props = t.get("inputSchema", {}).get("properties", {})
                        t_args = ", ".join(t_props.keys()) if t_props else "none"
                        console.print(f"    - [accent]{t_name}[/accent]: {t_desc} [dim]({t_args})[/dim]")
                else:
                    console.print("    [dim]No tools exposed.[/dim]")
        else:
            console.print("  [dim]No MCP servers configured in mcps.json.[/dim]")
        console.print()

    async def cmd_system(self, args):
        sys_idx = next((i for i, m in enumerate(self.messages) if m.get("role") == "system"), None)

        if not args:
            current = self.messages[sys_idx]["content"] if sys_idx is not None else "[dim]<none>[/dim]"
            console.print(f"[success]Current System Prompt:[/success]\n{current}\n")
            console.print("Usage: [warning]/system [text][/warning] or [warning]/system clear[/warning]")
            return

        new_prompt = " ".join(args).strip()
        if new_prompt.lower() == "clear":
            if sys_idx is not None:
                self.messages.pop(sys_idx)
            console.print("[warning]System prompt cleared from context.[/warning]")
        else:
            if sys_idx is not None:
                self.messages[sys_idx]["content"] = new_prompt
            else:
                self.messages.insert(0, {"role": "system", "content": new_prompt})
            console.print(f"[success]System prompt updated to:[/success]\n{new_prompt}")

    async def cmd_tools(self, args):
        if not args:
            state_str = "[success]ON[/success]" if self.tools_enabled else "[error]OFF[/error]"
            console.print(f"Tool inclusion & execution is currently {state_str}.\n")
            console.print("[success]Available Registered Tools:[/success]")
            schemas = self.tool_registry.get_schemas()
            if not schemas:
                console.print("  [dim]No tools registered.[/dim]")
            for s in schemas:
                fn = s.get("function", {})
                name = fn.get("name", "unnamed")
                desc = fn.get("description", "No description")
                console.print(f"  • [label]{name}[/label]: {escape(desc)}")
            console.print("\nUsage: [warning]/tools on[/warning] or [warning]/tools off[/warning]")
            return

        arg = args[0].lower()
        if arg == "on":
            self.tools_enabled = True
            console.print("[success]Tool context inclusion & execution enabled.[/success]")
        elif arg == "off":
            self.tools_enabled = False
            console.print("[warning]Tool context inclusion & execution disabled.[/warning]")
        else:
            console.print("[error]Invalid option. Use '/tools on' or '/tools off'.[/error]")

    async def cmd_mcps(self, args):
        info = self.mcp_manager.get_server_info()
        if not info:
            console.print("[dim]No MCP servers configured in mcps.json.[/dim]")
            return

        if args:
            action = args[0].lower()
            if action == "on":
                self.mcp_manager.set_global_state(True, self.tool_registry)
                console.print("[success]All MCP tools globally ENABLED.[/success]")
                return
            elif action == "off":
                self.mcp_manager.set_global_state(False, self.tool_registry)
                console.print("[warning]All MCP tools globally DISABLED.[/warning]")
                return
            elif action in ["enable", "disable"] and len(args) > 1:
                target = args[1]
                enable_flag = (action == "enable")
                success = self.mcp_manager.set_server_state(target, enable_flag, self.tool_registry)
                if success:
                    state_str = "enabled" if enable_flag else "disabled"
                    console.print(f"[success]MCP Server '{target}' tools {state_str}.[/success]")
                else:
                    console.print(f"[error]MCP Server '{target}' not found.[/error]")
                return
            else:
                console.print("[error]Usage: /mcps on | /mcps off | /mcps enable <server_name> | /mcps disable <server_name>[/error]")
                return

        global_str = "[success]ENABLED[/success]" if self.mcp_manager.global_enabled else "[error]DISABLED[/error]"
        console.print(f"\n[success]Configured MCP Servers (Global MCP Status: {global_str}):[/success]\n")

        for name, details in info.items():
            status = "[success]CONNECTED[/success]" if details["connected"] else "[error]DISCONNECTED[/error]"
            enabled_str = "[success]ENABLED[/success]" if details["enabled"] else "[error]DISABLED[/error]"
            cmd_str = f"{details['command']} {' '.join(details['args'])}" if details['command'] else "N/A"
            
            console.print(f"• [label]{name}[/label] ({status}) ({enabled_str}) — Command: [dim]{escape(cmd_str)}[/dim]")
            
            if details["error"]:
                console.print(f"  [error]Error: {details['error']}[/error]")

            tools = details.get("tools", [])
            if tools:
                console.print("  [accent]Exposed Tools:[/accent]")
                for t in tools:
                    desc = t.get("description", "No description")
                    properties = t.get("inputSchema", {}).get("properties", {})
                    args_summary = ", ".join(properties.keys()) if properties else "none"
                    console.print(f"    - [text]{t['name']}[/text]: {escape(desc)}")
                    console.print(f"      [dim]Arguments: ({args_summary})[/dim]")
            else:
                console.print("  [dim]No tools exposed.[/dim]")
            console.print()

        console.print("Usage: [warning]/mcps on[/warning] | [warning]/mcps off[/warning] | [warning]/mcps enable <server_name>[/warning] | [warning]/mcps disable <server_name>[/warning]\n")

    async def cmd_debug(self, args):
        if not args:
            state_str = "[success]ON[/success]" if self.debug_mode else "[error]OFF[/error]"
            console.print(f"Debug mode is currently {state_str}. Usage: [warning]/debug on[/warning] or [warning]/debug off[/warning]")
            return

        arg = args[0].lower()
        if arg == "on":
            self.debug_mode = True
            self.subagent_proxy.debug_mode = True
            console.print("[success]Debug mode enabled.[/success] CoT and Tool execution details will be shown.")
        elif arg == "off":
            self.debug_mode = False
            self.subagent_proxy.debug_mode = False
            console.print("[warning]Debug mode disabled.[/warning] CoT will be hidden.")
        else:
            console.print("[error]Invalid debug option. Use '/debug on' or '/debug off'.[/error]")

    async def cmd_exit(self, args):
        console.print("[warning]Closing MCP connections and exiting. Goodbye![/warning]")
        try:
            await asyncio.wait_for(self.mcp_manager.close_all(), timeout=3.0)
        except Exception:
            pass
        sys.exit(0)

    async def run(self):
        console.print(f"[brand]Mesh v{__version__} Started.[/brand] Initializing MCP servers...")
        
        await self.mcp_manager.initialize_all(self.tool_registry)

        console.print("[brand]Ready.[/brand] Type [warning]/help[/warning] for commands or start chatting.\n")
        
        while True:
            try:
                user_input = input("User > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ["exit", "quit", "/exit"]:
                    await self.cmd_exit([])

                if self.cmd_registry.is_command(user_input):
                    handled = await self.cmd_registry.dispatch(user_input)
                    if not handled:
                        console.print("[error]Unknown command. Type /help for options.[/error]")
                    continue

                self.messages.append({"role": "user", "content": user_input})
                await self.process_inference()

            except (KeyboardInterrupt, EOFError):
                console.print("\n[warning]Exiting...[/warning]")
                try:
                    await asyncio.wait_for(self.mcp_manager.close_all(), timeout=2.0)
                except Exception:
                    pass
                break

    async def process_inference(self):
        max_turns = 10
        current_turn = 0

        while current_turn < max_turns:
            current_turn += 1

            try:
                model_cfg, provider_cfg = self.config_mgr.get_active_model_and_provider()
            except Exception as e:
                console.print(f"[error]Configuration Error:[/error] {e}")
                return

            self.messages, auto_compacted, compact_details = await maybe_auto_compact(self.messages, self.config_mgr)
            if auto_compacted:
                console.print(f"[warning]🗜️  {compact_details}[/warning]")

            provider = OpenAIProvider(model_cfg, provider_cfg)
            schemas = self.tool_registry.get_schemas() if self.tools_enabled else None
            if schemas and self.tool_registry.mode_blocked_tools:
                schemas = [s for s in schemas if s["function"]["name"] not in self.tool_registry.mode_blocked_tools]

            console.print(f"\n[info]Assistant ({model_cfg.name} via {provider_cfg.name})[/info] >")

            tool_calls_to_run = []

            async def chunk_generator():
                async for chunk in provider.stream_chat(self.messages, tools=schemas):
                    ctype = chunk["type"]
                    cval = chunk["value"]

                    if ctype == "tool_calls" and self.tools_enabled:
                        for tc in cval:
                            idx = tc.index
                            while len(tool_calls_to_run) <= idx:
                                tool_calls_to_run.append({"id": "", "name": "", "args": ""})
                            if tc.id:
                                tool_calls_to_run[idx]["id"] = tc.id
                            if tc.function and tc.function.name:
                                tool_calls_to_run[idx]["name"] = tc.function.name
                            if tc.function and tc.function.arguments:
                                tool_calls_to_run[idx]["args"] += tc.function.arguments
                    else:
                        yield chunk

            try:
                response_text, reasoning_text = await self.renderer.render_stream(
                    chunk_generator(), 
                    debug_mode=self.debug_mode
                )
            except Exception as e:
                console.print(
                    f"\n[error]API/Provider Error ({provider_cfg.name}):[/error] "
                    f"Could not connect to [dim]{provider_cfg.base_url}[/dim].\n"
                    f"[error]Details: {str(e)}[/error]\n"
                    f"[warning]Tip: Ensure your local server (e.g. LM Studio / Ollama) is running, or switch models using /switch.[/warning]"
                )
                return

            assistant_msg = {"role": "assistant"}
            if response_text:
                assistant_msg["content"] = response_text

            formatted_tool_calls = []
            if tool_calls_to_run and self.tools_enabled:
                for i, tool_call in enumerate(tool_calls_to_run):
                    tool_call_id = tool_call["id"] or f"call_{i+1}"
                    tool_call["id"] = tool_call_id
                    
                    formatted_tool_calls.append({
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_call["name"],
                            "arguments": tool_call["args"]
                        }
                    })
                assistant_msg["tool_calls"] = formatted_tool_calls

            self.messages.append(assistant_msg)

            if not tool_calls_to_run or not self.tools_enabled:
                break

            for tool_call in tool_calls_to_run:
                if self.debug_mode:
                    console.print(f"\n[brand]🔧 DEBUG - Tool Execution Request:[/brand] {tool_call['name']}({tool_call['args']})")
                else:
                    console.print(f"\n[accent]⚡ Tool Execution Request: {tool_call['name']}({tool_call['args']})[/accent]")

                tool_result = await self.tool_registry.execute(tool_call["name"], tool_call["args"])

                if self.debug_mode:
                    console.print(f"[brand]🔧 DEBUG - Tool Execution Result:[/brand]\n{tool_result}")
                
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result
                })


if __name__ == "__main__":
    mesh = Mesh()
    asyncio.run(mesh.run())