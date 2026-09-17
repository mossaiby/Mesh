import os
import subprocess
import sys
from unittest import mock

import pytest

import sandbox
from tools.native_tools import ShellTool
from tools.permissions import PermissionManager


def _sandbox_backend_available() -> bool:
    return sandbox.detect_backend() != "none"


requires_sandbox_backend = pytest.mark.skipif(
    not _sandbox_backend_available(),
    reason="No sandboxing backend (bubblewrap/unshare/seatbelt) available on this machine.",
)


def test_detect_backend_returns_known_value():
    assert sandbox.detect_backend() in ("bubblewrap", "unshare", "seatbelt", "none")
    # Cached - calling it again must return the same answer without re-probing.
    assert sandbox.detect_backend() == sandbox.detect_backend()


def test_wrap_command_passthrough_when_no_backend():
    sandbox._DETECTED_BACKEND = "none"
    try:
        argv = sandbox.wrap_command("echo hi", ["/tmp"], allow_network=False, cwd="/tmp")
        assert argv[-1] == "echo hi"
    finally:
        sandbox._DETECTED_BACKEND = None  # force re-detection for later tests


def test_bubblewrap_argv_shape():
    # Calls the private builder directly rather than wrap_command(): the
    # builder's logic is inherently POSIX (bubblewrap only ever runs on real
    # Linux, where detect_backend() can actually return "bubblewrap"), but
    # wrap_command() normalizes paths with the *host* OS's os.path.abspath()
    # before dispatching - on a Windows test runner that would silently turn
    # "/tmp/..." into "C:\\tmp\\..." and break the string checks below for
    # reasons that have nothing to do with the logic actually being tested.
    argv = sandbox._build_bubblewrap_command("echo hi", ["/tmp"], allow_network=False, cwd="/tmp")
    assert argv[0] == "bwrap"
    assert "--unshare-net" in argv
    assert "/tmp" in argv
    assert argv[-3:] == ["/bin/sh", "-c", "echo hi"]


def test_bubblewrap_argv_allows_network_when_requested():
    argv = sandbox._build_bubblewrap_command("echo hi", ["/tmp"], allow_network=True, cwd="/tmp")
    assert "--unshare-net" not in argv


def test_bubblewrap_skips_tmp_scratch_when_write_dir_under_tmp():
    """Regression test: --tmpfs /tmp used to be unconditional, which made
    ALL of /tmp fully writable (not just the requested write dir) whenever
    a write dir happened to live under /tmp - which pytest's own tmp_path
    fixture, and most tools' default scratch directories, always do."""
    argv = sandbox._build_bubblewrap_command("echo hi", ["/tmp/some/nested/workdir"], allow_network=False, cwd="/tmp/some/nested/workdir")
    assert "--tmpfs" not in argv


def test_bubblewrap_adds_tmp_scratch_when_write_dir_elsewhere():
    argv = sandbox._build_bubblewrap_command("echo hi", ["/home/user/project"], allow_network=False, cwd="/home/user/project")
    assert "--tmpfs" in argv
    assert argv[argv.index("--tmpfs") + 1] == "/tmp"


def test_seatbelt_profile_denies_writes_and_network_by_default(tmp_path):
    sandbox._DETECTED_BACKEND = "seatbelt"
    try:
        write_dir = tmp_path / "workdir"
        write_dir.mkdir()
        argv = sandbox.wrap_command("echo hi", [str(write_dir)], allow_network=False, cwd=str(write_dir))
        profile_path = argv[2]
        try:
            profile = open(profile_path, encoding="utf-8").read()
            assert "(deny file-write* (subpath \"/\"))" in profile
            assert str(write_dir) in profile
            assert "(deny network*)" in profile
        finally:
            os.remove(profile_path)
    finally:
        sandbox._DETECTED_BACKEND = None


def test_windows_detect_backend_is_always_none():
    """Windows sandboxing isn't implemented yet (see the sandbox.py module
    docstring for why that's a deliberate choice, not an oversight) -
    detect_backend() must report "none" on Windows unconditionally, without
    even probing for bubblewrap/unshare/sandbox-exec. That probing matters:
    a coincidental "unshare" or "bwrap" on PATH (e.g. under WSL or Git Bash)
    would be wrong to pick up, since none of the mount-namespace machinery
    those backends generate is meaningful outside a real Linux kernel."""
    sandbox._DETECTED_BACKEND = None
    try:
        with mock.patch("sandbox.platform.system", return_value="Windows"), \
             mock.patch("sandbox.shutil.which", side_effect=AssertionError("shutil.which should never be called for Windows")):
            assert sandbox.detect_backend() == "none"
    finally:
        sandbox._DETECTED_BACKEND = None


