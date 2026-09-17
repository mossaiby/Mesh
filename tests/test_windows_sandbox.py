"""
Tests for windows_sandbox.py.

Important honesty note, matching the module's own docstring: nothing here
verifies that the actual Win32 API calls (CreateRestrictedToken,
CreateProcessAsUserW, the TOKEN_GROUPS struct layout, etc.) work correctly
on a real Windows machine - that's fundamentally not something that can be
checked from a non-Windows environment, and pretending otherwise with deep
mocks of the ctypes internals would just be testing this module's own
assumptions against itself. What IS tested here: the pure, platform-
independent logic (the _check() error-checking helper, ACL error handling),
and the orchestration/control-flow in run_write_restricted() (does it call
the right things in the right order, does it fail closed rather than
silently falling back when setup breaks) - all of which is real logic that
can have real bugs independent of whether the Win32 calls themselves are
correct.
"""

import inspect
import subprocess
from unittest import mock

import pytest

import windows_sandbox as ws


def test_is_available_reflects_platform():
    assert ws.is_available() == ws.IS_WINDOWS


def test_write_sid_is_a_plausible_sid_string():
    assert ws.MESH_SANDBOX_WRITE_SID.startswith("S-1-5-")
    assert all(part.isdigit() for part in ws.MESH_SANDBOX_WRITE_SID.split("-")[2:])


def test_check_raises_on_falsy_and_passes_through_truthy():
    assert ws._check(True, "SomeCall") is True
    assert ws._check(1, "SomeCall") == 1
    with pytest.raises(ws.WindowsSandboxError, match="SomeCall failed"):
        ws._check(False, "SomeCall")
    with pytest.raises(ws.WindowsSandboxError, match="SomeCall failed"):
        ws._check(0, "SomeCall")
    with pytest.raises(ws.WindowsSandboxError, match="SomeCall failed"):
        ws._check(None, "SomeCall")


def test_ensure_write_acl_success():
    with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout="Successfully processed", stderr="")):
        ws.ensure_write_acl("C:\\some\\dir")  # must not raise


def test_ensure_write_acl_failure_raises_with_diagnostic():
    with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="Access is denied.")):
        with pytest.raises(ws.WindowsSandboxError, match="Access is denied"):
            ws.ensure_write_acl("C:\\some\\dir")


@pytest.mark.asyncio
async def test_run_write_restricted_returns_error_when_not_windows():
    """Must explicitly force IS_WINDOWS False rather than rely on the real
    platform value - the same class of bug found and fixed in
    test_windows_sandbox_setup.py: relying on the ambient platform means
    this test's intended early-exit branch is skipped entirely when the
    suite runs on a real Windows machine, falling through into a REAL (if
    ultimately failing) PowerShell ACL call against a literal '/tmp' path -
    an unintended side effect from merely running pytest, not a
    meaningful test of anything."""
    with mock.patch.object(ws, "IS_WINDOWS", False):
        result = await ws.run_write_restricted("echo hi", ["/tmp"], cwd="/tmp")
    assert "error" in result


@pytest.mark.asyncio
async def test_run_write_restricted_calls_sync_write_acls():
    """run_write_restricted must go through sync_write_acls (which handles
    revocation - see its own tests below), not call ensure_write_acl
    directly anymore."""
    with mock.patch.object(ws, "IS_WINDOWS", True), \
         mock.patch.object(ws, "sync_write_acls") as mock_sync, \
         mock.patch("asyncio.to_thread", new=mock.AsyncMock(return_value={"stdout": "", "stderr": "", "exit_code": 0})):
        await ws.run_write_restricted("echo hi", ["C:\\a", "C:\\b", "C:\\c"], cwd="C:\\a")
        mock_sync.assert_called_once_with(["C:\\a", "C:\\b", "C:\\c"])


def test_sync_write_acls_grants_every_current_dir():
    with mock.patch.object(ws, "_load_previously_granted_dirs", return_value=set()), \
         mock.patch.object(ws, "_save_granted_dirs") as mock_save, \
         mock.patch.object(ws, "ensure_write_acl") as mock_grant, \
         mock.patch.object(ws, "revoke_write_acl") as mock_revoke, \
         mock.patch("os.path.abspath", side_effect=lambda p: p):  # avoid host-OS path-semantics differences
        ws.sync_write_acls(["/a", "/b"])

    granted = {call.args[0] for call in mock_grant.call_args_list}
    assert granted == {"/a", "/b"}
    mock_revoke.assert_not_called()
    mock_save.assert_called_once_with({"/a", "/b"})


