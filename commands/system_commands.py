import sys
from typing import List, Any
from rich.table import Table
from rich.text import Text
from rich.markup import escape
from compaction import compact_messages, estimate_tokens
import symbol_search
import project_rules
import hooks
from pricing import pricing_manager
from theme import console
from version import __version__


async def cmd_help(engine: Any, args: List[str]):
    console.print("\n[success]Available Slash Commands:[/success]\n")

    table = Table(show_header=False, box=None, padding=(0, 1, 0, 2))
    table.add_column("Command", style="label", no_wrap=True)
    table.add_column("Description")

    for cmd, desc in engine.cmd_registry.list_commands().items():
        table.add_row(cmd, Text(desc))

    console.print(table)
    console.print()


async def cmd_status(engine: Any, args: List[str]):
    model_cfg, provider_cfg = engine.config_mgr.get_active_model_and_provider()
    sys_idx = next((i for i, m in enumerate(engine.messages) if m.get("role") == "system"), None)
    sys_prompt = engine.messages[sys_idx]["content"] if sys_idx is not None else "None"
    
    console.print(f"\n[success]=== MESH STATUS (v{__version__}) ===[/success]\n")
    console.print(f"• [label]Active Model:[/label] {model_cfg.name} ({engine.config_mgr.config.active_model})")
    console.print(f"  [dim]Provider: {provider_cfg.name} | Base URL: {provider_cfg.base_url} | Model ID: {model_cfg.model_id}[/dim]")
    
    tools_state = "[success]ENABLED[/success]" if engine.tools_enabled else "[error]DISABLED[/error]"
    proxy_state = "[success]ON[/success]" if engine.subagent_proxy.enabled else "[error]OFF[/error]"
    selfheal_state = "[success]ON[/success]" if engine.self_healer.enabled else "[error]OFF[/error]"
    hooks_state = "[success]ON[/success]" if hooks.hook_manager.enabled else "[error]OFF[/error]"
    debug_state = "[success]ON[/success]" if engine.debug_mode else "[error]OFF[/error]"
    
    schemas = engine.tool_registry.get_schemas()
    console.print(f"• [label]Tools:[/label] {tools_state} ({len(schemas)} active schemas)")
    console.print(f"• [label]Indexed AST Symbols:[/label] {len(symbol_search.symbol_indexer.symbol_index)} codebase symbols")
    console.print(f"• [label]Active Branch:[/label] [accent]{engine.checkpoint_mgr.active_branch}[/accent] ({len(engine.checkpoint_mgr.checkpoints)} saved checkpoints)")

    filename, _ = project_rules.find_and_read_project_rules(".")
    proj_rules_str = f"[success]{filename}[/success]" if filename else "[dim]none[/dim]"
    console.print(f"• [label]Project Rules:[/label] {proj_rules_str}")

    console.print(f"• [label]Sub-Agent Proxy Distillation:[/label] {proxy_state}")
    console.print(f"• [label]Self-Healing Tool-Error Recovery:[/label] {selfheal_state}")
    console.print(f"• [label]Post-Edit Linter Hooks:[/label] {hooks_state}")
    console.print(f"• [label]Delegation Recursion Depth:[/label] {engine.config_mgr.config.max_delegation_depth}")
    guard_state = "[success]ON[/success]" if engine.safety_guard.enabled else "[error]OFF[/error]"
    guard_model_str = engine.config_mgr.config.guard_model or f"{engine.config_mgr.config.active_model} (active)"
    console.print(
        f"• [label]Safety Guard:[/label] {guard_state} "
        f"(mode: {engine.config_mgr.config.guard_autonomy}, model: {guard_model_str})"
    )
    advisor_model_str = engine.config_mgr.config.advisor_model or f"{engine.config_mgr.config.active_model} (active)"
    console.print(f"• [label]Advisor Model:[/label] {advisor_model_str}")
    console.print(f"• [label]Mode:[/label] {__import__('modes').MODES[engine.current_mode].label}")
    console.print(f"• [label]Debug Mode:[/label] {debug_state}")
    
    skills = engine.skill_registry.list_skills()
    active_skills_count = sum(1 for s in skills.values() if s.enabled)
    console.print(f"• [label]Skills:[/label] {active_skills_count}/{len(skills)} active")
    
    mcp_info = engine.mcp_manager.get_server_info()
    connected_mcp_count = sum(1 for details in mcp_info.values() if details["connected"])
    global_mcp_state = "[success]ENABLED[/success]" if engine.mcp_manager.global_enabled else "[error]DISABLED[/error]"
    console.print(f"• [label]MCP Servers:[/label] {global_mcp_state} ({connected_mcp_count}/{len(mcp_info)} connected)")
    
    console.print(f"• [label]Allowed Directories:[/label] {len(engine.permission_manager.allowed_dirs)} directories")

    est_tokens = estimate_tokens(engine.messages)
    window = max(1, model_cfg.context_window)
    usage_pct = int((est_tokens / window) * 100)
    autocompact_state = "[success]ON[/success]" if engine.config_mgr.config.auto_compact else "[error]OFF[/error]"
    console.print(
        f"• [label]Context Window:[/label] {len(engine.messages)} messages, "
        f"~{est_tokens}/{window} est. tokens ({usage_pct}%)"
    )
    console.print(
        f"• [label]Session Usage & Cost:[/label] {engine.session_prompt_tokens} in, {engine.session_completion_tokens} out "
        f"([accent]${engine.session_cost_usd:.4f} USD total[/accent])"
    )
    console.print(
        f"• [label]Auto-Compaction:[/label] {autocompact_state} "
        f"(triggers at {int(engine.config_mgr.config.auto_compact_threshold * 100)}%)"
    )
    console.print(f"• [label]System Prompt Length:[/label] {len(sys_prompt)} chars (~{len(sys_prompt.split())} words)")

    if engine.goal_tool.has_goal():
        snapshot = engine.goal_tool.snapshot()
        crit_str = f", {snapshot['criteria_complete']}/{snapshot['criteria_total']} criteria met" if snapshot["criteria_total"] else ""
        console.print(f"• [label]Goal:[/label] {snapshot['goal']}{crit_str}\n")
    else:
        console.print("• [label]Goal:[/label] [muted]none set[/muted]\n")


