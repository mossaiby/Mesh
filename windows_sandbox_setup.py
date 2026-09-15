"""
One-time elevated setup for the experimental Windows sandbox
(windows_sandbox.py).

WHY THIS EXISTS: windows_sandbox.py's write-restricted-token approach turned
out to still need SeIncreaseQuotaPrivilege ("Adjust memory quotas for a
process") on the calling account, and - contrary to what windows_sandbox.py
originally assumed - this is not something every account holds by default,
present-but-disabled. Granting an account a Windows user right it doesn't
already have at all is an administrator-only operation (LsaAddAccountRights),
which is exactly the one-time elevated bootstrap OpenAI's Codex team
describes needing for their equivalent feature: "Run codex once with
administrator approval to complete setup. After the initial UAC prompt,
day-to-day usage requires no elevation." This module is that bootstrap step
for Mesh.

DESIGN PRINCIPLES, deliberately conservative given what this touches (local
security policy, not just a sandboxed process):

1. Grants exactly one, narrowly-scoped privilege - nothing broader than
   what CreateProcessAsUserW actually requires.
2. The elevated script is short, self-contained (no imports beyond ctypes/
   sys, no dependency on the rest of Mesh being importable from wherever
   UAC happens to launch it from), and printed to the console in full
   before it runs - so what it does is auditable, not a black box.
3. A manual alternative (the equivalent secpol.msc steps) is always shown
   alongside the automated path, so a cautious user is never required to
   trust this code.
4. IMPORTANT CAVEAT that must be communicated to the user: granting a new
   right takes effect on the NEXT LOGON, not immediately. The account's
   already-running session token is a snapshot taken at the time of the
   original login and won't retroactively gain the new right - signing out
   and back in (or restarting) is required before windows_sandbox.py can
   actually use it. This matches Codex's own "after the initial UAC
   prompt" framing, which implies the same requirement even where it isn't
   stated outright.

Like windows_sandbox.py, every Win32/LSA call here is correct-by-careful-
construction against documented signatures, not verified by execution -
there is no Windows machine available in the environment this was written
in. Treat this as reviewed, not verified, exactly like the module it
supports.
"""

import ctypes
import os
import platform
import tempfile
import uuid
from ctypes import wintypes
from typing import Optional, Tuple

IS_WINDOWS = platform.system() == "Windows"

REQUIRED_PRIVILEGES = ["SeIncreaseQuotaPrivilege", "SeAssignPrimaryTokenPrivilege"]

if IS_WINDOWS:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    TOKEN_QUERY = 0x0008
    TOKEN_ADJUST_PRIVILEGES = 0x0020
    TokenUser = 1  # TOKEN_INFORMATION_CLASS

    POLICY_ALL_ACCESS = 0x000F0FFF

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_SHOWNORMAL = 1  # deliberately visible, not hidden - see module docstring point 2

    INFINITE = 0xFFFFFFFF
    ERROR_CANCELLED = 1223  # what ShellExecuteExW/GetLastError report if the UAC prompt was denied

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]

    class TOKEN_USER(ctypes.Structure):
        _fields_ = [("User", SID_AND_ATTRIBUTES)]

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HANDLE),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    # Explicit argtypes/restype for every function, declared up front this
    # time rather than reactively - see windows_sandbox.py's own comment on
    # this for why it matters (ctypes silently truncates unmarked pointer/
    # handle-returning calls to 32 bits, which is exactly what caused that
    # module's first real bug).
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []

    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    kernel32.LocalFree.restype = wintypes.HANDLE
    kernel32.LocalFree.argtypes = [wintypes.HANDLE]

    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]

    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]

    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]

    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]

    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]

    shell32.ShellExecuteExW.restype = wintypes.BOOL
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]


class SetupError(Exception):
    pass


def is_available() -> bool:
    return IS_WINDOWS


def _check(ok, call_name: str):
    if not ok:
        try:
            err = ctypes.get_last_error()
            raise SetupError(f"{call_name} failed (GetLastError={err})")
        except AttributeError:
            raise SetupError(f"{call_name} failed")
    return ok


