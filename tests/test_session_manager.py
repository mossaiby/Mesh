import os
import pytest
from session_manager import SessionManager, SESSIONS_DIR


def test_session_manager_save_load_and_removesuffix(mock_engine, temp_workspace):
    sm = SessionManager(mock_engine)

    # Test tricky session names ending in letters from '.json' to verify removesuffix fix
    session_names = ["session", "version", "production", "feature_json"]

    for s_name in session_names:
        success, msg = sm.save_session(s_name)
        assert success is True
        expected_file = os.path.join(SESSIONS_DIR, f"{s_name}.json")
        assert os.path.exists(expected_file)

        # Reconstruct engine from saved session
        engine_restored = mock_engine.__class__(temp_workspace)
        sm_restored = SessionManager(engine_restored)

        load_success, _ = sm_restored.load_session(s_name)
        assert load_success is True
        assert engine_restored.session_prompt_tokens == 1500
        assert engine_restored.session_completion_tokens == 600
        assert len(engine_restored.messages) == 2
        assert sm_restored.active_session_name == s_name


def test_session_manager_list_and_delete(mock_engine, temp_workspace):
    sm = SessionManager(mock_engine)
    sm.save_session("session_1")
    sm.save_session("session_2")

    sessions = sm.list_sessions()
    names = [s["name"] for s in sessions]
    assert "session_1" in names
    assert "session_2" in names

    # Delete session
    del_ok, _ = sm.delete_session("session_1")
    assert del_ok is True
    assert not os.path.exists(os.path.join(SESSIONS_DIR, "session_1.json"))
