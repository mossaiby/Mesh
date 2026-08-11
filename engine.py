import asyncio
import os
import sys
from typing import Optional, List, Dict, Any
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
    SearchSymbolsTool,
    BackgroundShellTool,
    GitStatusTool,
    GitDiffTool,
    GitCommitTool,
    GitPushTool,
    GitBranchTool,
)
import tool_synthesis
import symbol_search
import project_rules
import repo_map
import reflexion
import modes
import jobs
import context_mentions
from pricing import pricing_manager
from checkpoint import CheckpointManager
from guard import SafetyGuard
from subagent import SubAgentProxy
from self_heal import SelfHealer
from terminal_ui import MeshPromptSession
from commands.registry import CommandRegistry
from commands import (
    register_model_commands,
    register_agent_commands,
    register_session_commands,
    register_system_commands,
)
from mcp.client import MCPManager
from skills import SkillRegistry, PythonCodingSkill
from compaction import maybe_auto_compact, estimate_tokens
from theme import console


class MeshEngine:
    """
    Central orchestration engine for Mesh: handles provider streaming,
    turn completion loops, tool execution dispatching, system prompt assembly,
    and command routing.
    """
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
        self.checkpoint_mgr = CheckpointManager()
        self.prompt_session = MeshPromptSession(self)
        
        self.permission_manager = PermissionManager()
        self.skill_registry = SkillRegistry(self.tool_registry)
        self.cmd_registry = CommandRegistry()
        self.mcp_manager = MCPManager()
        self.debug_mode: bool = False
        self.subagent_proxy.debug_mode = self.debug_mode
        self.tools_enabled: bool = True
        self.current_mode: str = modes.DEFAULT_MODE
        self._pre_yolo_guard_autonomy: Optional[str] = None
        self._pre_yolo_permission_auto_approve: Optional[bool] = None
        self.messages: List[Dict[str, Any]] = []

        # Session metrics tracking
        self.session_prompt_tokens: int = 0
        self.session_completion_tokens: int = 0
        self.session_cost_usd: float = 0.0

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

        reflexion_section = reflexion.get_reflexion_instructions()
        if reflexion_section:
            full_sys += f"\n\n{reflexion_section}"

        proj_rules_section = project_rules.get_project_rules_instructions()
        if proj_rules_section:
            full_sys += f"\n\n{proj_rules_section}"

        repo_map_section = repo_map.get_repo_map_instructions(".", token_budget=500)
        if repo_map_section:
            full_sys += f"\n\n{repo_map_section}"

        sys_idx = next((i for i, m in enumerate(self.messages) if m.get("role") == "system"), None)
        
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
        self.tool_registry.register(BackgroundShellTool())
        self.tool_registry.register(GitStatusTool())
        self.tool_registry.register(GitDiffTool())
        self.tool_registry.register(GitCommitTool())
        self.tool_registry.register(GitPushTool())
        self.tool_registry.register(GitBranchTool())
        self.tool_registry.register(DelegateTaskTool(self.tool_registry, self.config_mgr))
        self.goal_tool = GoalTool(on_change=lambda: self.update_system_message())
        self.tool_registry.register(self.goal_tool)
        self.tool_registry.register(AdvisorTool(self.config_mgr))
        self.tool_registry.register(ExploreTool(self.tool_registry, self.config_mgr))
        self.tool_registry.register(SynthesizeTool(self.tool_registry))
        self.tool_registry.register(ConsensusTool(self.config_mgr))
        self.tool_registry.register(SearchSymbolsTool())
        
        # Load any existing dynamic tools from custom_tools/
        tool_synthesis.load_all_custom_tools(self.tool_registry)

        # Index codebase symbols asynchronously on launch
        symbol_search.symbol_indexer.index_directory(".")

        # 2. Register Skills & Load skills.json
        self.skill_registry.register(PythonCodingSkill())
        self.skill_registry.load_from_file()

        # 3. Register Command Handlers
        register_system_commands(self)
        register_model_commands(self)
        register_agent_commands(self)
        register_session_commands(self)

    async def run_script_file(self, filepath: str):
        """Reads and executes a script file line-by-line (commands & prompts)."""
        if not os.path.exists(filepath):
            console.print(f"[error]Script file '{filepath}' not found.[/error]")
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        except Exception as e:
            console.print(f"[error]Failed to read script file '{filepath}': {e}[/error]")
            return

        console.print(f"[brand]📜 Executing script file:[/brand] [label]{filepath}[/label] ({len(lines)} lines)\n")

        for idx, line in enumerate(lines, 1):
            console.print(f"[info]Script [{idx}/{len(lines)}]> [/info] {line}")
            if self.cmd_registry.is_command(line):
                handled = await self.cmd_registry.dispatch(line)
                if not handled:
                    console.print("[error]Unknown command in script. Type /help for options.[/error]")
            else:
                formatted_input, _ = context_mentions.process_prompt_context_mentions(line, ".")
                pre_prompt_count = len(self.messages)
                self.messages.append({"role": "user", "content": formatted_input})
                await self.process_inference(pre_prompt_count)

    async def run(self, script_file: Optional[str] = None, non_interactive: bool = False):
        console.print(f"[brand]Mesh v{__import__('version').__version__} Started.[/brand] Initializing MCP servers...")
        
        await self.mcp_manager.initialize_all(self.tool_registry)

        if script_file:
            await self.run_script_file(script_file)
            if non_interactive:
                console.print("\n[warning]Script execution complete in non-interactive mode. Exiting...[/warning]")
                await self.cmd_registry.dispatch("/exit")

        console.print("[brand]Ready.[/brand] Type [warning]/help[/warning] for commands or start chatting.\n")
        
        while True:
            try:
                user_input = await self.prompt_session.get_input_async()
                if not user_input:
                    continue
                if user_input.lower() in ["exit", "quit", "/exit"]:
                    await jobs.job_manager.stop_all()
                    await self.cmd_registry.dispatch("/exit")

                if self.cmd_registry.is_command(user_input):
                    handled = await self.cmd_registry.dispatch(user_input)
                    if not handled:
                        console.print("[error]Unknown command. Type /help for options.[/error]")
                    continue

                # Parse @filename context mentions
                formatted_input, _ = context_mentions.process_prompt_context_mentions(user_input, ".")

                pre_prompt_count = len(self.messages)
                self.messages.append({"role": "user", "content": formatted_input})
                await self.process_inference(pre_prompt_count)

            except (KeyboardInterrupt, EOFError):
                console.print("\n[warning]Exiting...[/warning]")
                try:
                    await jobs.job_manager.stop_all()
                    await asyncio.wait_for(self.mcp_manager.close_all(), timeout=2.0)
                except Exception:
                    pass
                break

    async def process_inference(self, pre_prompt_count: Optional[int] = None):
        max_turns = 10
        current_turn = 0
        rollback_count = pre_prompt_count if pre_prompt_count is not None else max(0, len(self.messages) - 1)

        try:
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

                tool_calls_to_run = []
                turn_prompt_tokens = 0
                turn_completion_tokens = 0

                async def chunk_generator():
                    nonlocal turn_prompt_tokens, turn_completion_tokens
                    async for chunk in provider.stream_chat(self.messages, tools=schemas):
                        ctype = chunk["type"]
                        cval = chunk["value"]

                        if ctype == "usage":
                            turn_prompt_tokens = cval.get("prompt_tokens", 0)
                            turn_completion_tokens = cval.get("completion_tokens", 0)
                        elif ctype == "tool_calls" and self.tools_enabled:
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

                console.print(f"\n[info]Assistant ({model_cfg.name} via {provider_cfg.name})[/info] >")

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

                # Calculate tokens post-stream if not returned in API usage chunk
                if turn_prompt_tokens == 0:
                    turn_prompt_tokens = estimate_tokens(self.messages)
                if turn_completion_tokens == 0 and response_text:
                    turn_completion_tokens = max(1, len(response_text) // 4)

                # Real-time USD cost calculation
                active_key = self.config_mgr.config.active_model
                _, _, turn_cost = pricing_manager.get_token_cost(active_key, turn_prompt_tokens, turn_completion_tokens)

                self.session_prompt_tokens += turn_prompt_tokens
                self.session_completion_tokens += turn_completion_tokens
                self.session_cost_usd += turn_cost

                cost_str = f"${turn_cost:.4f} turn, ${self.session_cost_usd:.4f} session"
                token_str = f"{turn_prompt_tokens} in, {turn_completion_tokens} out"

                # Render post-stream turn metrics footer
                console.print(f"[dim][{token_str} | {cost_str}][/dim]\n")

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

                    # Log errors to reflexion event recorder
                    if isinstance(tool_result, str) and '"error":' in tool_result:
                        reflexion.record_reflexion_event(
                            event_type="tool_failure",
                            details=f"Tool '{tool_call['name']}' failed with args {tool_call['args']}: {tool_result[:300]}"
                        )

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": tool_result
                    })

        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[warning]⛔ Turn cancelled by user.[/warning]\n")
            # Clean up incomplete user prompt and partial assistant/tool messages from cancelled turn
            self.messages = self.messages[:rollback_count]