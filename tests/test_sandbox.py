import os
import subprocess

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
    sandbox._DETECTED_BACKEND = "bubblewrap"
    try:
        argv = sandbox.wrap_command("echo hi", ["/tmp"], allow_network=False, cwd="/tmp")
        assert argv[0] == "bwrap"
        assert "--unshare-net" in argv
        assert "/tmp" in argv
        assert argv[-3:] == ["/bin/sh", "-c", "echo hi"]
    finally:
        sandbox._DETECTED_BACKEND = None


def test_bubblewrap_argv_allows_network_when_requested():
    sandbox._DETECTED_BACKEND = "bubblewrap"
    try:
        argv = sandbox.wrap_command("echo hi", ["/tmp"], allow_network=True, cwd="/tmp")
        assert "--unshare-net" not in argv
    finally:
        sandbox._DETECTED_BACKEND = None


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