def test_windows_wrap_command_falls_back_to_plain_cmd():
    """With no backend available (always true on Windows today), wrap_command()
    must degrade to running the command exactly as Mesh always has - a plain
    `cmd /c <command>` - rather than raising or attempting a sandboxing
    scheme that was never implemented."""
    sandbox._DETECTED_BACKEND = "none"
    try:
        with mock.patch("sandbox.platform.system", return_value="Windows"):
            argv = sandbox.wrap_command("echo hi", ["C:\\Users\\dev\\project"], allow_network=False, cwd="C:\\Users\\dev\\project")
        assert argv == ["cmd", "/c", "echo hi"]
    finally:
        sandbox._DETECTED_BACKEND = None


def test_windows_describe_status_reports_inactive_clearly():
    """The person running Mesh on Windows should see an explicit, honest
    "not sandboxed" status rather than something that could be mistaken for
    an active protection."""
    sandbox._DETECTED_BACKEND = "none"
    try:
        status = sandbox.describe_status()
        assert "NONE" in status
        assert "unsandboxed" in status.lower()
    finally:
        sandbox._DETECTED_BACKEND = None


@pytest.mark.asyncio
async def test_shell_tool_runs_unsandboxed_on_windows(tmp_path):
    """End-to-end version of the above through the actual tool: with no
    backend (the real situation on Windows), ShellTool must still run
    commands normally rather than failing or hanging - sandboxing is a
    defense-in-depth layer, not a requirement for the tool to function."""
    sandbox._DETECTED_BACKEND = "none"
    try:
        pm = PermissionManager()
        pm.allowed_dirs = [str(tmp_path)]
        tool = ShellTool(pm)

        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            res = await tool.execute(command=f'"{sys.executable}" -c "print(\'hello\')"')
            assert res["exit_code"] == 0
            assert "hello" in res["stdout"]
            assert res["_sandbox"] == "none"
        finally:
            os.chdir(cwd)
    finally:
        sandbox._DETECTED_BACKEND = None


@requires_sandbox_backend
@pytest.mark.asyncio
async def test_shell_tool_write_confined_to_allowed_dir(tmp_path):
    """The actual security property: a sandboxed shell command can write
    inside the permission allow-list, but not outside it - enforced by the
    kernel, not by application logic."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    outside_target = tmp_path / "outside.txt"  # a sibling dir, NOT in the allow-list

    pm = PermissionManager()
    pm.allowed_dirs = [str(workdir)]
    tool = ShellTool(pm)

    cwd = os.getcwd()
    try:
        os.chdir(workdir)

        res = await tool.execute(command="echo inside > allowed.txt && cat allowed.txt")
        assert res["exit_code"] == 0
        assert "inside" in res["stdout"]
        assert (workdir / "allowed.txt").exists()

        res = await tool.execute(command=f"echo leaked > {outside_target} 2>&1 || echo BLOCKED")
        assert "BLOCKED" in res["stdout"] or "BLOCKED" in res["stderr"]
        assert not outside_target.exists()
    finally:
        os.chdir(cwd)


@requires_sandbox_backend
@pytest.mark.asyncio
async def test_shell_tool_network_denied_by_default(tmp_path):
    pm = PermissionManager()
    pm.allowed_dirs = [str(tmp_path)]
    tool = ShellTool(pm)

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        res = await tool.execute(
            command="python3 -c \"import socket; socket.create_connection(('8.8.8.8', 53), timeout=2)\" 2>&1 || echo NETBLOCKED"
        )
        assert "NETBLOCKED" in res["stdout"]
    finally:
        os.chdir(cwd)


@requires_sandbox_backend
@pytest.mark.asyncio
async def test_shell_tool_network_allowed_when_requested(tmp_path):
    pm = PermissionManager()
    pm.allowed_dirs = [str(tmp_path)]
    tool = ShellTool(pm)

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        res = await tool.execute(command="echo network-allowed-ran", network=True)
        assert res["exit_code"] == 0
        assert "network-allowed-ran" in res["stdout"]
    finally:
        os.chdir(cwd)
