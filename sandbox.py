"""
Best-effort, tiered, OS-level sandboxing for commands Mesh executes
(`shell`, `job`, and `execute_python`).

This exists to close a real gap: everything else in Mesh's safety model
(`PermissionManager`'s directory allow-list, the static regex rules and LLM
risk assessment in `guard.py`) decides whether to *launch* a process. None
of it constrains what that process can actually touch once it's running -
that decision has always been left entirely to the OS user account Mesh
itself runs as. This module is a second, independent layer underneath all
of that: even a call every other layer approved gets kernel-enforced limits
on what filesystem paths it can write to and whether it can reach the
network at all.

Backends, strongest to weakest, chosen automatically per platform:

- Linux + bubblewrap (`bwrap`) installed: real user/mount/pid/net
  namespaces via the same tool most container runtimes and other agentic
  CLIs use for this. The strongest and most correct backend here.
- Linux without bubblewrap: a hand-rolled equivalent built from `unshare`
  and `mount`, using unprivileged user+mount namespaces the same way
  bubblewrap does internally. Real kernel enforcement, but more manual and
  with a documented rough edge (see `_build_unshare_script`'s docstring)
  around less-common mount layouts.
- macOS: a generated Seatbelt profile passed to `sandbox-exec`, the same
  primitive macOS-based agentic CLIs use. Written to the same
  specification as the Linux backends but NOT executable-tested in the
  environment this was developed in (no macOS available there) - treat
  this backend as reviewed-but-unverified until it's been run for real.
- Windows: no backend is implemented yet. `detect_backend()` correctly
  reports `"none"` on Windows rather than shipping ACL/firewall logic that
  was never actually exercised against a live Windows sandbox - see the
  module docstring in the code review that added this file for why that
  tradeoff was made deliberately rather than by omission.
- Nothing available (stripped-down container, unprivileged Windows,
  etc.): commands run unsandboxed, exactly as Mesh always has, but this is
  now a visible, logged state (see `describe_status()`) rather than an
  implicit one.

This is additive, not a replacement: the static rules and LLM guard in
`guard.py` still run first and can deny a command outright before any of
this even applies. This module is what happens to a command that *was*
approved, in case that approval turns out to be wrong.
"""

import os
import platform
import shlex
import shutil
import subprocess
from typing import List, Optional, Sequence

_DETECTED_BACKEND: Optional[str] = None

# Mount targets that must never be remounted read-only by the `unshare`
# backend: these are pseudo-filesystems most commands need live, writable
# access to for completely ordinary operation (process info, ttys, device
# nodes, sockets/pid files), not "data" in the sense the sandbox cares
# about protecting.
_UNSHARE_SKIP_PREFIXES = ("/proc", "/sys", "/dev", "/run")


def detect_backend() -> str:
    """Picks the strongest sandboxing backend available on this machine,
    caching the result (the answer can't change mid-process). Returns one
    of: "bubblewrap", "unshare", "seatbelt", "none"."""
    global _DETECTED_BACKEND
    if _DETECTED_BACKEND is not None:
        return _DETECTED_BACKEND

    system = platform.system()
    if system == "Linux":
        if shutil.which("bwrap"):
            _DETECTED_BACKEND = "bubblewrap"
        elif shutil.which("unshare") and _unshare_usable():
            _DETECTED_BACKEND = "unshare"
        else:
            _DETECTED_BACKEND = "none"
    elif system == "Darwin":
        _DETECTED_BACKEND = "seatbelt" if shutil.which("sandbox-exec") else "none"
    else:
        # Includes Windows - see the module docstring for why this is
        # deliberately "none" rather than an unverified implementation.
        _DETECTED_BACKEND = "none"

    return _DETECTED_BACKEND


