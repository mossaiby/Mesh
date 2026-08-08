import asyncio
import sys
import os
from rich.live import Live
from rich.markdown import Markdown
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
)
from tools.ask_tool import _read_single_key
from tools.note_tool import _read_notes, _write_notes, _append_notes
from tools.memory_tool import _load_memory, _save_memory
from commands.registry import CommandRegistry
from mcp.client import MCPManager
from skills import SkillRegistry, PythonCodingSkill
from compaction import compact_messages
from subagent import SubAgentProxy
from theme import console
from version import __version__



class Mesh:
    def __init__(self):
        self.config_mgr = ConfigManager()
        self.renderer = StreamRenderer()
        self.tool_registry = ToolRegistry()
        self.subagent_proxy = SubAgentProxy(self.config_mgr)
        self.tool_registry.subagent_proxy = self.subagent_proxy
        
        self.permission_manager = PermissionManager()
        self.skill_registry = SkillRegistry(self.tool_registry)
        self.cmd_registry = CommandRegistry()
        self.mcp_manager = MCPManager()
        self.debug_mode: bool = False
        self.subagent_proxy.debug_mode = self.debug_mode
        self.tools_enabled: bool = True
        
        self.setup_defaults()

        model_cfg, _ = self.config_mgr.get_active_model_and_provider()
        self.update_system_message(model_cfg.system_prompt)

    def update_system_message(self, base_prompt: str = None):
        if not base_prompt:
            model_cfg, _ = self.config_mgr.get_active_model_and_provider()
            base_prompt = model_cfg.system_prompt or "You are a helpful text-based AI assistant."

        skill_instructions = self.skill_registry.get_combined_system_instructions()
        full_sys = base_prompt
        if skill_instructions:
            full_sys += f"\n\nActive Skills Instructions:\n{skill_instructions}"

        sys_idx = next((i for i, m in enumerate(self.messages) if m.get("role") == "system"), None) if hasattr(self, "messages") else None
        
        if sys_idx is not None:
            self.messages[sys_idx]["content"] = full_sys
        else:
            self.messages = [{"role": "system", "content": full_sys}]

    def setup_defaults(self):
        # 1. Register Base Tools with PermissionManager
        self.tool_registry.register(CalculatorTool())
        self.tool_registry.register(MemoryTool())
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
        
        # 2. Register Skills & Load skills.json
        self.skill_registry.register(PythonCodingSkill())
        self.skill_registry.load_from_file()

        # 3. Slash Commands
        self.cmd_registry.register("help", "Show available slash commands", self.cmd_help)
        self.cmd_registry.register("status", "Show current Mesh status overview (/status)", self.cmd_status)
        self.cmd_registry.register("models", "List configured models and providers", self.cmd_models)
        self.cmd_registry.register("switch", "Switch active model interactively or by key (/switch [key])", self.cmd_switch)
        self.cmd_registry.register("clear", "Clear conversation context window", self.cmd_clear)
        self.cmd_registry.register("compact", "Semantically summarize older conversation context (/compact)", self.cmd_compact)
        self.cmd_registry.register("retry", "Retry the last LLM response turn (/retry)", self.cmd_retry)
        self.cmd_registry.register("context", "Display context window, tool schemas, and MCP status", self.cmd_context)
        self.cmd_registry.register("system", "Show or set system prompt (/system [text] or /system clear)", self.cmd_system)
        self.cmd_registry.register("note", "Manage or view Markdown notes (/note, /note append <text>, /note clear)", self.cmd_note)
        self.cmd_registry.register("memory", "Manage key-value memories (/memory [save|get|delete|clear])", self.cmd_memory)
        self.cmd_registry.register("skills", "List available skills or enable/disable them (/skills [enable|disable] <name>)", self.cmd_skills)
        self.cmd_registry.register("tools", "Show tools or toggle tool context inclusion (/tools on|off)", self.cmd_tools)
        self.cmd_registry.register("proxy", "Toggle sub-agent tool proxy distillation (/proxy on|off)", self.cmd_proxy)
        self.cmd_registry.register("dirs", "List or add/remove allowed directories (/dirs [add|remove|clear] <path>)", self.cmd_dirs)
        self.cmd_registry.register("mcps", "List/toggle MCP servers (/mcps [on|off] or /mcps [enable|disable] <server>)", self.cmd_mcps)
        self.cmd_registry.register("debug", "Toggle or set debug mode (/debug on|off)", self.cmd_debug)
        self.cmd_registry.register("version", "Show the current Mesh version (/version)", self.cmd_version)
        self.cmd_registry.register("exit", "Exit Mesh", self.cmd_exit)

    async def cmd_help(self, args):
        console.print("[success]Available Slash Commands:[/success]")
        for cmd, desc in self.cmd_registry.list_commands().items():
            console.print(f"  [label]{cmd}[/label] - {desc}")

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
        debug_state = "[success]ON[/success]" if self.debug_mode else "[error]OFF[/error]"
        
        schemas = self.tool_registry.get_schemas()
        console.print(f"• [label]Tools:[/label] {tools_state} ({len(schemas)} active schemas)")
        console.print(f"• [label]Sub-Agent Proxy Distillation:[/label] {proxy_state}")
        console.print(f"• [label]Debug Mode:[/label] {debug_state}")
        
        skills = self.skill_registry.list_skills()
        active_skills_count = sum(1 for s in skills.values() if s.enabled)
        console.print(f"• [label]Skills:[/label] {active_skills_count}/{len(skills)} active")
        
        mcp_info = self.mcp_manager.get_server_info()
        connected_mcp_count = sum(1 for details in mcp_info.values() if details["connected"])
        global_mcp_state = "[success]ENABLED[/success]" if self.mcp_manager.global_enabled else "[error]DISABLED[/error]"
        console.print(f"• [label]MCP Servers:[/label] {global_mcp_state} ({connected_mcp_count}/{len(mcp_info)} connected)")
        
        console.print(f"• [label]Allowed Directories:[/label] {len(self.permission_manager.allowed_dirs)} directories")
        console.print(f"• [label]Context Window:[/label] {len(self.messages)} messages stored")
        console.print(f"• [label]System Prompt Length:[/label] {len(sys_prompt)} chars (~{len(sys_prompt.split())} words)\n")

    async def cmd_models(self, args):
        active = self.config_mgr.config.active_model
        console.print("[success]Configured Models:[/success]")
        for key, model_cfg in self.config_mgr.config.models.items():
            provider_cfg = self.config_mgr.config.providers.get(model_cfg.provider)
            provider_name = provider_cfg.name if provider_cfg else model_cfg.provider
            
            mark = "[accent]*[/accent]" if key == active else " "
            console.print(
                f"{mark} [label]{key}[/label] -> {model_cfg.name} via "
                f"[brand]{provider_name}[/brand] ([dim]{model_cfg.model_id}[/dim])"
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
            self.update_system_message(model_cfg.system_prompt)
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
            console.print("\nUsage: [warning]/memory[/warning], [warning]/memory save <key> <value>[/warning], [warning]/memory get <key>[/warning], [warning]/memory delete <key>[/warning], or [warning]/memory clear[/warning]\n")
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
            console.print("[error]Usage: /memory [save|get|delete|clear] <key> [value][/error]")

    async def cmd_skills(self, args):
        skills = self.skill_registry.list_skills()
        if not args:
            console.print("\n[success]Registered Skills:[/success]")
            if not skills:
                console.print("  [dim]No skills registered.[/dim]")
            for name, skill in skills.items():
                status = "[success]ENABLED[/success]" if skill.enabled else "[error]DISABLED[/error]"
                console.print(f"• [label]{name}[/label] [{status}]: {skill.description}")
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
            console.print("[error]Usage: /dirs [add|remove|clear] <path>[/error]")

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
                    console.print(f"• [label]{name}[/label]: {desc}")
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
                console.print(f"• [label]{name}[/label] [{status}] [{enabled_str}] — [dim]{cmd_str}[/dim]")
                
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
                console.print(f"  • [label]{name}[/label]: {desc}")
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
                console.print("[error]Usage: /mcps [on|off] or /mcps [enable|disable] <server_name>[/error]")
                return

        global_str = "[success]ENABLED[/success]" if self.mcp_manager.global_enabled else "[error]DISABLED[/error]"
        console.print(f"\n[success]Configured MCP Servers (Global MCP Status: {global_str}):[/success]\n")

        for name, details in info.items():
            status = "[success]CONNECTED[/success]" if details["connected"] else "[error]DISCONNECTED[/error]"
            enabled_str = "[success]ENABLED[/success]" if details["enabled"] else "[error]DISABLED[/error]"
            cmd_str = f"{details['command']} {' '.join(details['args'])}" if details['command'] else "N/A"
            
            console.print(f"• [label]{name}[/label] [{status}] [{enabled_str}] — Command: [dim]{cmd_str}[/dim]")
            
            if details["error"]:
                console.print(f"  [error]Error: {details['error']}[/error]")

            tools = details.get("tools", [])
            if tools:
                console.print("  [accent]Exposed Tools:[/accent]")
                for t in tools:
                    desc = t.get("description", "No description")
                    properties = t.get("inputSchema", {}).get("properties", {})
                    args_summary = ", ".join(properties.keys()) if properties else "none"
                    console.print(f"    - [text]{t['name']}[/text]: {desc}")
                    console.print(f"      [dim]Arguments: ({args_summary})[/dim]")
            else:
                console.print("  [dim]No tools exposed.[/dim]")
            console.print()

        console.print("Usage: [warning]/mcps [on|off][/warning] or [warning]/mcps [enable|disable] <server_name>[/warning]\n")

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

            provider = OpenAIProvider(model_cfg, provider_cfg)
            schemas = self.tool_registry.get_schemas() if self.tools_enabled else None

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
                    console.print(f"\n[brand]🔧 [DEBUG] Tool Execution Request:[/brand] {tool_call['name']}({tool_call['args']})")
                else:
                    console.print(f"\n[accent]⚡ Tool Execution Request: {tool_call['name']}({tool_call['args']})[/accent]")

                tool_result = await self.tool_registry.execute(tool_call["name"], tool_call["args"])

                if self.debug_mode:
                    console.print(f"[brand]🔧 [DEBUG] Tool Execution Result:[/brand]\n{tool_result}")
                
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result
                })


if __name__ == "__main__":
    mesh = Mesh()
    asyncio.run(mesh.run())