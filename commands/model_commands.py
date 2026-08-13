import asyncio
import fnmatch
import re
import sys
from typing import List, Optional, Any
from rich.live import Live
from rich.text import Text
from providers import fetch_models_details
from tools.ask_tool import _read_single_key
from theme import console


COMMON_CONTEXT_SIZES = [
    (8192, "8,192 tokens (8K)"),
    (16384, "16,384 tokens (16K)"),
    (32768, "32,768 tokens (32K)"),
    (65536, "65,536 tokens (64K)"),
    (128000, "128,000 tokens (128K)"),
    (200000, "200,000 tokens (200K)"),
    (262144, "262,144 tokens (256K)"),
    (524288, "524,288 tokens (512K)"),
    (1000000, "1,000,000 tokens (1M)"),
    (2097152, "2,097,152 tokens (2M)"),
]


def _interactive_item_picker(items: List[str], title: str) -> Optional[str]:
    """Helper to render an interactive arrow-key picker for selecting an item from a list."""
    if not items:
        return None
    if not sys.stdin.isatty():
        console.print(f"[accent]{title}:[/accent]")
        for idx, item in enumerate(items, 1):
            console.print(f"  {idx}. {item}")
        raw = input("Choice > ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        return raw if raw else None

    current_idx = 0
    max_visible = 15

    def render_menu(selected_idx: int) -> Text:
        total = len(items)
        if total <= max_visible:
            scroll_offset = 0
            visible_count = total
        else:
            scroll_offset = max(0, min(selected_idx - max_visible // 2, total - max_visible))
            visible_count = max_visible

        lines = [f"\n[success]{title}:[/success]", "[dim]Use ↑/↓ Arrow Keys to navigate, Enter to select:[/dim]\n"]

        if scroll_offset > 0:
            lines.append(f"  [dim]▲ ... ({scroll_offset} items above)[/dim]")

        for idx in range(scroll_offset, scroll_offset + visible_count):
            item = items[idx]
            if idx == selected_idx:
                lines.append(f"  [accent]❯ 🔘 {item}[/accent]")
            else:
                lines.append(f"    [dim]⚪ {item}[/dim]")

        remaining = total - (scroll_offset + visible_count)
        if remaining > 0:
            lines.append(f"  [dim]▼ ... ({remaining} items below)[/dim]")

        return Text.from_markup("\n".join(lines))

    try:
        with Live(render_menu(current_idx), console=console, auto_refresh=False, vertical_overflow="visible") as live:
            while True:
                live.update(render_menu(current_idx), refresh=True)
                try:
                    key = _read_single_key()
                except (Exception, KeyboardInterrupt):
                    return None

                if key == "up":
                    current_idx = (current_idx - 1) % len(items)
                elif key == "down":
                    current_idx = (current_idx + 1) % len(items)
                elif key == "enter":
                    break
                elif key == "escape":
                    return None

        return items[current_idx]
    except (KeyboardInterrupt, Exception):
        return None


def _infer_tags_for_model(model_id: str) -> List[str]:
    """Auto-infers metadata tags for a model ID."""
    tags = []
    m_lower = model_id.lower()
    if "free" in m_lower:
        tags.append("free")
    if any(k in m_lower for k in ("coder", "coding", "code")):
        tags.append("coding")
    if any(k in m_lower for k in ("r1", "o1", "o3", "reasoning", "thinking", "nemotron", "sonnet")):
        tags.append("reasoning")
    if any(k in m_lower for k in ("fast", "mini", "flash", "instant", "1b", "3b", "8b", "haiku")):
        tags.append("fast")
    if "vision" in m_lower:
        tags.append("vision")
    return tags


async def infer_context_window(
    model_id: str,
    provider: str,
    explicit_ctx: Optional[int] = None,
    discovered_ctx: Optional[int] = None,
    config_mgr: Optional[Any] = None
) -> int:
    """
    Determines context window size using a clean multi-layer resolution strategy:
    1. Explicit user argument override
    2. Endpoint discovery metadata
    3. Dynamic web search verification fallback
    4. Interactive menu selection (8K to 2M tokens)
    """
    # 1. Explicit user CLI argument
    if explicit_ctx and explicit_ctx > 0:
        return explicit_ctx

    # 2. Endpoint discovery metadata
    if discovered_ctx and discovered_ctx > 0:
        return discovered_ctx

    # 3. Dynamic Web Search Verification Fallback
    if config_mgr:
        try:
            from tools.web_tools import WebSearchTool
            search_tool = WebSearchTool(config_mgr)
            query = f"{model_id} context window size tokens"
            res = await search_tool.execute(query=query, max_results=3)
            results = res.get("results", [])
            for item in results:
                snippet = (item.get("snippet", "") + " " + item.get("title", "")).lower()
                match = re.search(r'(\d+[\d,]*)\s*(?:token|context|k\b)', snippet)
                if match:
                    raw_num = match.group(1).replace(",", "")
                    num_val = int(float(raw_num[:-1]) * 1000) if raw_num.endswith("k") else int(raw_num)
                    if num_val in (8192, 16384, 32768, 65536, 128000, 200000, 262144, 524288, 1000000, 2097152):
                        return num_val
        except Exception:
            pass

    # 4. Interactive User Selection Menu (8K to 2M)
    loop = asyncio.get_running_loop()
    menu_items = [label for _, label in COMMON_CONTEXT_SIZES]
    prompt_title = f"Select Context Window Size for Model '{model_id}'"
    
    selected_label = await loop.run_in_executor(
        None,
        lambda: _interactive_item_picker(menu_items, prompt_title)
    )

    if selected_label:
        for size_val, label in COMMON_CONTEXT_SIZES:
            if selected_label == label:
                return size_val

    # Fallback default if menu cancelled
    return 128000


async def cmd_models(engine: Any, args: List[str]):
    sub = args[0].lower() if args else ""

    if sub == "add":
        if len(args) == 1:
            providers_str = ", ".join(engine.config_mgr.config.providers.keys())
            console.print(
                "[error]Usage: /models add <provider> [<pattern>] [<context_window>][/error]\n"
                f"Configured providers: [accent]{providers_str}[/accent]\n"
                "Examples: [warning]/models add groq *[/warning] | "
                "[warning]/models add openrouter *free*[/warning] | "
                "[warning]/models add lmstudio google/gemma-4-e4b 32768[/warning]\n"
            )
            return

        p_key = args[1].lower()
        pattern = args[2] if len(args) >= 3 else "*"
        explicit_ctx = int(args[3]) if len(args) >= 4 and args[3].isdigit() else None

        if p_key not in engine.config_mgr.config.providers:
            console.print(f"[error]Unknown provider '{p_key}'. Configured providers: {', '.join(engine.config_mgr.config.providers.keys())}[/error]")
            return

        p_cfg = engine.config_mgr.config.providers[p_key]

        console.print(f"[brand]🔍 Fetching model metadata from {p_cfg.name} matching pattern '{pattern}'...[/brand]")
        success, model_details, err = await fetch_models_details(p_cfg, timeout=engine.config_mgr.config.timeouts.api)

        if not success or not model_details:
            console.print(f"[error]Failed to discover models from {p_cfg.name}: {err}[/error]")
            return

        pat_lower = pattern.lower()
        if any(c in pattern for c in "*?[]"):
            matching_models = [m for m in model_details if fnmatch.fnmatch(m["id"].lower(), pat_lower)]
        else:
            matching_models = [m for m in model_details if pat_lower in m["id"].lower()]

        if not matching_models and pattern != "*":
            matching_models = [{"id": pattern, "name": pattern.split("/")[-1].title(), "context_window": None, "description": ""}]

        configured_keys = set(engine.config_mgr.config.models.keys())
        added_count = 0
        skipped_count = 0

        for m_info in matching_models:
            m_id = m_info["id"]
            model_key = f"{p_key}:{m_id}"
            if model_key in configured_keys:
                skipped_count += 1
                continue

            discovered_ctx = m_info.get("context_window")
            final_ctx = await infer_context_window(
                model_id=m_id,
                provider=p_key,
                explicit_ctx=explicit_ctx,
                discovered_ctx=discovered_ctx,
                config_mgr=engine.config_mgr
            )

            tags = _infer_tags_for_model(m_id)
            desc = m_info.get("description") or f"{m_info.get('name', m_id)} via {p_cfg.name}"

            engine.config_mgr.add_model(
                key=model_key,
                provider=p_key,
                model_id=m_id,
                name=m_info.get("name"),
                context_window=final_ctx,
                tags=tags,
                description=desc
            )
            console.print(f"  [success]✔ Added:[/success] [label]{model_key}[/label] ([dim]{m_id}[/dim] - [accent]{final_ctx:,}[/accent] tokens context)")
            added_count += 1

        if added_count > 0:
            console.print(f"\n[success]Successfully added {added_count} model(s) matching '{pattern}' to config.json![/success]")
            if skipped_count > 0:
                console.print(f"[dim]({skipped_count} model(s) were already configured)[/dim]\n")
        elif skipped_count > 0:
            console.print(f"[warning]All {skipped_count} model(s) matching '{pattern}' are already configured in config.json.[/warning]\n")
        else:
            console.print(f"[warning]No models found matching pattern '{pattern}' from {p_cfg.name}.[/warning]\n")

        return

    elif sub in ("discover", "fetch", "list-remote"):
        target_provider = args[1].lower() if len(args) > 1 else None
        providers_to_query = {}

        if target_provider:
            if target_provider in engine.config_mgr.config.providers:
                providers_to_query[target_provider] = engine.config_mgr.config.providers[target_provider]
            else:
                console.print(f"[error]Unknown provider '{target_provider}'. Configured providers: {', '.join(engine.config_mgr.config.providers.keys())}[/error]")
                return
        else:
            providers_to_query = engine.config_mgr.config.providers

        if not providers_to_query:
            console.print("[error]No providers configured in config.json.[/error]")
            return

        console.print("[brand]🔍 Discovering models offered by provider endpoints...[/brand]\n")

        configured_model_ids = {m.model_id for m in engine.config_mgr.config.models.values()}

        async def query_p(key: str, p_cfg):
            success, model_details, err = await fetch_models_details(p_cfg, timeout=engine.config_mgr.config.timeouts.api)
            return key, p_cfg, success, model_details, err

        results = await asyncio.gather(*(query_p(k, p) for k, p in providers_to_query.items()))

        for p_key, p_cfg, success, model_details, err in results:
            console.print(f"• [label]{p_cfg.name}[/label] ([brand]{p_key}[/brand]) — [dim]{p_cfg.base_url}[/dim]")
            if success:
                if not model_details:
                    console.print("  [dim]No models returned by endpoint.[/dim]\n")
                else:
                    console.print(f"  [success]Discovered {len(model_details)} available model(s):[/success]")
                    for m_info in model_details[:30]:
                        m_id = m_info["id"]
                        configured_tag = " [accent](configured)[/accent]" if m_id in configured_model_ids else ""
                        ctx_val = m_info.get("context_window")
                        ctx_str = f" ({ctx_val:,} tokens)" if ctx_val else ""
                        console.print(f"    - [text]{m_id}[/text]{ctx_str}{configured_tag}")
                    if len(model_details) > 30:
                        console.print(f"    [dim]... (+{len(model_details) - 30} more models)[/dim]")
                    console.print()
            else:
                console.print(f"  [error]Discovery failed:[/error] {err}\n")

        console.print("Tip: Run [warning]/models add <provider> [<pattern>][/warning] to add models (e.g. /models add openrouter *free*).\n")
        return

    cfg = engine.config_mgr.config
    active = cfg.active_model
    console.print("[success]Configured Models:[/success]")
    for key, model_cfg in cfg.models.items():
        provider_cfg = cfg.providers.get(model_cfg.provider)
        provider_name = provider_cfg.name if provider_cfg else model_cfg.provider
        
        mark = "[accent]*[/accent]" if key == active else " "
        
        roles = []
        if key == active:
            roles.append("active")
        if active == "auto":
            roles.append("candidate")
        if key == cfg.router_model:
            roles.append("router")
        if key == cfg.guard_model:
            roles.append("guard")
        if key == cfg.advisor_model:
            roles.append("advisor")
        
        roles_str = f" [accent]({', '.join(roles)})[/accent]" if roles else ""
        tags_str = f" [dim][tags: {', '.join(model_cfg.tags)}][/dim]" if model_cfg.tags else ""
        desc_str = f"\n    [dim]{model_cfg.description}[/dim]" if model_cfg.description else ""

        console.print(
            f"{mark} [label]{key}[/label] -> {model_cfg.name} via "
            f"[brand]{provider_name}[/brand] ([dim]{model_cfg.model_id}[/dim]) "
            f"[dim]— {model_cfg.context_window:,} token context[/dim]{roles_str}{tags_str}{desc_str}"
        )
    
    if active == "auto":
        console.print(f"\n[brand]🔀 Active Mode: AUTO-ROUTING[/brand] (using router model: [accent]{cfg.router_model or 'none'}[/accent])")

    console.print("\nUsage: [warning]/models[/warning] | [warning]/models discover [<provider>][/warning] | [warning]/models add <provider> [<pattern>] [<context_window>][/warning]\n")


async def cmd_switch(engine: Any, args: List[str]):
    cfg = engine.config_mgr.config
    models_dict = cfg.models
    if not models_dict:
        console.print("[error]No models configured in config.json.[/error]")
        return

    sub = args[0].lower() if args else ""

    if sub == "auto":
        if not cfg.router_model:
            console.print(
                "[error]Cannot enable auto-routing mode: 'router_model' is not configured in config.json.\n"
                "Use '/switch router <model_key>' to configure a router model first.[/error]"
            )
            return
        if cfg.router_model not in cfg.models:
            console.print(f"[error]Configured router model key '{cfg.router_model}' was not found in config.json.[/error]")
            return

        engine.config_mgr.set_active_model("auto")
        router_m = cfg.models[cfg.router_model]
        console.print(
            f"[success]Switched to Auto-Routing Mode ([label]auto[/label]).[/success]\n"
            f"Prompts will be dynamically routed turn-by-turn using router model '[accent]{cfg.router_model}[/accent]' ({router_m.name})."
        )
        return

    elif sub == "router":
        if len(args) == 1:
            r_str = cfg.router_model or "[dim]none set[/dim]"
            console.print(
                f"Router model is currently: [accent]{r_str}[/accent]\n"
                f"Usage: [warning]/switch router <model_key>[/warning] | [warning]/switch router clear[/warning]"
            )
            return
        target_key = args[1]
        if target_key.lower() in ("clear", "reset", "none"):
            cfg.router_model = None
            engine.config_mgr.save()
            console.print("[success]Router model cleared.[/success]")
            return
        if target_key not in models_dict:
            console.print(f"[error]Model key '{target_key}' not found in config.json. See /models for valid keys.[/error]")
            return
        cfg.router_model = target_key
        engine.config_mgr.save()
        console.print(f"[success]Router model set to '[label]{target_key}[/label]' ({models_dict[target_key].name}).[/success]")
        return

    if args:
        target_key = args[0]
        if target_key not in models_dict:
            console.print(f"[error]Model key '{target_key}' not found in config.json.[/error]")
            return
        selected_key = target_key
    else:
        model_keys = list(models_dict.keys()) + ["auto (Dynamic LLM Router)"]
        active_key = cfg.active_model
        current_idx = 0

        def render_switch_menu(selected_idx: int):
            lines = ["\n[success]Select a Model or Mode to Switch to:[/success]", "[dim]Use ↑/↓ Arrow Keys to navigate, Enter to select:[/dim]\n"]
            for idx, key in enumerate(model_keys):
                if key.startswith("auto"):
                    is_active = (active_key == "auto")
                    active_tag = " [accent](active)[/accent]" if is_active else ""
                    router_tag = f" [dim](using router: {cfg.router_model or 'none'})[/dim]"
                    item_text = f"🔀 Auto-Routing Mode{active_tag}{router_tag}"
                else:
                    m_cfg = models_dict[key]
                    provider_cfg = cfg.providers.get(m_cfg.provider)
                    p_name = provider_cfg.name if provider_cfg else m_cfg.provider
                    is_active = (key == active_key)
                    active_tag = " [accent](active)[/accent]" if is_active else ""
                    item_text = f"{m_cfg.name} ({key}) via {p_name}{active_tag}"
                
                if idx == selected_idx:
                    lines.append(f"  [accent]❯ 🔘 {item_text}[/accent]")
                else:
                    lines.append(f"    [dim]⚪ {item_text}[/dim]")
            return Text.from_markup("\n".join(lines))

        def interactive_switch():
            if not sys.stdin.isatty():
                console.print("[accent]Available Options:[/accent]")
                for idx, k in enumerate(model_keys, 1):
                    console.print(f"  {idx}. {k}")
                raw = input("Choice > ").strip()
                if raw.isdigit() and 1 <= int(raw) <= len(model_keys):
                    return model_keys[int(raw) - 1]
                return raw

            nonlocal current_idx
            with Live(render_switch_menu(current_idx), console=console, auto_refresh=False, vertical_overflow="visible") as live:
                while True:
                    live.update(render_switch_menu(current_idx), print=True)
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
        if selected_key.startswith("auto"):
            if not cfg.router_model or cfg.router_model not in cfg.models:
                console.print("[error]Cannot enable auto-routing: 'router_model' is not set or invalid in config.json.[/error]")
                return
            engine.config_mgr.set_active_model("auto")
            console.print(f"[success]Switched active mode to: [label]auto[/label] (Router: {cfg.router_model})[/success]")
        else:
            engine.config_mgr.set_active_model(selected_key)
            model_cfg, provider_cfg = engine.config_mgr.get_active_model_and_provider()
            console.print(f"[success]Switched active model to: [label]{selected_key}[/label] ({model_cfg.name} via {provider_cfg.name})[/success]")
    except Exception as e:
        console.print(f"[error]Error switching model: {e}[/error]")


def register_model_commands(engine: Any):
    engine.cmd_registry.register(
        "models",
        "List, discover, or add models: /models [discover|add] [<provider>] [<pattern>] [<context_window>]",
        lambda args: cmd_models(engine, args),
        category="Models & Settings"
    )
    engine.cmd_registry.register(
        "switch",
        "Switch active model or mode: /switch [auto|router|<model_key>]",
        lambda args: cmd_switch(engine, args),
        category="Models & Settings"
    )
