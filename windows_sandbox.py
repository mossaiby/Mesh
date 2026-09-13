"""
EXPERIMENTAL Windows sandboxing: write-restricted process tokens + a
synthetic ACL SID, confining filesystem writes to an explicit allow-list.

READ THIS BEFORE ENABLING (`sandbox_windows_experimental: true`):

Everything else in `sandbox.py` (bubblewrap, unshare, Seatbelt) was verified
against the real thing - either compiled and executed directly (bubblewrap,
in the environment this was developed in) or is a thin wrapper around a
tool that ships with the OS (Seatbelt). This module could not be verified
that way: it was developed with no Windows machine available at all. Every
Win32 API used here is long-stable and well-documented, and the design
follows the approach OpenAI's Codex team published for the exact same
problem [1], but "carefully written against the docs" is a categorically
weaker guarantee than "compiled and run." Treat this backend as reviewed,
not verified, until someone runs it for real - which is exactly why it
defaults to off and never activates silently.

[1] https://openai.com/index/building-codex-windows-sandbox/ - their
    "unelevated sandbox" prototype, which this module is a scoped-down
    version of. Two things worth knowing from that writeup before relying
    on this:

    1. They evaluated and rejected Mandatory Integrity Control (running low-
       integrity + relabeling writable roots) because relabeling a directory
       low-integrity doesn't just mean "our sandbox can write here" - it
       means ANY low-integrity process on the machine can. Write-restricted
       tokens (what this module uses instead) don't have that problem: the
       synthetic SID is meaningless to every other process on the system.

    2. Their own writeup is explicit that real network suppression on
       Windows needs a dedicated OS user account + Windows Firewall rule
       scoped to that account, which in turn needs a second privileged
       helper binary and one-time elevated setup - a substantially bigger
       undertaking than the filesystem piece. This module deliberately does
       NOT attempt network restriction at all; `allow_network` is accepted
       for interface consistency with the other backends but has no effect
       here. Don't rely on this for anything where network egress matters -
       the LLM guard and static rules in guard.py are still your only line
       of defense against that on Windows today.

HOW IT WORKS: a write-restricted token makes Windows perform an EXTRA check
on every write, on top of the normal one. For a write to succeed, both must
pass: (1) the real user's normal permissions allow it, AND (2) at least one
SID in the token's restricted SID list is also granted access to that
object. We create one synthetic SID that means nothing to any other process
on the machine, ACL it onto exactly the directories that should be
writable (via `icacls`, not raw ACL structs - one less place for this
module's own bugs to hide), and launch the command with a token whose
restricted SID list is just [Everyone, the current logon session, our
synthetic SID]. Writes inside the allowed directories pass both checks;
writes anywhere else fail the second one, because our SID was never
granted access there.
"""

import asyncio
import ctypes
import platform
import subprocess
import uuid
from ctypes import wintypes
from typing import Any, Dict, List, Optional

IS_WINDOWS = platform.system() == "Windows"

# A fixed, made-up SID under a sub-authority not used by any real Windows
# principal or well-known group. It never needs to resolve to an actual
# account - Windows allows arbitrary SIDs to appear in ACLs and in a
# token's restricted SID list purely as markers. Using one constant value
# (rather than generating a fresh one per run) keeps re-running the ACL
# setup idempotent instead of accumulating throwaway entries on every
# directory Mesh has ever touched.
MESH_SANDBOX_WRITE_SID = "S-1-5-94-1832-4471-9903-2216"

if IS_WINDOWS:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    TOKEN_DUPLICATE = 0x0002
    TOKEN_QUERY = 0x0008
    TOKEN_ASSIGN_PRIMARY = 0x0001
    TOKEN_ALL_ACCESS = 0xF01FF

    TokenPrimary = 1
    TokenGroups = 2  # TOKEN_INFORMATION_CLASS value for GetTokenInformation

    WRITE_RESTRICTED = 0x8  # CreateRestrictedToken flag: this is the whole mechanism
    SE_GROUP_LOGON_ID = 0xC0000000

    CREATE_NO_WINDOW = 0x08000000
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    STARTF_USESTDHANDLES = 0x00000100
    HANDLE_FLAG_INHERIT = 0x00000001

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", wintypes.LPVOID),
            ("bInheritHandle", wintypes.BOOL),
        ]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.c_void_p),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]


class WindowsSandboxError(Exception):
    """Raised when any step of setting up or running the sandboxed process
    fails. Callers should treat this as "the sandbox itself is broken,"
    not "the command failed" - see `run_write_restricted`'s docstring for
    why this fails loudly instead of silently falling back."""


def is_available() -> bool:
    return IS_WINDOWS


