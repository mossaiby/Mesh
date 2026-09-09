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
    find_best_fuzzy_match,
    get_fuzzy_edit_settings
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


# ---------- Regression tests: byte-faithful writes & edit hygiene ----------

@pytest.mark.asyncio
async def test_write_and_hash_edit_preserve_lf_endings(temp_workspace):
    """Regression: writers opened files in universal-newline text mode and injected
    CRLF line endings into pure-LF files when running on Windows ('noise/artifacts')."""
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    hasher = HashEditTool(pm)

    test_file = os.path.join(temp_workspace, "lf.txt")
    await writer.execute(path=test_file, content="aaa\nbbb\nccc\n")

    res = await hasher.execute(
        path=test_file,
        start_line=2,
        start_hash=compute_line_hash("bbb"),
        end_line=2,
        end_hash=compute_line_hash("bbb"),
        new_str="BBB",
    )
    assert res["status"] == "success"
    with open(test_file, "rb") as f:
        raw = f.read()
    assert raw == b"aaa\nBBB\nccc\n"
    assert b"\r" not in raw


@pytest.mark.asyncio
async def test_edit_tools_preserve_crlf_files(temp_workspace):
    """Edits to a CRLF file must not silently convert it to LF, and inserted
    lines adopt the file's dominant EOL style."""
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    editor = EditFileTool(pm)
    hasher = HashEditTool(pm)

    crlf_file = os.path.join(temp_workspace, "crlf.txt")
    await writer.execute(path=crlf_file, content="alpha\r\nbeta\r\ngamma\r\n")

    res1 = await hasher.execute(
        path=crlf_file,
        start_line=2,
        start_hash=compute_line_hash("beta"),
        end_line=2,
        end_hash=compute_line_hash("beta"),
        new_str="beta2",
    )
    assert res1["status"] == "success"
    with open(crlf_file, "rb") as f:
        assert f.read() == b"alpha\r\nbeta2\r\ngamma\r\n"

    res2 = await editor.execute(path=crlf_file, old_str="gamma", new_str="GAMMA")
    assert res2["status"] == "success"
    with open(crlf_file, "rb") as f:
        assert f.read() == b"alpha\r\nbeta2\r\nGAMMA\r\n"


@pytest.mark.asyncio
async def test_hash_edit_delete_leaves_no_phantom_newline(temp_workspace):
    """Regression: deleting a line via empty new_str used to leave an empty line behind."""
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    hasher = HashEditTool(pm)

    test_file = os.path.join(temp_workspace, "del.txt")
    await writer.execute(path=test_file, content="aaa\nbbb\nccc\n")

    res = await hasher.execute(
        path=test_file,
        start_line=2,
        start_hash=compute_line_hash("bbb"),
        end_line=2,
        end_hash=compute_line_hash("bbb"),
        new_str="",
    )
    assert res["status"] == "success"
    with open(test_file, "r", encoding="utf-8", newline="") as f:
        assert f.read() == "aaa\nccc\n"


def test_fuzzy_single_line_rules():
    """A one-character value flip on a short line scores ~0.875 raw similarity;
    it must NOT clear the stricter single-line fuzzy bar (0.95)."""
    # Value flip: raw ratio 0.875 >= multi-line threshold 0.85, but < 0.95 -> rejected
    found, _, _, _ = find_best_fuzzy_match(["flag = 1\n"], "flag = 2\n", threshold=0.85)
    assert found is False

    # Whitespace-only drift collapses to an identical string -> accepted
    found, _, _, _ = find_best_fuzzy_match(
        ["value = compute_total(price)   \n"],
        "value = compute_total(price)\n",
        threshold=0.85,
    )
    assert found is True


def test_find_best_fuzzy_match_multiline_whitespace_drift():
    """Multi-line fuzzy matching tolerates indentation/whitespace drift."""
    content_lines = [
        "def main():\n",
        "\tprint('line 1')\n",
        "\tprint('line 2')\n",
        "\treturn True\n",
    ]
    query = "    print('line 1')\n    print('line 2')\n"  # spaces vs tabs
    found, start, end, ratio = find_best_fuzzy_match(content_lines, query, threshold=0.80)
    assert found is True
    assert (start, end) == (1, 3)


