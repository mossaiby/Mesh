import json
from typing import Dict, Any
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
from render.stream_renderer import StreamRenderer
from theme import console


MEMORY_SEARCH_SYSTEM_PROMPT = (
    "You are Mesh's memory search assistant. You will be given the full contents of a "
    "small persistent key-value memory store and a natural-language query. Find entries "
    "relevant to the query even when the wording differs from the query - synonyms, "
    "paraphrases, related concepts, or values that answer the question even if the key "
    "name doesn't share any words with it. Do not require exact keyword overlap.\n\n"
    "Respond with ONLY a single JSON object, no prose, no markdown code fences, in "
    "exactly this shape:\n"
    '{"matches": [{"key": "...", "value": "...", "why": "brief reason this is relevant"}], '
    '"answer": "a short direct answer to the query synthesized from the matches, or null '
    'if nothing in memory is relevant"}\n\n'
    "Order matches by relevance, most relevant first. If nothing in the memory store is "
    "relevant to the query, return an empty matches list and answer: null. Do not "
    "fabricate memory entries that aren't present in the store you were given."
)


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


async def semantic_memory_search(
    query: str,
    memory: Dict[str, Any],
    config_mgr: ConfigManager,
    verbose: bool = False
) -> Dict[str, Any]:
    if not memory:
        return {"status": "empty", "matches": [], "answer": None}

    if not query or not query.strip():
        return {"status": "error", "matches": [], "answer": None, "error": "Query is required."}

    messages = [
        {"role": "system", "content": MEMORY_SEARCH_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Memory store (JSON):\n{json.dumps(memory, indent=2)}\n\nQuery: {query}"
        }
    ]

    try:
        model_cfg, provider_cfg = config_mgr.get_active_model_and_provider()
    except Exception as e:
        return {"status": "error", "matches": [], "answer": None, "error": f"Configuration error: {e}"}

    provider = OpenAIProvider(model_cfg, provider_cfg)
    renderer = StreamRenderer()

    if verbose:
        console.print(f"[brand]🔍 Searching memory for:[/brand] {query}")

    try:
        raw_text, _ = await renderer.render_stream(provider.stream_chat(messages))
    except Exception as e:
        return {"status": "error", "matches": [], "answer": None, "error": f"Memory search failed: {e}"}

    data = _safe_parse_json(raw_text)
    if not data:
        return {
            "status": "error",
            "matches": [],
            "answer": None,
            "error": "Could not parse a structured result from the model's response."
        }

    raw_matches = data.get("matches") or []
    clean_matches = [
        {
            "key": str(m.get("key", "")).strip(),
            "value": str(m.get("value", "")).strip(),
            "why": str(m.get("why", "")).strip()
        }
        for m in raw_matches
        if isinstance(m, dict) and str(m.get("key", "")).strip() in memory
    ]

    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        answer = None

    if verbose:
        console.print(f"[brand]✅ Found {len(clean_matches)} relevant memory entr{'y' if len(clean_matches) == 1 else 'ies'}.[/brand]")

    return {"status": "ok", "matches": clean_matches, "answer": answer}