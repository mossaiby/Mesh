"""
Tests for the general lifecycle hook system in hooks.py.

Every hook command here is built via _py_command()/_json_command(), not
raw shell syntax (`echo '...'`, `>&2`, `;` as a separator, `sleep`) -
found the hard way that asyncio.create_subprocess_shell() uses the
PLATFORM's native shell (cmd.exe on Windows, /bin/sh on POSIX), and these
have fundamentally different quoting rules: single quotes are just
literal characters to cmd.exe (not string delimiters), ';' isn't a
command separator, '>&2' redirection syntax isn't interchangeable, and
'sleep' doesn't exist at all. A first version of this file used raw sh
syntax throughout and passed in the environment it was written in, then
failed four tests outright the first time it actually ran on Windows -
not because the hook mechanism was broken, but because the *test's own
hook commands* were POSIX-only. Base64-encoding any payload a hook needs
to print sidesteps the whole problem: the encoded string contains no
shell metacharacters at all, so it's safe to embed in a double-quoted
`-c "..."` argument identically on any platform.
"""

import base64
import json
import sys

import pytest

from hooks import HookManager


def _write_hooks(tmp_path, data):
    path = tmp_path / "hooks.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _py_command(code: str) -> str:
    """Runs `code` with the same interpreter running the tests, quoted so
    it's safe under both cmd.exe and /bin/sh."""
    return f'"{sys.executable}" -c "{code}"'


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _print_json_command(data: dict) -> str:
    """A hook that prints `data` as JSON on stdout - the base64 round-trip
    means the actual command string never contains a quote character."""
    payload = _b64(json.dumps(data))
    return _py_command(f"import base64; print(base64.b64decode('{payload}').decode())")


def _print_text_command(text: str) -> str:
    payload = _b64(text)
    return _py_command(f"import base64; print(base64.b64decode('{payload}').decode())")


def _stderr_and_exit_command(message: str, exit_code: int) -> str:
    payload = _b64(message)
    return _py_command(
        f"import sys, base64; sys.stderr.write(base64.b64decode('{payload}').decode()); sys.exit({exit_code})"
    )


def _exit_command(exit_code: int) -> str:
    return _py_command(f"import sys; sys.exit({exit_code})")


def _sleep_command(seconds: float) -> str:
    return _py_command(f"import time; time.sleep({seconds})")


def test_reload_with_no_file_present(tmp_path):
    hm = HookManager(enabled=True, hooks_path=str(tmp_path / "does_not_exist.json"))
    assert hm.describe_lifecycle_hooks() == {}
    assert hm.reload_lifecycle_hooks() is None


def test_reload_with_malformed_json(tmp_path):
    path = tmp_path / "hooks.json"
    path.write_text("not valid json {{{", encoding="utf-8")
    hm = HookManager(enabled=True, hooks_path=str(path))
    assert hm.describe_lifecycle_hooks() == {}
    # constructing already tried to load once; reload should report the error
    error = hm.reload_lifecycle_hooks()
    assert error is not None
    assert "Failed to load" in error


def test_non_list_top_level_keys_are_ignored(tmp_path):
    """A "$comment"-style documentation key at the top level (as used in
    hooks.json.example) must not leak into describe_lifecycle_hooks() as a
    fake event - only keys whose value is a list of dicts are real events."""
    path = _write_hooks(tmp_path, {
        "$comment": "this is documentation, not an event",
        "session_start": [{"command": _print_text_command("hi")}],
    })
    hm = HookManager(enabled=True, hooks_path=path)
    assert hm.describe_lifecycle_hooks() == {"session_start": 1}


@pytest.mark.asyncio
async def test_run_event_noop_when_disabled(tmp_path):
    path = _write_hooks(tmp_path, {"session_start": [{"command": _print_text_command("should-not-run")}]})
    hm = HookManager(enabled=False, hooks_path=path)
    result = await hm.run_event("session_start", {})
    assert result == {"block": False, "reason": None, "feedback": [], "modified_prompt": None}


@pytest.mark.asyncio
async def test_run_event_noop_when_no_hooks_for_event(tmp_path):
    path = _write_hooks(tmp_path, {"session_start": [{"command": _print_text_command("hi")}]})
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("session_end", {})
    assert result["feedback"] == []


