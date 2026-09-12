import asyncio
import json
import re
from typing import Dict, Any, Optional, Tuple
from config import ConfigManager
from providers import get_provider
from tools.ask_tool import AskUserTool
from theme import console
from glyphs import SHIELD, VS16


GUARD_SYSTEM_PROMPT = (
    "You are Mesh's safety guard: you assess ONE tool call for risk before it is allowed "
    "to execute. You do not perform the call yourself, and you have no other context "
    "about the conversation - judge only what is in front of you.\n\n"
    "Classify the risk as:\n"
    "- \"low\": routine, reversible, or read-mostly. Normal development work, editing "
    "project files, running standard build/test/lint commands, typical MCP tool use.\n"
    "- \"medium\": could meaningfully modify state but isn't inherently destructive or "
    "irreversible - e.g. installing a well-known package, deleting a specific named "
    "file the user would plausibly want gone, git operations that rewrite local history.\n"
    "- \"high\": destructive, hard to reverse, or security-sensitive - e.g. recursive "
    "deletion of broad paths (rm -rf on a non-trivial directory), piping a remote script "
    "straight into a shell, modifying system files outside the project, exfiltrating "
    "secrets/credentials, disabling security controls, force-pushing over shared "
    "history, dropping/truncating a database, granting broad permissions.\n\n"
    "Map risk to a verdict:\n"
    "- low -> \"allow\"\n"
    "- medium -> \"ask\"\n"
    "- high -> \"deny\"\n\n"
    "Respond with ONLY a single JSON object, no prose, no markdown code fences:\n"
    '{"risk": "low"|"medium"|"high", "verdict": "allow"|"ask"|"deny", "reason": "one short sentence"}\n\n'
    "When genuinely uncertain, prefer \"ask\" over \"allow\" - the cost of a needless "
    "prompt is much lower than the cost of a wrongly-automated risky action."
)


def _safe_parse_json(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()

    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(raw[start:end + 1])
            except Exception:
                return {}
        else:
            return {}

    return data if isinstance(data, dict) else {}


# --- Deterministic pre-filter -----------------------------------------------
#
# The LLM-backed assessment below is the primary safety mechanism, but it has
# two real weaknesses: it can be wrong or manipulated (a jailbroken or just
# mistaken guard-model verdict is the only thing standing between a bad tool
# call and execution), and it's off entirely by default (`guard_enabled:
# false`), at which point `SafetyGuard.assess()` is never even called - see
# `tools/registry.py`. Neither of those should be able to let through a
# genuinely catastrophic action.
#
# This is a small, dependency-free, regex-based safety net for the handful of
# command patterns that have essentially no legitimate everyday use and are
# unambiguous enough to hardcode: recursive deletes of broad paths, piping a
# remote script straight into a shell, disk-formatting/fork-bomb style
# commands, and so on. It runs unconditionally in `SafetyGuard.check()`,
# before the `enabled` flag is even consulted - see there for how the two
# layers combine.
#
# This is deliberately narrow. It is not a substitute for the LLM guard (it
# has no situational judgment at all) and it is not meant to catch "medium"
# risk - just the handful of things that should never be automated no matter
# what.

_DENY_COMMAND_PATTERNS = [
    (re.compile(r"\brm\s+(?:-\w*r\w*f\w*|-\w*f\w*r\w*)\s+(?:/|/\*|~|~/\*|\$HOME)\s*(?:$|[;&|])", re.IGNORECASE),
     "a recursive force-delete targeting the root, home directory, or an entire drive"),
    (re.compile(r"\brm\b[^\n]*--no-preserve-root", re.IGNORECASE),
     "a recursive delete with --no-preserve-root"),
    (re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:bash|sh|zsh|python[0-9.]*)\b", re.IGNORECASE),
     "piping a remotely-downloaded script straight into a shell/interpreter"),
    (re.compile(r"\b(?:iwr|invoke-webrequest|curl)\b[^\n|]*\|\s*iex\b", re.IGNORECASE),
     "downloading and executing a remote script via PowerShell (`| iex`)"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.IGNORECASE),
     "a classic shell fork bomb"),
    (re.compile(r"\bmkfs(?:\.\w+)?\b", re.IGNORECASE),
     "formatting a filesystem/device"),
    (re.compile(r"\bdd\b[^\n]*\bof=/dev/(?:sd|nvme|hd|disk)", re.IGNORECASE),
     "writing raw data directly onto a physical disk device"),
    (re.compile(r"\bchmod\b\s+(?:-R\s+)?777\s+/(?:\s|$)", re.IGNORECASE),
     "recursively opening permissions on the root filesystem"),
    (re.compile(r"\b(?:shutdown\b.*-h\s+now|reboot\s+--force|halt\s+--force)\b", re.IGNORECASE),
     "forcing an immediate system shutdown/reboot"),
]

