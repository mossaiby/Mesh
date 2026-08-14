import asyncio
import os
import sys
import time
from typing import Optional, List, Dict, Any, Tuple
from config import ConfigManager
from providers import get_provider
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
    HashEditTool,
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
import router
import distill
import repair
import hooks
from session_logger import SessionLogger
from session_manager import SessionManager
from pricing import pricing_manager
from checkpoint import CheckpointManager
from guard import SafetyGuard
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
        self.session_logger = SessionLogger(
            filepath=self.config_mgr.config.logging.filepath,
            enabled=self.config_mgr.config.logging.enabled
        )
        self.session_manager = SessionManager(self)
        self.subagent_distiller = distill.SubAgentDistiller(self.config_mgr)
        self.tool_registry.subagent_distiller = self.subagent_distiller
        self.repair_engine = repair.RepairEngine(self.config_mgr)
        self.tool_registry.repair_engine = self.repair_engine
        self.safety_guard = SafetyGuard(self.config_mgr, enabled=self.config_mgr.config.guard_enabled)
        self.tool_registry.safety_guard = self.safety_guard
        self.checkpoint_mgr = CheckpointManager()
        self.prompt_session = MeshPromptSession(self)
        
        self.permission_manager = PermissionManager()
        self.skill_registry = SkillRegistry(self.tool_registry)
        self.cmd_registry = CommandRegistry()
        self.mcp_manager = MCPManager(config_mgr=self.config_mgr)
        hooks.hook_manager._config_mgr = self.config_mgr
        self.debug_mode: bool = False
        self.subagent_distiller.debug_mode = self.debug_mode
        self.tools_enabled: bool = True
        self.is_running: bool = False
        self.current_mode: str = modes.DEFAULT_MODE
        self._pre_yolo_guard_autonomy: Optional[str] = None
        self._pre_yolo_permission_auto_approve: Optional[bool] = None
        self.messages: List[Dict[str, Any]] = []

        # Session metrics tracking
        self.session_prompt_tokens: int = 0
        self.session_completion_tokens: int = 0
        self.session_cached_tokens: int = 0
        self.session_cost_usd: float = 0.0

        self.setup_defaults()
        self.tool_registry.mode_blocked_tools = modes.blocked_tools_for_mode(self.current_mode, self.tool_registry)
        self.update_system_message(self.config_mgr.config.system_prompt)

    def reload_project_context(self):
        """Re-indexes codebase symbols, reloads project rules, and regenerates Repo Map for CWD."""
        symbol_search.symbol_indexer.index_directory(".")
        tool_synthesis.load_all_custom_tools(self.tool_registry)
        self.update_system_message()

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

        repo_map_section = repo_map.get_repo_map_instructions(".", token_budget=self.config_mgr.config.budgets.repo_map)
        if repo_map_section:
            full_sys += f"\n\n{repo_map_section}"

        sys_idx = next((i for i, m in enumerate(self.messages) if m.get("role") == "system"), None)
        
        if sys_idx is not None:
            self.messages[sys_idx]["content"] = full_sys
        else:
            self.messages = [{"role": "system", "content": full_sys}]

    def setup_defaults(self):
        # 1. Register Base Tools
        self.tool_registry.register(CalculatorTool())
        self.tool_registry.register(MemoryTool(self.config_mgr))
        self.tool_registry.register(NoteTool())
        self.tool_registry.register(AskUserTool())
        self.tool_registry.register(TodoTool())
        self.tool_registry.register(WebSearchTool(self.config_mgr))
        self.tool_registry.register(WebFetchTool(self.config_mgr))
        self.tool_registry.register(ReadFileTool(self.permission_manager))
        self.tool_registry.register(WriteFileTool(self.permission_manager))
        self.tool_registry.register(EditFileTool(self.permission_manager))
        self.tool_registry.register(HashEditTool(self.permission_manager))
        self.tool_registry.register(GlobTool(self.permission_manager))
        self.tool_registry.register(ShellTool(self.permission_manager, self.config_mgr))
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
        self.tool_registry.register(SearchSymbolsTool(self.config_mgr))
        
        tool_synthesis.load_all_custom_tools(self.tool_registry)
        symbol_search.symbol_indexer.index_directory(".")

        # 2. Register Skills
        self.skill_registry.register(PythonCodingSkill(self.config_mgr))
        self.skill_registry.load_from_file()

        # 3. Register Commands
        register_system_commands(self)
        register_model_commands(self)
        register_agent_commands(self)
        register_session_commands(self)

    async def run_script_file(self, filepath: str):
        if not os.path.exists(filepath):
            console.print(f"[error]Script file '{filepath}' not found.[/error]")
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = []
                for raw_line in f:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    # Ignore pure comments starting with // or # followed by whitespace
                    if stripped.startswith("//") or stripped.startswith("# "):
                        continue
                    lines.append(stripped)
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
            elif line.startswith("!"):
                cmd_text = line[1:].strip()
                await self.cmd_registry.dispatch(f"/shell {cmd_text}")
            elif line.startswith("#"):
                code_text = line[1:].strip()
                await self.cmd_registry.dispatch(f"/python {code_text}")
            else:
                formatted_input, _ = context_mentions.process_prompt_context_mentions(line, ".")
                pre_prompt_count = len(self.messages)
                self.messages.append({"role": "user", "content": formatted_input})
                self.session_logger.log_user_prompt(formatted_input)
                await self.process_inference(pre_prompt_count)

    async def run(
        self,
        script_file: Optional[str] = None,
        non_interactive: bool = False,
        log_file: Optional[str] = None,
        session_name: Optional[str] = None,
        resume_latest: bool = False
    ):
        console.print(
            f"[brand]⚡ Mesh: A Modern, Modular and Hackable AI Harness[/brand] "
            f"([dim]v{__import__('version').__version__}[/dim])\n"
            f"Developed by [accent]Farshid Mossaiby[/accent] ([accent]https://github.com/mossaiby/Mesh[/accent])\n"
        )

        if log_file is not None:
            self.session_logger.enable(filepath=log_file)
            console.print(f"[success]Session Markdown logging ENABLED -> `{self.session_logger.filepath}`[/success]")

        if resume_latest:
            latest = self.session_manager.get_latest_session_name()
            if latest:
                success, msg = self.session_manager.load_session(latest)
                console.print(f"[{'success' if success else 'error'}]{msg}[/{'success' if success else 'error'}]")
            else:
                console.print("[warning]No saved sessions found to resume.[/warning]")
        elif session_name:
            if os.path.exists(os.path.join("sessions", f"{session_name}.json")):
                success, msg = self.session_manager.load_session(session_name)
                console.print(f"[{'success' if success else 'error'}]{msg}[/{'success' if success else 'error'}]")
            else:
                self.session_manager.active_session_name = session_name
                console.print(f"[success]Active session set to '[accent]{session_name}[/accent]'.[/success]")

        console.print("[dim]Initializing MCP servers...[/dim]")
        await self.mcp_manager.initialize_all(self.tool_registry)

        if script_file:
            await self.run_script_file(script_file)
            if non_interactive:
                console.print("\n[warning]Script execution complete in non-interactive mode. Exiting...[/warning]")
                if self.session_manager.active_session_name:
                    self.session_manager.save_session()
                await jobs.job_manager.stop_all()
                await asyncio.wait_for(self.mcp_manager.close_all(), timeout=3.0)
                return

        console.print("[brand]Ready.[/brand] Type [warning]/help[/warning] for commands or start chatting.\n")
        
        self.is_running = True
        while self.is_running:
            try:
                user_input = await self.prompt_session.get_input_async()
                if not user_input:
                    continue
                if user_input.lower() in ["exit", "quit", "/exit"]:
                    await self.cmd_registry.dispatch("/exit")
                    if not self.is_running:
                        break
                    continue

                if user_input.startswith("!"):
                    cmd_text = user_input[1:].strip()
                    await self.cmd_registry.dispatch(f"/shell {cmd_text}")
                    continue

                if user_input.startswith("#"):
                    code_text = user_input[1:].strip()
                    await self.cmd_registry.dispatch(f"/python {code_text}")
                    continue

                if self.cmd_registry.is_command(user_input):
                    handled = await self.cmd_registry.dispatch(user_input)
                    if not self.is_running:
                        break
                    if not handled:
                        console.print("[error]Unknown command. Type /help for options.[/error]")
                    continue

                formatted_input, _ = context_mentions.process_prompt_context_mentions(user_input, ".")

                pre_prompt_count = len(self.messages)
                self.messages.append({"role": "user", "content": formatted_input})
                self.session_logger.log_user_prompt(formatted_input)
                await self.process_inference(pre_prompt_count)

            except (KeyboardInterrupt, EOFError):
                console.print("\n[warning]Exiting...[/warning]")
                if self.session_manager.active_session_name:
                    self.session_manager.save_session()
                try:
                    await jobs.job_manager.stop_all()
                    await asyncio.wait_for(self.mcp_manager.close_all(), timeout=2.0)
                except Exception:
                    pass
                self.is_running = False
                break

    async def process_inference(self, pre_prompt_count: Optional[int] = None):
        max_turns = self.config_mgr.config.turns.engine
        current_turn = 0
        rollback_count = pre_prompt_count if pre_prompt_count is not None else max(0, len(self.messages) - 1)

        try:
            while current_turn < max_turns and self.is_running:
                current_turn += 1

                if self.config_mgr.config.active_model == "auto":
                    latest_user_prompt = ""
                    for msg in reversed(self.messages):
                        if msg.get("role") == "user":
                            latest_user_prompt = msg.get("content", "")
                            break

                    try:
                        chosen_key, route_reason = await router.select_model_for_prompt(
                            prompt=latest_user_prompt,
                            messages=self.messages,
                            config_mgr=self.config_mgr
                        )
                        model_cfg, provider_cfg = self.config_mgr.get_model_and_provider(chosen_key)
                        console.print(f"[brand]🔀 Auto-routed prompt to [label]{chosen_key}[/label] ({model_cfg.name}):[/brand] [dim]{route_reason}[/dim]")
                    except Exception as e:
                        console.print(f"[error]Model Routing Error:[/error] {e}")
                        return
                else:
                    try:
                        model_cfg, provider_cfg = self.config_mgr.get_active_model_and_provider()
                    except Exception as e:
                        console.print(f"[error]Configuration Error:[/error] {e}")
                        return

                self.messages, auto_compacted, compact_details = await maybe_auto_compact(self.messages, self.config_mgr)
                if auto_compacted:
                    console.print(f"[warning]📑   {compact_details}[/warning]")
                    self.session_logger.log_system_event(compact_details)

                provider = get_provider(model_cfg, provider_cfg, self.config_mgr)
                schemas = self.tool_registry.get_schemas() if self.tools_enabled else None
                if schemas and self.tool_registry.mode_blocked_tools:
                    schemas = [s for s in schemas if s["function"]["name"] not in self.tool_registry.mode_blocked_tools]

                tool_calls_to_run = []
                turn_prompt_tokens = 0
                turn_completion_tokens = 0
                turn_cached_tokens = 0

                t_start = time.perf_counter()
                t_first_token = None

                async def chunk_generator():
                    nonlocal turn_prompt_tokens, turn_completion_tokens, turn_cached_tokens, t_first_token
                    async for chunk in provider.stream_chat(self.messages, tools=schemas):
                        ctype = chunk["type"]
                        cval = chunk["value"]

                        if t_first_token is None and ctype in ("content", "reasoning", "tool_calls"):
                            t_first_token = time.perf_counter()

                        if ctype == "usage":
                            turn_prompt_tokens = cval.get("prompt_tokens", 0)
                            turn_completion_tokens = cval.get("completion_tokens", 0)
                            turn_cached_tokens = cval.get("cached_tokens", 0)
                        elif ctype == "tool_calls" and self.tools_enabled:
                            for tc in cval:
                                idx = tc.get("index", 0) if isinstance(tc, dict) else getattr(tc, "index", 0)
                                while len(tool_calls_to_run) <= idx:
                                    tool_calls_to_run.append({"id": "", "name": "", "args": ""})
                                
                                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                                if tc_id:
                                    tool_calls_to_run[idx]["id"] = tc_id
                                
                                fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
                                if fn:
                                    fn_name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)
                                    fn_args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", None)
                                    if fn_name:
                                        tool_calls_to_run[idx]["name"] = fn_name
                                    if fn_args:
                                        tool_calls_to_run[idx]["args"] += fn_args
                        else:
                            yield chunk

                console.print(f"\n[info]Assistant ({model_cfg.name} via {provider_cfg.name}) >[/info]")

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

                t_end = time.perf_counter()

                if response_text:
                    self.session_logger.log_assistant_response(response_text, model_name=model_cfg.name)

                if turn_prompt_tokens == 0:
                    turn_prompt_tokens = estimate_tokens(self.messages)
                if turn_completion_tokens == 0 and response_text:
                    turn_completion_tokens = max(1, len(response_text) // 4)

                turn_model_key = chosen_key if self.config_mgr.config.active_model == "auto" else self.config_mgr.config.active_model
                _, _, turn_cost = pricing_manager.get_token_cost(
                    turn_model_key, 
                    turn_prompt_tokens, 
                    turn_completion_tokens, 
                    cached_tokens=turn_cached_tokens
                )

                self.session_prompt_tokens += turn_prompt_tokens
                self.session_completion_tokens += turn_completion_tokens
                self.session_cached_tokens += turn_cached_tokens
                self.session_cost_usd += turn_cost

                ttft_sec = (t_first_token - t_start) if t_first_token is not None else (t_end - t_start)
                gen_sec = (t_end - t_first_token) if t_first_token is not None else 0.0
                tps = (turn_completion_tokens / gen_sec) if gen_sec > 0.001 else 0.0

                cfg = self.config_mgr.config
                metrics_parts = []

                if cfg.show_tokens:
                    if turn_cached_tokens > 0:
                        metrics_parts.append(f"{turn_prompt_tokens} in ({turn_cached_tokens} cached), {turn_completion_tokens} out")
                    else:
                        metrics_parts.append(f"{turn_prompt_tokens} in, {turn_completion_tokens} out")

                if cfg.show_cost:
                    metrics_parts.append(f"${turn_cost:.4f} turn, ${self.session_cost_usd:.4f} session")

                if cfg.show_statistics:
                    ttft_fmt = f"{ttft_sec*1000:.0f}ms" if ttft_sec < 1.0 else f"{ttft_sec:.2f}s"
                    metrics_parts.append(f"TTFT: {ttft_fmt}, {tps:.1f} tok/s")

                if metrics_parts:
                    console.print(f"[dim][{' | '.join(metrics_parts)}][/dim]\n")

                assistant_msg = {"role": "assistant"}
                if response_text:
                    assistant_msg["content"] = response_text

                # Filter out empty placeholder tool call slots from streaming gaps
                active_calls = [tc for tc in tool_calls_to_run if tc.get("name")]

                formatted_tool_calls = []
                if active_calls and self.tools_enabled:
                    for i, tool_call in enumerate(active_calls):
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

                if not active_calls or not self.tools_enabled:
                    break

                # Partition active_calls into contiguous batches:
                # Contiguous read-only calls execute concurrently via asyncio.gather.
                # Mutating and interactive calls execute sequentially.
                batches: List[Tuple[bool, List[Dict[str, str]]]] = []
                current_readonly_batch: List[Dict[str, str]] = []

                for tool_call in active_calls:
                    if self.tool_registry.is_read_only(tool_call["name"], tool_call["args"]):
                        current_readonly_batch.append(tool_call)
                    else:
                        if current_readonly_batch:
                            batches.append((True, current_readonly_batch))
                            current_readonly_batch = []
                        batches.append((False, [tool_call]))

                if current_readonly_batch:
                    batches.append((True, current_readonly_batch))

                for is_readonly, call_batch in batches:
                    # Print tool request headers
                    for tool_call in call_batch:
                        if self.debug_mode:
                            console.print(f"[brand]🔧 DEBUG - Tool Request:[/brand] [tool]{tool_call['name']}[/tool]([dim]{tool_call['args']}[/dim])")
                        else:
                            console.print(f"[accent]⚡ Tool Request:[/accent] [tool]{tool_call['name']}[/tool]([dim]{tool_call['args']}[/dim])")

                    # Execute concurrently if batch has multiple read-only calls; otherwise sequentially
                    if is_readonly and len(call_batch) > 1:
                        results = await asyncio.gather(*(self.tool_registry.execute(tc["name"], tc["args"]) for tc in call_batch))
                    else:
                        results = [await self.tool_registry.execute(call_batch[0]["name"], call_batch[0]["args"])]

                    # Process results in original sequence
                    for tool_call, tool_result in zip(call_batch, results):
                        self.session_logger.log_tool_call(tool_call["name"], tool_call["args"], tool_result)

                        if self.debug_mode:
                            console.print(f"[brand]🔧 DEBUG - Tool Result ([tool]{tool_call['name']}[/tool]):[/brand]\n{tool_result}")

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
            self.messages = self.messages[:rollback_count]
