import asyncio
import sys
from typing import List, Any
from rich.markup import escape
from rich.markdown import Markdown
from compaction import compact_messages, estimate_tokens
import symbol_search
import project_rules
import hooks
import jobs
from theme import console
from version import __version__


CONFIG_SET_MAP = {
    "timeout": {
        "web": ("timeouts", "web", float, "Web search/fetch HTTP request timeout (sec)"),
        "shell": ("timeouts", "shell", float, "Native shell command execution timeout (sec)"),
        "mcp": ("timeouts", "mcp", float, "MCP client request timeout (sec)"),
        "linter": ("timeouts", "linter", float, "Post-edit linter hook execution timeout (sec)"),
        "python": ("timeouts", "python", float, "Python execution tool timeout (sec)"),
        "api": ("timeouts", "api", float, "Provider model discovery API call timeout (sec)"),
    },
    "budget": {
        "web": ("budgets", "web", int, "Web fetch maximum text character limit"),
        "repo-map": ("budgets", "repo_map", int, "Repository architecture map token budget"),
        "dream": ("budgets", "dream", int, "Dream analysis transcript max character budget"),
        "git-diff": ("budgets", "git_diff", int, "Git commit message generator diff character budget"),
        "symbol": ("budgets", "symbol", int, "Maximum symbol search matches returned"),
    },
    "turns": {
        "agent": ("turns", "agent", int, "Default maximum tool turns per sub-agent"),
        "engine": ("turns", "engine", int, "Maximum assistant turn loops per prompt turn"),
        "loop": ("turns", "loop", int, "Maximum test/fix iterations for /loop"),
        "depth": ("turns", "depth", int, "Maximum delegation recursion depth"),
        "branches": ("turns", "branches", int, "Default parallel strategy branches for /agent explore"),
    },
    "repair": {
        "retries": ("repair_settings", "retries", int, "Mechanical retries for transient tool errors"),
        "delay": ("repair_settings", "delay", float, "Mechanical retry delay in seconds"),
    },
    "retry": {
        "retries": ("retry_settings", "retries", int, "Maximum provider API request retry attempts"),
        "initial-delay": ("retry_settings", "initial_delay", float, "Initial retry delay in seconds"),
        "max-delay": ("retry_settings", "max_delay", float, "Maximum backoff delay ceiling in seconds"),
        "backoff-factor": ("retry_settings", "backoff_factor", float, "Exponential backoff multiplier factor"),
        "jitter": ("retry_settings", "jitter", bool, "Apply randomized jitter to retry backoff delay (true/false)"),
    },
    "compact": {
        "threshold": ("auto_compact_threshold", None, float, "Auto-compaction context threshold ratio (0.01-1.0 or 1-100%)"),
        "minkeep": ("compaction_settings", "minkeep", int, "Minimum recent messages to keep uncompacted"),
    }
}


async def cmd_help(engine: Any, args: List[str]):
    commands = engine.cmd_registry.list_commands()

    if args:
        target = args[0].lower().strip()
        if not target.startswith("/"):
            target = f"/{target}"

        if target in commands:
            desc = commands[target]
            console.print(f"\n[success]Help for {target}:[/success]")
            console.print(f"  [label]{target}[/label] — {escape(desc)}\n")
            return
        else:
            console.print(f"[error]Unknown command '{target}'. Type /help to see available commands.[/error]\n")
            return

    console.print("\n[success]Available Slash Commands:[/success]\n")

    categorized = engine.cmd_registry.list_commands_by_category()

    for category, cmds in categorized.items():
        console.print(f"[brand]▸ {category}[/brand]")
        cmd_labels = [f"[label]{cmd}[/label]" for cmd, _ in cmds]
        console.print(f"  {', '.join(cmd_labels)}\n")

    console.print("Type [warning]/help <command>[/warning] (e.g., [warning]/help git[/warning]) for detailed usage.\n")