_ASK_COMMAND_PATTERNS = [
    (re.compile(r"\bgit\s+push\b[^\n]*(?:--force(?!-with-lease)\b|(?<!\S)-f\b)", re.IGNORECASE),
     "a hard force-push (not --force-with-lease) that can silently overwrite a collaborator's history"),
]

_PROTECTED_BRANCHES = {"main", "master", "prod", "production", "release"}


def static_precheck(tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Checks a tool call against the hardcoded rules above.

    Returns a guard-result dict (same shape as `SafetyGuard.assess()`'s
    return value, plus `"source": "static"`) if a rule matched, or None if
    nothing fired - in which case the caller falls through to the LLM guard
    (if enabled) or to a plain allow (if not).
    """
    command = arguments.get("command") if tool_name in ("shell", "job") else None
    if isinstance(command, str) and command.strip():
        for pattern, description in _DENY_COMMAND_PATTERNS:
            if pattern.search(command):
                return {
                    "risk": "high",
                    "verdict": "deny",
                    "reason": f"Static safety rule matched: {description}.",
                    "source": "static",
                }
        for pattern, description in _ASK_COMMAND_PATTERNS:
            if pattern.search(command):
                return {
                    "risk": "medium",
                    "verdict": "ask",
                    "reason": f"Static safety rule matched: {description}.",
                    "source": "static",
                }

    if tool_name == "git_push" and arguments.get("force"):
        branch = str(arguments.get("branch") or "").strip().lower()
        if branch in _PROTECTED_BRANCHES:
            return {
                "risk": "medium",
                "verdict": "ask",
                "reason": f"Static safety rule matched: force-pushing over the protected branch '{branch}'.",
                "source": "static",
            }

    return None


class SafetyGuard:
    """
    Risk-assesses tool calls flagged with requires_guard=True before execution.
    """

    def __init__(self, config_mgr: ConfigManager, enabled: bool = True):
        self.config_mgr = config_mgr
        self.enabled = enabled
        self._ask_tool = AskUserTool()
        self._session_trusted_tools: set = set()
        self._prompt_lock = asyncio.Lock()

    def trust_tool_for_session(self, tool_name: str) -> None:
        self._session_trusted_tools.add(tool_name)

    def reset_session_trust(self) -> None:
        self._session_trusted_tools.clear()

    def get_session_trusted_tools(self) -> set:
        return set(self._session_trusted_tools)

    async def assess(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        model_key = self.config_mgr.config.guard_model or self.config_mgr.config.active_model
        if model_key == "auto":
            model_key = self.config_mgr.config.router_model
            if not model_key:
                return {"risk": "unknown", "verdict": "ask", "reason": "Guard model unavailable (router_model not configured); asking to be safe."}

        try:
            model_cfg, provider_cfg = self.config_mgr.get_model_and_provider(model_key)
        except Exception as e:
            return {"risk": "unknown", "verdict": "ask", "reason": f"Guard model unavailable ({e}); asking to be safe."}

        provider = get_provider(model_cfg, provider_cfg, self.config_mgr)

        user_content = f"Tool: {tool_name}\nArguments:\n{json.dumps(arguments, indent=2)}"
        messages = [
            {"role": "system", "content": GUARD_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]

        raw_text = ""
        try:
            async for chunk in provider.stream_chat(messages):
                if chunk["type"] == "content":
                    raw_text += chunk["value"]
        except Exception as e:
            return {"risk": "unknown", "verdict": "ask", "reason": f"Guard assessment call failed ({e}); asking to be safe."}

        data = _safe_parse_json(raw_text)
        verdict = data.get("verdict")
        if verdict not in ("allow", "ask", "deny"):
            return {"risk": "unknown", "verdict": "ask", "reason": "Guard response was unparseable; asking to be safe."}

        return {
            "risk": data.get("risk", "unknown"),
            "verdict": verdict,
            "reason": data.get("reason", "")
        }

    async def check(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        # The static safety net always runs, regardless of `self.enabled` or
        # of session-level trust - see the module-level docstring above
        # `static_precheck` for why. A hard "deny" here is final.
        static_hit = static_precheck(tool_name, arguments)
        if static_hit is not None and static_hit["verdict"] == "deny":
            console.print(
                f"[error]{SHIELD}{VS16}   Safety Guard BLOCKED tool '[tool]{tool_name}[/tool]' "
                f"(static rule):[/error] {static_hit['reason']}"
            )
            return False, static_hit

        if tool_name in self._session_trusted_tools:
            return True, {"risk": "low", "verdict": "allow", "reason": "Trusted for this session by the user."}

        if static_hit is not None:
            # A static "ask" rule fired - resolve it the same way an LLM
            # "ask" verdict would be, even if the LLM guard itself is
            # disabled or configured with a different model.
            return await self._resolve_verdict(tool_name, arguments, static_hit)

        if not self.enabled:
            return True, {
                "risk": "unknown",
                "verdict": "allow",
                "reason": "Safety Guard (LLM layer) is disabled; no static rule matched.",
            }

        assessment = await self.assess(tool_name, arguments)
        return await self._resolve_verdict(tool_name, arguments, assessment)

    async def _resolve_verdict(self, tool_name: str, arguments: Dict[str, Any], assessment: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        risk = assessment.get("risk", "unknown")
        verdict = assessment.get("verdict")
        reason = assessment.get("reason", "")

        if verdict == "allow":
            return True, assessment

        if verdict == "deny":
            console.print(f"[error]{SHIELD}{VS16}   Safety Guard BLOCKED tool '[tool]{tool_name}[/tool]':[/error] {reason}")
            return False, assessment

        if self.config_mgr.config.guard_autonomy == "autonomous":
            console.print(f"[warning]{SHIELD}{VS16}   Safety Guard auto-approved tool '[tool]{tool_name}[/tool]' (autonomous mode):[/warning] {reason}")
            return True, {**assessment, "resolution": "auto_approved"}

        async with self._prompt_lock:
            args_preview = json.dumps(arguments, indent=2)
            if len(args_preview) > 800:
                args_preview = args_preview[:800] + "\n... (truncated)"

            question = (
                f"Safety Guard flagged tool '{tool_name}' as [{risk} risk]: {reason}\n"
                f"Arguments:\n{args_preview}"
            )
            options = [
                "Allow Once",
                f"Always Allow '{tool_name}' (skip guard for this tool for the rest of the session)",
                "Deny"
            ]
            res = await self._ask_tool.execute(question=question, options=options, allow_custom=False)
            choice = res.get("user_response", "Deny")

        if choice == "Allow Once":
            console.print(f"[warning]Allowed tool '[tool]{tool_name}[/tool]' once.[/warning]")
            return True, {**assessment, "resolution": "allowed_once"}
        elif choice.startswith("Always Allow"):
            self.trust_tool_for_session(tool_name)
            console.print(f"[success]Tool '[tool]{tool_name}[/tool]' will no longer be guard-checked for the rest of this session.[/success]")
            return True, {**assessment, "resolution": "always_allowed"}
        else:
            console.print(f"[error]Denied tool '[tool]{tool_name}[/tool]'.[/error]")
            return False, {**assessment, "resolution": "user_denied"}