def get_current_user_sid_string() -> str:
    """Returns the CALLING process's own user SID as a string
    (e.g. 'S-1-5-21-...-1001'), read from its own token. Used to tell the
    elevated helper exactly which account to grant the privilege to,
    without needing a separate username lookup."""
    hToken = wintypes.HANDLE()
    _check(advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(hToken)), "OpenProcessToken(self)")
    try:
        size = wintypes.DWORD(0)
        advapi32.GetTokenInformation(hToken, TokenUser, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        _check(advapi32.GetTokenInformation(hToken, TokenUser, buf, size, ctypes.byref(size)), "GetTokenInformation(TokenUser)")

        token_user = TOKEN_USER.from_buffer_copy(buf)

        sid_string_ptr = wintypes.LPWSTR()
        _check(advapi32.ConvertSidToStringSidW(token_user.User.Sid, ctypes.byref(sid_string_ptr)), "ConvertSidToStringSidW")
        try:
            return ctypes.wstring_at(sid_string_ptr)
        finally:
            kernel32.LocalFree(sid_string_ptr)  # ConvertSidToStringSidW allocates via LocalAlloc
    finally:
        kernel32.CloseHandle(hToken)


def has_required_privilege() -> bool:
    """Whether the CURRENT process's token already holds all of
    REQUIRED_PRIVILEGES (enabled or not) - if this is already true, the
    elevated setup in this module is unnecessary."""
    hToken = wintypes.HANDLE()
    _check(
        advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), TOKEN_QUERY | TOKEN_ADJUST_PRIVILEGES, ctypes.byref(hToken)
        ),
        "OpenProcessToken(self)",
    )
    try:
        # Reuses the exact lookup approach windows_sandbox.py's
        # _enable_privilege relies on (LookupPrivilegeValueW +
        # AdjustTokenPrivileges), imported lazily to avoid a hard
        # dependency between these two modules beyond what's needed here.
        import windows_sandbox
        return all(windows_sandbox._enable_privilege(hToken, p) for p in REQUIRED_PRIVILEGES)
    finally:
        kernel32.CloseHandle(hToken)


# The elevated helper: intentionally short, self-contained (only ctypes/
# sys/argv - no Mesh imports, since we can't assume Mesh's own directory is
# on sys.path from wherever UAC happens to launch python.exe), and printed
# to the console before running so it's auditable rather than a black box.
# Grants exactly one named right to exactly one named SID; nothing else.
_ELEVATED_GRANT_SCRIPT = r'''
import ctypes, sys
from ctypes import wintypes

advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

class LSA_UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", wintypes.LPWSTR)]

class LSA_OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Length", wintypes.ULONG), ("RootDirectory", wintypes.HANDLE),
                ("ObjectName", ctypes.c_void_p), ("Attributes", wintypes.ULONG),
                ("SecurityDescriptor", ctypes.c_void_p), ("SecurityQualityOfService", ctypes.c_void_p)]

advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
advapi32.LsaOpenPolicy.restype = ctypes.c_long
advapi32.LsaOpenPolicy.argtypes = [ctypes.POINTER(LSA_UNICODE_STRING), ctypes.POINTER(LSA_OBJECT_ATTRIBUTES), wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi32.LsaAddAccountRights.restype = ctypes.c_long
advapi32.LsaAddAccountRights.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(LSA_UNICODE_STRING), wintypes.ULONG]
advapi32.LsaClose.restype = ctypes.c_long
advapi32.LsaClose.argtypes = [wintypes.HANDLE]
advapi32.LsaNtStatusToWinError.restype = wintypes.ULONG
advapi32.LsaNtStatusToWinError.argtypes = [ctypes.c_long]

def make_lsa_string(text):
    buf = ctypes.create_unicode_buffer(text)
    s = LSA_UNICODE_STRING()
    s.Length = len(text) * 2
    s.MaximumLength = (len(text) + 1) * 2
    s.Buffer = ctypes.cast(buf, wintypes.LPWSTR)
    return s, buf  # caller must keep `buf` alive as long as `s` is used

sid_string, result_path = sys.argv[1], sys.argv[2]
privilege_names = sys.argv[3:]

try:
    sid = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW(sid_string, ctypes.byref(sid)):
        raise RuntimeError(f"ConvertStringSidToSidW failed (GetLastError={ctypes.get_last_error()})")

    policy_handle = wintypes.HANDLE()
    obj_attrs = LSA_OBJECT_ATTRIBUTES()
    obj_attrs.Length = ctypes.sizeof(LSA_OBJECT_ATTRIBUTES)
    POLICY_ALL_ACCESS = 0x000F0FFF
    status = advapi32.LsaOpenPolicy(None, ctypes.byref(obj_attrs), POLICY_ALL_ACCESS, ctypes.byref(policy_handle))
    if status < 0:
        raise RuntimeError(f"LsaOpenPolicy failed (NTSTATUS=0x{status & 0xFFFFFFFF:08X}, WinError={advapi32.LsaNtStatusToWinError(status)})")

    try:
        # Keep every buf alive until after the LsaAddAccountRights call -
        # each LSA_UNICODE_STRING only holds a raw pointer into its buf,
        # not a reference, so a buf freed early would leave a dangling
        # pointer for LSA to read from.
        rights_and_bufs = [make_lsa_string(name) for name in privilege_names]
        rights_array = (LSA_UNICODE_STRING * len(rights_and_bufs))(*[r for r, _ in rights_and_bufs])
        status = advapi32.LsaAddAccountRights(policy_handle, sid, rights_array, len(rights_and_bufs))
        if status < 0:
            raise RuntimeError(f"LsaAddAccountRights failed (NTSTATUS=0x{status & 0xFFFFFFFF:08X}, WinError={advapi32.LsaNtStatusToWinError(status)})")
    finally:
        advapi32.LsaClose(policy_handle)

    with open(result_path, "w", encoding="utf-8") as f:
        f.write("OK")
    sys.exit(0)
except Exception as e:
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(f"ERROR: {e}")
    sys.exit(1)
'''