async def cmd_history(engine: Any, args: List[str]):
    prompt_session = getattr(engine, "prompt_session", None)
    if not prompt_session:
        console.print("[error]Prompt session is unavailable.[/error]")
        return

    if args and args[0].lower() == "clear":
        success, msg = prompt_session.clear_history()
        console.print(f"[{'success' if success else 'error'}]{msg}[/{'success' if success else 'error'}]")
        return

    limit = 30
    if args and args[0].isdigit():
        limit = max(1, int(args[0]))

    entries = prompt_session.get_history_entries(limit=limit)
    console.print(f"\n[success]=== Command History (Last {len(entries)}) ===[/success]\n")
    if not entries:
        console.print("  [dim]Command history is empty (.mesh/history.txt).[/dim]\n")
    else:
        for idx, (timestamp, command) in enumerate(entries, 1):
            if timestamp:
                console.print(f"  [dim]{timestamp}[/dim]")
            console.print(f"  [dim]{idx:3d}.[/dim] [text]{escape(command)}[/text]")
        console.print()

    console.print("Usage: [warning]/history[/warning] | [warning]/history <limit>[/warning] | [warning]/history clear[/warning]\n")


async def cmd_status(engine: Any, args: List[str]):
    cfg = engine.config_mgr.config
    active_key = cfg.active_model

    if active_key == "auto":
        model_str = f"auto (dynamic router using [accent]{cfg.router_model or 'none'}[/accent])"
        p_str = "Dynamic Auto-Router"
    else:
        model_cfg, provider_cfg = engine.config_mgr.get_active_model_and_provider()
        model_str = f"{model_cfg.name} ({active_key})"
        p_str = f"{provider_cfg.name} | Base URL: {provider_cfg.base_url} | Model ID: {model_cfg.model_id}"

    sys_idx = next((i for i, m in enumerate(engine.messages) if m.get("role") == "system"), None)
    sys_prompt = engine.messages[sys_idx]["content"] if sys_idx is not None else "None"
    
    console.print(f"\n[success]=== MESH STATUS (v{__version__}) ===[/success]")
    console.print("[dim]Developed by Farshid Mossaiby | https://github.com/mossaiby/Mesh[/dim]\n")
    console.print(f"• [label]Active Model:[/label] {model_str}")
    console.print(f"  [dim]Provider: {p_str}[/dim]")
    
    tools_state = "[success]ENABLED[/success]" if engine.tools_enabled else "[error]DISABLED[/error]"
    distill_state = "[success]ON[/success]" if engine.subagent_distiller.enabled else "[error]OFF[/error]"
    repair_state = "[success]ON[/success]" if engine.repair_engine.enabled else "[error]OFF[/error]"
    hooks_state = "[success]ON[/success]" if hooks.hook_manager.enabled else "[error]OFF[/error]"
    debug_state = "[success]ON[/success]" if engine.debug_mode else "[error]OFF[/error]"
    
    schemas = engine.tool_registry.get_schemas()
    console.print(f"• [label]Tools:[/label] {tools_state} ({len(schemas)} active schemas)")
    
    indexing_tag = " [accent](indexing in background...)[/accent]" if symbol_search.symbol_indexer.is_indexing else ""
    console.print(f"• [label]Indexed AST Symbols:[/label] {len(symbol_search.symbol_indexer.symbol_index)} codebase symbols (cache: .mesh/symbols.cache.json){indexing_tag}")
    console.print(f"• [label]Active Branch:[/label] [accent]{engine.checkpoint_mgr.active_branch}[/accent] ({len(engine.checkpoint_mgr.checkpoints)} saved checkpoints)")

    filename, _ = project_rules.find_and_read_project_rules(".")
    proj_rules_str = f"[success]{filename}[/success]" if filename else "[dim]none[/dim]"
    console.print(f"• [label]Project Rules:[/label] {proj_rules_str}")

    console.print(f"• [label]Sub-Agent Tool Distillation:[/label] {distill_state}")
    console.print(f"• [label]Repair Engine:[/label] {repair_state}")
    console.print(f"• [label]Post-Edit Linter Hooks:[/label] {hooks_state}")
    console.print(f"• [label]Delegation Recursion Depth:[/label] {cfg.max_delegation_depth}")
    guard_state = "[success]ON[/success]" if engine.safety_guard.enabled else "[error]OFF[/error]"
    guard_model_str = cfg.guard_model or f"{cfg.active_model} (active)"
    console.print(
        f"• [label]Safety Guard:[/label] {guard_state} "
        f"(mode: {cfg.guard_autonomy}, model: {guard_model_str})"
    )
    advisor_model_str = cfg.advisor_model or f"{cfg.active_model} (active)"
    console.print(f"• [label]Advisor Model:[/label] {advisor_model_str}")
    router_model_str = cfg.router_model or "[dim]none set[/dim]"
    console.print(f"• [label]Router Model:[/label] {router_model_str}")

    proxy_url_str = cfg.network_proxy or "[dim]disabled (direct)[/dim]"
    console.print(f"• [label]Network Proxy:[/label] {proxy_url_str}")

    thinking_s = "[success]ON[/success]" if cfg.thinking else "[error]OFF[/error]"
    console.print(f"• [label]Thinking / Reasoning:[/label] {thinking_s} (effort: [accent]{cfg.effort}[/accent])")

    tokens_s = "[success]ON[/success]" if cfg.show_tokens else "[error]OFF[/error]"
    cost_s = "[success]ON[/success]" if cfg.show_cost else "[error]OFF[/error]"
    stats_s = "[success]ON[/success]" if cfg.show_statistics else "[error]OFF[/error]"
    console.print(f"• [label]Metrics Display:[/label] tokens ({tokens_s}), cost ({cost_s}), statistics ({stats_s})")

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
    window = max(1, cfg.models.get(cfg.active_model, cfg.models.get(cfg.router_model, list(cfg.models.values())[0])).context_window) if cfg.models else 8192
    usage_pct = int((est_tokens / window) * 100)
    autocompact_state = "[success]ON[/success]" if cfg.auto_compact else "[error]OFF[/error]"
    console.print(
        f"• [label]Context Window:[/label] {len(engine.messages)} messages, "
        f"~{est_tokens}/{window} est. tokens ({usage_pct}%)"
    )
    cached_str = f" ({engine.session_cached_tokens} cached)" if getattr(engine, "session_cached_tokens", 0) > 0 else ""
    console.print(
        f"• [label]Session Usage & Cost:[/label] {engine.session_prompt_tokens} in{cached_str}, {engine.session_completion_tokens} out "
        f"([accent]${engine.session_cost_usd:.4f} USD total[/accent])"
    )
    console.print(
        f"• [label]Auto-Compaction:[/label] {autocompact_state} "
        f"(triggers at {int(cfg.auto_compact_threshold * 100)}%)"
    )
    console.print(f"• [label]System Prompt Length:[/label] {len(sys_prompt)} chars (~{len(sys_prompt.split())} words)")

    if engine.goal_tool.has_goal():
        snapshot = engine.goal_tool.snapshot()
        crit_str = f", {snapshot['criteria_complete']}/{snapshot['criteria_total']} criteria met" if snapshot["criteria_total"] else ""
        console.print(f"• [label]Goal:[/label] {snapshot['goal']}{crit_str}\n")
    else:
        console.print("• [label]Goal:[/label] [muted]none set[/muted]\n")


