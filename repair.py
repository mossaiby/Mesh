import json
from typing import Dict, Any, Optional
from config import ConfigManager
from providers import get_provider


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

TRANSIENT_PATTERNS = [
    "timeout", "timed out", "connection", "temporarily unavailable",
    "rate limit", "429", "connection reset", "network", "econnrefused",
    "econnreset", "service unavailable", "502", "503", "504",
]

NON_REPAIRABLE_PATTERNS = [
    "permission denied",
    "blocked by safety guard",
    "denied by user",
    "execution denied"
]

REPAIR_EXCLUDED_TOOLS = {"shell", "ask_user"}


def is_transient(error_message: str) -> bool:
    msg = (error_message or "").lower()
    return any(p in msg for p in TRANSIENT_PATTERNS)


def is_non_repairable(error_message: str) -> bool:
    msg = (error_message or "").lower()
    return any(p in msg for p in NON_REPAIRABLE_PATTERNS)


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


class RepairEngine:
    """
    Provides automatic recovery for failed tool calls:
    1. Mechanical retries for transient errors.
    2. LLM-assisted argument repair for structural mistakes.
    """

    def __init__(
        self,
        config_mgr: ConfigManager,
        enabled: bool = True,
        mechanical_retries: Optional[int] = None,
        mechanical_delay: Optional[float] = None
    ):
        self.config_mgr = config_mgr
        self.enabled = enabled
        self.mechanical_retries = mechanical_retries if mechanical_retries is not None else config_mgr.config.repair_settings.retries
        self.mechanical_delay = mechanical_delay if mechanical_delay is not None else config_mgr.config.repair_settings.delay

    async def attempt_repair(
        self,
        tool_schema: Dict[str, Any],
        tool_name: str,
        failed_arguments: Dict[str, Any],
        error_message: str
    ) -> Optional[Dict[str, Any]]:
        """Runs the repair sub-agent call. Returns corrected arguments as a dict if found."""
        if tool_name in REPAIR_EXCLUDED_TOOLS:
            return None

        try:
            model_cfg, provider_cfg = self.config_mgr.get_active_model_and_provider()
        except Exception:
            return None

        provider = get_provider(model_cfg, provider_cfg, self.config_mgr)

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
