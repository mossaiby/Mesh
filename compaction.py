from typing import List, Dict, Any, Tuple, Optional
from config import ConfigManager
from providers import get_provider


CHARS_PER_TOKEN = 4


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
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
    keep_count = min_keep if min_keep is not None else config_mgr.config.compaction_settings.minkeep

    system_msgs = [m for m in messages if m.get("role") == "system"]
    chat_msgs = [m for m in messages if m.get("role") != "system"]

    split_idx = find_safe_split_index(chat_msgs, min_keep=keep_count)

    if split_idx <= 0:
        return messages, False, "Not enough conversation history to compact (requires at least 4-6 messages)."

    to_summarize = chat_msgs[:split_idx]
    to_keep = chat_msgs[split_idx:]

    history_text_lines = []
    for msg in to_summarize:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls", None)
        
        line = f"Role: {role}"
        if content:
            line += f"\nContent: {content}"
        if tool_calls:
            line += f"\nTool Calls: {tool_calls}"
        history_text_lines.append(line)

    formatted_history = "\n\n---\n\n".join(history_text_lines)

    summarization_prompt = [
        {
            "role": "system",
            "content": (
                "You are a conversation summarizer. Provide a concise, structured summary "
                "of the provided conversation history. Highlight key user preferences, "
                "decisions made, technical facts established, and ongoing task status. "
                "Be brief and objective."
            )
        },
        {
            "role": "user",
            "content": f"Summarize the following conversation history:\n\n{formatted_history}"
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
        f"Compacted {compacted_count} old messages into 1 summary. "
        f"Total messages reduced from {orig_count} to {new_count}."
    )
    return new_messages, True, details


async def maybe_auto_compact(
    messages: List[Dict[str, Any]],
    config_mgr: ConfigManager,
    min_keep: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], bool, str]:
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

    estimated = estimate_tokens(messages)
    if estimated < trigger_at:
        return messages, False, ""

    keep_count = min_keep if min_keep is not None else cfg.compaction_settings.minkeep
    new_messages, success, details = await compact_messages(messages, config_mgr, min_keep=keep_count)
    if not success:
        return messages, False, ""

    usage_pct = int((estimated / context_window) * 100)
    details = f"Auto-compacted at ~{usage_pct}% of context window ({estimated}/{context_window} est. tokens). {details}"
    return new_messages, True, details
