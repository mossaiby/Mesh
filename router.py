import json
from typing import Dict, Any, Tuple, List
from config import ConfigManager
from providers import get_provider


ROUTER_SYSTEM_PROMPT = (
    "You are Mesh's Intelligent Model Router. Your job is to analyze the user's prompt "
    "and current conversation context, and select the best model from the available candidate models.\n\n"
    "Evaluate:\n"
    "- Task Complexity: Does it require heavy reasoning, deep software engineering, multi-step planning, or simple text generation?\n"
    "- Candidate Model Strengths: Inspect model tags, names, context windows, and descriptions.\n"
    "- Efficiency: Prefer smaller/faster/cheaper models for simple tasks, and powerful reasoning/coding models for complex engineering or math.\n\n"
    "Respond with ONLY a single JSON object in this exact shape, with no markdown code fences:\n"
    '{"selected_model": "<model_key>", "reason": "<one sentence concise explanation for the choice>"}\n\n'
    "You MUST select one of the provided valid candidate model keys."
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


async def select_model_for_prompt(
    prompt: str,
    messages: List[Dict[str, Any]],
    config_mgr: ConfigManager
) -> Tuple[str, str]:
    """
    Consults the router_model to dynamically choose the best model key for the given prompt/context.
    Returns (chosen_model_key, reasoning_text).
    """
    cfg = config_mgr.config
    if not cfg.router_model:
        raise ValueError("Router model is not configured in models.json. Set 'router_model' or run '/switch router <key>'.")

    if cfg.router_model not in cfg.models:
        raise ValueError(f"Configured router model '{cfg.router_model}' is not found in models.json.")

    candidates = {k: v for k, v in cfg.models.items() if k != "auto"}
    if not candidates:
        raise ValueError("No candidate models configured in models.json.")

    if len(candidates) == 1:
        key = list(candidates.keys())[0]
        return key, "Only one candidate model available."

    candidate_summaries = []
    for key, m_cfg in candidates.items():
        p_cfg = cfg.providers.get(m_cfg.provider)
        p_name = p_cfg.name if p_cfg else m_cfg.provider
        tags_str = f" [tags: {', '.join(m_cfg.tags)}]" if m_cfg.tags else ""
        desc_str = f" - {m_cfg.description}" if m_cfg.description else ""
        candidate_summaries.append(
            f"- Key: '{key}' | Name: '{m_cfg.name}' via {p_name} | Context Window: {m_cfg.context_window}{tags_str}{desc_str}"
        )

    models_manifest = "\n".join(candidate_summaries)

    user_input_preview = prompt.strip()
    if len(user_input_preview) > 1500:
        user_input_preview = user_input_preview[:1500] + "\n... (truncated)"

    user_content = (
        f"Candidate Models:\n{models_manifest}\n\n"
        f"User Prompt to Route:\n{user_input_preview}"
    )

    router_model_cfg, router_provider_cfg = config_mgr.get_model_and_provider(cfg.router_model)
    provider = get_provider(router_model_cfg, router_provider_cfg, config_mgr)

    router_messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]

    raw_text = ""
    try:
        async for chunk in provider.stream_chat(router_messages):
            if chunk["type"] == "content":
                raw_text += chunk["value"]
    except Exception as e:
        fallback_key = list(candidates.keys())[0]
        return fallback_key, f"Router call failed ({e}); falling back to '{fallback_key}'."

    data = _safe_parse_json(raw_text)
    selected = data.get("selected_model")
    reason = data.get("reason", "Auto-selected based on prompt analysis.")

    if selected and selected in candidates:
        return selected, reason

    if selected:
        for k in candidates:
            if k.lower() in selected.lower():
                return k, reason

    fallback_key = cfg.router_model if cfg.router_model in candidates else list(candidates.keys())[0]
    return fallback_key, f"Router response key invalid; defaulting to '{fallback_key}'."
