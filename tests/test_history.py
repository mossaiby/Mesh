import os
from terminal_ui import MeshPromptSession, HISTORY_FILE


def test_mesh_prompt_session_history_lifecycle(mock_engine, temp_workspace):
    session = MeshPromptSession(mock_engine)

    # 1. Verify FileHistory format writing
    test_content = (
        "# 2026-08-15 14:20:31.582095\n"
        "+What is the capital of France?\n"
        "# 2026-08-15 14:20:37.123456\n"
        "+/models discover openrouter\n"
        "# 2026-08-15 14:20:40.000000\n"
        "+/status\n"
        "# 2026-08-15 14:20:45.000000\n"
        "+/compact\n"
    )
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write(test_content)

    # 2. Test reading recent entries (returns list of (timestamp, command) tuples)
    recent = session.get_history_entries(limit=3)
    assert len(recent) == 3
    assert recent[-1][1] == "/compact"
    assert recent[-1][0] == "2026-08-15 14:20:45"
    assert recent[-2][1] == "/status"

    # 3. Test clearing history
    success, msg = session.clear_history()
    assert success is True
    assert len(session.get_history_entries(limit=10)) == 0
