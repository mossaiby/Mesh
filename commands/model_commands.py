import asyncio
import fnmatch
import sys
from typing import List, Optional, Any
from rich.live import Live
from rich.text import Text
from providers.openai_provider import OpenAIProvider
from tools.ask_tool import _read_single_key
from theme import console


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
        return raw

    current_idx = 0
    max_visible = 40

    def render_menu(selected_idx: int) -> Text:
        lines = [f"\n[success]{title}:[/success]", "[dim]Use ↑/↓ Arrow Keys to navigate, Enter to select:[/dim]\n"]
        visible_items = items[:max_visible]
        for idx, item in enumerate(visible_items):
            if idx == selected_idx:
                lines.append(f"  [accent]❯ 🔘 {item}[/accent]")
            else:
                lines.append(f"    [dim]⚪ {item}[/dim]")
        if len(items) > max_visible:
            lines.append(f"  [dim]... (+{len(items) - max_visible} more items)[/dim]")
        return Text.from_markup("\n".join(lines))

    with Live(render_menu(current_idx), console=console, auto_refresh=False, vertical_overflow="visible") as live:
        while True:
            live.update(render_menu(current_idx), refresh=True)
            try:
                key = _read_single_key()
            except Exception:
                break

            if key == "up":
                current_idx = (current_idx - 1) % min(len(items), max_visible)
            elif key == "down":
                current_idx = (current_idx + 1) % min(len(items), max_visible)
            elif key == "enter":
                break

    return items[current_idx]