def test_sync_write_acls_revokes_directories_no_longer_in_allow_list():
    """Regression test for the actual confinement gap found in practice: a
    directory granted access in an earlier session (e.g. /Temp, once in
    /dirs) remained writable indefinitely after being removed from /dirs,
    because nothing had ever revoked the earlier ACL grant - ACL grants are
    permanent, on-disk changes, unlike everything else this sandbox relies
    on."""
    with mock.patch.object(ws, "_load_previously_granted_dirs", return_value={"/old", "/still-current"}), \
         mock.patch.object(ws, "_save_granted_dirs"), \
         mock.patch.object(ws, "ensure_write_acl"), \
         mock.patch.object(ws, "revoke_write_acl") as mock_revoke, \
         mock.patch("os.path.isdir", return_value=True), \
         mock.patch("os.path.abspath", side_effect=lambda p: p):
        ws.sync_write_acls(["/still-current"])

    mock_revoke.assert_called_once_with("/old")


def test_sync_write_acls_does_not_revoke_a_directory_that_no_longer_exists():
    """Best-effort by design (see revoke_write_acl's docstring) - if the
    directory was deleted entirely, there's nothing to revoke and no
    PowerShell call should even be attempted against a nonexistent path."""
    with mock.patch.object(ws, "_load_previously_granted_dirs", return_value={"/deleted"}), \
         mock.patch.object(ws, "_save_granted_dirs"), \
         mock.patch.object(ws, "ensure_write_acl"), \
         mock.patch.object(ws, "revoke_write_acl") as mock_revoke, \
         mock.patch("os.path.isdir", return_value=False), \
         mock.patch("os.path.abspath", side_effect=lambda p: p):
        ws.sync_write_acls([])

    mock_revoke.assert_not_called()


@pytest.mark.asyncio
async def test_run_write_restricted_fails_closed_on_acl_error():
    """If ACL setup fails, the command must NOT run unsandboxed as a
    fallback - it must report an error instead. This is the deliberate
    fail-closed design the module docstring describes: silently falling
    back would give less protection than an opted-in user was told they'd
    get."""
    with mock.patch.object(ws, "IS_WINDOWS", True), \
         mock.patch.object(ws, "ensure_write_acl", side_effect=ws.WindowsSandboxError("icacls exploded")), \
         mock.patch("asyncio.to_thread", new=mock.AsyncMock()) as mock_to_thread:
        result = await ws.run_write_restricted("echo hi", ["C:\\a"], cwd="C:\\a")
        assert "error" in result
        assert "icacls exploded" in result["error"]
        mock_to_thread.assert_not_called()  # never got as far as actually running the command


@pytest.mark.asyncio
async def test_run_write_restricted_fails_closed_on_token_setup_error():
    """Same fail-closed property, but for a failure inside the actual
    sandboxed-process machinery (_run_write_restricted_sync) rather than
    the ACL step - e.g. CreateRestrictedToken failing on some Windows
    configuration this wasn't tested against."""
    with mock.patch.object(ws, "IS_WINDOWS", True), \
         mock.patch.object(ws, "ensure_write_acl"), \
         mock.patch("asyncio.to_thread", new=mock.AsyncMock(side_effect=ws.WindowsSandboxError("CreateRestrictedToken failed (GetLastError=5)"))):
        result = await ws.run_write_restricted("echo hi", ["C:\\a"], cwd="C:\\a")
        assert "error" in result
        assert "CreateRestrictedToken" in result["error"]