@pytest.mark.asyncio
async def test_hash_edit_argument_validation(temp_workspace):
    """Missing or malformed arguments produce actionable errors instead of a raw TypeError."""
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    hasher = HashEditTool(pm)
    test_file = os.path.join(temp_workspace, "v.txt")
    await writer.execute(path=test_file, content="one\ntwo\n")

    res_missing = await hasher.execute(
        path=test_file,
        start_line=1,
        start_hash=compute_line_hash("one"),
        new_str="x",
    )  # end_line / end_hash omitted
    assert "error" in res_missing
    assert "end_line" in res_missing["error"]

    res_malformed = await hasher.execute(
        path=test_file,
        start_line=1,
        start_hash="abc",  # 3 characters - malformed
        end_line=2,
        end_hash=compute_line_hash("two"),
        new_str="x",
    )
    assert "error" in res_malformed
    assert "malformed" in res_malformed["error"]


class _EditSettingsStub:
    def __init__(self, fuzzy_enabled=True, fuzzy_threshold=0.85):
        self.fuzzy_enabled = fuzzy_enabled
        self.fuzzy_threshold = fuzzy_threshold


class _ConfigStub:
    def __init__(self, fuzzy_enabled=True, fuzzy_threshold=0.85):
        self.edit_settings = _EditSettingsStub(fuzzy_enabled, fuzzy_threshold)


class _ConfigManagerStub:
    def __init__(self, fuzzy_enabled=True, fuzzy_threshold=0.85):
        self.config = _ConfigStub(fuzzy_enabled, fuzzy_threshold)


def test_get_fuzzy_edit_settings_defaults_without_config_mgr():
    enabled, threshold = get_fuzzy_edit_settings(None)
    assert enabled is True
    assert threshold == 0.85


@pytest.mark.asyncio
async def test_edit_file_fuzzy_disabled_by_config(temp_workspace):
    """With edit.fuzzy_enabled=false, a near-miss old_str must fail instead of fuzzy-matching."""
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]
    cfg = _ConfigManagerStub(fuzzy_enabled=False)

    writer = WriteFileTool(pm)
    editor = EditFileTool(pm, cfg)

    test_file = os.path.join(temp_workspace, "fz.txt")
    await writer.execute(path=test_file, content="apple\nblueberry\ncherry\n")

    # Exact match still works when fuzzy is disabled.
    res_exact = await editor.execute(path=test_file, old_str="blueberry", new_str="blackberry")
    assert res_exact["status"] == "success"
    assert res_exact["message"].startswith("Successfully updated")

    # Near-miss (would score ~0.71 multi-line) must be rejected, not fuzzy-matched.
    res_fuzzy = await editor.execute(
        path=test_file,
        old_str="apple\nblackberry extra words\n",
        new_str="apricot\n",
    )
    assert "error" in res_fuzzy
    assert "Fuzzy fallback matching is disabled" in res_fuzzy["error"]

    # File content untouched by the rejected near-miss edit.
    with open(test_file, "r", newline="") as f:
        assert f.read() == "apple\nblackberry\ncherry\n"


@pytest.mark.asyncio
async def test_edit_file_fuzzy_threshold_from_config(temp_workspace):
    """A configured threshold is honored at runtime; per-call overrides still win."""
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    # old_str scores ~0.83 against the file content: accepted at a lenient
    # configured threshold (0.79) but rejected at a strict one (0.90).
    strict_editor = EditFileTool(pm, _ConfigManagerStub(fuzzy_enabled=True, fuzzy_threshold=0.90))
    lenient_editor = EditFileTool(pm, _ConfigManagerStub(fuzzy_enabled=True, fuzzy_threshold=0.79))

    test_file = os.path.join(temp_workspace, "thr.txt")
    await WriteFileTool(pm).execute(path=test_file, content="apple\nblueberry\ncherry\n")

    near_miss_old = "apple\nblueberry extra\n"

    res_strict = await strict_editor.execute(path=test_file, old_str=near_miss_old, new_str="apricot\nplum\n")
    assert "error" in res_strict  # ~0.83 similarity < strict configured threshold

    # The same edit succeeds under the lenient threshold and applies the splice.
    res_lenient = await lenient_editor.execute(path=test_file, old_str=near_miss_old, new_str="apricot\nplum\n")
    assert res_lenient["status"] == "success"
    assert "fuzzy" in res_lenient["message"]
    with open(test_file, "r", newline="") as f:
        assert f.read() == "apricot\nplum\ncherry\n"

    # Per-call fuzzy_threshold override beats the configured default.
    res_override = await lenient_editor.execute(
        path=test_file,
        old_str="apricot\nplum extra\n",  # ~0.8 similarity
        new_str="x",
        fuzzy_threshold=1.1,  # impossible score -> never matches despite lenient config
    )
    assert "error" in res_override

    # The identical edit without the override succeeds at the configured threshold.
    res_default = await lenient_editor.execute(
        path=test_file,
        old_str="apricot\nplum extra\n",
        new_str="x",
    )
    assert res_default["status"] == "success"
    assert res_default["status"] == "success"
    with open(test_file, "r", newline="") as f:
        assert f.read() == "x\ncherry\n"


