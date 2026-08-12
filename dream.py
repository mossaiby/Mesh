import json
from typing import List, Dict, Any, Tuple
from config import ConfigManager
from providers import get_provider


DREAM_SYSTEM_PROMPT = (
    "You are Mesh's 'dream' analysis pass: you review a finished conversation transcript "
    "after the fact and extract durable, reusable knowledge from it. You do NOT continue "
    "the conversation, address the user, or add commentary.\n\n"
    "Extract three kinds of things, only when clearly present in the transcript:\n\n"
    "1. notes - durable, human-readable facts, decisions, or open questions worth keeping "
    "in a persistent project log. Each note should be a short, self-contained sentence or "
    "Markdown bullet.\n\n"
    "2. memory - small structured key-value facts worth recalling automatically in future "
    "sessions (preferences, IDs, configuration values, recurring answers). Keys should be "
    "short, lowercase, and use underscores.\n\n"
    "3. skills - a reusable skill ONLY if the conversation shows a workflow or instruction "
    "set that was clearly repeated, or that the user explicitly asked to remember/reuse for "
    "future sessions. A skill has: a short name (lowercase_snake_case), a one-line "
    "description, and a system_instruction written as a direct second-person instruction "
    "('You should...', 'Always...', 'When X, do Y...') that would teach a fresh assistant "
    "to reproduce this workflow on its own. Do not invent a skill from a single one-off "
    "request - only from a pattern that actually recurred or was explicitly requested to "
    "be remembered.\n\n"
    "Respond with ONLY a single JSON object, no prose, no markdown code fences, in exactly "
    "this shape:\n"
    '{"notes": ["..."], "memory": [{"key": "...", "value": "..."}], '
    '"skills": [{"name": "...", "description": "...", "system_instruction": "..."}]}\n\n'
    "If a category has nothing worth extracting, return an empty list for it. Do not "
    "fabricate content that isn't grounded in the transcript."
)


def _format_transcript(messages: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        if role == "system":
            continue

        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls")

        line = f"{role.upper()}: {content}" if content else f"{role.upper()}:"
        if tool_calls:
            names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
            line += f" [tool_calls: {', '.join(names)}]"

        if line.strip():
            lines.append(line)

    text = "\n\n".join(lines)
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def _safe_parse_json(raw: str) -> Dict[str, Any]:
    raw = raw.strip()

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


async def dream_extract(
    messages: List[Dict[str, Any]],
    config_mgr: ConfigManager
) -> Tuple[Dict[str, List[Any]], str]:
    empty = {"notes": [], "memory": [], "skills": []}

    chat_only = [m for m in messages if m.get("role") != "system"]
    transcript = _format_transcript(chat_only)
    if not transcript.strip():
        return empty, "Conversation is empty; nothing to dream about."

    dream_prompt = [
        {"role": "system", "content": DREAM_SYSTEM_PROMPT},
        {"role": "user", "content": f"Conversation transcript:\n\n{transcript}"}
    ]

    try:
        model_cfg, provider_cfg = config_mgr.get_active_model_and_provider()
    except Exception as e:
        return empty, f"Configuration error: {e}"

    provider = get_provider(model_cfg, provider_cfg, config_mgr)

    raw_text = ""
    try:
        async for chunk in provider.stream_chat(dream_prompt):
            if chunk["type"] == "content":
                raw_text += chunk["value"]
    except Exception as e:
        return empty, f"Dream analysis failed: {e}"

    data = _safe_parse_json(raw_text)
    if not data:
        return empty, "Could not parse a structured extraction from the model's response."

    notes = data.get("notes") or []
    memory_items = data.get("memory") or []
    skills = data.get("skills") or []

    clean_notes = [n.strip() for n in notes if isinstance(n, str) and n.strip()]

    clean_memory = [
        {"key": str(m.get("key", "")).strip(), "value": str(m.get("value", "")).strip()}
        for m in memory_items
        if isinstance(m, dict) and str(m.get("key", "")).strip() and str(m.get("value", "")).strip()
    ]

    clean_skills = [
        {
            "name": str(s.get("name", "")).strip(),
            "description": str(s.get("description", "")).strip(),
            "system_instruction": str(s.get("system_instruction", "")).strip()
        }
        for s in skills
        if isinstance(s, dict) and str(s.get("name", "")).strip() and str(s.get("system_instruction", "")).strip()
    ]

    return {"notes": clean_notes, "memory": clean_memory, "skills": clean_skills}, ""