@pytest.mark.asyncio
async def test_matcher_regex_filters_by_tool_name(tmp_path):
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [
            {"matcher": "shell|job", "command": _print_json_command({"feedback": "shell-or-job matched"})},
            {"matcher": "calculator", "command": _print_json_command({"feedback": "calculator matched"})},
        ]
    })
    hm = HookManager(enabled=True, hooks_path=path)

    result = await hm.run_event("pre_tool_use", {"tool_name": "shell", "arguments": {}})
    assert result["feedback"] == ["shell-or-job matched"]

    result = await hm.run_event("pre_tool_use", {"tool_name": "calculator", "arguments": {}})
    assert result["feedback"] == ["calculator matched"]

    result = await hm.run_event("pre_tool_use", {"tool_name": "write_file", "arguments": {}})
    assert result["feedback"] == []


@pytest.mark.asyncio
async def test_omitted_matcher_matches_every_tool(tmp_path):
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [{"command": _print_json_command({"feedback": "always runs"})}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("pre_tool_use", {"tool_name": "anything_at_all", "arguments": {}})
    assert result["feedback"] == ["always runs"]


@pytest.mark.asyncio
async def test_exit_code_2_blocks_pre_tool_use(tmp_path):
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [{"command": _stderr_and_exit_command("not allowed", 2)}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("pre_tool_use", {"tool_name": "shell", "arguments": {}})
    assert result["block"] is True
    assert result["reason"] == "not allowed"


@pytest.mark.asyncio
async def test_exit_code_2_is_ignored_for_non_blocking_events(tmp_path):
    """Only pre_tool_use has anything meaningful to block - exit code 2 on
    any other event must not be treated as a block."""
    path = _write_hooks(tmp_path, {
        "session_start": [{"command": _exit_command(2)}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("session_start", {})
    assert result["block"] is False


@pytest.mark.asyncio
async def test_json_block_field_also_blocks(tmp_path):
    """The exit-code-2 convention and a plain JSON {"block": true} response
    are both supported ways to block a pre_tool_use call."""
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [{"command": _print_json_command({"block": True, "reason": "nope"})}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("pre_tool_use", {"tool_name": "shell", "arguments": {}})
    assert result["block"] is True
    assert result["reason"] == "nope"


@pytest.mark.asyncio
async def test_non_json_stdout_becomes_feedback(tmp_path):
    path = _write_hooks(tmp_path, {
        "session_start": [{"command": _print_text_command("plain text output")}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("session_start", {})
    assert result["feedback"] == ["plain text output"]


@pytest.mark.asyncio
async def test_modified_prompt_only_applies_to_user_prompt_submit(tmp_path):
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [{"command": _print_json_command({"modified_prompt": "should be ignored here"})}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("pre_tool_use", {"tool_name": "shell", "arguments": {}})
    assert result["modified_prompt"] is None


@pytest.mark.asyncio
async def test_hook_receives_the_actual_context_via_stdin(tmp_path):
    code = (
        "import sys, json; "
        "d = json.load(sys.stdin); "
        "print(json.dumps({'feedback': d['tool_name'] + ':' + str(d['arguments'])}))"
    )
    path = _write_hooks(tmp_path, {"pre_tool_use": [{"command": _py_command(code)}]})
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("pre_tool_use", {"tool_name": "shell", "arguments": {"command": "ls"}})
    assert result["feedback"] == ["shell:{'command': 'ls'}"]


@pytest.mark.asyncio
async def test_hook_timeout_does_not_hang_or_raise(tmp_path):
    path = _write_hooks(tmp_path, {"session_start": [{"command": _sleep_command(5)}]})
    hm = HookManager(enabled=True, hooks_path=path)

    class _FakeTimeouts:
        hook = 0.3

    class _FakeConfig:
        timeouts = _FakeTimeouts()

    class _FakeConfigMgr:
        config = _FakeConfig()

    hm._config_mgr = _FakeConfigMgr()
    result = await hm.run_event("session_start", {})
    assert result["feedback"] == []  # timed out, no feedback, but did not hang/raise


@pytest.mark.asyncio
async def test_hook_that_fails_to_launch_does_not_raise(tmp_path):
    path = _write_hooks(tmp_path, {"session_start": [{"command": "this_binary_does_not_exist_xyz"}]})
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("session_start", {})
    assert result["block"] is False


def test_linter_detection_still_works_for_python(tmp_path):
    """Regression check that the original, narrow post-edit linter
    mechanism (unrelated to the new lifecycle hooks) wasn't disturbed."""
    hm = HookManager(enabled=True, hooks_path=str(tmp_path / "unused.json"))
    # Whatever linter is or isn't installed in this environment, this must
    # not raise, and must return either a command list or None.
    result = hm._detect_linter_cmd("some_file.py")
    assert result is None or isinstance(result, list)
