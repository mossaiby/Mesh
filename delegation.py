import asyncio
import contextvars
from typing import Dict, Any, List, Optional
from rich.markup import escape
from config import ConfigManager
from providers import get_provider
from render.stream_renderer import StreamRenderer
from theme import console


DELEGATE_SYSTEM_PROMPT = (
    "You are a focused, autonomous sub-agent inside Mesh, spun up to complete ONE "
    "self-contained task on behalf of the main assistant. You have access to tools - "
    "use them as needed to gather information and make changes. You cannot ask the "
    "user any questions, and no one is watching this conversation turn by turn, so "
    "make reasonable assumptions and proceed rather than stalling.\n\n"
    "If delegate_task is available to you and the task genuinely splits into independent "
    "sub-tasks, you may delegate those sub-tasks to further sub-agents yourself rather "
    "than doing everything in this one conversation - issuing several delegate_task calls "
    "in the same turn runs them in parallel. Don't delegate a task that's simpler to just "
    "do directly.\n\n"
    "When the task is complete (or you've determined it cannot be completed), stop "
    "calling tools and respond with a concise final report describing what you did, "
    "what you found or changed, and the outcome. This final report is the ONLY thing "
    "the caller will see - it does not see your intermediate tool calls - so make the "
    "report self-contained and specific rather than saying things like 'as shown above'."
)

ALWAYS_EXCLUDED_TOOLS = {"ask_user"}

HARD_MAX_TURNS_CAP = 10
MAX_CONCURRENT_DELEGATIONS = 4
_delegation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DELEGATIONS)

CURRENT_DELEGATION_DEPTH: "contextvars.ContextVar[int]" = contextvars.ContextVar(
    "current_delegation_depth", default=0
)


def max_turns_for_depth(requested_max_turns: int, depth: int) -> int:
    tapered_cap = max(2, HARD_MAX_TURNS_CAP - 2 * (depth - 1))
    return max(1, min(requested_max_turns, tapered_cap))


async def _execute_turn_tool_calls(
    tool_registry: Any,
    active_calls: List[Dict[str, str]]
) -> List[str]:
    results: List[Optional[str]] = [None] * len(active_calls)

    async def run_bounded(i: int, tc: Dict[str, str]):
        async with _delegation_semaphore:
            results[i] = await tool_registry.execute(tc["name"], tc["args"])

    delegate_indices = [i for i, tc in enumerate(active_calls) if tc["name"] == "delegate_task"]
    other_indices = [i for i, tc in enumerate(active_calls) if tc["name"] != "delegate_task"]

    if delegate_indices:
        await asyncio.gather(*(run_bounded(i, active_calls[i]) for i in delegate_indices))

    for i in other_indices:
        results[i] = await tool_registry.execute(active_calls[i]["name"], active_calls[i]["args"])

    return results