async def _handle_config_set(engine: Any, set_args: List[str]):
    cfg = engine.config_mgr.config

    if not set_args:
        console.print("\n[success]Configurable System Parameters (/config set):[/success]\n")
        for cat, params in CONFIG_SET_MAP.items():
            console.print(f"[brand]▸ Category: {cat}[/brand]")
            for p_name, (container_attr, sub_attr, val_type, desc) in params.items():
                if sub_attr:
                    curr_val = getattr(getattr(cfg, container_attr), sub_attr)
                else:
                    curr_val = getattr(cfg, container_attr)
                    if p_name == "threshold":
                        curr_val = f"{int(curr_val * 100)}%"
                console.print(f"  • [label]{cat} {p_name}[/label]: [accent]{curr_val}[/accent] — [dim]{desc}[/dim]")
            console.print()
        console.print("Usage: [warning]/config set <category> <param> <value>[/warning] (e.g. [warning]/config set timeout web 120[/warning] or [warning]/config set retry retries 5[/warning])\n")
        return

    category = set_args[0].lower()
    if category not in CONFIG_SET_MAP:
        valid_cats = ", ".join(CONFIG_SET_MAP.keys())
        console.print(f"[error]Unknown config set category '{category}'. Valid categories: {valid_cats}[/error]")
        return

    params = CONFIG_SET_MAP[category]

    if len(set_args) == 1:
        console.print(f"\n[success]Category '{category}' Parameters:[/success]\n")
        for p_name, (container_attr, sub_attr, val_type, desc) in params.items():
            if sub_attr:
                curr_val = getattr(getattr(cfg, container_attr), sub_attr)
            else:
                curr_val = getattr(cfg, container_attr)
                if p_name == "threshold":
                    curr_val = f"{int(curr_val * 100)}%"
            console.print(f"  • [label]{category} {p_name}[/label]: [accent]{curr_val}[/accent] — [dim]{desc}[/dim]")
        console.print(f"\nUsage: [warning]/config set {category} <param> <value>[/warning]\n")
        return

    param = set_args[1].lower()
    if param not in params:
        valid_params = ", ".join(params.keys())
        console.print(f"[error]Unknown parameter '{param}' in category '{category}'. Valid parameters: {valid_params}[/error]")
        return

    container_attr, sub_attr, val_type, desc = params[param]

    if len(set_args) == 2:
        if sub_attr:
            curr_val = getattr(getattr(cfg, container_attr), sub_attr)
        else:
            curr_val = getattr(cfg, container_attr)
            if param == "threshold":
                curr_val = f"{int(curr_val * 100)}%"
        console.print(
            f"Parameter [label]{category} {param}[/label] is currently: [accent]{curr_val}[/accent]\n"
            f"Description: [dim]{desc}[/dim]\n"
            f"Usage: [warning]/config set {category} {param} <value>[/warning]"
        )
        return

    raw_val = set_args[2]

    try:
        if val_type == int:
            typed_val = int(raw_val)
            if typed_val < 0:
                console.print("[error]Value must be a positive integer.[/error]")
                return
        elif val_type == float:
            typed_val = float(raw_val)
            if param == "threshold":
                if typed_val > 1.0:
                    typed_val = typed_val / 100.0
                if not (0.01 <= typed_val <= 1.0):
                    console.print("[error]Threshold percentage must be between 1 and 100 (or 0.01 and 1.0).[/error]")
                    return
            elif typed_val <= 0:
                console.print("[error]Value must be greater than zero.[/error]")
                return
        elif val_type == bool:
            if raw_val.lower() in ("true", "1", "yes", "on"):
                typed_val = True
            elif raw_val.lower() in ("false", "0", "no", "off"):
                typed_val = False
            else:
                console.print("[error]Value must be 'true' or 'false'.[/error]")
                return
        else:
            typed_val = raw_val
    except ValueError:
        console.print(f"[error]Invalid value '{raw_val}'. Expected type: {val_type.__name__}.[/error]")
        return

    if sub_attr:
        setattr(getattr(cfg, container_attr), sub_attr, typed_val)
    else:
        setattr(cfg, container_attr, typed_val)

    if category == "turns" and param == "depth":
        cfg.max_delegation_depth = typed_val
    elif category == "repair":
        if hasattr(engine, "repair_engine") and engine.repair_engine:
            if param == "retries":
                engine.repair_engine.mechanical_retries = typed_val
            elif param == "delay":
                engine.repair_engine.mechanical_delay = typed_val

    engine.config_mgr.save()

    if param == "threshold":
        display_val = f"{int(typed_val * 100)}%"
    elif isinstance(typed_val, bool):
        display_val = "true" if typed_val else "false"
    else:
        display_val = f"{typed_val}"

    console.print(f"[success]✔ Successfully set [label]{category} {param}[/label] to [accent]{display_val}[/accent].[/success]")


