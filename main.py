import asyncio
import sys
import os
from rich.console import Console
from rich.markdown import Markdown
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
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    GlobTool,
    ShellTool,
)
from tools.note_tool import _read_notes, _write_notes, _append_notes
from tools.memory_tool import _load_memory, _save_memory
from commands.registry import CommandRegistry
from mcp.client import MCPManager
from skills import SkillRegistry, PythonCodingSkill
from compaction import compact_messages

console = Console()


class AIHarness:
    def __init__(self):
        self.config_mgr = ConfigManager()
        self.renderer = StreamRenderer()
        self.tool_registry = ToolRegistry()
        self.permission_manager = PermissionManager()
        self.skill_registry = SkillRegistry(self.tool_registry)
        self.cmd_registry = CommandRegistry()
        self.mcp_manager = MCPManager()
        self.debug_mode: bool = False
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
        self.cmd_registry.register("models", "List configured models and providers", self.cmd_models)
        self.cmd_registry.register("switch", "Switch active model (e.g., /switch llama3-openrouter)", self.cmd_switch)
        self.cmd_registry.register("clear", "Clear conversation context window", self.cmd_clear)
        self.cmd_registry.register("compact", "Semantically summarize older conversation context (/compact)", self.cmd_compact)
        self.cmd_registry.register("retry", "Retry the last LLM response turn (/retry)", self.cmd_retry)
        self.cmd_registry.register("context", "Display context window, tool schemas, and MCP status", self.cmd_context)
        self.cmd_registry.register("system", "Show or set system prompt (/system [text] or /system clear)", self.cmd_system)
        self.cmd_registry.register("note", "Manage or view Markdown notes (/note, /note append <text>, /note clear)", self.cmd_note)
        self.cmd_registry.register("memory", "Manage key-value memories (/memory [save|get|delete|clear])", self.cmd_memory)
        self.cmd_registry.register("skills", "List available skills or enable/disable them (/skills [enable|disable] <name>)", self.cmd_skills)
        self.cmd_registry.register("tools", "Show tools or toggle tool context inclusion (/tools on|off)", self.cmd_tools)
        self.cmd_registry.register("dirs", "List or add/remove allowed directories (/dirs [add|remove|clear] <path>)", self.cmd_dirs)
        self.cmd_registry.register("mcps", "List/toggle MCP servers (/mcps [on|off] or /mcps [enable|disable] <server>)", self.cmd_mcps)
        self.cmd_registry.register("debug", "Toggle or set debug mode (/debug on|off)", self.cmd_debug)
        self.cmd_registry.register("exit", "Exit the AI Harness application", self.cmd_exit)

    async def cmd_help(self, args):
        console.print("[bold green]Available Slash Commands:[/bold green]")
        for cmd, desc in self.cmd_registry.list_commands().items():
            console.print(f"  [bold yellow]{cmd}[/bold yellow] - {desc}")

    async def cmd_models(self, args):
        active = self.config_mgr.config.active_model
        console.print("[bold green]Configured Models:[/bold green]")
        for key, model_cfg in self.config_mgr.config.models.items():
            provider_cfg = self.config_mgr.config.providers.get(model_cfg.provider)
            provider_name = provider_cfg.name if provider_cfg else model_cfg.provider
            
            mark = "[bold cyan]*[/bold cyan]" if key == active else " "
            console.print(
                f"{mark} [bold yellow]{key}[/bold yellow] -> {model_cfg.name} via "
                f"[magenta]{provider_name}[/magenta] ([dim]{model_cfg.model_id}[/dim])"
            )

    async def cmd_switch(self, args):
        if not args:
            console.print("[red]Usage: /switch <model_key>[/red]")
            return
        try:
            self.config_mgr.set_active_model(args[0])
            model_cfg, _ = self.config_mgr.get_active_model_and_provider()
            self.update_system_message(model_cfg.system_prompt)
            console.print(f"[green]Switched active model to: {args[0]}[/green]")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")

    async def cmd_clear(self, args):
        self.update_system_message()
        console.print("[yellow]Conversation context cleared (system prompt and skills preserved).[/yellow]")

    async def cmd_compact(self, args):
        console.print("[yellow]Analyzing and compacting conversation history...[/yellow]")
        new_messages, success, details = await compact_messages(self.messages, self.config_mgr)
        if success:
            self.messages = new_messages
            console.print(f"[bold green]Compaction Successful![/bold green] {details}")
        else:
            console.print(f"[yellow]{details}[/yellow]")

    async def cmd_retry(self, args):
        last_user_idx = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                last_user_idx = i
                break

        if last_user_idx is None:
            console.print("[yellow]No user message found in context to retry.[/yellow]")
            return

        self.messages = self.messages[:last_user_idx + 1]
        console.print("[yellow]Retrying last completion turn...[/yellow]")
        await self.process_inference()

    async def cmd_note(self, args):
        if not args:
            notes = _read_notes()
            if not notes.strip():
                console.print("[dim]notes.md is currently empty.[/dim]")
            else:
                console.print("\n[bold green]=== Current Notes (notes.md) ===[/bold green]\n")
                console.print(Markdown(notes))
                console.print()
            console.print("Usage: [yellow]/note[/yellow], [yellow]/note append <text>[/yellow], or [yellow]/note clear[/yellow]\n")
            return

        subcmd = args[0].lower()
        if subcmd == "clear":
            _write_notes("")
            console.print("[yellow]notes.md cleared.[/yellow]")
        elif subcmd == "append":
            text_to_append = " ".join(args[1:]).strip()
            if not text_to_append:
                console.print("[red]Usage: /note append <text>[/red]")
                return
            _append_notes(text_to_append)
            console.print("[green]Appended text to notes.md.[/green]")
        else:
            text_to_append = " ".join(args).strip()
            _append_notes(text_to_append)
            console.print("[green]Appended text to notes.md.[/green]")

    async def cmd_memory(self, args):
        mem = _load_memory()

        if not args:
            console.print("\n[bold green]=== Saved Memory Items (memory.json) ===[/bold green]\n")
            if not mem:
                console.print("  [dim]No memory keys saved.[/dim]")
            else:
                for k, v in mem.items():
                    console.print(f"  • [bold yellow]{k}[/bold yellow]: {v}")
            console.print("\nUsage: [yellow]/memory[/yellow], [yellow]/memory save <key> <value>[/yellow], [yellow]/memory get <key>[/yellow], [yellow]/memory delete <key>[/yellow], or [yellow]/memory clear[/yellow]\n")
            return

        subcmd = args[0].lower()

        if subcmd == "save" and len(args) >= 3:
            key = args[1]
            val = " ".join(args[2:]).strip()
            mem[key] = val
            _save_memory(mem)
            console.print(f"[green]Saved memory key '{key}'.[/green]")

        elif subcmd == "get" and len(args) >= 2:
            key = args[1]
            if key in mem:
                console.print(f"[bold yellow]{key}:[/bold yellow] {mem[key]}")
            else:
                console.print(f"[red]Memory key '{key}' not found.[/red]")

        elif subcmd == "delete" and len(args) >= 2:
            key = args[1]
            if key in mem:
                del mem[key]
                _save_memory(mem)
                console.print(f"[yellow]Deleted memory key '{key}'.[/yellow]")
            else:
                console.print(f"[red]Memory key '{key}' not found.[/red]")

        elif subcmd == "clear":
            _save_memory({})
            console.print("[yellow]Cleared all persistent memories from memory.json.[/yellow]")

        else:
            console.print("[red]Usage: /memory [save|get|delete|clear] <key> [value][/red]")

    async def cmd_skills(self, args):
        skills = self.skill_registry.list_skills()
        if not args:
            console.print("\n[bold green]Registered Skills:[/bold green]")
            if not skills:
                console.print("  [dim]No skills registered.[/dim]")
            for name, skill in skills.items():
                status = "[bold green]ENABLED[/bold green]" if skill.enabled else "[bold red]DISABLED[/bold red]"
                console.print(f"• [bold yellow]{name}[/bold yellow] [{status}]: {skill.description}")
                tools = skill.get_tools()
                if tools:
                    tool_names = ", ".join([t.name for t in tools])
                    console.print(f"  [dim]Tools provided: {tool_names}[/dim]")
            console.print("\nUsage: [yellow]/skills enable <name>[/yellow] or [yellow]/skills disable <name>[/yellow]\n")
            return

        action = args[0].lower()
        if action in ["enable", "disable"] and len(args) > 1:
            target = args[1]
            enable_flag = (action == "enable")
            success = self.skill_registry.set_skill_state(target, enable_flag)
            if success:
                self.update_system_message()
                console.print(f"[green]Skill '{target}' set to {action}d.[/green]")
            else:
                console.print(f"[red]Skill '{target}' not found.[/red]")
        else:
            console.print("[red]Usage: /skills enable <name> or /skills disable <name>[/red]")

    async def cmd_dirs(self, args):
        if not args:
            console.print("\n[bold green]Currently Allowed Directories:[/bold green]")
            for d in self.permission_manager.allowed_dirs:
                console.print(f"  • [bold yellow]{d}[/bold yellow]")
            console.print("\nUsage: [yellow]/dirs add <path>[/yellow] or [yellow]/dirs remove <path>[/yellow] or [yellow]/dirs clear[/yellow]\n")
            return

        action = args[0].lower()
        if action == "add" and len(args) > 1:
            target_path = " ".join(args[1:])
            added = self.permission_manager.add_dir(target_path)
            console.print(f"[bold green]Added directory to allowed list:[/bold green] {added}")
        elif action == "remove" and len(args) > 1:
            target_path = " ".join(args[1:])
            removed = self.permission_manager.remove_dir(target_path)
            if removed:
                console.print(f"[yellow]Removed directory from allowed list:[/yellow] {target_path}")
            else:
                console.print(f"[red]Directory not found in allowed list:[/red] {target_path}")
        elif action == "clear":
            self.permission_manager.allowed_dirs = [str(os.getcwd())]
            console.print("[yellow]Reset allowed directories to Current Working Directory.[/yellow]")
        else:
            console.print("[red]Usage: /dirs [add|remove|clear] <path>[/red]")

    async def cmd_context(self, args):
        console.print(f"\n[bold green]=== CONTEXT MESSAGES ({len(self.messages)} Messages) ===[/bold green]\n")
        for idx, msg in enumerate(self.messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", None)
            tool_call_id = msg.get("tool_call_id", None)

            header = f"[{idx}] Role: [bold yellow]{role}[/bold yellow]"
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

        tools_state = "[bold green]ENABLED[/bold green]" if self.tools_enabled else "[bold red]DISABLED[/bold red]"
        console.print(f"[bold green]=== ACTIVE TOOL SCHEMAS ({tools_state}) ===[/bold green]\n")
        if self.tools_enabled:
            schemas = self.tool_registry.get_schemas()
            if schemas:
                for s in schemas:
                    fn = s.get("function", {})
                    name = fn.get("name", "unnamed")
                    desc = fn.get("description", "No description")
                    params = fn.get("parameters", {}).get("properties", {})
                    param_keys = ", ".join(params.keys()) if params else "none"
                    console.print(f"• [bold yellow]{name}[/bold yellow]: {desc}")
                    console.print(f"  [dim]Parameters: ({param_keys})[/dim]")
            else:
                console.print("  [dim]No tools currently registered.[/dim]")
        else:
            console.print("  [dim]Tools are disabled (/tools off). No schemas are sent to the model.[/dim]")
        console.print()

        global_mcp_str = "[bold green]ENABLED[/bold green]" if self.mcp_manager.global_enabled else "[bold red]DISABLED[/bold red]"
        console.print(f"[bold green]=== MCP SERVERS & TOOLS (Global MCP: {global_mcp_str}) ===[/bold green]\n")
        mcp_info = self.mcp_manager.get_server_info()
        if mcp_info:
            for name, details in mcp_info.items():
                status = "[bold green]CONNECTED[/bold green]" if details["connected"] else "[bold red]DISCONNECTED[/bold red]"
                enabled_str = "[bold green]ENABLED[/bold green]" if details["enabled"] else "[bold red]DISABLED[/bold red]"
                cmd_str = f"{details['command']} {' '.join(details['args'])}" if details['command'] else "N/A"
                console.print(f"• [bold yellow]{name}[/bold yellow] [{status}] [{enabled_str}] — [dim]{cmd_str}[/dim]")
                
                tools = details.get("tools", [])
                if tools:
                    for t in tools:
                        t_name = t.get("name", "unnamed")
                        t_desc = t.get("description", "No description")
                        t_props = t.get("inputSchema", {}).get("properties", {})
                        t_args = ", ".join(t_props.keys()) if t_props else "none"
                        console.print(f"    - [cyan]{t_name}[/cyan]: {t_desc} [dim]({t_args})[/dim]")
                else:
                    console.print("    [dim]No tools exposed.[/dim]")
        else:
            console.print("  [dim]No MCP servers configured in mcps.json.[/dim]")
        console.print()

    async def cmd_system(self, args):
        sys_idx = next((i for i, m in enumerate(self.messages) if m.get("role") == "system"), None)

        if not args:
            current = self.messages[sys_idx]["content"] if sys_idx is not None else "[dim]<none>[/dim]"
            console.print(f"[bold green]Current System Prompt:[/bold green]\n{current}\n")
            console.print("Usage: [yellow]/system [text][/yellow] or [yellow]/system clear[/yellow]")
            return

        new_prompt = " ".join(args).strip()
        if new_prompt.lower() == "clear":
            if sys_idx is not None:
                self.messages.pop(sys_idx)
            console.print("[yellow]System prompt cleared from context.[/yellow]")
        else:
            if sys_idx is not None:
                self.messages[sys_idx]["content"] = new_prompt
            else:
                self.messages.insert(0, {"role": "system", "content": new_prompt})
            console.print(f"[bold green]System prompt updated to:[/bold green]\n{new_prompt}")

    async def cmd_tools(self, args):
        if not args:
            state_str = "[bold green]ON[/bold green]" if self.tools_enabled else "[bold red]OFF[/bold red]"
            console.print(f"Tool inclusion & execution is currently {state_str}.\n")
            console.print("[bold green]Available Registered Tools:[/bold green]")
            schemas = self.tool_registry.get_schemas()
            if not schemas:
                console.print("  [dim]No tools registered.[/dim]")
            for s in schemas:
                fn = s.get("function", {})
                console.print(f"  • [bold yellow]{fn.get('name')}[/bold yellow]: {fn.get('description')}")
            console.print("\nUsage: [yellow]/tools on[/yellow] or [yellow]/tools off[/yellow]")
            return

        arg = args[0].lower()
        if arg == "on":
            self.tools_enabled = True
            console.print("[bold green]Tool context inclusion & execution enabled.[/bold green]")
        elif arg == "off":
            self.tools_enabled = False
            console.print("[yellow]Tool context inclusion & execution disabled.[/yellow]")
        else:
            console.print("[red]Invalid option. Use '/tools on' or '/tools off'.[/red]")

    async def cmd_mcps(self, args):
        info = self.mcp_manager.get_server_info()
        if not info:
            console.print("[dim]No MCP servers configured in mcps.json.[/dim]")
            return

        if args:
            action = args[0].lower()
            if action == "on":
                self.mcp_manager.set_global_state(True, self.tool_registry)
                console.print("[bold green]All MCP tools globally ENABLED.[/bold green]")
                return
            elif action == "off":
                self.mcp_manager.set_global_state(False, self.tool_registry)
                console.print("[yellow]All MCP tools globally DISABLED.[/yellow]")
                return
            elif action in ["enable", "disable"] and len(args) > 1:
                target = args[1]
                enable_flag = (action == "enable")
                success = self.mcp_manager.set_server_state(target, enable_flag, self.tool_registry)
                if success:
                    state_str = "enabled" if enable_flag else "disabled"
                    console.print(f"[green]MCP Server '{target}' tools {state_str}.[/green]")
                else:
                    console.print(f"[red]MCP Server '{target}' not found.[/red]")
                return
            else:
                console.print("[red]Usage: /mcps [on|off] or /mcps [enable|disable] <server_name>[/red]")
                return

        global_str = "[bold green]ENABLED[/bold green]" if self.mcp_manager.global_enabled else "[bold red]DISABLED[/bold red]"
        console.print(f"\n[bold green]Configured MCP Servers (Global MCP Status: {global_str}):[/bold green]\n")

        for name, details in info.items():
            status = "[bold green]CONNECTED[/bold green]" if details["connected"] else "[bold red]DISCONNECTED[/bold red]"
            enabled_str = "[bold green]ENABLED[/bold green]" if details["enabled"] else "[bold red]DISABLED[/bold red]"
            cmd_str = f"{details['command']} {' '.join(details['args'])}" if details['command'] else "N/A"
            
            console.print(f"• [bold yellow]{name}[/bold yellow] [{status}] [{enabled_str}] — Command: [dim]{cmd_str}[/dim]")
            
            if details["error"]:
                console.print(f"  [dim red]Error: {details['error']}[/dim red]")

            tools = details.get("tools", [])
            if tools:
                console.print("  [bold cyan]Exposed Tools:[/bold cyan]")
                for t in tools:
                    desc = t.get("description", "No description")
                    properties = t.get("inputSchema", {}).get("properties", {})
                    args_summary = ", ".join(properties.keys()) if properties else "none"
                    console.print(f"    - [bold white]{t['name']}[/bold white]: {desc}")
                    console.print(f"      [dim]Arguments: ({args_summary})[/dim]")
            else:
                console.print("  [dim]No tools exposed.[/dim]")
            console.print()

        console.print("Usage: [yellow]/mcps [on|off][/yellow] or [yellow]/mcps [enable|disable] <server_name>[/yellow]\n")

    async def cmd_debug(self, args):
        if not args:
            state_str = "[bold green]ON[/bold green]" if self.debug_mode else "[bold red]OFF[/bold red]"
            console.print(f"Debug mode is currently {state_str}. Usage: [yellow]/debug on[/yellow] or [yellow]/debug off[/yellow]")
            return

        arg = args[0].lower()
        if arg == "on":
            self.debug_mode = True
            console.print("[bold green]Debug mode enabled.[/bold green] CoT and Tool execution details will be shown.")
        elif arg == "off":
            self.debug_mode = False
            console.print("[yellow]Debug mode disabled.[/yellow] CoT will be hidden.")
        else:
            console.print("[red]Invalid debug option. Use '/debug on' or '/debug off'.[/red]")

    async def cmd_exit(self, args):
        console.print("[yellow]Closing MCP connections and exiting. Goodbye![/yellow]")
        try:
            await asyncio.wait_for(self.mcp_manager.close_all(), timeout=3.0)
        except Exception:
            pass
        sys.exit(0)

    async def run(self):
        console.print("[bold magenta]AI Harness CLI Started.[/bold magenta] Initializing MCP servers...")
        
        await self.mcp_manager.initialize_all(self.tool_registry)

        console.print("[bold magenta]Ready.[/bold magenta] Type [yellow]/help[/yellow] for commands or start chatting.\n")
        
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
                        console.print("[red]Unknown command. Type /help for options.[/red]")
                    continue

                self.messages.append({"role": "user", "content": user_input})
                await self.process_inference()

            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Exiting...[/yellow]")
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
                console.print(f"[bold red]Configuration Error:[/bold red] {e}")
                return

            provider = OpenAIProvider(model_cfg, provider_cfg)
            schemas = self.tool_registry.get_schemas() if self.tools_enabled else None

            console.print(f"\n[bold blue]Assistant ({model_cfg.name} via {provider_cfg.name})[/bold blue] >")

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
                    f"\n[bold red]API/Provider Error ({provider_cfg.name}):[/bold red] "
                    f"Could not connect to [dim]{provider_cfg.base_url}[/dim].\n"
                    f"[dim red]Details: {str(e)}[/dim red]\n"
                    f"[yellow]Tip: Ensure your local server (e.g. LM Studio / Ollama) is running, or switch models using /switch.[/yellow]"
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
                    console.print(f"\n[bold magenta]🔧 [DEBUG] Tool Execution Request:[/bold magenta] {tool_call['name']}({tool_call['args']})")
                else:
                    console.print(f"\n[dim cyan]⚡ Tool Execution Request: {tool_call['name']}({tool_call['args']})[/dim cyan]")

                tool_result = await self.tool_registry.execute(tool_call["name"], tool_call["args"])

                if self.debug_mode:
                    console.print(f"[bold magenta]🔧 [DEBUG] Tool Execution Result:[/bold magenta]\n{tool_result}")
                
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result
                })


if __name__ == "__main__":
    harness = AIHarness()
    asyncio.run(harness.run())