def ensure_write_acl(directory: str) -> None:
    """Grants our synthetic SID modify access to `directory`, so a token
    restricted to that SID can write there. Idempotent - safe to call every
    time a command runs. Uses `icacls` rather than raw ACL/security-
    descriptor structs: it's the same operation, tested Microsoft tooling,
    and one less place for this module's own bugs to hide."""
    result = subprocess.run(
        ["icacls", directory, "/grant", f"*{MESH_SANDBOX_WRITE_SID}:(OI)(CI)(M)"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise WindowsSandboxError(
            f"icacls failed to grant sandbox write access to {directory!r}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def _check(ok, call_name: str):
    """Every ctypes call below returns a BOOL/handle that must be checked;
    this centralizes that so a failure is always caught immediately, with
    GetLastError() where available, rather than silently continuing with
    an invalid handle. `ctypes.get_last_error()` only exists at all when
    running on Windows (it's undefined on other platforms), so this
    degrades to a plain message elsewhere rather than raising an unrelated
    AttributeError on top of the real failure."""
    if not ok:
        try:
            err = ctypes.get_last_error()
            raise WindowsSandboxError(f"{call_name} failed (GetLastError={err})")
        except AttributeError:
            raise WindowsSandboxError(f"{call_name} failed")
    return ok


def _sid_from_string(sid_string: str):
    psid = ctypes.c_void_p()
    ok = advapi32.ConvertStringSidToSidW(sid_string, ctypes.byref(psid))
    _check(ok, f"ConvertStringSidToSidW({sid_string!r})")
    return psid


def _get_logon_sid(token) -> ctypes.c_void_p:
    """Finds the SID representing the current logon session, from the
    token's group list (the one group flagged SE_GROUP_LOGON_ID). This is
    what lets normal, session-scoped resources (temp directories, etc.)
    keep working under the restricted token.

    Uses ctypes' own structure layout rather than hand-computed byte
    offsets deliberately: TOKEN_GROUPS is `DWORD GroupCount;
    SID_AND_ATTRIBUTES Groups[ANYSIZE_ARRAY];`, and because
    SID_AND_ATTRIBUTES's first member is a pointer, the struct's real
    alignment requirement pads GroupCount out to a pointer-sized boundary
    on 64-bit Windows before Groups actually starts - `sizeof(DWORD)` (4)
    is NOT the right offset, `sizeof(PVOID)` (8) is. Building the actual
    struct and letting ctypes compute that avoids trusting a manual
    offset that's exactly the kind of thing impossible to get right by
    guessing rather than either running it or checking against a real
    Windows ctypes environment.
    """
    class _TokenGroupsHeader(ctypes.Structure):
        _fields_ = [("GroupCount", wintypes.DWORD)]

    size = wintypes.DWORD(0)
    advapi32.GetTokenInformation(token, TokenGroups, None, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    ok = advapi32.GetTokenInformation(token, TokenGroups, buf, size, ctypes.byref(size))
    _check(ok, "GetTokenInformation(TokenGroups)")

    group_count = _TokenGroupsHeader.from_buffer_copy(buf).GroupCount

    class _TokenGroupsFull(ctypes.Structure):
        _fields_ = [("GroupCount", wintypes.DWORD), ("Groups", SID_AND_ATTRIBUTES * group_count)]

    groups_struct = _TokenGroupsFull.from_buffer_copy(buf)
    for group in groups_struct.Groups:
        if group.Attributes & SE_GROUP_LOGON_ID:
            # Duplicate the SID out of the buffer we're about to free.
            length = advapi32.GetLengthSid(group.Sid)
            sid_copy = ctypes.create_string_buffer(length)
            _check(advapi32.CopySid(length, sid_copy, group.Sid), "CopySid(logon sid)")
            return ctypes.cast(sid_copy, ctypes.c_void_p)

    raise WindowsSandboxError("Could not find a logon-session SID in the current token's groups")


def _build_restricted_token():
    """OpenProcessToken -> DuplicateTokenEx (primary) -> CreateRestrictedToken
    with WRITE_RESTRICTED and our three-SID allow-list. Returns the
    restricted token handle; caller is responsible for closing it."""
    hToken = wintypes.HANDLE()
    _check(
        advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), TOKEN_DUPLICATE | TOKEN_QUERY, ctypes.byref(hToken)
        ),
        "OpenProcessToken",
    )

    hDupToken = wintypes.HANDLE()
    try:
        _check(
            advapi32.DuplicateTokenEx(
                hToken, TOKEN_ALL_ACCESS, None, 2, TokenPrimary, ctypes.byref(hDupToken)
            ),
            "DuplicateTokenEx",
        )
    finally:
        kernel32.CloseHandle(hToken)

    everyone_sid = _sid_from_string("S-1-1-0")
    logon_sid = _get_logon_sid(hDupToken)
    write_sid = _sid_from_string(MESH_SANDBOX_WRITE_SID)

    restricted_sids = (SID_AND_ATTRIBUTES * 3)(
        (everyone_sid, 0), (logon_sid, 0), (write_sid, 0)
    )

    hRestricted = wintypes.HANDLE()
    try:
        _check(
            advapi32.CreateRestrictedToken(
                hDupToken,
                WRITE_RESTRICTED,
                3,
                restricted_sids,
                0,
                None,
                0,
                None,
                ctypes.byref(hRestricted),
            ),
            "CreateRestrictedToken",
        )
    finally:
        kernel32.CloseHandle(hDupToken)

    return hRestricted


async def run_write_restricted(command: str, write_dirs: List[str], cwd: str,
                                timeout: Optional[float] = None) -> Dict[str, Any]:
    """Runs `command` (a cmd.exe command line) under a write-restricted
    token, confined to `write_dirs`. Returns the same shape ShellTool
    expects ({"stdout", "stderr", "exit_code"}), or {"error": ...} if the
    sandbox itself couldn't be set up - which is treated as a hard failure,
    not a reason to quietly fall back to running the command unsandboxed.
    That's a deliberate choice: this backend is opt-in and unverified, so a
    setup failure most likely means something about this Windows
    configuration doesn't match what was assumed here, and running the
    command anyway would silently give less protection than the person who
    turned this on was told they were getting.
    """
    if not IS_WINDOWS:
        return {"error": "windows_sandbox.run_write_restricted() called on a non-Windows platform."}

    try:
        for d in write_dirs:
            ensure_write_acl(d)

        return await asyncio.to_thread(_run_write_restricted_sync, command, cwd, timeout)
    except WindowsSandboxError as e:
        return {"error": f"Windows sandbox setup failed: {e}"}


def _run_write_restricted_sync(command: str, cwd: str, timeout: Optional[float]) -> Dict[str, Any]:
    sa = SECURITY_ATTRIBUTES(nLength=ctypes.sizeof(SECURITY_ATTRIBUTES), bInheritHandle=True)

    stdout_read, stdout_write = wintypes.HANDLE(), wintypes.HANDLE()
    stderr_read, stderr_write = wintypes.HANDLE(), wintypes.HANDLE()
    _check(kernel32.CreatePipe(ctypes.byref(stdout_read), ctypes.byref(stdout_write), ctypes.byref(sa), 0), "CreatePipe(stdout)")
    _check(kernel32.CreatePipe(ctypes.byref(stderr_read), ctypes.byref(stderr_write), ctypes.byref(sa), 0), "CreatePipe(stderr)")
    # The read ends must NOT be inherited by the child, or the pipe never
    # signals EOF once the child exits (it thinks it's still open, because
    # the child also holds a copy of the read handle).
    kernel32.SetHandleInformation(stdout_read, HANDLE_FLAG_INHERIT, 0)
    kernel32.SetHandleInformation(stderr_read, HANDLE_FLAG_INHERIT, 0)

    hRestricted = None
    hProcess = None
    hThread = None
    try:
        hRestricted = _build_restricted_token()

        startup_info = STARTUPINFOW()
        startup_info.cb = ctypes.sizeof(STARTUPINFOW)
        startup_info.dwFlags = STARTF_USESTDHANDLES
        startup_info.hStdOutput = stdout_write
        startup_info.hStdError = stderr_write
        startup_info.hStdInput = wintypes.HANDLE(0)

        proc_info = PROCESS_INFORMATION()
        cmdline = ctypes.create_unicode_buffer(f'cmd.exe /c "{command}"')

        ok = advapi32.CreateProcessAsUserW(
            hRestricted, None, cmdline, None, None, True,
            CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
            None, cwd, ctypes.byref(startup_info), ctypes.byref(proc_info),
        )
        _check(ok, "CreateProcessAsUserW")
        hProcess, hThread = proc_info.hProcess, proc_info.hThread

        # The write ends belong to the child now; the parent must close its
        # copies or its own ReadFile calls below will never see EOF.
        kernel32.CloseHandle(stdout_write)
        kernel32.CloseHandle(stderr_write)
        stdout_write = stderr_write = None

        stdout_data = _read_pipe_to_end(stdout_read)
        stderr_data = _read_pipe_to_end(stderr_read)

        timeout_ms = int(timeout * 1000) if timeout and timeout > 0 else 0xFFFFFFFF  # INFINITE
        wait_result = kernel32.WaitForSingleObject(hProcess, timeout_ms)
        if wait_result != 0:  # WAIT_OBJECT_0
            kernel32.TerminateProcess(hProcess, 1)
            return {"error": f"Command timed out after {timeout} seconds (Windows sandbox)."}

        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))

        return {
            "command": command,
            "exit_code": exit_code.value,
            "stdout": stdout_data.decode("utf-8", errors="replace").strip(),
            "stderr": stderr_data.decode("utf-8", errors="replace").strip(),
            "_sandbox": "windows-restricted-token (EXPERIMENTAL)",
        }
    finally:
        for handle in (stdout_read, stderr_read, stdout_write, stderr_write, hThread, hProcess, hRestricted):
            if handle:
                kernel32.CloseHandle(handle)


def _read_pipe_to_end(handle, chunk_size: int = 65536) -> bytes:
    buf = ctypes.create_string_buffer(chunk_size)
    bytes_read = wintypes.DWORD()
    out = bytearray()
    while True:
        ok = kernel32.ReadFile(handle, buf, chunk_size, ctypes.byref(bytes_read), None)
        if not ok or bytes_read.value == 0:
            break
        out.extend(buf.raw[: bytes_read.value])
    return bytes(out)
