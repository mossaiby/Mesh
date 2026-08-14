from compaction import estimate_tokens, find_safe_split_index


def test_estimate_tokens():
    messages = [
        {"role": "user", "content": "12345678"},  # 8 chars
        {"role": "assistant", "content": "12345678"}  # 8 chars
    ]
    tokens = estimate_tokens(messages)
    assert tokens >= 4


def test_find_safe_split_index():
    chat_msgs = [
        {"role": "user", "content": "msg 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "msg 2"},
        {"role": "assistant", "content": "reply 2"},
        {"role": "user", "content": "msg 3"},
        {"role": "assistant", "content": "reply 3"},
    ]
    # min_keep = 2 -> keep msg 3 and reply 3, split at msg 3 (index 4)
    split_idx = find_safe_split_index(chat_msgs, min_keep=2)
    assert split_idx == 4
    assert chat_msgs[split_idx]["role"] == "user"
