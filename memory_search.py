import json
from typing import Dict, Any
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
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
    """Best-effort JSON parsing that tolerates stray markdown fences or
    leading/trailing prose some models add despite instructions not to."""
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
    """
    Searches a small key-value memory store for entries relevant to `query`
    using a dedicated out-of-band LLM call, rather than exact key matching or
    embedding/cosine-similarity search. This is intentionally the same
    "focused sub-agent call" pattern used by dream.py/compaction.py/
    delegation.py elsewhere in Mesh - it needs no embedding model or vector
    index, works uniformly across every configured backend, and tends to
    handle paraphrase/synonyms better than similarity search on short
    key-value strings.

    Returns a dict with:
        status: "empty" | "ok" | "error"
        matches: list of {key, value, why} (empty on "empty"/"error")
        answer: a short synthesized answer, or None
        error: present only when status == "error"
    """
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

    if verbose:
        console.print(f"[brand]🔍 Searching memory for:[/brand] {query}")

    raw_text = ""
    try:
        async for chunk in provider.stream_chat(messages):
            if chunk["type"] == "content":
                raw_text += chunk["value"]
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
