from typing import List, Dict, Any, Tuple
from config import ConfigManager
from providers.openai_provider import OpenAIProvider


def find_safe_split_index(chat_msgs: List[Dict[str, Any]], min_keep: int = 2) -> int:
    """
    Finds a safe index to split chat_msgs so that tool call/result
    pairs are not broken across the boundary.
    """
    if len(chat_msgs) <= min_keep:
        return 0

    split_idx = len(chat_msgs) - min_keep

    while split_idx > 0:
        msg = chat_msgs[split_idx]
        if msg.get("role") == "user":
            break
        if msg.get("role") == "assistant" and not msg.get("tool_calls"):
            break
        split_idx -= 1

    return split_idx


async def compact_messages(
    messages: List[Dict[str, Any]], 
    config_mgr: ConfigManager, 
    min_keep: int = 2
) -> Tuple[List[Dict[str, Any]], bool, str]:
    """
    Semantically compacts older conversation history into a structured summary.
    Returns (new_messages, success, message_details).
    """
    system_msgs = [m for m in messages if m.get("role") == "system"]
    chat_msgs = [m for m in messages if m.get("role") != "system"]

    split_idx = find_safe_split_index(chat_msgs, min_keep=min_keep)

    if split_idx <= 0:
        return messages, False, "Not enough conversation history to compact (requires at least 4-6 messages)."

    to_summarize = chat_msgs[:split_idx]
    to_keep = chat_msgs[split_idx:]

    # Format history to summarize
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
    provider = OpenAIProvider(model_cfg, provider_cfg)

    summary_text = ""
    async for chunk in provider.stream_chat(summarization_prompt):
        if chunk["type"] == "content":
            summary_text += chunk["value"]

    if not summary_text.strip():
        return messages, False, "Failed to generate summary from model."

    # Reconstruct compacted messages list
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