async def cmd_config(engine: Any, args: List[str]):
    cfg = engine.config_mgr.config

    if not args:
        proxy_s = "[success]ON[/success]" if engine.subagent_proxy.enabled else "[error]OFF[/error]"
        heal_s = "[success]ON[/success]" if engine.self_healer.enabled else "[error]OFF[/error]"
        hooks_s = "[success]ON[/success]" if hooks.hook_manager.enabled else "[error]OFF[/error]"
        compact_s = "[success]ON[/success]" if cfg.auto_compact else "[error]OFF[/error]"

        console.print("\n[success]Mesh System Configuration:[/success]")
        console.print(f"  • [label]proxy[/label]: {proxy_s}")
        console.print(f"  • [label]repair[/label]: {heal_s}")
        console.print(f"  • [label]hooks[/label]: {hooks_s}")
        console.print(f"  • [label]compact[/label]: {compact_s} (threshold: {int(cfg.auto_compact_threshold * 100)}%)\n")
        console.print("Usage: [warning]/config proxy [on|off][/warning] | [warning]/config repair [on|off][/warning] | [warning]/config hooks [on|off][/warning] | [warning]/config compact [on|off|threshold <0-100>][/warning]\n")
        return

    sub = args[0].lower()
    sub_args = args[1:]

    if sub == "proxy":
        if not sub_args:
            state_str = "[success]ON[/success]" if engine.subagent_proxy.enabled else "[error]OFF[/error]"
            console.print(f"Proxy distillation is {state_str}.")
            return
        if sub_args[0].lower() == "on":
            engine.subagent_proxy.enabled = True
            console.print("[success]Sub-agent proxy distillation ENABLED.[/success]")
        elif sub_args[0].lower() == "off":
            engine.subagent_proxy.enabled = False
            console.print("[warning]Sub-agent proxy distillation DISABLED.[/warning]")

    elif sub in ("repair", "selfheal"):
        if not sub_args:
            state_str = "[success]ON[/success]" if engine.self_healer.enabled else "[error]OFF[/error]"
            console.print(f"Self-healing repair is {state_str}.")
            return
        if sub_args[0].lower() == "on":
            engine.self_healer.enabled = True
            console.print("[success]Self-healing tool recovery ENABLED.[/success]")
        elif sub_args[0].lower() == "off":
            engine.self_healer.enabled = False
            console.print("[warning]Self-healing tool recovery DISABLED.[/warning]")

    elif sub == "hooks":
        if not sub_args:
            state_str = "[success]ON[/success]" if hooks.hook_manager.enabled else "[error]OFF[/error]"
            console.print(f"Post-edit hooks are {state_str}.")
            return
        if sub_args[0].lower() == "on":
            hooks.hook_manager.enabled = True
            console.print("[success]Post-edit linter hooks ENABLED.[/success]")
        elif sub_args[0].lower() == "off":
            hooks.hook_manager.enabled = False
            console.print("[warning]Post-edit linter hooks DISABLED.[/warning]")

    elif sub == "compact":
        if not sub_args:
            state_str = "[success]ON[/success]" if cfg.auto_compact else "[error]OFF[/error]"
            console.print(f"Auto-compaction is {state_str} (threshold: {int(cfg.auto_compact_threshold * 100)}%).")
            return
        act = sub_args[0].lower()
        if act == "on":
            cfg.auto_compact = True
            console.print("[success]Auto-compaction ENABLED.[/success]")
        elif act == "off":
            cfg.auto_compact = False
            console.print("[warning]Auto-compaction DISABLED.[/warning]")
        elif act == "threshold" and len(sub_args) > 1:
            try:
                pct = float(sub_args[1])
                if 0 < pct <= 100:
                    cfg.auto_compact_threshold = pct / 100.0
                    console.print(f"[success]Auto-compaction threshold set to {pct:.0f}%.[/success]")
                else:
                    console.print("[error]Threshold must be between 0 and 100.[/error]")
            except ValueError:
                console.print("[error]Threshold must be a number between 0 and 100.[/error]")

    else:
        console.print("[error]Usage: /config [proxy|repair|hooks|compact] <args>[/error]")


