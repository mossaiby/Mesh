"""
Tests for windows_sandbox_setup.py. Same honesty note as
tests/test_windows_sandbox.py: nothing here verifies the actual LSA/UAC
Win32 calls work on a real Windows machine - what's tested is the pure
logic (_check), the embedded elevated-helper script's own validity, and
run_elevated_setup()'s orchestration (does it stop at the right point on
each kind of failure, does it report a clear reason).
"""

import inspect
import subprocess
import sys
from unittest import mock

import pytest

import windows_sandbox_setup as wss


def test_is_available_reflects_platform():
    assert wss.is_available() == wss.IS_WINDOWS


def test_check_raises_on_falsy_and_passes_through_truthy():
    assert wss._check(True, "SomeCall") is True
    with pytest.raises(wss.SetupError, match="SomeCall failed"):
        wss._check(False, "SomeCall")


def test_manual_instructions_mention_the_actual_setting():
    text = wss.build_manual_instructions()
    assert "secpol.msc" in text
    assert "Adjust memory quotas for a process" in text
    assert "sign" in text.lower() or "restart" in text.lower()


def test_embedded_script_is_valid_python():
    """The embedded elevated-helper script is a raw string, so nothing
    checks its syntax just by importing/compiling this module - verify it
    separately so a future edit that breaks it is caught here rather than
    inside a live UAC-elevated process on someone's machine."""
    compile(wss._ELEVATED_GRANT_SCRIPT, "<embedded_grant_script>", "exec")


def test_embedded_script_takes_sid_and_result_path_plus_variable_privileges():
    assert 'sid_string, result_path = sys.argv[1], sys.argv[2]' in wss._ELEVATED_GRANT_SCRIPT
    assert 'privilege_names = sys.argv[3:]' in wss._ELEVATED_GRANT_SCRIPT


def test_required_privileges_includes_both_known_needs():
    """Regression test for the actual second wall hit on a real machine:
    granting only SeIncreaseQuotaPrivilege still left CreateProcessAsUserW
    failing with ERROR_PRIVILEGE_NOT_HELD - the documented restricted-token
    exemption for SE_ASSIGNPRIMARYTOKEN_NAME didn't hold up in practice, so
    both privileges are now granted unconditionally rather than relying on
    that exemption."""
    assert "SeIncreaseQuotaPrivilege" in wss.REQUIRED_PRIVILEGES
    assert "SeAssignPrimaryTokenPrivilege" in wss.REQUIRED_PRIVILEGES


def test_success_path_source_mentions_the_relogin_caveat():
    """The deeper stages of run_elevated_setup() (actually invoking
    ShellExecuteExW/CreateProcess-adjacent Win32 structures) can't be
    meaningfully mocked - ctypes.byref()/ctypes.sizeof() reject anything
    that isn't a genuine ctypes type, so there's no way to substitute a
    fake SHELLEXECUTEINFOW the way earlier tests substitute plain
    functions. This checks the one property that matters most there by
    inspecting the actual source instead: the success-path message must
    mention needing to sign out/restart. A success message that omitted
    this would be actively misleading, since the privilege genuinely
    doesn't take effect until then - see the module docstring."""
    source = inspect.getsource(wss.run_elevated_setup)
    success_return = source[source.index("if exit_code.value == 0"):]
    assert "sign" in success_return.lower() or "restart" in success_return.lower()


@pytest.mark.asyncio
async def test_run_elevated_setup_returns_error_when_not_windows():
    result = await wss.run_elevated_setup()
    assert result[0] is False


@pytest.mark.asyncio
async def test_run_elevated_setup_stops_if_sid_lookup_fails():
    """If we can't even determine our own account's SID, nothing about UAC
    or LSA should be attempted at all."""
    with mock.patch.object(wss, "IS_WINDOWS", True), \
         mock.patch.object(wss, "get_current_user_sid_string", side_effect=wss.SetupError("boom")), \
         mock.patch.object(wss, "shell32", mock.Mock(), create=True):
        success, message = await wss.run_elevated_setup()
        assert success is False
        assert "SID" in message
        wss.shell32.ShellExecuteExW.assert_not_called()


def test_has_required_privilege_opens_token_with_adjust_privileges_access():
    """Regression test for a real bug: AdjustTokenPrivileges requires
    TOKEN_ADJUST_PRIVILEGES access on the token handle, not just
    TOKEN_QUERY - opening with TOKEN_QUERY alone made every call to this
    function fail with ERROR_ACCESS_DENIED (5), which looked identical to
    (and was initially mistaken for) the account genuinely lacking the
    privilege. The access mask must include both bits."""
    fake_advapi32 = mock.Mock()
    fake_advapi32.OpenProcessToken.return_value = True

    with mock.patch.object(wss, "advapi32", fake_advapi32, create=True), \
         mock.patch.object(wss, "kernel32", mock.Mock(), create=True), \
         mock.patch.object(wss, "TOKEN_QUERY", 0x8, create=True), \
         mock.patch.object(wss, "TOKEN_ADJUST_PRIVILEGES", 0x20, create=True), \
         mock.patch.dict("sys.modules", {"windows_sandbox": mock.Mock(_enable_privilege=mock.Mock(return_value=True))}):
        wss.has_required_privilege()

    requested_access = fake_advapi32.OpenProcessToken.call_args.args[1]
    assert requested_access & 0x8   # TOKEN_QUERY
    assert requested_access & 0x20  # TOKEN_ADJUST_PRIVILEGES
