import json
import os

import pytest

from hooks import HookManager


def _write_hooks(tmp_path, data):
    path = tmp_path / "hooks.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


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
        "session_start": [{"command": "echo hi"}],
    })
    hm = HookManager(enabled=True, hooks_path=path)
    assert hm.describe_lifecycle_hooks() == {"session_start": 1}


@pytest.mark.asyncio
async def test_run_event_noop_when_disabled(tmp_path):
    path = _write_hooks(tmp_path, {"session_start": [{"command": "echo should-not-run"}]})
    hm = HookManager(enabled=False, hooks_path=path)
    result = await hm.run_event("session_start", {})
    assert result == {"block": False, "reason": None, "feedback": [], "modified_prompt": None}


@pytest.mark.asyncio
async def test_run_event_noop_when_no_hooks_for_event(tmp_path):
    path = _write_hooks(tmp_path, {"session_start": [{"command": "echo hi"}]})
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("session_end", {})
    assert result["feedback"] == []


@pytest.mark.asyncio
async def test_matcher_regex_filters_by_tool_name(tmp_path):
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [
            {"matcher": "shell|job", "command": "echo '{\"feedback\": \"shell-or-job matched\"}'"},
            {"matcher": "calculator", "command": "echo '{\"feedback\": \"calculator matched\"}'"},
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
        "pre_tool_use": [{"command": "echo '{\"feedback\": \"always runs\"}'"}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("pre_tool_use", {"tool_name": "anything_at_all", "arguments": {}})
    assert result["feedback"] == ["always runs"]


@pytest.mark.asyncio
async def test_exit_code_2_blocks_pre_tool_use(tmp_path):
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [{"command": "echo 'not allowed' >&2; exit 2"}]
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
        "session_start": [{"command": "exit 2"}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("session_start", {})
    assert result["block"] is False


@pytest.mark.asyncio
async def test_json_block_field_also_blocks(tmp_path):
    """The exit-code-2 convention and a plain JSON {"block": true} response
    are both supported ways to block a pre_tool_use call."""
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [{"command": "echo '{\"block\": true, \"reason\": \"nope\"}'"}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("pre_tool_use", {"tool_name": "shell", "arguments": {}})
    assert result["block"] is True
    assert result["reason"] == "nope"


@pytest.mark.asyncio
async def test_non_json_stdout_becomes_feedback(tmp_path):
    path = _write_hooks(tmp_path, {
        "session_start": [{"command": "echo plain text output"}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("session_start", {})
    assert result["feedback"] == ["plain text output"]


@pytest.mark.asyncio
async def test_modified_prompt_only_applies_to_user_prompt_submit(tmp_path):
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [{"command": "echo '{\"modified_prompt\": \"should be ignored here\"}'"}]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("pre_tool_use", {"tool_name": "shell", "arguments": {}})
    assert result["modified_prompt"] is None


@pytest.mark.asyncio
async def test_hook_receives_the_actual_context_via_stdin(tmp_path):
    path = _write_hooks(tmp_path, {
        "pre_tool_use": [{
            "command": (
                "python3 -c \"import sys, json; "
                "d = json.load(sys.stdin); "
                "print(json.dumps({'feedback': d['tool_name'] + ':' + str(d['arguments'])}))\""
            )
        }]
    })
    hm = HookManager(enabled=True, hooks_path=path)
    result = await hm.run_event("pre_tool_use", {"tool_name": "shell", "arguments": {"command": "ls"}})
    assert result["feedback"] == ["shell:{'command': 'ls'}"]


@pytest.mark.asyncio
async def test_hook_timeout_does_not_hang_or_raise(tmp_path):
    path = _write_hooks(tmp_path, {"session_start": [{"command": "sleep 5"}]})
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