async def cmd_context(engine: Any, args: List[str]):
    console.print(f"\n[success]=== CONTEXT MESSAGES ({len(engine.messages)} Messages) ===[/success]\n")
    for idx, msg in enumerate(engine.messages):
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

    tools_state = "[success]ENABLED[/success]" if engine.tools_enabled else "[error]DISABLED[/error]"
    proxy_state = "[success]ON[/success]" if engine.subagent_proxy.enabled else "[error]OFF[/error]"
    console.print(f"[success]=== ACTIVE TOOL SCHEMAS ({tools_state} | Proxy Distillation: {proxy_state}) ===[/success]\n")
    if engine.tools_enabled:
        schemas = engine.tool_registry.get_schemas()
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

    global_mcp_str = "[success]ENABLED[/success]" if engine.mcp_manager.global_enabled else "[error]DISABLED[/error]"
    console.print(f"[success]=== MCP SERVERS & TOOLS (Global MCP: {global_mcp_str}) ===[/success]\n")
    mcp_info = engine.mcp_manager.get_server_info()
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


async def cmd_system(engine: Any, args: List[str]):
    sys_idx = next((i for i, m in enumerate(engine.messages) if m.get("role") == "system"), None)

    if not args:
        current = engine.messages[sys_idx]["content"] if sys_idx is not None else "[dim]<none>[/dim]"
        console.print(f"[success]Current System Prompt:[/success]\n{current}\n")
        console.print("Usage: [warning]/system [text][/warning] or [warning]/system clear[/warning]")
        return

    new_prompt = " ".join(args).strip()
    if new_prompt.lower() == "clear":
        if sys_idx is not None:
            engine.messages.pop(sys_idx)
        console.print("[warning]System prompt cleared from context.[/warning]")
    else:
        if sys_idx is not None:
            engine.messages[sys_idx]["content"] = new_prompt
        else:
            engine.messages.insert(0, {"role": "system", "content": new_prompt})
        console.print(f"[success]System prompt updated to:[/success]\n{new_prompt}")