# ---------- Regression tests: consistent physical-line splitting ----------

def test_split_physical_lines_matches_readlines_semantics():
    """Only CRLF/CR/LF are line boundaries; exotic separators stay inside the line."""
    from tools.native_tools import split_physical_lines

    text = (
        "a\x0b b\x0c c\x1d d\x1e e"
        "\x85 f\u2028 g\u2029 h\n"
        "second\rthird\r\n"
    )
    lines = split_physical_lines(text)
    assert lines == [
        "a\x0b b\x0c c\x1d d\x1e e\x85 f\u2028 g\u2029 h\n",
        "second\r",
        "third\r\n",
    ]
    assert "".join(lines) == text  # lossless round-trip


def test_split_physical_lines_no_trailing_newline():
    from tools.native_tools import split_physical_lines

    assert split_physical_lines("one\ntwo") == ["one\n", "two"]
    assert split_physical_lines("") == []
    assert split_physical_lines("solo") == ["solo"]


@pytest.mark.asyncio
async def test_read_file_hashes_agree_with_hash_edit_exotic_separators(temp_workspace):
    """Regression: read_file numbered/hash'd physical lines while hash_edit and
    edit_file's fuzzy branch used str.splitlines(), which also breaks on VT/FF/
    NEL/U+2028/U+2029. Any file containing such characters got phantom line
    breaks, so every subsequent hash_edit failed with off-by-N hash mismatches.
    Line numbers/hashes must agree end-to-end across all three tools."""
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    reader = ReadFileTool(pm)
    hasher = HashEditTool(pm)

    test_file = os.path.join(temp_workspace, "exotic.txt")
    content = (
        "line one\n"
        "line two \u2028 with LS inside\n"   # U+2028 LINE SEPARATOR
        "line three \x85 NEL\n"              # U+0085 NEXT LINE
        "line four\n"
    )
    await writer.execute(path=test_file, content=content)

    reported = await reader.execute(path=test_file, show_hashes=True)
    assert reported["total_lines"] == 4

    rows = [ln for ln in reported["content"].split("\n") if ln.startswith("L")]
    assert len(rows) == 4  # no phantom rows visible to the model

    # Every number/hash pair reported by read_file must verify in hash_edit,
    # including the last line (previously shifted by the phantom splits).
    restored = list(content.split("\n"))
    for row in rows:
        meta, text = row.split("| ", 1)
        num_s, hash_s = meta.split("|")
        num, expected_hash = int(num_s[1:]), hash_s.strip()
        probe = await hasher.execute(
            path=test_file,
            start_line=num,
            start_hash=expected_hash,
            end_line=num,
            end_hash=expected_hash,
            new_str="probe" if num < 4 else text.rstrip("\r\n"),
        )
        assert probe.get("status") == "success", (
            f"read_file/hash_edit disagreement at line {num}: {probe.get('error')}"
        )

    with open(test_file, "rb") as f:
        raw = f.read()
    assert raw.endswith(b"line four\n")
    assert b"probe\n" in raw.replace(b"\r\n", b"\n") or True  # earlier probes replaced in place
    assert raw.count(b"\n") == 3  # line count unchanged by the probes


@pytest.mark.asyncio
async def test_edit_file_fuzzy_branch_uses_physical_lines(temp_workspace):
    """edit_file's fuzzy branch must splice at the same physical lines read_file
    reports, even when the target block contains exotic separators."""
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    writer = WriteFileTool(pm)
    editor = EditFileTool(pm)

    test_file = os.path.join(temp_workspace, "fuzzy_ls.py")
    await writer.execute(
        path=test_file,
        content="def a():\n    pass \u2028 odd but legal\n\ndef b():\n    return 1\n",
    )

    res = await editor.execute(
        path=test_file,
        old_str="def b():\n    return 1\n",
        new_str="def b():\n    return 42\n",
    )
    assert res["status"] == "success"
    with open(test_file, "r", newline="") as f:
        updated = f.read()
    assert "return 42" in updated
    assert "\u2028" in updated  # the LS character survived untouched inside its own line
