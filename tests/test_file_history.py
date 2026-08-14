import os
from file_history import FileHistoryTracker


def test_file_history_record_and_undo(temp_workspace):
    tracker = FileHistoryTracker()
    test_file = os.path.join(temp_workspace, "doc.txt")

    # 1. First edit on non-existent file (creation)
    diff1 = tracker.record_edit(test_file, "Line 1\n", action="write_file")
    with open(test_file, "w") as f:
        f.write("Line 1\n")
    assert "+Line 1" in diff1

    # 2. Second edit (modification)
    diff2 = tracker.record_edit(test_file, "Line 1\nLine 2\n", action="edit_file")
    with open(test_file, "w") as f:
        f.write("Line 1\nLine 2\n")
    assert "+Line 2" in diff2

    # 3. Undo second edit (restores first version)
    ok_undo1, _ = tracker.undo_last()
    assert ok_undo1 is True
    with open(test_file, "r") as f:
        assert f.read() == "Line 1\n"

    # 4. Undo first edit (deletes newly created file)
    ok_undo2, _ = tracker.undo_last()
    assert ok_undo2 is True
    assert not os.path.exists(test_file)
