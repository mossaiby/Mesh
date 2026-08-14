from dataclasses import dataclass, field
from typing import Set, Dict, Optional


@dataclass(frozen=True)
class ModeDef:
    name: str
    label: str
    description: str
    system_note: str
    # If allowed_tools is specified, only those tools are permitted in this mode.
    # All other registered tools will be blocked.
    allowed_tools: Optional[frozenset] = None
    # If True, every tool with requires_guard=True (write_file, edit_file,
    # shell, every MCP tool) is blocked, plus delegate_task -
    # this is what makes a mode "read-only": it reuses the exact same
    # "does this tool mutate state" signal the Safety Guard already relies
    # on, rather than introducing a second classification scheme.
    blocks_mutating_tools: bool = False
    extra_blocked_tools: frozenset = field(default_factory=frozenset)
    # If True, entering this mode forces guard_autonomy to "autonomous" and
    # PermissionManager.auto_approve to True for its duration (restored to
    # whatever they were before on leaving).
    force_autonomous: bool = False


MODES: Dict[str, ModeDef] = {
    "build": ModeDef(
        name="build",
        label="Build",
        description="Full tool access (default) - investigate and make changes directly.",
        system_note=(
            "You are in Build Mode (the default): you have full tool access. Investigate "
            "as needed and make changes directly rather than just describing what you "
            "would do."
        ),
    ),
    "plan": ModeDef(
        name="plan",
        label="Plan",
        description="Read-only. Investigate and propose a plan; no writes, shell, delegation, or MCP tools.",
        system_note=(
            "You are in Plan Mode: read-only. write_file, edit_file, shell, "
            "delegate_task, and MCP tools are not available to you right now - use "
            "read_file, glob_files, web_search, web_fetch, and consult_advisor to "
            "investigate, then produce a clear, concrete plan for the user to review "
            "(consider laying it out step-by-step with todo_manager). Do not describe "
            "actions as if you took them - you haven't, and can't yet. If the user wants "
            "it executed, they'll switch to Build Mode."
        ),
        blocks_mutating_tools=True,
    ),
    "review": ModeDef(
        name="review",
        label="Review",
        description="Read-only. Critically examine existing work; no writes, shell, delegation, or MCP tools.",
        system_note=(
            "You are in Review Mode: read-only. write_file, edit_file, shell, "
            "delegate_task, and MCP tools are not available to you right now - use "
            "read_file, glob_files, web_search, web_fetch, and consult_advisor to examine "
            "what's already there. Report concrete findings (bugs, risks, security issues, "
            "correctness problems, style inconsistencies) clearly and specifically. This "
            "is a critique of existing work, not a plan for new work - don't propose an "
            "unrelated feature roadmap unless asked."
        ),
        blocks_mutating_tools=True,
    ),
    "chat": ModeDef(
        name="chat",
        label="Chat",
        description="Conversational Q&A, brainstorming, and research. Limited to web search, fetching, calculations, advisor, and memory.",
        system_note=(
            "You are in Chat Mode: focused on direct, thoughtful conversation, answering "
            "questions, brainstorming, and explaining concepts. You do not have access to "
            "local workspace files, code editing, shell execution, or task orchestration "
            "tools. You may use web search (web_search, web_fetch) for current facts or "
            "documentation, calculator for exact calculations, consult_advisor for second "
            "opinions, and memory to recall user preferences."
        ),
        allowed_tools=frozenset({
            "calculator",
            "web_search",
            "web_fetch",
            "consult_advisor",
            "memory",
        }),
    ),
    "yolo": ModeDef(
        name="yolo",
        label="YOLO",
        description="Full tool access, no confirmation prompts for ambiguous-risk actions. High-risk actions are still always blocked.",
        system_note=(
            "You are in YOLO Mode: act autonomously and don't pause for confirmation on "
            "ambiguous-risk actions - the user has explicitly opted into fewer "
            "interruptions. This does NOT relax judgment: the Safety Guard still blocks "
            "genuinely high-risk actions outright regardless of mode, and you should "
            "still avoid anything destructive or hard to reverse without good reason. "
            "YOLO removes friction, not responsibility."
        ),
        force_autonomous=True,
    ),
}

DEFAULT_MODE = "build"


def blocked_tools_for_mode(mode_key: str, tool_registry) -> Set[str]:
    """Computes the concrete set of tool names blocked by a mode, using the
    registry's live requires_guard tools rather than a hardcoded list, so
    newly-connected MCP tools are automatically covered by Plan/Review mode
    without this module needing to know about them."""
    mode = MODES.get(mode_key, MODES[DEFAULT_MODE])

    # If the mode defines an explicit allowed_tools allow-list, block all others
    if mode.allowed_tools is not None:
        all_registered_tools = set(tool_registry._tools.keys())
        return all_registered_tools - set(mode.allowed_tools)

    blocked: Set[str] = set(mode.extra_blocked_tools)
    if mode.blocks_mutating_tools:
        blocked |= tool_registry.get_tool_names_requiring_guard()
        blocked.add("delegate_task")

    return blocked
