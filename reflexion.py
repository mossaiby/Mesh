import json
import os
from typing import Dict, Any, List, Optional, Tuple
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
from theme import console

REFLEXION_FILE = "reflexion.json"

DISTILL_SYSTEM_PROMPT = (
    "You are Mesh's Reflexion Assistant. You will be given a log of tool failures, "
    "user corrections, and execution errors from recent CLI sessions.\n\n"
    "Distill these logs into durable, project-specific 'Lessons Learned' that an AI "
    "assistant should remember in future sessions (e.g. environment constraints, "
    "test flags, file locations, path quirks).\n\n"
    "Respond with ONLY a single JSON object in this exact shape:\n"
    '{"lessons": ["Lesson 1...", "Lesson 2..."]}\n\n'
    "No prose, no markdown code fences."
)


def _load_reflexion_data() -> Dict[str, Any]:
    if not os.path.exists(REFLEXION_FILE):
        return {"events": [], "lessons": []}
    try:
        with open(REFLEXION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"events": [], "lessons": []}


def _save_reflexion_data(data: Dict[str, Any]) -> None:
    with open(REFLEXION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def record_reflexion_event(event_type: str, details: str) -> None:
    """Records a failure or correction event for future reflexion analysis."""
    data = _load_reflexion_data()
    data.setdefault("events", []).append({
        "type": event_type,
        "details": details
    })
    _save_reflexion_data(data)


def get_reflexion_instructions() -> str:
    """Returns Markdown section containing distilled lessons for system prompt injection."""
    data = _load_reflexion_data()
    lessons = data.get("lessons", [])
    if not lessons:
        return ""

    lines = ["## Project Lessons Learned (Reflexion Journal)"]
    for l in lessons:
        lines.append(f"- {l}")
    return "\n".join(lines)


def clear_reflexion() -> None:
    _save_reflexion_data({"events": [], "lessons": []})


async def distill_reflexion_lessons(config_mgr: ConfigManager) -> Tuple[bool, str]:
    """Runs an LLM pass over recorded error events to synthesize durable lessons."""
    data = _load_reflexion_data()
    events = data.get("events", [])
    if not events:
        return False, "No new events in reflexion log to distill."

    prompt_content = f"Recorded Event Log:\n{json.dumps(events, indent=2)}"
    messages = [
        {"role": "system", "content": DISTILL_SYSTEM_PROMPT},
        {"role": "user", "content": prompt_content}
    ]

    try:
        model_cfg, provider_cfg = config_mgr.get_active_model_and_provider()
        provider = OpenAIProvider(model_cfg, provider_cfg)

        raw_text = ""
        async for chunk in provider.stream_chat(messages):
            if chunk["type"] == "content":
                raw_text += chunk["value"]

        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
        new_lessons = parsed.get("lessons", [])

        if isinstance(new_lessons, list) and new_lessons:
            data["lessons"] = list(set(data.get("lessons", []) + [str(l).strip() for l in new_lessons if str(l).strip()]))
            data["events"] = []  # Clear events after successful distillation
            _save_reflexion_data(data)
            return True, f"Distilled {len(new_lessons)} new lesson(s) into reflexion journal."
        
        return False, "No durable lessons were identified from the event log."
    except Exception as e:
        return False, f"Reflexion distillation failed: {str(e)}"