async def cmd_config(engine: Any, args: List[str]):
    cfg = engine.config_mgr.config

    if not args:
        distill_s = "[success]ON[/success]" if engine.subagent_distiller.enabled else "[error]OFF[/error]"
        proxy_s = f"[accent]{cfg.network_proxy}[/accent]" if cfg.network_proxy else "[dim]disabled[/dim]"
        repair_s = "[success]ON[/success]" if engine.repair_engine.enabled else "[error]OFF[/error]"
        hooks_s = "[success]ON[/success]" if hooks.hook_manager.enabled else "[error]OFF[/error]"
        compact_s = "[success]ON[/success]" if cfg.auto_compact else "[error]OFF[/error]"
        thinking_s = "[success]ON[/success]" if cfg.thinking else "[error]OFF[/error]"
        effort_s = f"[accent]{cfg.effort}[/accent]"
        tokens_s = "[success]ON[/success]" if cfg.show_tokens else "[error]OFF[/error]"
        cost_s = "[success]ON[/success]" if cfg.show_cost else "[error]OFF[/error]"
        stats_s = "[success]ON[/success]" if cfg.show_statistics else "[error]OFF[/error]"

        console.print("\n[success]Mesh System Configuration:[/success]")
        console.print(f"  • [label]distill[/label]: {distill_s}")
        console.print(f"  • [label]proxy[/label]: {proxy_s}")
        console.print(f"  • [label]repair[/label]: {repair_s}")
        console.print(f"  • [label]hooks[/label]: {hooks_s}")
        console.print(f"  • [label]compact[/label]: {compact_s} (threshold: {int(cfg.auto_compact_threshold * 100)}%)")
        console.print(f"  • [label]thinking[/label]: {thinking_s}")
        console.print(f"  • [label]effort[/label]: {effort_s}")
        console.print(f"  • [label]tokens[/label]: {tokens_s}")
        console.print(f"  • [label]cost[/label]: {cost_s}")
        console.print(f"  • [label]statistics[/label]: {stats_s}")
        console.print("  • [label]schema[/label]: Generate or update config.schema.json for IDE autocompletion")
        console.print("  • [label]set[/label]: Fine-tune timeouts, budgets, turns, repair, retry, & compaction parameters")
        console.print("    [dim](Usage: /config set <category> <param> <value>, e.g. /config set timeout web 120 or /config set retry retries 5)[/dim]\n")
        console.print("Usage: [warning]/config distill|proxy|repair|hooks|compact|thinking|effort|tokens|cost|statistics|schema|set [args][/warning]\n")
        return

    sub = args[0].lower()
    sub_args = args[1:]

    if sub == "set":
        await _handle_config_set(engine, sub_args)

    elif sub == "schema":
        target_path = sub_args[0] if sub_args else "config.schema.json"
        from config import generate_config_schema
        generate_config_schema(target_path)
        console.print(f"[success]✔ Generated IDE JSON Schema for Mesh config -> `{target_path}`[/success]")

    elif sub == "distill":
        if not sub_args:
            state_str = "[success]ON[/success]" if engine.subagent_distiller.enabled else "[error]OFF[/error]"
            console.print(f"Sub-agent tool output distillation is {state_str}.")
            return
        if sub_args[0].lower() == "on":
            engine.subagent_distiller.enabled = True
            console.print("[success]Sub-agent tool output distillation ENABLED.[/success]")
        elif sub_args[0].lower() == "off":
            engine.subagent_distiller.enabled = False
            console.print("[warning]Sub-agent tool output distillation DISABLED.[/warning]")

    elif sub == "proxy":
        if not sub_args:
            proxy_str = f"[accent]{cfg.network_proxy}[/accent]" if cfg.network_proxy else "[dim]disabled (direct connection)[/dim]"
            console.print(f"Network proxy is currently: {proxy_str}\nUsage: [warning]/config proxy <url>[/warning] | [warning]/config proxy clear[/warning]")
            return
        target_val = sub_args[0]
        if target_val.lower() in ("clear", "off", "none", "disable"):
            cfg.network_proxy = None
            engine.config_mgr.save()
            console.print("[success]Cleared network proxy setting and unset proxy environment variables.[/success]")
        else:
            cfg.network_proxy = target_val
            engine.config_mgr.save()
            console.print(f"[success]Network proxy set to '[accent]{target_val}[/accent]' and applied to environment variables.[/success]")

    elif sub == "repair":
        if not sub_args:
            state_str = "[success]ON[/success]" if engine.repair_engine.enabled else "[error]OFF[/error]"
            console.print(f"Repair Engine is {state_str}.")
            return
        if sub_args[0].lower() == "on":
            engine.repair_engine.enabled = True
            console.print("[success]Repair Engine ENABLED.[/success]")
        elif sub_args[0].lower() == "off":
            engine.repair_engine.enabled = False
            console.print("[warning]Repair Engine DISABLED.[/warning]")

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
            engine.config_mgr.save()
            console.print("[success]Auto-compaction ENABLED.[/success]")
        elif act == "off":
            cfg.auto_compact = False
            engine.config_mgr.save()
            console.print("[warning]Auto-compaction DISABLED.[/warning]")
        elif act == "threshold" and len(sub_args) > 1:
            try:
                pct = float(sub_args[1])
                if 0 < pct <= 100:
                    cfg.auto_compact_threshold = pct / 100.0
                    engine.config_mgr.save()
                    console.print(f"[success]Auto-compaction threshold set to {pct:.0f}%.[/success]")
                else:
                    console.print("[error]Threshold must be between 0 and 100.[/error]")
            except ValueError:
                console.print("[error]Threshold must be a number between 0 and 100.[/error]")

    elif sub == "thinking":
        if not sub_args:
            state_str = "[success]ON[/success]" if cfg.thinking else "[error]OFF[/error]"
            console.print(f"Thinking / Reasoning mode is {state_str}.")
            return
        act = sub_args[0].lower()
        if act == "on":
            cfg.thinking = True
            engine.config_mgr.save()
            console.print("[success]Thinking / Reasoning mode ENABLED.[/success]")
        elif act == "off":
            cfg.thinking = False
            engine.config_mgr.save()
            console.print("[warning]Thinking / Reasoning mode DISABLED.[/warning]")

    elif sub == "effort":
        if not sub_args:
            console.print(f"Reasoning effort level is currently: [accent]{cfg.effort}[/accent]\nUsage: [warning]/config effort low|medium|high[/warning]")
            return
        act = sub_args[0].lower()
        if act in ("low", "medium", "high"):
            cfg.effort = act
            engine.config_mgr.save()
            console.print(f"[success]Reasoning effort level set to '[accent]{act}[/accent]'.[/success]")
        else:
            console.print("[error]Invalid effort level. Options: low, medium, high.[/error]")

    elif sub == "tokens":
        if not sub_args:
            state_str = "[success]ON[/success]" if cfg.show_tokens else "[error]OFF[/error]"
            console.print(f"Token count display is {state_str}.")
            return
        act = sub_args[0].lower()
        if act == "on":
            cfg.show_tokens = True
            engine.config_mgr.save()
            console.print("[success]Token count display ENABLED.[/success]")
        elif act == "off":
            cfg.show_tokens = False
            engine.config_mgr.save()
            console.print("[warning]Token count display DISABLED.[/warning]")

    elif sub == "cost":
        if not sub_args:
            state_str = "[success]ON[/success]" if cfg.show_cost else "[error]OFF[/error]"
            console.print(f"Cost display is {state_str}.")
            return
        act = sub_args[0].lower()
        if act == "on":
            cfg.show_cost = True
            engine.config_mgr.save()
            console.print("[success]Cost display ENABLED.[/success]")
        elif act == "off":
            cfg.show_cost = False
            engine.config_mgr.save()
            console.print("[warning]Cost display DISABLED.[/warning]")

    elif sub == "statistics":
        if not sub_args:
            state_str = "[success]ON[/success]" if cfg.show_statistics else "[error]OFF[/error]"
            console.print(f"Token statistics display is {state_str}.")
            return
        act = sub_args[0].lower()
        if act == "on":
            cfg.show_statistics = True
            engine.config_mgr.save()
            console.print("[success]Token statistics display (TTFT, tok/s) ENABLED.[/success]")
        elif act == "off":
            cfg.show_statistics = False
            engine.config_mgr.save()
            console.print("[warning]Token statistics display DISABLED.[/warning]")

    else:
        console.print("[error]Usage: /config [distill|proxy|repair|hooks|compact|thinking|effort|tokens|cost|statistics|schema|set] <args>[/error]")


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
            console.print(Markdown(content))
        if tool_calls:
            console.print(f"  [dim italic]Tool Calls: {tool_calls}[/dim italic]")
        if not content and not tool_calls:
            console.print("  [dim]<empty>[/dim]")

        console.print()

    tools_state = "[success]ENABLED[/success]" if engine.tools_enabled else "[error]DISABLED[/error]"
    distill_s = "[success]ON[/success]" if engine.subagent_distiller.enabled else "[error]OFF[/error]"
    console.print(f"[success]=== ACTIVE TOOL NAMES ({tools_state} | Distillation: {distill_s}) ===[/success]\n")
    if engine.tools_enabled:
        schemas = engine.tool_registry.get_schemas()
        if schemas:
            tool_names = [s.get("function", {}).get("name", "unnamed") for s in schemas]
            console.print(f"  • [label]Registered ({len(tool_names)}):[/label] {', '.join(tool_names)}")
        else:
            console.print("  [dim]No tools currently registered.[/dim]")
    else:
        console.print("  [dim]Tools are disabled (/tools off). No schemas sent to model.[/dim]")
    console.print()

    global_mcp_str = "[success]ENABLED[/success]" if engine.mcp_manager.global_enabled else "[error]DISABLED[/error]"
    console.print(f"[success]=== MCP SERVERS (Global MCP: {global_mcp_str}) ===[/success]\n")
    mcp_info = engine.mcp_manager.get_server_info()
    if mcp_info:
        for name, details in mcp_info.items():
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
    engine.messages.clear()
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
        engine.subagent_distiller.debug_mode = True
        console.print("[success]Debug mode enabled.[/success] CoT and Tool execution details will be shown.")
    elif arg == "off":
        engine.debug_mode = False
        engine.subagent_distiller.debug_mode = False
        console.print("[warning]Debug mode disabled.[/warning] CoT will be hidden.")
    else:
        console.print("[error]Invalid debug option. Use '/debug on' or '/debug off'.[/error]")


