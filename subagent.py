from typing import Dict, Any, Optional
from config import ConfigManager
from providers.openai_provider import OpenAIProvider


class SubAgentProxy:
    """
    Sub-agent proxy that executes tools on behalf of the main agent and
    distills/summarizes the raw tool output based on the declared intent.
    """
    def __init__(self, config_mgr: ConfigManager):
        self.config_mgr = config_mgr
        self.enabled: bool = True

    async def distill_tool_result(
        self, 
        tool_name: str, 
        intent: str, 
        raw_result: Any
    ) -> str:
        """
        Passes the raw tool execution result through a focused sub-agent
        to filter out noise and extract only relevant facts matching 'intent'.
        """
        raw_str = str(raw_result)

        # Unescape escaped newlines to accurately count lines in JSON payloads
        raw_unwrapped = raw_str.replace("\\n", "\n")
        line_count = len(raw_unwrapped.strip().splitlines())
        char_count = len(raw_str)

        # Bypass distillation only if BOTH line count AND character count are very small, or intent is missing
        if not intent or (line_count <= 4 and char_count < 300):
            return raw_str

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert Tool Execution Sub-Agent. Your job is to analyze raw tool "
                    "outputs and extract ONLY the precise information requested by the target INTENT. "
                    "Filter out noise, unneeded lines, logs, or boilerplate. Be concise, accurate, "
                    "and objective. If the raw output contains an error, explain it clearly."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Tool Name: {tool_name}\n"
                    f"Target Intent: {intent}\n\n"
                    f"Raw Tool Output:\n{raw_unwrapped}\n\n"
                    "Provide a concise, distilled summary answering the target intent:"
                )
            }
        ]

        try:
            model_cfg, provider_cfg = self.config_mgr.get_active_model_and_provider()
            provider = OpenAIProvider(model_cfg, provider_cfg)

            distilled = ""
            async for chunk in provider.stream_chat(messages):
                if chunk["type"] == "content":
                    distilled += chunk["value"]

            if distilled.strip():
                return f"[Sub-Agent Distillation for Intent: '{intent}']\n{distilled.strip()}"
            return raw_str
        except Exception:
            # Fallback to raw result if sub-agent call fails
            return raw_str