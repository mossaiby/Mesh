from checkpoint import CheckpointManager


def test_checkpoint_manager_snapshot_and_restore(mock_engine):
    cm = CheckpointManager()

    # 1. Create snapshot
    cm.active_branch = "feature-auth"
    snap = cm.create_snapshot("checkpoint-1", mock_engine)
    assert snap["branch"] == "feature-auth"
    assert len(snap["messages"]) == 2

    # 2. Mutate active engine state
    mock_engine.messages.append({"role": "user", "content": "Mutated message"})
    mock_engine.current_mode = "plan"

    # 3. Restore snapshot
    restore_ok = cm.restore_snapshot("checkpoint-1", mock_engine)
    assert restore_ok is True
    assert len(mock_engine.messages) == 2
    assert mock_engine.current_mode == "build"
    assert cm.active_branch == "feature-auth"
