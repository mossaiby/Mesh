import asyncio
import json
from typing import Dict, Any, Optional, Tuple
from config import ConfigManager
from providers import get_provider
from tools.ask_tool import AskUserTool
from theme import console


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
        if tool_name in self._session_trusted_tools:
            return True, {"risk": "low", "verdict": "allow", "reason": "Trusted for this session by the user."}

        assessment = await self.assess(tool_name, arguments)
        risk = assessment.get("risk", "unknown")
        verdict = assessment.get("verdict")
        reason = assessment.get("reason", "")

        if verdict == "allow":
            return True, assessment

        if verdict == "deny":
            console.print(f"[error]🛡️   Safety Guard BLOCKED tool '[tool]{tool_name}[/tool]':[/error] {reason}")
            return False, assessment

        if self.config_mgr.config.guard_autonomy == "autonomous":
            console.print(f"[warning]🛡️   Safety Guard auto-approved tool '[tool]{tool_name}[/tool]' (autonomous mode):[/warning] {reason}")
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