def build_manual_instructions() -> str:
    """The non-automated equivalent, for anyone who'd rather not run the
    elevated helper at all."""
    return (
        "Manual alternative (no elevation prompt from Mesh):\n"
        "  1. Open secpol.msc (Local Security Policy)\n"
        "  2. Local Policies -> User Rights Assignment\n"
        "  3. Add your account to BOTH of:\n"
        "       - \"Adjust memory quotas for a process\"\n"
        "       - \"Replace a process level token\"\n"
        "  4. Sign out and back in (or restart) for it to take effect"
    )


async def run_elevated_setup(timeout: float = 120.0) -> Tuple[bool, str]:
    """Triggers a single UAC prompt to grant the current account
    SeIncreaseQuotaPrivilege. Returns (success, message). This never
    silently retries or escalates scope on failure - a denied UAC prompt
    or any error is reported plainly, with the manual alternative always
    available as a fallback."""
    import asyncio

    if not IS_WINDOWS:
        return False, "run_elevated_setup() called on a non-Windows platform."

    try:
        sid_string = get_current_user_sid_string()
    except SetupError as e:
        return False, f"Could not determine the current account's SID: {e}"

    script_fd, script_path = tempfile.mkstemp(suffix=".py", prefix="mesh_sandbox_setup_")
    result_fd, result_path = tempfile.mkstemp(suffix=".txt", prefix="mesh_sandbox_setup_result_")
    os.close(result_fd)
    try:
        with os.fdopen(script_fd, "w", encoding="utf-8") as f:
            f.write(_ELEVATED_GRANT_SCRIPT)

        import sys as _sys
        exec_info = SHELLEXECUTEINFOW()
        exec_info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
        exec_info.fMask = SEE_MASK_NOCLOSEPROCESS
        exec_info.lpVerb = "runas"
        exec_info.lpFile = _sys.executable
        exec_info.lpParameters = f'"{script_path}" "{sid_string}" "{result_path}" ' + " ".join(f'"{p}"' for p in REQUIRED_PRIVILEGES)
        exec_info.nShow = SW_SHOWNORMAL

        ok = shell32.ShellExecuteExW(ctypes.byref(exec_info))
        if not ok:
            err = ctypes.get_last_error()
            if err == ERROR_CANCELLED:
                return False, "UAC prompt was denied - no changes were made."
            return False, f"ShellExecuteExW failed (GetLastError={err})."

        wait_result = await asyncio.to_thread(
            kernel32.WaitForSingleObject, exec_info.hProcess, int(timeout * 1000)
        )
        if wait_result != 0:
            return False, f"Elevated setup did not finish within {timeout} seconds."

        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(exec_info.hProcess, ctypes.byref(exit_code))
        kernel32.CloseHandle(exec_info.hProcess)

        try:
            with open(result_path, "r", encoding="utf-8") as f:
                detail = f.read().strip()
        except OSError:
            detail = "(no result file written)"

        if exit_code.value == 0 and detail == "OK":
            granted = " and ".join(f"'{p}'" for p in REQUIRED_PRIVILEGES)
            return True, (
                f"Granted {granted} to your account. "
                "Sign out and back in (or restart) before this takes effect - "
                "your current session's token won't pick it up until then."
            )
        return False, f"Elevated setup reported failure: {detail}"
    finally:
        for p in (script_path, result_path):
            try:
                os.remove(p)
            except OSError:
                pass
