import os
import pytest
from tools.native_tools import (
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    HashEditTool,
    GlobTool,
    GrepTool,
    ShellTool,
    compute_line_hash,
    find_best_fuzzy_match
)
from tools.permissions import PermissionManager
from file_history import file_history_tracker


def test_compute_line_hash():
    # Stable 4-character hex hash verification
    h1 = compute_line_hash("def calculate_sum(a, b):")
    h2 = compute_line_hash("def calculate_sum(a, b):\n")
    h3 = compute_line_hash("def calculate_sum(a, b):\r\n")
    assert len(h1) == 4
    assert h1 == h2 == h3
    assert h1 != compute_line_hash("def calculate_diff(a, b):")


def test_find_best_fuzzy_match():
    content_lines = [
        "def main():\n",
        "    print('line 1')\n",
        "    print('line 2')\n",
        "    return True\n"
    ]
    # Match with slight indentation whitespace difference
    query_str = "  print('line 1')\n  print('line 2')\n"
    found, start, end, ratio = find_best_fuzzy_match(content_lines, query_str, threshold=0.80)
    assert found is True
    assert start == 1
    assert end == 3
    assert ratio >= 0.80


@pytest.mark.asyncio
async def test_read_and_write_file_tools(temp_workspace):
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    reader = ReadFileTool(pm)

    test_file = os.path.join(temp_workspace, "src", "app.py")
    test_content = "import sys\n\ndef main():\n    print('Hello World')\n"

    # Write file (creates nested directories)
    res_w = await writer.execute(path=test_file, content=test_content)
    assert res_w["status"] == "success"
    assert os.path.exists(test_file)

    # Read full file
    res_r = await reader.execute(path=test_file)
    assert res_r["content"] == test_content
    assert res_r["total_lines"] == 4

    # Read with line ranges and line hashes
    res_hashes = await reader.execute(path=test_file, start_line=2, end_line=3, show_hashes=True)
    assert "L2|" in res_hashes["content"]
    assert "L3|" in res_hashes["content"]
    assert "def main():" in res_hashes["content"]


@pytest.mark.asyncio
async def test_edit_file_exact_and_fuzzy(temp_workspace):
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    editor = EditFileTool(pm)

    test_file = os.path.join(temp_workspace, "sample.txt")
    await writer.execute(path=test_file, content="apple\nbanana\ncherry\n")

    # Exact match replace
    res1 = await editor.execute(path=test_file, old_str="banana", new_str="blueberry")
    assert res1["status"] == "success"
    with open(test_file, "r") as f:
        assert f.read() == "apple\nblueberry\ncherry\n"

    # Fuzzy match replace
    res2 = await editor.execute(
        path=test_file,
        old_str="apple \nblueberry \n",
        new_str="apricot\nblackberry\n",
        fuzzy_threshold=0.80
    )
    assert res2["status"] == "success"
    assert "fuzzy" in res2["message"]


@pytest.mark.asyncio
async def test_hash_edit_tool_line_splice_and_drift_detection(temp_workspace):
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    reader = ReadFileTool(pm)
    hasher = HashEditTool(pm)

    test_file = os.path.join(temp_workspace, "code.py")
    initial_content = "line 1\nline 2\nline 3\n"
    await writer.execute(path=test_file, content=initial_content)

    # Get hashes
    h1 = compute_line_hash("line 1")
    h2 = compute_line_hash("line 2")

    # Replace line 2 with a string without trailing newline (must NOT corrupt line 3)
    res_edit = await hasher.execute(
        path=test_file,
        start_line=2,
        start_hash=h2,
        end_line=2,
        end_hash=h2,
        new_str="new line 2"  # Note: no trailing \n
    )
    assert res_edit["status"] == "success"

    with open(test_file, "r") as f:
        updated = f.read()
    assert updated == "line 1\nnew line 2\nline 3\n"

    # Attempt hash edit with stale/wrong hash (Drift protection)
    res_stale = await hasher.execute(
        path=test_file,
        start_line=1,
        start_hash="ffff",  # Invalid hash
        end_line=1,
        end_hash="ffff",
        new_str="new line 1"
    )
    assert "error" in res_stale
    assert "Hash verification failed" in res_stale["error"]


@pytest.mark.asyncio
async def test_glob_tool(temp_workspace):
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    glob_tool = GlobTool(pm)

    await writer.execute(path=os.path.join(temp_workspace, "a.py"), content="")
    await writer.execute(path=os.path.join(temp_workspace, "b.py"), content="")
    await writer.execute(path=os.path.join(temp_workspace, "sub", "c.py"), content="")

    res = await glob_tool.execute(pattern="**/*.py", root_dir=temp_workspace)
    assert res["count"] == 3


@pytest.mark.asyncio
async def test_grep_tool(temp_workspace):
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    grep_tool = GrepTool(pm)

    await writer.execute(
        path=os.path.join(temp_workspace, "src", "service.py"),
        content="def start_server():\n    print('Starting HTTP server')\n    return True\n"
    )
    await writer.execute(
        path=os.path.join(temp_workspace, "docs", "README.md"),
        content="# API Documentation\nUse start_server to launch.\n"
    )

    # 1. Recursive directory search
    res1 = await grep_tool.execute(pattern=r"start_server", path=temp_workspace)
    assert res1["count"] == 2
    assert not res1["truncated"]

    # 2. File pattern filtering
    res2 = await grep_tool.execute(pattern=r"start_server", path=temp_workspace, file_pattern="*.py")
    assert res2["count"] == 1
    assert res2["matches"][0]["path"].endswith("service.py")
    assert res2["matches"][0]["line"] == 1

    # 3. Context lines
    res3 = await grep_tool.execute(pattern=r"Starting HTTP", path=temp_workspace, context_lines=1)
    assert res3["count"] == 1
    assert len(res3["matches"][0]["context"]) == 3
    assert "L2:     print('Starting HTTP server')" in res3["matches"][0]["context"]

    # 4. Case-insensitive search
    res4 = await grep_tool.execute(pattern=r"starting http", path=temp_workspace, case_sensitive=False)
    assert res4["count"] == 1

    # 5. Invalid regex pattern handling
    res5 = await grep_tool.execute(pattern=r"[invalid-regex", path=temp_workspace)
    assert "error" in res5


@pytest.mark.asyncio
async def test_shell_tool_execution(temp_workspace):
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    shell_tool = ShellTool(pm)
    cmd = "python -c \"print('Hello from shell')\""
    res = await shell_tool.execute(command=cmd)
    assert res["exit_code"] == 0
    assert "Hello from shell" in res["stdout"]