async def cmd_models(engine: Any, args: List[str]):
    sub = args[0].lower() if args else ""

    if sub == "add":
        loop = asyncio.get_running_loop()

        if len(args) >= 3:
            p_key = args[1].lower()
            pattern = args[2]
            ctx = int(args[3]) if len(args) > 3 and args[3].isdigit() else (
                128000 if ("groq" in p_key or "openrouter" in p_key) else 8192
            )

            if p_key not in engine.config_mgr.config.providers:
                console.print(f"[error]Unknown provider '{p_key}'. Configured providers: {', '.join(engine.config_mgr.config.providers.keys())}[/error]")
                return

            p_cfg = engine.config_mgr.config.providers[p_key]

            console.print(f"[brand]🔍 Fetching models from {p_cfg.name} to match pattern '{pattern}'...[/brand]")
            success, model_ids, err = await OpenAIProvider.fetch_available_models(p_cfg)

            if not success:
                console.print(f"[error]Failed to discover models from {p_cfg.name}: {err}[/error]")
                return

            pat_lower = pattern.lower()
            if any(c in pattern for c in "*?[]"):
                matching_ids = [m for m in model_ids if fnmatch.fnmatch(m.lower(), pat_lower)]
            else:
                matching_ids = [m for m in model_ids if pat_lower in m.lower()]

            if not matching_ids:
                matching_ids = [pattern]

            configured_keys = set(engine.config_mgr.config.models.keys())
            added_count = 0
            skipped_count = 0

            for m_id in matching_ids:
                model_key = f"{p_key}:{m_id}"
                if model_key in configured_keys:
                    skipped_count += 1
                    continue

                engine.config_mgr.add_model(model_key, p_key, m_id, context_window=ctx)
                console.print(f"  [success]✔ Added:[/success] [label]{model_key}[/label] ([dim]{m_id}[/dim])")
                added_count += 1

            if added_count > 0:
                console.print(f"\n[success]Successfully added {added_count} model(s) matching '{pattern}' to models.json![/success]")
                if skipped_count > 0:
                    console.print(f"[dim]({skipped_count} model(s) were already configured)[/dim]\n")
            elif skipped_count > 0:
                console.print(f"[warning]All {skipped_count} model(s) matching '{pattern}' are already configured in models.json.[/warning]\n")
            else:
                console.print(f"[warning]No models found matching pattern '{pattern}' from {p_cfg.name}.[/warning]\n")

            return

        providers = list(engine.config_mgr.config.providers.keys())
        if not providers:
            console.print("[error]No providers configured in models.json.[/error]")
            return

        selected_provider = await loop.run_in_executor(
            None, 
            lambda: _interactive_item_picker(providers, "Select a Provider to Discover & Add Models")
        )
        if not selected_provider or selected_provider not in engine.config_mgr.config.providers:
            return

        p_cfg = engine.config_mgr.config.providers[selected_provider]
        console.print(f"[brand]🔍 Fetching available models from {p_cfg.name}...[/brand]")

        success, model_ids, err = await OpenAIProvider.fetch_available_models(p_cfg)
        if not success or not model_ids:
            console.print(f"[error]Failed to discover models from {p_cfg.name}: {err}[/error]")
            return

        configured_model_ids = {m.model_id for m in engine.config_mgr.config.models.values()}
        unconfigured_ids = [m for m in model_ids if m not in configured_model_ids]

        if not unconfigured_ids:
            console.print(f"[warning]All {len(model_ids)} models discovered from {p_cfg.name} are already configured![/warning]")
            return

        selected_model_id = await loop.run_in_executor(
            None, 
            lambda: _interactive_item_picker(unconfigured_ids, f"Select a Discovered Model to Add from {p_cfg.name}")
        )
        if not selected_model_id:
            return

        default_ctx = 128000 if ("groq" in selected_provider or "openrouter" in selected_provider) else 8192
        model_key = f"{selected_provider}:{selected_model_id}"

        try:
            engine.config_mgr.add_model(model_key, selected_provider, selected_model_id, context_window=default_ctx)
            console.print(f"\n[success]Successfully added model '[label]{model_key}[/label]' ({selected_model_id}) to models.json![/success]")
            
            switch_choice = await loop.run_in_executor(
                None,
                lambda: _interactive_item_picker(["Yes, switch active model now", "No, keep current active model"], f"Switch active model to {model_key}?")
            )
            if switch_choice and switch_choice.startswith("Yes"):
                engine.config_mgr.set_active_model(model_key)
                console.print(f"[success]Switched active model to: [label]{model_key}[/label][/success]")
        except Exception as e:
            console.print(f"[error]Failed to add model: {e}[/error]")
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
            console.print("[error]No providers configured in models.json.[/error]")
            return

        console.print("[brand]🔍 Discovering models offered by provider endpoints...[/brand]\n")

        configured_model_ids = {m.model_id for m in engine.config_mgr.config.models.values()}

        async def query_p(key: str, p_cfg):
            success, model_ids, err = await OpenAIProvider.fetch_available_models(p_cfg)
            return key, p_cfg, success, model_ids, err

        results = await asyncio.gather(*(query_p(k, p) for k, p in providers_to_query.items()))

        for p_key, p_cfg, success, model_ids, err in results:
            console.print(f"• [label]{p_cfg.name}[/label] ([brand]{p_key}[/brand]) — [dim]{p_cfg.base_url}[/dim]")
            if success:
                if not model_ids:
                    console.print("  [dim]No models returned by endpoint.[/dim]\n")
                else:
                    console.print(f"  [success]Discovered {len(model_ids)} available model(s):[/success]")
                    for m_id in model_ids[:30]:
                        configured_tag = " [accent](configured)[/accent]" if m_id in configured_model_ids else ""
                        console.print(f"    - [text]{m_id}[/text]{configured_tag}")
                    if len(model_ids) > 30:
                        console.print(f"    [dim]... (+{len(model_ids) - 30} more models)[/dim]")
                    console.print()
            else:
                console.print(f"  [error]Discovery failed:[/error] {err}\n")

        console.print("Tip: Run [warning]/models add[/warning] to interactively pick or batch-add models (e.g. /models add openrouter *free*).\n")
        return

    active = engine.config_mgr.config.active_model
    console.print("[success]Configured Models:[/success]")
    for key, model_cfg in engine.config_mgr.config.models.items():
        provider_cfg = engine.config_mgr.config.providers.get(model_cfg.provider)
        provider_name = provider_cfg.name if provider_cfg else model_cfg.provider
        
        mark = "[accent]*[/accent]" if key == active else " "
        console.print(
            f"{mark} [label]{key}[/label] -> {model_cfg.name} via "
            f"[brand]{provider_name}[/brand] ([dim]{model_cfg.model_id}[/dim]) "
            f"[dim]— {model_cfg.context_window} token context window[/dim]"
        )
    console.print("\nUsage: [warning]/models[/warning] | [warning]/models discover [<provider>][/warning] | [warning]/models add [<provider>] [<pattern>][/warning]\n")


async def cmd_switch(engine: Any, args: List[str]):
    models_dict = engine.config_mgr.config.models
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
        active_key = engine.config_mgr.config.active_model
        current_idx = model_keys.index(active_key) if active_key in model_keys else 0

        def render_switch_menu(selected_idx: int):
            lines = ["\n[success]Select a Model to Switch to:[/success]", "[dim]Use ↑/↓ Arrow Keys to navigate, Enter to select:[/dim]\n"]
            for idx, key in enumerate(model_keys):
                cfg = models_dict[key]
                provider_cfg = engine.config_mgr.config.providers.get(cfg.provider)
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
        engine.config_mgr.set_active_model(selected_key)
        model_cfg, provider_cfg = engine.config_mgr.get_active_model_and_provider()
        console.print(f"[success]Switched active model to: [label]{selected_key}[/label] ({model_cfg.name} via {provider_cfg.name})[/success]")
    except Exception as e:
        console.print(f"[error]Error switching model: {e}[/error]")


def register_model_commands(engine: Any):
    engine.cmd_registry.register(
        "models",
        "List, discover, or add models: /models | /models discover [<provider>] | /models add [<provider>] [<pattern>]",
        lambda args: cmd_models(engine, args),
        category="Models & Settings"
    )
    engine.cmd_registry.register(
        "switch",
        "Switch active model interactively, or directly: /switch <model_key>",
        lambda args: cmd_switch(engine, args),
        category="Models & Settings"
    )