async def run_delegated_task(
    task: str,
    tool_registry: Any,
    config_mgr: ConfigManager,
    max_turns: Optional[int] = None,
    excluded_tools: Optional[set] = None,
    verbose: bool = True,
    depth: int = 1,
    max_depth: Optional[int] = None,
) -> Dict[str, Any]:
    default_turns = config_mgr.config.turns.agent
    turns_limit = max_turns if max_turns is not None else default_turns

    effective_max_depth = max_depth if max_depth is not None else config_mgr.config.turns.depth

    excluded = set(excluded_tools) if excluded_tools is not None else set(ALWAYS_EXCLUDED_TOOLS)
    if depth >= effective_max_depth:
        excluded.add("delegate_task")

    depth_token = CURRENT_DELEGATION_DEPTH.set(depth)
    try:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": DELEGATE_SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ]

        all_schemas = tool_registry.get_schemas(inject_intent=False)
        schemas = [s for s in all_schemas if s["function"]["name"] not in excluded]

        try:
            model_cfg, provider_cfg = config_mgr.get_active_model_and_provider()
        except Exception as e:
            return {"status": "error", "error": f"Configuration error: {e}", "tool_calls": [], "turns_used": 0, "depth": depth}

        provider = get_provider(model_cfg, provider_cfg, config_mgr)
        renderer = StreamRenderer()

        tool_call_log: List[Dict[str, Any]] = []
        turns_used = 0
        depth_tag = f"[dim](depth {depth})[/dim] " if depth > 1 else ""

        if verbose:
            console.print(f"[brand]📤 Delegating task to sub-agent:[/brand] {depth_tag}{task}")

        for turn in range(turns_limit):
            turns_used = turn + 1
            tool_calls_to_run: List[Dict[str, str]] = []

            async def sub_chunk_gen():
                async for chunk in provider.stream_chat(messages, tools=schemas):
                    ctype = chunk["type"]
                    cval = chunk["value"]

                    if ctype == "tool_calls":
                        for delta in cval:
                            idx = delta["index"] if isinstance(delta, dict) else getattr(delta, "index", 0)
                            while len(tool_calls_to_run) <= idx:
                                tool_calls_to_run.append({"id": "", "name": "", "args": ""})
                            
                            tc_id = delta.get("id") if isinstance(delta, dict) else getattr(delta, "id", None)
                            if tc_id:
                                tool_calls_to_run[idx]["id"] = tc_id
                            
                            fn = delta.get("function") if isinstance(delta, dict) else getattr(delta, "function", None)
                            if fn:
                                fn_name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)
                                fn_args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", None)
                                if fn_name:
                                    tool_calls_to_run[idx]["name"] = fn_name
                                if fn_args:
                                    tool_calls_to_run[idx]["args"] += fn_args
                    else:
                        yield chunk

            try:
                debug_flag = getattr(tool_registry.subagent_distiller, "debug_mode", False) if hasattr(tool_registry, "subagent_distiller") else False
                content_text, _ = await renderer.render_stream(sub_chunk_gen(), debug_mode=debug_flag)
            except Exception as e:
                return {
                    "status": "error",
                    "error": f"Sub-agent model call failed: {e}",
                    "tool_calls": tool_call_log,
                    "turns_used": turns_used,
                    "depth": depth,
                }

            active_calls = [tc for tc in tool_calls_to_run if tc["name"]]

            if not active_calls:
                if verbose:
                    console.print(f"[brand]✅ Sub-agent finished after {turns_used} turn(s).[/brand] {depth_tag}")
                return {
                    "status": "success",
                    "report": content_text.strip() or "(Sub-agent returned no final report.)",
                    "tool_calls": tool_call_log,
                    "turns_used": turns_used,
                    "depth": depth,
                }

            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if content_text:
                assistant_msg["content"] = content_text
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"] or f"call_{i + 1}",
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["args"]}
                }
                for i, tc in enumerate(active_calls)
            ]
            messages.append(assistant_msg)

            if verbose:
                for tc in active_calls:
                    name_esc = escape(str(tc.get("name", "")))
                    args_esc = escape(str(tc.get("args", "")))
                    console.print(f"  [dim]↳ {depth_tag}sub-agent tool call:[/dim] [tool]{name_esc}[/tool]([dim]{args_esc}[/dim])")

            result_strs = await _execute_turn_tool_calls(tool_registry, active_calls)

            for i, tc in enumerate(active_calls):
                tool_call_id = assistant_msg["tool_calls"][i]["id"]
                result_str = result_strs[i]
                tool_call_log.append({"name": tc["name"], "args": tc["args"], "result": result_str})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_str
                })

        if verbose:
            console.print(f"[warning]⚠️   Sub-agent hit the {turns_limit}-turn limit without finishing.[/warning] {depth_tag}")
        return {
            "status": "max_turns_reached",
            "report": (
                f"Sub-agent did not finish within its {turns_limit}-turn limit. "
                "Partial progress was made - see tool_calls for what was attempted."
            ),
            "tool_calls": tool_call_log,
            "turns_used": turns_used,
            "depth": depth,
        }
    finally:
        CURRENT_DELEGATION_DEPTH.reset(depth_token)
