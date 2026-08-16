from typing import List, Dict, Any, Tuple, Optional
from config import ConfigManager
from providers import get_provider

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

CHARS_PER_TOKEN = 4
_ENCODER_CACHE: Dict[str, Any] = {}


def get_encoder(model_name: Optional[str] = None):
    """
    Retrieves and caches a tiktoken encoding for the target model name,
    falling back to 'cl100k_base' for OpenAI/Anthropic-style tokenization.
    """
    if not TIKTOKEN_AVAILABLE:
        return None

    cache_key = model_name or "cl100k_base"
    if cache_key in _ENCODER_CACHE:
        return _ENCODER_CACHE[cache_key]

    encoder = None
    if model_name:
        clean_model = model_name.split(":")[-1].split("/")[-1].lower()
        try:
            encoder = tiktoken.encoding_for_model(clean_model)
        except Exception:
            try:
                encoder = tiktoken.encoding_for_model(model_name)
            except Exception:
                pass

    if encoder is None:
        try:
            encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            encoder = None

    _ENCODER_CACHE[cache_key] = encoder
    return encoder


def count_text_tokens(text: str, model_name: Optional[str] = None) -> int:
    """
    Counts tokens for raw text string using tiktoken if available,
    falling back to character count heuristic (CHARS_PER_TOKEN = 4).
    """
    if not text:
        return 0

    encoder = get_encoder(model_name)
    if encoder is not None:
        try:
            return len(encoder.encode(text, disallowed_special=()))
        except Exception:
            pass

    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_tokens(messages: List[Dict[str, Any]], model_name: Optional[str] = None) -> int:
    """
    Estimates token count for message list using tiktoken BPE tokenizer when available,
    falling back to character count heuristic (CHARS_PER_TOKEN = 4).
    """
    if not messages:
        return 0

    encoder = get_encoder(model_name)
    if encoder is not None:
        try:
            total_tokens = 0
            for msg in messages:
                total_tokens += 3  # Per-message framing overhead (<|im_start|>role ... <|im_end|>)
                role = msg.get("role") or ""
                if role:
                    total_tokens += len(encoder.encode(role, disallowed_special=()))

                content = msg.get("content") or ""
                if content:
                    total_tokens += len(encoder.encode(content, disallowed_special=()))

                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    total_tokens += len(encoder.encode(str(tool_calls), disallowed_special=()))

            total_tokens += 3  # Priming tokens
            return max(1, total_tokens)
        except Exception:
            pass

    # Fallback to character-count heuristic
    total_chars = 0
    for msg in messages:
        content = msg.get("content") or ""
        if content:
            total_chars += len(content)

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            total_chars += len(str(tool_calls))

        total_chars += 4

    return max(1, total_chars // CHARS_PER_TOKEN)


def find_safe_split_index(chat_msgs: List[Dict[str, Any]], min_keep: int = 2) -> int:
    """
    Finds a safe index to split history so that preserved messages start on a clean
    user boundary and don't orphan assistant tool calls or tool response pairs.
    """
    if len(chat_msgs) <= min_keep:
        return 0

    split_idx = len(chat_msgs) - min_keep

    while split_idx > 0:
        if chat_msgs[split_idx].get("role") == "user":
            return split_idx
        split_idx -= 1

    return 0


async def compact_messages(
    messages: List[Dict[str, Any]], 
    config_mgr: ConfigManager, 
    min_keep: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], bool, str]:
    """
    Summarizes older conversation turns into a structured summary block.
    Uses in-context prefix matching to leverage the provider's prompt cache
    (saving up to 90% in token cost and latency during the summarization pass).
    """
    keep_count = min_keep if min_keep is not None else config_mgr.config.compaction_settings.minkeep

    system_msgs = [m for m in messages if m.get("role") == "system"]
    chat_msgs = [m for m in messages if m.get("role") != "system"]

    split_idx = find_safe_split_index(chat_msgs, min_keep=keep_count)

    if split_idx <= 0:
        return messages, False, "Not enough conversation history to compact (requires at least 4-6 messages)."

    to_summarize = chat_msgs[:split_idx]
    to_keep = chat_msgs[split_idx:]

    # Leverage provider prefix cache by keeping the exact message history up to split_idx
    # and appending the summarization request as the final user message.
    summarization_prompt = list(system_msgs) + list(to_summarize) + [
        {
            "role": "user",
            "content": (
                "[System Request: Summarize Conversation History]\n"
                "Please provide a concise, structured summary of the conversation above up to this point. "
                "Highlight key user preferences, decisions made, technical facts established, file edits, "
                "and ongoing task status. Be brief, objective, and dense with facts."
            )
        }
    ]

    model_cfg, provider_cfg = config_mgr.get_active_model_and_provider()
    provider = get_provider(model_cfg, provider_cfg, config_mgr)

    summary_text = ""
    async for chunk in provider.stream_chat(summarization_prompt):
        if chunk["type"] == "content":
            summary_text += chunk["value"]

    if not summary_text.strip():
        return messages, False, "Failed to generate summary from model."

    # Reassemble compacted history
    new_messages = []
    new_messages.extend(system_msgs)
    new_messages.append({
        "role": "user",
        "content": f"[Conversation History Summary]\n{summary_text.strip()}"
    })
    new_messages.append({
        "role": "assistant",
        "content": "Understood. I have preserved the summary of our previous discussion and am ready to continue."
    })
    new_messages.extend(to_keep)

    orig_count = len(messages)
    new_count = len(new_messages)
    compacted_count = len(to_summarize)

    details = (
        f"Compacted {compacted_count} old messages into 1 summary (cached in-context). "
        f"Total messages reduced from {orig_count} to {new_count}."
    )
    return new_messages, True, details


async def maybe_auto_compact(
    messages: List[Dict[str, Any]],
    config_mgr: ConfigManager,
    min_keep: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], bool, str]:
    """
    Checks if estimated token usage exceeds the configured auto-compact threshold ratio.
    If exceeded, triggers compaction automatically.
    """
    cfg = config_mgr.config
    if not cfg.auto_compact:
        return messages, False, ""

    try:
        model_cfg, _ = config_mgr.get_active_model_and_provider()
    except Exception:
        return messages, False, ""

    context_window = max(1, model_cfg.context_window)
    threshold = min(max(cfg.auto_compact_threshold, 0.0), 1.0)
    trigger_at = int(context_window * threshold)

    model_id = model_cfg.model_id if model_cfg else None
    estimated = estimate_tokens(messages, model_name=model_id)
    if estimated < trigger_at:
        return messages, False, ""

    keep_count = min_keep if min_keep is not None else cfg.compaction_settings.minkeep
    new_messages, success, details = await compact_messages(messages, config_mgr, min_keep=keep_count)
    if not success:
        return messages, False, ""

    usage_pct = int((estimated / context_window) * 100)
    details = f"Auto-compacted at ~{usage_pct}% of context window ({estimated}/{context_window} est. tokens). {details}"
    return new_messages, True, details