def _unshare_usable() -> bool:
    """`unshare --mount --map-root-user` needs unprivileged user
    namespaces, which most modern Linux distros enable by default but a
    minority (some hardened kernels, some containers) disable. Actually
    trying it is the only reliable way to know."""
    try:
        result = subprocess.run(
            ["unshare", "--mount", "--map-root-user", "true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def describe_status() -> str:
    """One-line, human-readable summary of the active backend, for
    `/sandbox status` and startup logging."""
    backend = detect_backend()
    return {
        "bubblewrap": "bubblewrap (full filesystem + network isolation)",
        "unshare": "unshare/mount namespaces (filesystem + network isolation, best-effort on unusual mount layouts)",
        "seatbelt": "macOS Seatbelt (sandbox-exec)",
        "none": "NONE - commands run unsandboxed at the OS level (relying on the static safety net and Safety Guard only)",
    }[backend]


def wrap_command(command: str, allowed_write_dirs: Sequence[str], allow_network: bool = False,
                  cwd: Optional[str] = None) -> List[str]:
    """Wraps a shell command string so that, when run, it can only write to
    `allowed_write_dirs` and (unless `allow_network`) has no network access
    at all - enforced by whichever backend `detect_backend()` picked, or
    returns the command unwrapped if no backend is available.

    Returns an argv list suitable for `subprocess`/`asyncio.create_subprocess_exec`.
    The caller is responsible for actually running it and still applies
    all its normal timeout/output handling on top.
    """
    backend = detect_backend()
    cwd = os.path.abspath(cwd or os.getcwd())
    write_dirs = [os.path.abspath(d) for d in allowed_write_dirs if d and os.path.isdir(d)]
    if cwd not in write_dirs:
        write_dirs.append(cwd)

    if backend == "bubblewrap":
        return _build_bubblewrap_command(command, write_dirs, allow_network, cwd)
    if backend == "unshare":
        return _build_unshare_command(command, write_dirs, allow_network, cwd)
    if backend == "seatbelt":
        return _build_seatbelt_command(command, write_dirs, allow_network, cwd)

    # No backend: run the command exactly as Mesh always has.
    return ["/bin/sh", "-c", command] if platform.system() != "Windows" else ["cmd", "/c", command]


def _build_bubblewrap_command(command: str, write_dirs: List[str], allow_network: bool, cwd: str) -> List[str]:
    args = ["bwrap", "--die-with-parent", "--unshare-pid"]
    if not allow_network:
        args += ["--unshare-net"]

    # Whole filesystem read-only by default, then carve out exactly the
    # directories the caller said should be writable, plus the usual
    # pseudo-filesystems a normal process needs live access to.
    args += ["--ro-bind", "/", "/"]
    args += ["--dev", "/dev", "--proc", "/proc"]

    # A writable scratch /tmp is convenient for tools that expect one, but
    # bwrap processes --tmpfs/--bind arguments as an ordered overlay: a
    # fresh, fully-writable tmpfs at /tmp would make EVERYTHING under /tmp
    # writable, not just the explicitly bound write_dirs - including any
    # sibling path that happens to live there too (pytest's tmp_path fixture,
    # most tools' default scratch directories, etc. all do). Only add the
    # generic scratch tmpfs when nothing the caller asked to keep writable
    # depends on /tmp's real contents; see the identical reasoning in
    # `_build_unshare_script` below, which had this same bug fixed first.
    any_write_dir_under_tmp = any(d == "/tmp" or d.startswith("/tmp/") for d in write_dirs)
    if not any_write_dir_under_tmp:
        args += ["--tmpfs", "/tmp"]

    for d in write_dirs:
        args += ["--bind", d, d]

    args += ["--chdir", cwd, "--"]
    args += ["/bin/sh", "-c", command]
    return args


def _build_unshare_command(command: str, write_dirs: List[str], allow_network: bool, cwd: str) -> List[str]:
    script = _build_unshare_script(command, write_dirs, cwd)
    args = ["unshare", "--mount", "--map-root-user"]
    if not allow_network:
        args.append("--net")
    args += ["sh", "-c", script]
    return args


def _build_unshare_script(command: str, write_dirs: List[str], cwd: str) -> str:
    """Builds the shell script run inside the new mount namespace.

    Rough edge, stated plainly: this remounts every currently-mounted
    filesystem read-only (except pseudo-filesystems and the requested
    write directories), discovered via `findmnt` at sandbox-creation time.
    That covers the overwhelmingly common case of a single root filesystem
    plus standard pseudo-mounts correctly. A system with unusual extra
    mount points that are neither a write dir nor safely remountable
    read-only (some network filesystems, some overlay setups) may see a
    command fail where bubblewrap would have handled it more gracefully -
    install bubblewrap for the fully robust version of this. This backend
    exists for the (common) case where bubblewrap isn't installed at all,
    not as a permanent substitute for it.
    """
    write_dir_set = "\n".join(f'  {shlex.quote(d)})' for d in write_dirs)
    bind_writable = "\n".join(
        f"mount --bind {shlex.quote(d)} {shlex.quote(d)} 2>/dev/null && "
        f"mount -o remount,bind,rw {shlex.quote(d)} 2>/dev/null"
        for d in write_dirs
    )

    skip_prefixes_sh = " ".join(shlex.quote(p) for p in _UNSHARE_SKIP_PREFIXES)
    write_dirs_sh = " ".join(shlex.quote(d) for d in write_dirs)

    # Mounting a fresh tmpfs over /tmp gives commands general scratch space
    # even when /tmp isn't one of the explicitly requested write dirs - but
    # doing that unconditionally would shadow any write dir that happens to
    # live under /tmp (extremely common - most temp/test directories do),
    # since a new mount at a parent path hides whatever was mounted/visible
    # under the old view of that path, in either order. Only replace /tmp
    # wholesale when nothing the caller asked to keep writable depends on
    # the *existing* contents of /tmp being reachable.
    any_write_dir_under_tmp = any(d == "/tmp" or d.startswith("/tmp/") for d in write_dirs)
    tmp_scratch_line = "" if any_write_dir_under_tmp else "mount -t tmpfs tmpfs /tmp 2>/dev/null"

    return f"""
set -f
mount --make-rprivate / 2>/dev/null

is_skipped() {{
  target="$1"
  for prefix in {skip_prefixes_sh}; do
    case "$target" in
      "$prefix"|"$prefix"/*) return 0 ;;
    esac
  done
  for d in {write_dirs_sh}; do
    case "$target" in
      "$d"|"$d"/*) return 0 ;;
    esac
  done
  return 1
}}

# Remount everything mounted under / read-only, deepest paths first, except
# pseudo-filesystems and the directories this command is allowed to write to.
findmnt -R -n -o TARGET / 2>/dev/null | awk '{{ print length, $0 }}' | sort -rn | cut -d' ' -f2- | \\
while IFS= read -r target; do
  if ! is_skipped "$target"; then
    mount -o remount,bind,ro "$target" 2>/dev/null
  fi
done

{tmp_scratch_line}

{bind_writable}

cd {shlex.quote(cwd)} 2>/dev/null
exec sh -c {shlex.quote(command)}
"""


def _build_seatbelt_command(command: str, write_dirs: List[str], allow_network: bool, cwd: str) -> List[str]:
    """Generates a macOS Seatbelt profile and runs the command under it via
    `sandbox-exec`. Written to mirror the Linux backends' semantics
    (deny-by-default filesystem writes outside `write_dirs`, deny network
    unless `allow_network`) but not executable-tested - see the module
    docstring."""
    write_literals = " ".join(f'(subpath "{d}")' for d in write_dirs)
    network_rule = "(allow network*)" if allow_network else "(deny network*)"

    profile = f"""(version 1)
(allow default)
(deny file-write* (subpath "/"))
(allow file-write* {write_literals if write_dirs else '(subpath "/dev/null")'})
{network_rule}
"""

    import tempfile
    profile_fd, profile_path = tempfile.mkstemp(suffix=".sb")
    with os.fdopen(profile_fd, "w") as f:
        f.write(profile)

    return ["sandbox-exec", "-f", profile_path, "/bin/sh", "-c", f"cd {shlex.quote(cwd)} 2>/dev/null; {command}"]