def test_build_restricted_token_fails_closed_when_quota_privilege_unavailable():
    """Regression test for the actual bug found on a real Windows machine:
    CreateProcessAsUserW's SE_ASSIGNPRIMARYTOKEN_NAME requirement is
    exempted for a restricted version of the caller's own token, but its
    SEPARATE SE_INCREASE_QUOTA_NAME requirement is NOT exempted by that -
    it's always required, and is commonly present-but-disabled by default.
    _build_restricted_token() must fail with a clear, specific error if it
    can't be enabled, rather than proceeding and hitting a much more
    confusing failure three calls later inside CreateProcessAsUserW."""
    fake_advapi32 = mock.Mock()
    fake_advapi32.OpenProcessToken.return_value = True
    with mock.patch.object(ws, "advapi32", fake_advapi32, create=True), \
         mock.patch.object(ws, "kernel32", mock.Mock(), create=True), \
         mock.patch.object(ws, "TOKEN_DUPLICATE", 0x2, create=True), \
         mock.patch.object(ws, "TOKEN_QUERY", 0x8, create=True), \
         mock.patch.object(ws, "TOKEN_ADJUST_PRIVILEGES", 0x20, create=True), \
         mock.patch.object(ws, "_enable_privilege", return_value=False):
        with pytest.raises(ws.WindowsSandboxError, match="SeIncreaseQuotaPrivilege"):
            ws._build_restricted_token()


def test_build_restricted_token_checks_quota_privilege_before_duplicating():
    """The quota-privilege check must happen (and be allowed to fail
    closed) BEFORE DuplicateTokenEx runs - not after - so a missing
    privilege is reported clearly instead of surfacing as a confusing
    failure several calls later."""
    fake_advapi32 = mock.Mock()
    fake_advapi32.OpenProcessToken.return_value = True
    with mock.patch.object(ws, "advapi32", fake_advapi32, create=True), \
         mock.patch.object(ws, "kernel32", mock.Mock(), create=True), \
         mock.patch.object(ws, "TOKEN_DUPLICATE", 0x2, create=True), \
         mock.patch.object(ws, "TOKEN_QUERY", 0x8, create=True), \
         mock.patch.object(ws, "TOKEN_ADJUST_PRIVILEGES", 0x20, create=True), \
         mock.patch.object(ws, "_enable_privilege", return_value=False):
        with pytest.raises(ws.WindowsSandboxError):
            ws._build_restricted_token()
        fake_advapi32.DuplicateTokenEx.assert_not_called()


def test_build_restricted_token_checks_both_required_privileges():
    """Regression test for the actual second wall hit on a real machine:
    granting only SeIncreaseQuotaPrivilege still left CreateProcessAsUserW
    failing with ERROR_PRIVILEGE_NOT_HELD, so both privileges must actually
    be checked/enabled here, not just one."""
    fake_advapi32 = mock.Mock()
    fake_advapi32.OpenProcessToken.return_value = True
    checked = []

    def fake_enable(token, name):
        checked.append(name)
        return True  # let it proceed past the check for both

    with mock.patch.object(ws, "advapi32", fake_advapi32, create=True), \
         mock.patch.object(ws, "kernel32", mock.Mock(), create=True), \
         mock.patch.object(ws, "TOKEN_DUPLICATE", 0x2, create=True), \
         mock.patch.object(ws, "TOKEN_QUERY", 0x8, create=True), \
         mock.patch.object(ws, "TOKEN_ADJUST_PRIVILEGES", 0x20, create=True), \
         mock.patch.object(ws, "_enable_privilege", side_effect=fake_enable):
        try:
            ws._build_restricted_token()
        except Exception:
            pass  # unrelated mocking gaps past this point aren't the point of this test

    assert "SeIncreaseQuotaPrivilege" in checked
    assert "SeAssignPrimaryTokenPrivilege" in checked


def test_create_process_does_not_request_a_new_hidden_console():
    """Regression test for the actual bug found on a real Windows machine:
    CREATE_NO_WINDOW doesn't skip console creation, it creates a NEW,
    hidden console - which requires the launching token to have access to
    a Window Station/Desktop object that a write-restricted token
    typically lacks, killing the child during bootstrap with
    STATUS_DLL_INIT_FAILED (0xC0000142) before it runs anything. The
    window must be hidden via STARTUPINFO (STARTF_USESHOWWINDOW + SW_HIDE)
    instead, which doesn't require creating a new console at all.

    Checks the flag's actual value/definition rather than the bare string
    "CREATE_NO_WINDOW", since the module's own explanatory comment on this
    (deliberately) mentions it by name."""
    source = inspect.getsource(ws)
    assert "CREATE_NO_WINDOW = 0x08000000" not in source
    assert "0x08000000" not in source
    assert "STARTF_USESHOWWINDOW" in source
    assert "SW_HIDE" in source