async def cmd_tools(engine: Any, args: List[str]):
    if not args:
        state_str = "[success]ON[/success]" if engine.tools_enabled else "[error]OFF[/error]"
        console.print(f"Tool inclusion & execution is currently {state_str}.\n")
        console.print("[success]Available Registered Tools:[/success]")
        schemas = engine.tool_registry.get_schemas()
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
        engine.tools_enabled = True
        console.print("[success]Tool context inclusion & execution enabled.[/success]")
    elif arg == "off":
        engine.tools_enabled = False
        console.print("[warning]Tool context inclusion & execution disabled.[/warning]")
    else:
        console.print("[error]Invalid option. Use '/tools on' or '/tools off'.[/error]")


async def cmd_skills(engine: Any, args: List[str]):
    skills = engine.skill_registry.list_skills()
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
        success = engine.skill_registry.set_skill_state(target, enable_flag)
        if success:
            engine.update_system_message()
            console.print(f"[success]Skill '{target}' set to {action}d.[/success]")
        else:
            console.print(f"[error]Skill '{target}' not found.[/error]")
    else:
        console.print("[error]Usage: /skills enable <name> or /skills disable <name>[/error]")


async def cmd_dirs(engine: Any, args: List[str]):
    if not args:
        console.print("\n[success]Currently Allowed Directories:[/success]")
        for d in engine.permission_manager.allowed_dirs:
            console.print(f"  • [label]{d}[/label]")
        console.print("\nUsage: [warning]/dirs add <path>[/warning] or [warning]/dirs remove <path>[/warning] or [warning]/dirs clear[/warning]\n")
        return

    action = args[0].lower()
    if action == "add" and len(args) > 1:
        target_path = " ".join(args[1:])
        added = engine.permission_manager.add_dir(target_path)
        console.print(f"[success]Added directory to allowed list:[/success] {added}")
    elif action == "remove" and len(args) > 1:
        target_path = " ".join(args[1:])
        removed = engine.permission_manager.remove_dir(target_path)
        if removed:
            console.print(f"[warning]Removed directory from allowed list:[/warning] {target_path}")
        else:
            console.print(f"[error]Directory not found in allowed list:[/error] {target_path}")
    elif action == "clear":
        engine.permission_manager.allowed_dirs = [str(__import__('os').getcwd())]
        console.print("[warning]Reset allowed directories to Current Working Directory.[/warning]")
    else:
        console.print("[error]Usage: /dirs add <path> | /dirs remove <path> | /dirs clear[/error]")


async def cmd_mcps(engine: Any, args: List[str]):
    info = engine.mcp_manager.get_server_info()
    if not info:
        console.print("[dim]No MCP servers configured in mcps.json.[/dim]")
        return

    if args:
        action = args[0].lower()
        if action == "on":
            engine.mcp_manager.set_global_state(True, engine.tool_registry)
            console.print("[success]All MCP tools globally ENABLED.[/success]")
            return
        elif action == "off":
            engine.mcp_manager.set_global_state(False, engine.tool_registry)
            console.print("[warning]All MCP tools globally DISABLED.[/warning]")
            return
        elif action in ["enable", "disable"] and len(args) > 1:
            target = args[1]
            enable_flag = (action == "enable")
            success = engine.mcp_manager.set_server_state(target, enable_flag, engine.tool_registry)
            if success:
                state_str = "enabled" if enable_flag else "disabled"
                console.print(f"[success]MCP Server '{target}' tools {state_str}.[/success]")
            else:
                console.print(f"[error]MCP Server '{target}' not found.[/error]")
            return
        else:
            console.print("[error]Usage: /mcps on | /mcps off | /mcps enable <server_name> | /mcps disable <server_name>[/error]")
            return

    global_str = "[success]ENABLED[/success]" if engine.mcp_manager.global_enabled else "[error]DISABLED[/error]"
    console.print(f"\n[success]Configured MCP Servers (Global MCP Status: {global_str}):[/success]\n")

    for name, details in info.items():
        status = "[success]CONNECTED[/success]" if details["connected"] else "[error]DISCONNECTED[/error]"
        enabled_str = "[success]ENABLED[/success]" if details["enabled"] else "[error]DISABLED[/error]"
        cmd_str = f"{details['command']} {' '.join(details['args'])}" if details['command'] else "N/A"
        
        console.print(f"• [label]{name}[/label] ({status}) ({enabled_str}) — [dim]{escape(cmd_str)}[/dim]")
        
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


