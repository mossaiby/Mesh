from typing import Dict, Any, List, Optional
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
from theme import console


DELEGATE_SYSTEM_PROMPT = (
    "You are a focused, autonomous sub-agent inside Mesh, spun up to complete ONE "
    "self-contained task on behalf of the main assistant. You have access to tools - "
    "use them as needed to gather information and make changes. You cannot ask the "
    "user any questions, and no one is watching this conversation turn by turn, so "
    "make reasonable assumptions and proceed rather than stalling.\n\n"
    "When the task is complete (or you've determined it cannot be completed), stop "
    "calling tools and respond with a concise final report describing what you did, "
    "what you found or changed, and the outcome. This final report is the ONLY thing "
    "the main assistant will see - it does not see your intermediate tool calls - so "
    "make the report self-contained and specific rather than saying things like 'as "
    "shown above'."
)

# Tools a delegated sub-agent should never call itself:
#  - delegate_task: prevents unbounded/recursive delegation chains
#  - ask_user: a sub-agent has no live user to interact with mid-task
DEFAULT_EXCLUDED_TOOLS = {"delegate_task", "ask_user"}

DEFAULT_MAX_TURNS = 6


async def run_delegated_task(
    task: str,
    tool_registry: Any,
    config_mgr: ConfigManager,
    max_turns: int = DEFAULT_MAX_TURNS,
    excluded_tools: Optional[set] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Runs an autonomous sub-agent loop to complete `task` using tools from
    `tool_registry`, entirely separate from the main conversation.

    This is intentionally independent of SubAgentProxy (`/proxy`), which only
    distills the *output* of a single tool call for the main agent - it does
    not run its own tool loop. Here, a fresh sub-agent conversation plans and
    executes a whole task end-to-end, then hands back one final report.

    Because the sub-agent's own tool schemas are built with
    inject_intent=False, none of its tool calls carry an `_intent` argument,
    so ToolRegistry.execute() never routes them through SubAgentProxy
    regardless of whether /proxy is currently on or off.

    Returns a dict with:
        status: "success" | "max_turns_reached" | "error"
        report: the sub-agent's final text report (present unless status == "error")
        tool_calls: list of {name, args, result} for every tool call made
        turns_used: how many model turns were used
        error: present only when status == "error"
    """
    excluded = excluded_tools if excluded_tools is not None else DEFAULT_EXCLUDED_TOOLS

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": DELEGATE_SYSTEM_PROMPT},
        {"role": "user", "content": task}
    ]

    all_schemas = tool_registry.get_schemas(inject_intent=False)
    schemas = [s for s in all_schemas if s["function"]["name"] not in excluded]

    try:
        model_cfg, provider_cfg = config_mgr.get_active_model_and_provider()
    except Exception as e:
        return {"status": "error", "error": f"Configuration error: {e}", "tool_calls": [], "turns_used": 0}

    provider = OpenAIProvider(model_cfg, provider_cfg)

    tool_call_log: List[Dict[str, Any]] = []
    turns_used = 0

    if verbose:
        console.print(f"[brand]\U0001F4E4 Delegating task to sub-agent:[/brand] {task}")

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
            }

        active_calls = [tc for tc in tool_calls_to_run if tc["name"]]

        if not active_calls:
            # No tool calls this turn -> the sub-agent is done; this is its final report.
            if verbose:
                console.print(f"[brand]\u2705 Sub-agent finished after {turns_used} turn(s).[/brand]")
            return {
                "status": "success",
                "report": content_text.strip() or "(Sub-agent returned no final report.)",
                "tool_calls": tool_call_log,
                "turns_used": turns_used,
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

        for i, tc in enumerate(active_calls):
            tool_call_id = assistant_msg["tool_calls"][i]["id"]

            if verbose:
                console.print(f"  [dim]\u21B3 sub-agent tool call: {tc['name']}({tc['args']})[/dim]")

            result_str = await tool_registry.execute(tc["name"], tc["args"])
            tool_call_log.append({"name": tc["name"], "args": tc["args"], "result": result_str})

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result_str
            })

    # Ran out of turns without the sub-agent producing a final text-only response
    if verbose:
        console.print(f"[warning]\u26A0\uFE0F  Sub-agent hit the {max_turns}-turn limit without finishing.[/warning]")
    return {
        "status": "max_turns_reached",
        "report": (
            f"Sub-agent did not finish within its {max_turns}-turn limit. "
            "Partial progress was made - see tool_calls for what was attempted."
        ),
        "tool_calls": tool_call_log,
        "turns_used": turns_used,
    }
