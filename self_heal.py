import json
from typing import Dict, Any, Optional
from config import ConfigManager
from providers.openai_provider import OpenAIProvider


REPAIR_SYSTEM_PROMPT = (
    "You are Mesh's tool-call repair assistant. A tool call just failed. You will be "
    "given the tool's JSON schema, the arguments that were actually passed, and the "
    "error message that resulted. Your job is ONLY to fix structural/syntactic mistakes "
    "in the arguments themselves - wrong parameter names, wrong types, malformed JSON, "
    "an invalid enum value, an off-by-one index, a typo'd action name, a missing "
    "required field whose value is obviously implied by the other arguments, etc. - "
    "using nothing but the schema and the error message.\n\n"
    "Do NOT guess at information you cannot know from what you were given. For example, "
    "if the error says a file or path doesn't exist, you have no way to know the correct "
    "path from the schema and error alone, so that is NOT something you can fix. Only "
    "propose a fix you are confident is correct purely from the schema and error text.\n\n"
    "Respond with ONLY a single JSON object, no prose, no markdown code fences:\n"
    '{"fixable": true/false, "corrected_arguments": {...} or null, "reasoning": "one short sentence"}\n\n'
    "If not confidently fixable, return fixable: false and corrected_arguments: null."
)

# Error substrings that indicate a transient, safe-to-retry-unchanged failure
# (network/timeout/rate-limit issues), as opposed to something wrong with the
# arguments themselves. Retried mechanically, with no model call involved.
TRANSIENT_PATTERNS = [
    "timeout", "timed out", "connection", "temporarily unavailable",
    "rate limit", "429", "connection reset", "network", "econnrefused",
    "econnreset", "service unavailable", "502", "503", "504",
]

# Never attempt any healing on these - they're deliberate boundaries
# (a permission/guard decision), not a broken tool call to be fixed.
NON_HEALABLE_PATTERNS = [
    "permission denied",
    "blocked by safety guard",
    "denied by user",
    "execution denied"
]

# Tools excluded from LLM-based argument auto-repair: either the side effect
# of blindly re-running corrected arguments is too severe to do without a
# human in the loop (arbitrary shell execution), or the tool is about human
# interaction rather than a "wrong argument" situation.
REPAIR_EXCLUDED_TOOLS = {"run_shell_command", "ask_user"}


def is_transient(error_message: str) -> bool:
    msg = (error_message or "").lower()
    return any(p in msg for p in TRANSIENT_PATTERNS)


def is_non_healable(error_message: str) -> bool:
    msg = (error_message or "").lower()
    return any(p in msg for p in NON_HEALABLE_PATTERNS)


def _safe_parse_json(raw: str) -> Dict[str, Any]:
    """Best-effort JSON parsing that tolerates stray markdown fences some
    models add despite instructions not to."""
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


class SelfHealer:
    """
    Provides two independent, best-effort layers of automatic recovery for
    failed tool calls, used by ToolRegistry.execute() so that both the main
    agent loop and delegated sub-agents (which share the same ToolRegistry)
    benefit from it:

      1. Mechanical retry - no model call. If the error looks transient
         (network/timeout/rate-limit), retry the exact same arguments a
         couple of times with a short delay before giving up on that path.

      2. LLM-assisted argument repair - one small, focused sub-agent call
         (the same "small out-of-band LLM call" pattern used by dream.py,
         compaction.py, and memory_search.py elsewhere in Mesh) that looks
         at the tool's schema, the arguments that failed, and the error
         message, and proposes corrected arguments if - and only if - it's
         confident the fix is purely structural, not something requiring
         outside knowledge like "what the real file path actually is".

    Both layers always fall back to returning the original error untouched
    if they can't help - this never masks a real failure, it only adds a
    best-effort recovery attempt in front of it.
    """

    def __init__(
        self,
        config_mgr: ConfigManager,
        enabled: bool = True,
        mechanical_retries: int = 2,
        mechanical_delay: float = 0.75
    ):
        self.config_mgr = config_mgr
        self.enabled = enabled
        self.mechanical_retries = mechanical_retries
        self.mechanical_delay = mechanical_delay

    async def attempt_repair(
        self,
        tool_schema: Dict[str, Any],
        tool_name: str,
        failed_arguments: Dict[str, Any],
        error_message: str
    ) -> Optional[Dict[str, Any]]:
        """Runs the repair sub-agent call. Returns corrected arguments as a
        dict if a confident fix was found, otherwise None."""
        if tool_name in REPAIR_EXCLUDED_TOOLS:
            return None

        try:
            model_cfg, provider_cfg = self.config_mgr.get_active_model_and_provider()
        except Exception:
            return None

        provider = OpenAIProvider(model_cfg, provider_cfg)

        user_content = (
            f"Tool schema:\n{json.dumps(tool_schema, indent=2)}\n\n"
            f"Arguments that were tried:\n{json.dumps(failed_arguments, indent=2)}\n\n"
            f"Error:\n{error_message}"
        )
        messages = [
            {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]

        raw_text = ""
        try:
            async for chunk in provider.stream_chat(messages):
                if chunk["type"] == "content":
                    raw_text += chunk["value"]
        except Exception:
            return None

        data = _safe_parse_json(raw_text)
        if not data or not data.get("fixable"):
            return None

        corrected = data.get("corrected_arguments")
        if not isinstance(corrected, dict):
            return None

        return corrected