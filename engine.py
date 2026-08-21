import asyncio
import os
import sys
from typing import Optional, List, Dict, Any
from config import ConfigManager
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
    GrepTool,
    ShellTool,
    DelegateTaskTool,
    GoalTool,
    AdvisorTool,
    ExploreTool,
    SynthesizeTool,
    ConsensusTool,
    SearchSymbolsTool,
    BackgroundShellTool,
    GitInitTool,
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
import distill
import repair
import hooks
from session_logger import SessionLogger
from session_manager import SessionManager
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
from tool_orchestrator import ToolOrchestrator
from inference_coordinator import InferenceCoordinator
from theme import console


class MeshEngine:
    """
    Central orchestration engine for Mesh: handles component lifecycle,
    REPL input loops, system prompt assembly, command routing, and delegates
    inference streaming and tool execution to InferenceCoordinator and ToolOrchestrator.
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

        # Subsystems for tool orchestration and multi-turn inference
        self.tool_orchestrator = ToolOrchestrator(self)
        self.inference_coordinator = InferenceCoordinator(self, self.tool_orchestrator)

        self.setup_defaults()
        self.tool_registry.mode_blocked_tools = modes.blocked_tools_for_mode(self.current_mode, self.tool_registry)
        self.update_system_message(self.config_mgr.config.system_prompt)

    def reload_project_context(self):
        """Re-indexes codebase symbols in background, reloads project rules, and regenerates Repo Map for CWD."""
        symbol_search.symbol_indexer.start_background_indexing(".", force=True, on_complete=lambda count: self.update_system_message())
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
        self.tool_registry.register(GrepTool(self.permission_manager))
        self.tool_registry.register(ShellTool(self.permission_manager, self.config_mgr))
        self.tool_registry.register(BackgroundShellTool())
        self.tool_registry.register(GitInitTool())
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
        symbol_search.symbol_indexer.load_cache(".")

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

        # Start non-blocking background symbol indexing
        symbol_search.symbol_indexer.start_background_indexing(
            ".",
            on_complete=lambda count: self.update_system_message()
        )

        if script_file:
            await self.run_script_file(script_file)
            if non_interactive:
                console.print("\n[warning]Script execution complete in non-interactive mode. Exiting...[/warning]")
                if self.session_manager.active_session_name:
                    self.session_manager.save_session()
                try:
                    await jobs.job_manager.stop_all()
                    await asyncio.wait_for(self.mcp_manager.close_all(), timeout=3.0)
                except Exception:
                    pass
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
                    try:
                        self.session_manager.save_session()
                    except Exception:
                        pass
                try:
                    await jobs.job_manager.stop_all()
                    await asyncio.wait_for(self.mcp_manager.close_all(), timeout=2.0)
                except Exception:
                    pass
                except (KeyboardInterrupt, asyncio.CancelledError):
                    pass
                self.is_running = False
                break

    async def process_inference(self, pre_prompt_count: Optional[int] = None):
        """Delegates turn inference and multi-step tool execution loop to InferenceCoordinator."""
        await self.inference_coordinator.process_inference(pre_prompt_count)