async def cmd_exit(engine: Any, args: List[str]):
    console.print("[warning]Closing MCP connections and exiting. Goodbye![/warning]")
    if engine.session_manager.active_session_name:
        engine.session_manager.save_session()
    try:
        await jobs.job_manager.stop_all()
        await asyncio.wait_for(engine.mcp_manager.close_all(), timeout=3.0)
    except Exception:
        pass
    engine.is_running = False


def register_system_commands(engine: Any):
    engine.cmd_registry.register("help", "Display available slash commands and usage help: /help [<command>]", lambda args: cmd_help(engine, args), category="Session & System")
    engine.cmd_registry.register("status", "Display Mesh system status and configuration overview: /status", lambda args: cmd_status(engine, args), category="Models & Settings")
    engine.cmd_registry.register("history", "View or clear interactive command history: /history [<limit>] | /history clear", lambda args: cmd_history(engine, args), category="Session & System")
    engine.cmd_registry.register("config", "View or configure system settings and parameters: /config [distill|proxy|repair|hooks|compact|thinking|effort|tokens|cost|statistics|schema|set] <args>", lambda args: cmd_config(engine, args), category="Models & Settings")
    engine.cmd_registry.register("context", "Display conversation context window, active tools, and MCP server states: /context", lambda args: cmd_context(engine, args), category="Context & Integration")
    engine.cmd_registry.register("system", "View or update the system prompt: /system [<text>] | /system clear", lambda args: cmd_system(engine, args), category="Context & Integration")
    engine.cmd_registry.register("tools", "List registered tools and schemas, or toggle tool execution: /tools [on|off]", lambda args: cmd_tools(engine, args), category="Context & Integration")
    engine.cmd_registry.register("skills", "List registered skills, or toggle a skill: /skills enable|disable <name>", lambda args: cmd_skills(engine, args), category="Context & Integration")
    engine.cmd_registry.register("dirs", "View or modify allowed working directories: /dirs [add|remove|clear] [<path>]", lambda args: cmd_dirs(engine, args), category="Context & Integration")
    engine.cmd_registry.register("mcps", "View or toggle Model Context Protocol servers: /mcps [on|off|enable|disable] [<server>]", lambda args: cmd_mcps(engine, args), category="Context & Integration")
    engine.cmd_registry.register("compact", "Semantically summarize older conversation history to free context tokens: /compact", lambda args: cmd_compact(engine, args), category="Context & Integration")
    engine.cmd_registry.register("clear", "Clear conversation context window (preserves system prompt and skills): /clear", lambda args: cmd_clear(engine, args), category="Session & System")
    engine.cmd_registry.register("retry", "Retry the last assistant turn: /retry", lambda args: cmd_retry(engine, args), category="Session & System")
    engine.cmd_registry.register("debug", "View or toggle debug mode (CoT & tool execution traces): /debug [on|off]", lambda args: cmd_debug(engine, args), category="Session & System")
    engine.cmd_registry.register("exit", "Close active sessions and exit Mesh: /exit", lambda args: cmd_exit(engine, args), category="Session & System")
