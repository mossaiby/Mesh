from typing import List, Any
import delegation
import explore
import consensus
import advisor
import squad
import modes
from theme import console


async def cmd_delegate(engine: Any, args: List[str]):
    if not args:
        console.print("[error]Usage: /delegate <task description> | /delegate depth [<n>][/error]")
        return

    if args[0].lower() == "depth":
        if len(args) == 1:
            console.print(
                f"Delegation recursion depth is currently [accent]{engine.config_mgr.config.max_delegation_depth}[/accent] "
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
        engine.config_mgr.config.max_delegation_depth = n
        console.print(f"[success]Delegation recursion depth set to {n}.[/success]")
        return

    task = " ".join(args)
    result = await delegation.run_delegated_task(
        task=task,
        tool_registry=engine.tool_registry,
        config_mgr=engine.config_mgr,
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


async def cmd_explore(engine: Any, args: List[str]):
    if not args:
        console.print("[error]Usage: /explore [<num_branches>] <task description>[/error]")
        return

    num_branches = 3
    if args[0].isdigit() and 2 <= int(args[0]) <= 5:
        num_branches = int(args[0])
        task = " ".join(args[1:])
    else:
        task = " ".join(args)

    if not task.strip():
        console.print("[error]Usage: /explore [<num_branches>] <task description>[/error]")
        return

    result = await explore.explore_branches(
        task=task,
        strategies=None,
        tool_registry=engine.tool_registry,
        config_mgr=engine.config_mgr,
        num_branches=num_branches,
        debug_mode=engine.debug_mode
    )

    if result["status"] == "success":
        console.print(f"\n[success]🌲 Exploration Swarm Synthesis:[/success]\n\n{result['synthesis']}\n")
    else:
        console.print(f"[error]Exploration failed:[/error] {result.get('error', 'Unknown error')}")


async def cmd_consensus(engine: Any, args: List[str]):
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
        config_mgr=engine.config_mgr
    )

    if result["status"] == "success":
        console.print(f"\n[label]Auditor Critique ({result['auditor_model']}):[/label]\n{result['critique']}\n")
        console.print(f"[success]⚖️ Verified Consensus Recommendation ({result['proposer_model']}):[/success]\n{result['consensus_recommendation']}\n")
    else:
        console.print(f"[error]Consensus audit failed:[/error] {result.get('error', 'Unknown error')}")


async def cmd_squad(engine: Any, args: List[str]):
    if not args:
        console.print("[error]Usage: /squad <task description>[/error]")
        return

    task = " ".join(args)
    result = await squad.run_squad_pipeline(
        task=task,
        tool_registry=engine.tool_registry,
        config_mgr=engine.config_mgr,
        verbose=engine.debug_mode
    )

    if result["status"] == "success":
        console.print(f"\n[success]👥 Autonomous Task Squad Final Report:[/success]\n\n{result['final_report']}\n")
    else:
        console.print(f"[error]Task squad pipeline failed.[/error]")


async def cmd_advisor(engine: Any, args: List[str]):
    cfg = engine.config_mgr.config

    if not args:
        advisor_model_str = cfg.advisor_model or f"{cfg.active_model} (active model)"
        console.print(
            f"Advisor is currently using model: [accent]{advisor_model_str}[/accent]\n"
            f"Usage: [warning]/advisor <question>[/warning] | [warning]/advisor model <key>[/warning] | [warning]/advisor model clear[/warning]"
        )
        return

    sub = args[0].lower()

    if sub == "model":
        if len(args) == 1:
            cfg.advisor_model = None
            engine.config_mgr.save()
            console.print("[success]Advisor model reset to the active model.[/success]")
            return
        key = args[1]
        if key.lower() in ("clear", "reset", "none"):
            cfg.advisor_model = None
            engine.config_mgr.save()
            console.print("[success]Advisor model reset to the active model.[/success]")
            return
        if key not in cfg.models:
            console.print(f"[error]Unknown model key '{key}'. See /models for valid keys.[/error]")
            return
        cfg.advisor_model = key
        engine.config_mgr.save()
        console.print(f"[success]Advisor model set to '[accent]{key}[/accent]'.[/success]")
        return

    question = " ".join(args)
    console.print(f"[brand]🧭 Consulting advisor:[/brand] {question}")

    result = await advisor.get_advice(question=question, config_mgr=engine.config_mgr)
    if result["status"] == "error":
        console.print(f"[error]{result['error']}[/error]")
    else:
        console.print(f"\n[success]Advice[/success] [dim](from {result['advisor_model']}):[/dim]\n{result['advice']}\n")


async def cmd_guard(engine: Any, args: List[str]):
    cfg = engine.config_mgr.config

    if not args:
        state_str = "[success]ON[/success]" if engine.safety_guard.enabled else "[error]OFF[/error]"
        model_str = cfg.guard_model or f"{cfg.active_model} (active model)"
        trusted = ", ".join(sorted(engine.safety_guard.get_session_trusted_tools())) or "none"
        console.print(
            f"Safety Guard is currently {state_str}, mode [accent]{cfg.guard_autonomy}[/accent], "
            f"using model [accent]{model_str}[/accent].\n"
            f"Session-trusted tools: [dim]{trusted}[/dim]\n"
            f"Usage: [warning]/guard on[/warning] | [warning]/guard off[/warning] | "
            f"[warning]/guard mode supervised[/warning] | [warning]/guard mode autonomous[/warning] | "
            f"[warning]/guard model [<key>][/warning] | [warning]/guard trust <tool_name>[/warning]"
        )
        return

    sub = args[0].lower()

    if sub == "on":
        engine.safety_guard.enabled = True
        console.print("[success]Safety Guard ENABLED.[/success]")
    elif sub == "off":
        engine.safety_guard.enabled = False
        console.print("[warning]Safety Guard DISABLED - guarded tool calls will run unchecked.[/warning]")
    elif sub == "mode" and len(args) >= 2:
        mode = args[1].lower()
        if mode not in ("supervised", "autonomous"):
            console.print("[error]Usage: /guard mode supervised | /guard mode autonomous[/error]")
            return
        cfg.guard_autonomy = mode
        if engine.current_mode == "yolo":
            engine._pre_yolo_guard_autonomy = mode
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
        engine.safety_guard.trust_tool_for_session(tool_name)
        console.print(f"[success]'{tool_name}' will no longer be guard-checked for the rest of this session.[/success]")
    else:
        console.print(
            "[error]Usage: /guard [on|off] | /guard mode [supervised|autonomous] | "
            "/guard model [<key>] | /guard trust <tool_name>[/error]"
        )


async def cmd_mode(engine: Any, args: List[str]):
    if not args:
        current = modes.MODES[engine.current_mode]
        console.print(f"Current mode: [accent]{current.label}[/accent] - {current.description}\n")
        console.print("[label]Available modes:[/label]")
        for key, mode_def in modes.MODES.items():
            marker = "[accent]*[/accent]" if key == engine.current_mode else " "
            console.print(f"  {marker} [label]{key}[/label] - {mode_def.description}")
        console.print("\nUsage: [warning]/mode <name>[/warning]")
        return

    requested = args[0].lower()
    if requested not in modes.MODES:
        valid = ", ".join(modes.MODES.keys())
        console.print(f"[error]Unknown mode '{requested}'. Valid modes: {valid}[/error]")
        return

    if requested == engine.current_mode:
        console.print(f"[dim]Already in {modes.MODES[requested].label} mode.[/dim]")
        return

    leaving_yolo = engine.current_mode == "yolo" and requested != "yolo"
    entering_yolo = requested == "yolo" and engine.current_mode != "yolo"

    if entering_yolo:
        engine._pre_yolo_guard_autonomy = engine.config_mgr.config.guard_autonomy
        engine._pre_yolo_permission_auto_approve = engine.permission_manager.auto_approve
        engine.config_mgr.config.guard_autonomy = "autonomous"
        engine.permission_manager.auto_approve = True
    elif leaving_yolo:
        if engine._pre_yolo_guard_autonomy is not None:
            engine.config_mgr.config.guard_autonomy = engine._pre_yolo_guard_autonomy
        if engine._pre_yolo_permission_auto_approve is not None:
            engine.permission_manager.auto_approve = engine._pre_yolo_permission_auto_approve
        engine._pre_yolo_guard_autonomy = None
        engine._pre_yolo_permission_auto_approve = None

    engine.current_mode = requested
    engine.tool_registry.mode_blocked_tools = modes.blocked_tools_for_mode(requested, engine.tool_registry)
    engine.update_system_message()

    mode_def = modes.MODES[requested]
    console.print(f"[success]Switched to {mode_def.label} Mode.[/success] {mode_def.description}")
    if engine.tool_registry.mode_blocked_tools:
        blocked_str = ", ".join(sorted(engine.tool_registry.mode_blocked_tools))
        console.print(f"[dim]Unavailable in this mode: {blocked_str}[/dim]")


def register_agent_commands(engine: Any):
    engine.cmd_registry.register("delegate", "Delegate a self-contained task to an autonomous sub-agent: /delegate <task description> | /delegate depth [<n>]", lambda args: cmd_delegate(engine, args))
    engine.cmd_registry.register("explore", "Run parallel speculative branch exploration: /explore [<num_branches>] <task description>", lambda args: cmd_explore(engine, args))
    engine.cmd_registry.register("consensus", "Run an adversarial multi-model consensus audit: /consensus <question> | <proposal>", lambda args: cmd_consensus(engine, args))
    engine.cmd_registry.register("squad", "Execute 4-stage autonomous task squad (Architect -> Coder -> Test Engineer -> Security Auditor): /squad <task>", lambda args: cmd_squad(engine, args))
    engine.cmd_registry.register("advisor", "Consult the advisor or configure its model: /advisor <question> | /advisor model [<key>]", lambda args: cmd_advisor(engine, args))
    engine.cmd_registry.register("guard", "View or configure the tool-call safety guard: /guard [on|off] | /guard mode [supervised|autonomous] | /guard model [<key>] | /guard trust <tool>", lambda args: cmd_guard(engine, args))
    engine.cmd_registry.register("mode", "View or switch operating mode: /mode [plan|build|review|yolo]", lambda args: cmd_mode(engine, args))