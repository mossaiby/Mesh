import json
from typing import Dict, Any
from rich.markdown import Markdown
from rich.styled import Styled
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
from theme import console


class SubAgentDistiller:
    """
    Sub-agent distiller that executes tools on behalf of the main agent and
    distills/summarizes raw tool outputs into structured JSON based on intent.
    """
    def __init__(self, config_mgr: ConfigManager):
        self.config_mgr = config_mgr
        self.enabled: bool = False  # Disabled by default so _intent is omitted until /config distill on
        self.debug_mode: bool = False

    async def distill_tool_result(
        self, 
        tool_name: str, 
        intent: str, 
        raw_result: Any
    ) -> str:
        """
        Passes the raw tool execution result through a focused sub-agent
        to filter out noise and return a structured JSON summary matching 'intent'.
        """
        raw_str = str(raw_result)

        # Unescape escaped newlines to accurately count lines in JSON payloads
        raw_unwrapped = raw_str.replace("\\n", "\n")
        line_count = len(raw_unwrapped.strip().splitlines())
        char_count = len(raw_str)

        # Bypass distillation only if BOTH line count AND character count are very small, or intent is missing
        if not intent or (line_count <= 4 and char_count < 300):
            return raw_str if (raw_str.startswith("{") or raw_str.startswith("[")) else json.dumps({"raw_output": raw_str})

        if self.debug_mode:
            console.print(f"\n[brand]🤖 [SUB-AGENT DISTILLER] Distilling '{tool_name}' output for intent:[/brand] [italic]{intent}[/italic]")

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
            sub_reasoning = ""
            printed_reasoning_header = False

            async for chunk in provider.stream_chat(messages):
                ctype = chunk["type"]
                cval = chunk["value"]

                # 1. Sub-agent Reasoning / Chain of Thought tokens
                if ctype == "reasoning":
                    sub_reasoning += cval

                # 2. Sub-agent Content tokens
                elif ctype == "content":
                    if sub_reasoning and self.debug_mode and not printed_reasoning_header:
                        console.print("\n[brand]🧠 [SUB-AGENT REASONING]:[/brand]")
                        console.print(Styled(Markdown(sub_reasoning), "dim"))
                        console.print()  # Blank line separator
                        printed_reasoning_header = True

                    distilled += cval
                    if self.debug_mode:
                        console.print(f"[brand]{cval}[/brand]", end="")

            if self.debug_mode:
                console.print("\n[brand]🤖 [SUB-AGENT DISTILLER] Distillation Complete.[/brand]\n")

            if distilled.strip():
                return json.dumps({
                    "status": "success",
                    "intent": intent,
                    "distilled_summary": distilled.strip()
                }, indent=2)
                
            return raw_str if (raw_str.startswith("{") or raw_str.startswith("[")) else json.dumps({"raw_output": raw_str})
        except Exception as e:
            if self.debug_mode:
                console.print(f"\n[error]🤖 [SUB-AGENT DISTILLER] Distillation Failed:[/error] {e}\n")
            return json.dumps({
                "status": "partial_fallback",
                "intent": intent,
                "raw_output": raw_str,
                "error": str(e)
            })


# Backward compatibility alias
SubAgentProxy = SubAgentDistiller
