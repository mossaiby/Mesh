from typing import Dict, Any, Optional
from config import ConfigManager
from providers.openai_provider import OpenAIProvider


ADVISOR_SYSTEM_PROMPT = (
    "You are Mesh's advisor: an experienced second opinion, consulted by the main "
    "assistant when it wants advice before proceeding. You are not executing anything "
    "and have no tools - this is pure reasoning and judgment, not action.\n\n"
    "Give a candid, concise answer: state your actual recommendation, flag the real "
    "risks or tradeoffs, and mention a genuine alternative if one exists. It's fine to "
    "disagree with the premise of the question if you think it's wrong, and fine to say "
    "'it depends' if it genuinely does - but say what it depends on. Don't pad the "
    "answer with disclaimers or restate the question back. A few sentences to a short "
    "paragraph is usually enough; only go longer if the question genuinely needs it."
)


async def get_advice(
    question: str,
    config_mgr: ConfigManager,
    context: str = "",
    advisor_model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Consults a dedicated advisor sub-agent for a candid opinion on `question`,
    optionally with background `context`. This is a single-shot reasoning
    call with no tools - it never takes action, only gives an opinion, which
    is what distinguishes it from delegate_task (which does the work) and
    self_heal's repair pass (which fixes one specific failure).

    Uses `advisor_model` if given, else config_mgr.config.advisor_model if
    set, else the currently active model - so the advisor can be a genuinely
    different model from whichever one is driving the conversation, for a
    real second opinion rather than the same model re-asked.

    Returns a dict with:
        status: "ok" | "error"
        advice: the advisor's response (present unless status == "error")
        advisor_model: the model key actually consulted
        error: present only when status == "error"
    """
    if not question or not question.strip():
        return {"status": "error", "error": "A question is required."}

    model_key = advisor_model or config_mgr.config.advisor_model or config_mgr.config.active_model

    try:
        model_cfg, provider_cfg = config_mgr.get_model_and_provider(model_key)
    except Exception as e:
        return {"status": "error", "error": f"Configuration error for advisor model '{model_key}': {e}"}

    provider = OpenAIProvider(model_cfg, provider_cfg)

    user_content = f"Question: {question.strip()}"
    if context and context.strip():
        user_content = f"Context: {context.strip()}\n\n{user_content}"

    messages = [
        {"role": "system", "content": ADVISOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]

    raw_text = ""
    try:
        async for chunk in provider.stream_chat(messages):
            if chunk["type"] == "content":
                raw_text += chunk["value"]
    except Exception as e:
        return {"status": "error", "error": f"Advisor consultation failed: {e}"}

    advice = raw_text.strip()
    if not advice:
        return {"status": "error", "error": "Advisor returned an empty response."}

    return {"status": "ok", "advice": advice, "advisor_model": model_key}