async def cmd_compact(engine: Any, args: List[str]):
    console.print("[warning]Analyzing and compacting conversation history...[/warning]")
    new_messages, success, details = await compact_messages(engine.messages, engine.config_mgr)
    if success:
        engine.messages = new_messages
        console.print(f"[success]Compaction Successful![/success] {details}")
    else:
        console.print(f"[warning]{details}[/warning]")


async def cmd_clear(engine: Any, args: List[str]):
    engine.update_system_message()
    console.print("[warning]Conversation context cleared (system prompt and skills preserved).[/warning]")


async def cmd_retry(engine: Any, args: List[str]):
    last_user_idx = None
    for i in range(len(engine.messages) - 1, -1, -1):
        if engine.messages[i].get("role") == "user":
            last_user_idx = i
            break

    if last_user_idx is None:
        console.print("[warning]No user message found in context to retry.[/warning]")
        return

    engine.messages = engine.messages[:last_user_idx + 1]
    console.print("[warning]Retrying last completion turn...[/warning]")
    await engine.process_inference()


async def cmd_debug(engine: Any, args: List[str]):
    if not args:
        state_str = "[success]ON[/success]" if engine.debug_mode else "[error]OFF[/error]"
        console.print(f"Debug mode is currently {state_str}. Usage: [warning]/debug on[/warning] or [warning]/debug off[/warning]")
        return

    arg = args[0].lower()
    if arg == "on":
        engine.debug_mode = True
        engine.subagent_proxy.debug_mode = True
        console.print("[success]Debug mode enabled.[/success] CoT and Tool execution details will be shown.")
    elif arg == "off":
        engine.debug_mode = False
        engine.subagent_proxy.debug_mode = False
        console.print("[warning]Debug mode disabled.[/warning] CoT will be hidden.")
    else:
        console.print("[error]Invalid debug option. Use '/debug on' or '/debug off'.[/error]")


async def cmd_exit(engine: Any, args: List[str]):
    console.print("[warning]Closing MCP connections and exiting. Goodbye![/warning]")
    try:
        await asyncio.wait_for(engine.mcp_manager.close_all(), timeout=3.0)
    except Exception:
        pass
    sys.exit(0)


def register_system_commands(engine: Any):
    engine.cmd_registry.register("help", "Show available slash commands", lambda args: cmd_help(engine, args))
    engine.cmd_registry.register("status", "Show current Mesh status overview", lambda args: cmd_status(engine, args))
    engine.cmd_registry.register("config", "View or set automation toggles: /config [proxy|repair|hooks|compact]", lambda args: cmd_config(engine, args))
    engine.cmd_registry.register("context", "Display context window, tool schemas, and MCP status", lambda args: cmd_context(engine, args))
    engine.cmd_registry.register("system", "Show the system prompt, or set it: /system <text> | /system clear", lambda args: cmd_system(engine, args))
    engine.cmd_registry.register("tools", "List registered tools, or toggle inclusion: /tools on | /tools off", lambda args: cmd_tools(engine, args))
    engine.cmd_registry.register("skills", "List skills, or toggle one: /skills enable <name> | /skills disable <name>", lambda args: cmd_skills(engine, args))
    engine.cmd_registry.register("dirs", "List allowed directories, or edit them: /dirs add <path> | /dirs remove <path> | /dirs clear", lambda args: cmd_dirs(engine, args))
    engine.cmd_registry.register("mcps", "List MCP servers, or toggle them: /mcps on | /mcps off | /mcps enable <server_name> | /mcps disable <server_name>", lambda args: cmd_mcps(engine, args))
    engine.cmd_registry.register("compact", "Semantically summarize older conversation context", lambda args: cmd_compact(engine, args))
    engine.cmd_registry.register("clear", "Clear the conversation context window", lambda args: cmd_clear(engine, args))
    engine.cmd_registry.register("retry", "Retry the last LLM response turn", lambda args: cmd_retry(engine, args))
    engine.cmd_registry.register("debug", "Toggle debug mode (CoT & tool traces): /debug on | /debug off", lambda args: cmd_debug(engine, args))
    engine.cmd_registry.register("exit", "Exit Mesh", lambda args: cmd_exit(engine, args))