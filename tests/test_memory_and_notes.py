import os
import pytest
from tools.memory_tool import MemoryTool, _load_memory, _save_memory, MEMORY_FILE
from tools.note_tool import NoteTool, _read_notes, _write_notes, NOTES_FILE


@pytest.mark.asyncio
async def test_memory_tool_crud(temp_workspace):
    mem_tool = MemoryTool()

    # Save
    r_save = await mem_tool.execute(action="save", key="favorite_db", value="PostgreSQL")
    assert r_save["status"] == "success"
    assert os.path.exists(MEMORY_FILE)

    # Get
    r_get = await mem_tool.execute(action="get", key="favorite_db")
    assert r_get["value"] == "PostgreSQL"

    # List
    r_list = await mem_tool.execute(action="list")
    assert "favorite_db" in r_list["memories"]

    # Delete
    r_del = await mem_tool.execute(action="delete", key="favorite_db")
    assert r_del["status"] == "success"
    assert "favorite_db" not in _load_memory()


@pytest.mark.asyncio
async def test_note_tool_operations(temp_workspace):
    note_tool = NoteTool()

    # Write
    await note_tool.execute(action="write", content="# Project Log\n- Initialized repo")
    assert os.path.exists(NOTES_FILE)

    # Append
    await note_tool.execute(action="append", content="- Added auth middleware")
    read_res = await note_tool.execute(action="read")
    assert "Initialized repo" in read_res["notes"]
    assert "Added auth middleware" in read_res["notes"]

    # Clear
    await note_tool.execute(action="clear")
    assert _read_notes() == ""
