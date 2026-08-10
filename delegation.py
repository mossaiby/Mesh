import asyncio
import contextvars
from typing import Dict, Any, List, Optional, Tuple
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
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

# Tools a delegated sub-agent should never call, at any depth:
#  - ask_user: a sub-agent has no live user to interact with mid-task
# delegate_task is NOT unconditionally excluded - whether a sub-agent may
# delegate further depends on the current depth vs. the configured max
# (see run_delegated_task below). This is what makes delegation recursive
# rather than strictly one level deep.
ALWAYS_EXCLUDED_TOOLS = {"ask_user"}

DEFAULT_MAX_TURNS = 6
HARD_MAX_TURNS_CAP = 10

# How many delegate_task calls within a single turn are allowed to run
# concurrently. Bounds worst-case fan-out from one turn (a sub-agent could
# otherwise request many delegations at once) while still letting genuinely
# independent sub-tasks actually run in parallel rather than one at a time.
MAX_CONCURRENT_DELEGATIONS = 4
_delegation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DELEGATIONS)

# Tracks how many levels deep the currently-running delegation chain is.
# Depth 0 = the main agent (not itself a delegation). Depth 1 = the first
# level of sub-agent spawned by delegate_task. A ContextVar (rather than
# passing depth explicitly through every call) is what lets a single shared
# DelegateTaskTool instance know "how deep am I being called from right now"
# even though the same tool object is reused at every level - each nested
# asyncio Task gets its own copy of the context, so sibling/parallel
# sub-agents never see each other's depth.
CURRENT_DELEGATION_DEPTH: "contextvars.ContextVar[int]" = contextvars.ContextVar(
    "current_delegation_depth", default=0
)


def max_turns_for_depth(requested_max_turns: int, depth: int) -> int:
    """Tapers the per-call turn budget down as delegation depth increases,
    so a deep recursive chain can't multiply total work unboundedly even
    within the hard depth cap. Depth 1 (the first level) is unaffected."""
    tapered_cap = max(2, HARD_MAX_TURNS_CAP - 2 * (depth - 1))
    return max(1, min(requested_max_turns, tapered_cap))


async def _execute_turn_tool_calls(
    tool_registry: Any,
    active_calls: List[Dict[str, str]]
) -> List[str]:
    """
    Executes one turn's tool calls. Multiple delegate_task calls in the same
    turn run concurrently (bounded by _delegation_semaphore) so genuinely
    independent sub-tasks are actually worked on in parallel, rather than
    one at a time. Every other tool runs sequentially in call order, since
    most tools touch shared, unlocked, file-backed state (memory.json,
    notes.md, the in-memory todo list) where concurrent execution could
    race - delegate_task's own sub-agent loop doesn't share that risk
    because it operates in its own isolated message history.

    Returns results in the same order as active_calls.
    """
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
    max_turns: int = DEFAULT_MAX_TURNS,
    excluded_tools: Optional[set] = None,
    verbose: bool = True,
    depth: int = 1,
    max_depth: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Runs an autonomous sub-agent loop to complete `task` using tools from
    `tool_registry`, entirely separate from the main conversation.

    This is intentionally independent of SubAgentProxy (`/proxy`), which only
    distills the *output* of a single tool call for the main agent - it does
    not run its own tool loop. Here, a fresh sub-agent conversation plans and
    executes a whole task end-to-end, then hands back one final report.

    Delegation is recursive up to `max_depth` (config_mgr.config.
    max_delegation_depth if not given explicitly): a sub-agent running at
    `depth` may itself call delegate_task - spawning a child at `depth + 1`
    - as long as `depth < max_depth`. At the deepest allowed level,
    delegate_task is excluded from that sub-agent's own tools, so recursion
    always terminates.

    Because the sub-agent's own tool schemas are built with
    inject_intent=False, none of its tool calls carry an `_intent` argument,
    so ToolRegistry.execute() never routes them through SubAgentProxy
    regardless of whether /proxy is currently on or off.

    Returns a dict with:
        status: "success" | "max_turns_reached" | "error"
        report: the sub-agent's final text report (present unless status == "error")
        tool_calls: list of {name, args, result} for every tool call made
        turns_used: how many model turns were used
        depth: the depth this sub-agent ran at
        error: present only when status == "error"
    """
    effective_max_depth = max_depth if max_depth is not None else getattr(
        config_mgr.config, "max_delegation_depth", 2
    )

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

        provider = OpenAIProvider(model_cfg, provider_cfg)

        tool_call_log: List[Dict[str, Any]] = []
        turns_used = 0
        depth_tag = f"[dim](depth {depth})[/dim] " if depth > 1 else ""

        if verbose:
            console.print(f"[brand]\U0001F4E4 Delegating task to sub-agent:[/brand] {depth_tag}{task}")

        for turn in range(max_turns):
            turns_used = turn + 1
            tool_calls_to_run: List[Dict[str, str]] = []
            content_text = ""

            try:
                async for chunk in provider.stream_chat(messages, tools=schemas):
                    ctype = chunk["type"]
                    cval = chunk["value"]

                    if ctype == "content":
                        content_text += cval
                    elif ctype == "tool_calls":
                        for delta in cval:
                            idx = delta.index
                            while len(tool_calls_to_run) <= idx:
                                tool_calls_to_run.append({"id": "", "name": "", "args": ""})
                            if delta.id:
                                tool_calls_to_run[idx]["id"] = delta.id
                            if delta.function and delta.function.name:
                                tool_calls_to_run[idx]["name"] = delta.function.name
                            if delta.function and delta.function.arguments:
                                tool_calls_to_run[idx]["args"] += delta.function.arguments
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
                # No tool calls this turn -> the sub-agent is done; this is its final report.
                if verbose:
                    console.print(f"[brand]\u2705 Sub-agent finished after {turns_used} turn(s).[/brand] {depth_tag}")
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
                    console.print(f"  [dim]\u21B3 {depth_tag}sub-agent tool call: {tc['name']}({tc['args']})[/dim]")

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

        # Ran out of turns without the sub-agent producing a final text-only response
        if verbose:
            console.print(f"[warning]\u26A0\uFE0F  Sub-agent hit the {max_turns}-turn limit without finishing.[/warning] {depth_tag}")
        return {
            "status": "max_turns_reached",
            "report": (
                f"Sub-agent did not finish within its {max_turns}-turn limit. "
                "Partial progress was made - see tool_calls for what was attempted."
            ),
            "tool_calls": tool_call_log,
            "turns_used": turns_used,
            "depth": depth,
        }
    finally:
        CURRENT_DELEGATION_DEPTH.reset(depth_token)
