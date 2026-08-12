from typing import Dict, Any, Optional
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
from render.stream_renderer import StreamRenderer


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

    try:
        renderer = StreamRenderer()
        advice, _ = await renderer.render_stream(provider.stream_chat(messages))
    except Exception as e:
        return {"status": "error", "error": f"Advisor consultation failed: {e}"}

    advice = advice.strip()
    if not advice:
        return {"status": "error", "error": "Advisor returned an empty response."}

    return {"status": "ok", "advice": advice, "advisor_model": model_key}