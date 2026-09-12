import os
import sys
import glob
import re
import fnmatch
import asyncio
import difflib
import zlib
import subprocess
from typing import Dict, Any, Optional, Tuple, List
from tools.base import BaseTool
from tools.permissions import PermissionManager, default_permission_manager
from file_history import file_history_tracker
from hooks import hook_manager
from config import default_timeout
import symbol_search
from ignored_dirs import IGNORED_DIRS, filter_dirs, path_is_ignored


def compute_line_hash(line: str) -> str:
    """Computes a stable 4-character hex hash for a line of text."""
    clean = line.rstrip("\r\n")
    return f"{zlib.crc32(clean.encode('utf-8')) & 0xffff:04x}"


def write_text_exact(path: str, content: str) -> None:
    """Writes UTF-8 text byte-faithfully: no OS newline translation, no injected CR."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)


def detect_dominant_eol(lines: List[str]) -> str:
    """Returns the dominant line ending ('\r\n' or '\n') among the given lines."""
    crlf = sum(1 for ln in lines if ln.endswith("\r\n"))
    lf = sum(1 for ln in lines if ln.endswith("\n") and not ln.endswith("\r\n"))
    return "\r\n" if crlf > lf else "\n"


def _normalize_eol(text: str, eol: str) -> str:
    """Normalizes every newline in text to the given EOL style."""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    return unified if eol == "\n" else unified.replace("\n", eol)


def split_physical_lines(text: str) -> List[str]:
    """
    Splits text into physical lines keeping their terminators, treating only
    CRLF, CR and LF as line boundaries (same records file.readlines() yields,
    and the way editors/git/python tracebacks number lines).

    str.splitlines() must NOT be used for line-oriented file editing: it also
    breaks on VT/FF (\\x0b, \\x0c), FS/GS/RS (\\x1c-\\x1e), NEL (\\x85), U+2028
    and U+2029. When such characters appear inside a file's content,
    str.splitlines() invents phantom line breaks, desynchronizing read_file
    line numbers/hashes from hash_edit/edit_file (every subsequent hash_edit
    then fails with off-by-N hash mismatches).
    """
    parts = re.split(r"(\r\n|\r|\n)", text)
    lines = [parts[i] + parts[i + 1] for i in range(0, len(parts) - 1, 2)]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _collapse_ws(text: str) -> str:
    """Canonical form for similarity scoring: collapses per-line whitespace."""
    return "\n".join(" ".join(segment.split()) for segment in text.splitlines())


def splice_line_range(
    lines: List[str],
    start_idx: int,
    end_idx: int,
    new_str: str
) -> List[str]:
    """
    Line-oriented splice shared by edit_file (fuzzy branch) and hash_edit.

    - Empty new_str deletes lines[start_idx:end_idx] entirely (no phantom newline).
    - Otherwise new_str is normalized to the file's dominant EOL, and a bare
      (newline-less) new_str inherits the replaced range's terminator so the
      following line stays properly separated.
    """
    if new_str == "":
        return lines[:start_idx] + lines[end_idx:]

    replaced = lines[start_idx:end_idx]
    prev_ending = ""
    if replaced:
        last = replaced[-1]
        if last.endswith("\r\n"):
            prev_ending = "\r\n"
        elif last.endswith("\n"):
            prev_ending = "\n"

    tail = _normalize_eol(new_str, detect_dominant_eol(lines))
    if prev_ending and not tail.endswith(("\n", "\r")):
        tail += prev_ending
    return lines[:start_idx] + [tail] + lines[end_idx:]


def find_best_fuzzy_match(
    content_lines: List[str],
    old_str: str,
    threshold: float = 0.85,
    single_line_threshold: float = 0.95
) -> Tuple[bool, int, int, float]:
    """
    Searches for the best fuzzy match for old_str within content_lines.
    Returns (found, start_line_idx, end_line_idx, ratio).

    Similarity is computed on a whitespace-collapsed canonical form so that
    indentation-only drift does not mask a real match. Single-line windows are
    held to a stricter bar (raw ratio >= single_line_threshold, or identical
    after whitespace collapsing) because short strings let tiny but semantic
    edits (e.g. 'flag = 1' vs 'flag = 2' scores 0.875) clear the normal bar.
    """
    old_lines = split_physical_lines(old_str)
    n_old = len(old_lines)
    if n_old == 0 or not content_lines:
        return False, -1, -1, 0.0

    old_collapsed = _collapse_ws(old_str)
    best_ratio = 0.0
    best_start = -1
    best_end = -1

    window_sizes = [w for w in (n_old, n_old - 1, n_old + 1) if 1 <= w <= len(content_lines)]

    for w_size in window_sizes:
        for i in range(len(content_lines) - w_size + 1):
            window_text = "".join(content_lines[i : i + w_size])
            if w_size == 1:
                # Strict rule for single-line targets (see docstring).
                raw_ratio = difflib.SequenceMatcher(None, window_text, old_str).ratio()
                collapsed_ratio = difflib.SequenceMatcher(
                    None, _collapse_ws(window_text), old_collapsed
                ).ratio()
                if raw_ratio >= single_line_threshold or collapsed_ratio >= 0.999:
                    ratio = max(raw_ratio, collapsed_ratio)
                else:
                    ratio = 0.0
            else:
                ratio = difflib.SequenceMatcher(
                    None, _collapse_ws(window_text), old_collapsed
                ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_start = i
                best_end = i + w_size

    if best_ratio >= threshold and best_start != -1:
        return True, best_start, best_end, best_ratio

    return False, best_start, best_end, best_ratio


def get_fuzzy_edit_settings(config_mgr: Optional[Any] = None) -> Tuple[bool, float]:
    """
    Resolves fuzzy edit behavior from configuration (edit_settings.fuzzy_enabled /
    edit_settings.fuzzy_threshold) with safe fallbacks when no ConfigManager is
    available or the settings are missing (e.g. older config.json files).
    """
    enabled = True
    threshold = 0.85
    try:
        if config_mgr is not None:
            edit_cfg = getattr(config_mgr.config, "edit_settings", None)
            if edit_cfg is not None:
                enabled = bool(edit_cfg.fuzzy_enabled)
                try:
                    threshold = float(edit_cfg.fuzzy_threshold)
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return enabled, threshold


def resolve_fuzzy_edit_params(
    config_mgr: Optional[Any] = None,
    requested_threshold: Optional[float] = None
) -> Tuple[bool, float]:
    """
    Combines configured fuzzy edit defaults with an explicit per-call override.
    A non-None requested_threshold always wins over the configured value.
    """
    enabled, threshold = get_fuzzy_edit_settings(config_mgr)
    if requested_threshold is not None:
        try:
            threshold = float(requested_threshold)
        except (TypeError, ValueError):
            pass
    return enabled, threshold


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Reads text content from a file with optional line range and 4-character line hashes for hash_edit."
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read."},
            "start_line": {"type": "integer", "description": "Optional 1-based start line number."},
            "end_line": {"type": "integer", "description": "Optional 1-based end line number."},
            "show_hashes": {
                "type": "boolean",
                "description": "Optional: If true, formats output with 1-based line numbers and 4-character line hashes (e.g. 'L12|a3f1| content') for hash_edit."
            }
        },
        "required": ["path"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    async def execute(
        self,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        show_hashes: bool = False
    ) -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, path):
            return {"error": f"Permission denied for path '{path}'."}

        if not os.path.exists(path):
            return {"error": f"File '{path}' does not exist."}

        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
                lines = f.readlines()

            total_lines = len(lines)
            
            try:
                start_line_int = int(start_line) if start_line is not None else None
            except (ValueError, TypeError):
                start_line_int = None

            try:
                end_line_int = int(end_line) if end_line is not None else None
            except (ValueError, TypeError):
                end_line_int = None

            if start_line_int is not None and end_line_int is not None and end_line_int < start_line_int:
                return {"error": f"Invalid line range: end_line ({end_line_int}) cannot be less than start_line ({start_line_int})."}

            s_idx = (start_line_int - 1) if start_line_int and start_line_int > 0 else 0
            e_idx = end_line_int if end_line_int and end_line_int > 0 else total_lines

            selected_lines = lines[s_idx:e_idx]

            if show_hashes:
                formatted_lines = []
                for i, line_text in enumerate(selected_lines, start=s_idx + 1):
                    h = compute_line_hash(line_text)
                    clean_line = line_text.rstrip("\r\n")
                    formatted_lines.append(f"L{i}|{h}| {clean_line}")
                content_str = "\n".join(formatted_lines)
            else:
                content_str = "".join(selected_lines)

            return {
                "path": path,
                "total_lines": total_lines,
                "start_line": s_idx + 1,
                "end_line": min(e_idx, total_lines),
                "show_hashes": show_hashes,
                "content": content_str
            }
        except Exception as e:
            return {"error": f"Failed to read file '{path}': {str(e)}"}


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Writes content to a file (creates parent directories if needed)."
    is_proxied = True
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to write the file."},
            "content": {"type": "string", "description": "File content to write."}
        },
        "required": ["path", "content"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    async def execute(self, path: str, content: str) -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, path):
            return {"error": f"Permission denied for path '{path}'."}

        try:
            diff_text = file_history_tracker.record_edit(path, content, action="write_file")

            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            write_text_exact(path, content)

            # Hot update symbol index for modified file
            try:
                symbol_search.symbol_indexer.index_file(path)
            except Exception:
                pass

            res = {
                "status": "success",
                "message": f"Wrote {len(content)} characters to '{path}'.",
                "diff": diff_text
            }

            # Trigger post-edit linter hook
            linter_feedback = await hook_manager.run_post_edit_hooks_async(path)
            if linter_feedback:
                res["_linter_feedback"] = linter_feedback

            return res
        except Exception as e:
            return {"error": f"Failed to write file '{path}': {str(e)}"}


class EditFileTool(BaseTool):
    name = "edit_file"
    description = "Edits a file by replacing target string with new string. Supports exact matches and fuzzy block matching for slight whitespace differences."
    is_proxied = True
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit."},
            "old_str": {"type": "string", "description": "Exact target string or approximate code block to be replaced."},
            "new_str": {"type": "string", "description": "New replacement string."},
            "fuzzy_threshold": {
                "type": "number",
                "description": "Optional similarity threshold override for this edit (0.5-1.0); omit to use the configured default (/config set edit threshold)."
            }
        },
        "required": ["path", "old_str", "new_str"]
    }

    def __init__(
        self,
        permission_manager: Optional[PermissionManager] = None,
        config_mgr: Optional[Any] = None
    ):
        self.permission_manager = permission_manager or default_permission_manager
        self._config_mgr = config_mgr

    async def execute(
        self,
        path: str,
        old_str: str,
        new_str: str,
        fuzzy_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, path):
            return {"error": f"Permission denied for path '{path}'."}

        if not os.path.exists(path):
            return {"error": f"File '{path}' does not exist."}

        fuzzy_enabled, effective_threshold = resolve_fuzzy_edit_params(
            self._config_mgr, fuzzy_threshold
        )

        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
                content = f.read()

            match_method = "exact"
            if old_str in content:
                updated_content = content.replace(old_str, new_str, 1)
            elif fuzzy_enabled:
                content_lines = split_physical_lines(content)
                found, start_idx, end_idx, ratio = find_best_fuzzy_match(
                    content_lines, old_str, threshold=effective_threshold
                )
                if found:
                    match_method = f"fuzzy ({int(ratio * 100)}% similarity at lines {start_idx + 1}-{end_idx})"
                    updated_lines = splice_line_range(content_lines, start_idx, end_idx, new_str)
                    updated_content = "".join(updated_lines)
                else:
                    line_info = f"at line {start_idx + 1}" if start_idx != -1 else ""
                    sim_info = f" (closest match was {int(ratio * 100)}% similar {line_info})" if start_idx != -1 else ""
                    return {
                        "error": (
                            f"Target string 'old_str' not found in '{path}'{sim_info}. "
                            f"Try using read_file with show_hashes=True and hash_edit for exact line range replacements."
                        )
                    }
            else:
                # Fuzzy fallback is disabled via "/config set edit fuzzy off".
                return {
                    "error": (
                        f"Target string 'old_str' not found in '{path}'. "
                        f"Fuzzy fallback matching is disabled (/config set edit fuzzy off). "
                        f"Try using read_file with show_hashes=True and hash_edit for exact line range replacements."
                    )
                }

            diff_text = file_history_tracker.record_edit(path, updated_content, action="edit_file")

            write_text_exact(path, updated_content)

            # Hot update symbol index for modified file
            try:
                symbol_search.symbol_indexer.index_file(path)
            except Exception:
                pass

            res = {
                "status": "success",
                "message": f"Successfully updated '{path}' using {match_method} match.",
                "diff": diff_text
            }

            # Trigger post-edit linter hook
            linter_feedback = await hook_manager.run_post_edit_hooks_async(path)
            if linter_feedback:
                res["_linter_feedback"] = linter_feedback

            return res
        except Exception as e:
            return {"error": f"Failed to edit file '{path}': {str(e)}"}


class HashEditTool(BaseTool):
    name = "hash_edit"
    description = "Edits a file by verifying 4-character line hashes at start_line and end_line before replacing line range. Prevents silent edit collisions."
    is_proxied = True
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit."},
            "start_line": {"type": "integer", "description": "1-based start line number to replace."},
            "start_hash": {"type": "string", "description": "Expected 4-character line hash at start_line."},
            "end_line": {"type": "integer", "description": "1-based end line number to replace."},
            "end_hash": {"type": "string", "description": "Expected 4-character line hash at end_line."},
            "new_str": {"type": "string", "description": "New replacement string for the specified line range."}
        },
        "required": ["path", "start_line", "start_hash", "end_line", "end_hash", "new_str"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    async def execute(
        self,
        path: str,
        start_line: int,
        start_hash: str = None,
        end_line: int = None,
        end_hash: str = None,
        new_str: str = None
    ) -> Dict[str, Any]:
        # Friendly argument validation (prevents raw TypeError leaking to the model).
        missing = [arg for arg, val in (
            ("path", path),
            ("start_line", start_line),
            ("start_hash", start_hash),
            ("end_line", end_line),
            ("end_hash", end_hash),
            ("new_str", new_str),
        ) if val is None]
        if missing:
            return {
                "error": (
                    f"Missing required arguments for hash_edit: {', '.join(missing)}. "
                    f"Required signature: hash_edit(path, start_line, start_hash, end_line, end_hash, new_str). "
                    f"Get current line numbers and hashes via read_file with show_hashes=True."
                )
            }
        if not await self.permission_manager.check_and_request_permission(self.name, path):
            return {"error": f"Permission denied for path '{path}'."}

        if not os.path.exists(path):
            return {"error": f"File '{path}' does not exist."}

        try:
            start_line = int(start_line)
            end_line = int(end_line)
        except (ValueError, TypeError):
            return {"error": "start_line and end_line must be valid integers."}

        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
                content = f.read()

            lines = split_physical_lines(content)
            total_lines = len(lines)

            if start_line < 1 or start_line > total_lines:
                return {"error": f"start_line {start_line} out of range (file has {total_lines} lines)."}

            if end_line < start_line or end_line > total_lines:
                return {"error": f"end_line {end_line} invalid (must be between start_line {start_line} and total lines {total_lines})."}

            actual_start_hash = compute_line_hash(lines[start_line - 1])
            actual_end_hash = compute_line_hash(lines[end_line - 1])

            mismatches = []
            if not isinstance(start_hash, str) or len(start_hash.strip()) != 4:
                mismatches.append(
                    f"start_hash '{start_hash}' is malformed: expected a 4-character hash "
                    f"(found line {start_line} content starts with {repr(lines[start_line-1].strip()[:40])})."
                )
            if not isinstance(end_hash, str) or len(end_hash.strip()) != 4:
                mismatches.append(
                    f"end_hash '{end_hash}' is malformed: expected a 4-character hash "
                    f"(found line {end_line} content starts with {repr(lines[end_line-1].strip()[:40])})."
                )

            if not mismatches:
                if actual_start_hash.lower() != start_hash.lower().strip():
                    mismatches.append(f"start_line {start_line} hash mismatch: expected '{start_hash}', found '{actual_start_hash}' (content: {repr(lines[start_line-1].strip())})")

            if not mismatches:
                if actual_end_hash.lower() != end_hash.lower().strip():
                    mismatches.append(f"end_line {end_line} hash mismatch: expected '{end_hash}', found '{actual_end_hash}' (content: {repr(lines[end_line-1].strip())})")

            if mismatches:
                return {
                    "error": "Hash verification failed! File content has changed or line numbers were off:\n" + "\n".join(mismatches) + "\nRe-read the file using read_file with show_hashes=True."
                }

            updated_lines = splice_line_range(lines, start_line - 1, end_line, new_str)
            updated_content = "".join(updated_lines)

            diff_text = file_history_tracker.record_edit(path, updated_content, action="hash_edit")

            write_text_exact(path, updated_content)

            # Hot update symbol index for modified file
            try:
                symbol_search.symbol_indexer.index_file(path)
            except Exception:
                pass

            res = {
                "status": "success",
                "message": f"Successfully updated '{path}' (replaced lines {start_line}-{end_line} with verified hashes).",
                "diff": diff_text
            }

            # Trigger post-edit linter hook
            linter_feedback = await hook_manager.run_post_edit_hooks_async(path)
            if linter_feedback:
                res["_linter_feedback"] = linter_feedback

            return res

        except Exception as e:
            return {"error": f"Failed to hash_edit file '{path}': {str(e)}"}


class GlobTool(BaseTool):
    name = "glob_files"
    description = "Finds files matching a glob pattern (e.g., '**/*.py')."
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py')."},
            "root_dir": {"type": "string", "description": "Optional root directory (defaults to current directory)."}
        },
        "required": ["pattern"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    async def execute(self, pattern: str, root_dir: str = ".") -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, root_dir):
            return {"error": f"Permission denied for root directory '{root_dir}'."}

        try:
            search_pattern = os.path.join(root_dir, pattern)
            matches = glob.glob(search_pattern, recursive=True)
            # glob.glob() has no way to prune a directory mid-walk, so a
            # pattern like '**/*.py' still descends into .venv/node_modules
            # internally - filter those out of the results here so callers
            # never see (or spend tokens reading) dependency-tree noise.
            matches = [m for m in matches if not path_is_ignored(m)]
            return {"pattern": pattern, "matches": matches[:100], "count": len(matches)}
        except Exception as e:
            return {"error": f"Glob search failed: {str(e)}"}


class GrepTool(BaseTool):
    name = "grep"
    description = (
        "Searches for a regular expression pattern across files in a directory (recursively) "
        "or within a single file. Returns matching lines with 1-based line numbers and relative file paths."
    )
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression or search string to match."
            },
            "path": {
                "type": "string",
                "description": "Optional directory or specific file path to search (defaults to current directory '.')."
            },
            "file_pattern": {
                "type": "string",
                "description": "Optional glob pattern to filter target files (e.g. '*.py', '*.ts', '**/*.json')."
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Whether the search is case-sensitive (default: true)."
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matching lines to return (default: 100)."
            },
            "context_lines": {
                "type": "integer",
                "description": "Optional number of leading and trailing context lines to include per match (default: 0)."
            }
        },
        "required": ["pattern"]
    }

    IGNORED_DIRS = IGNORED_DIRS  # re-exported from ignored_dirs.py, the shared source of truth

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager or default_permission_manager

    @staticmethod
    def _is_binary_file(filepath: str) -> bool:
        """Heuristic check to skip binary files by detecting null bytes in header."""
        try:
            with open(filepath, "rb") as f:
                chunk = f.read(1024)
                return b"\x00" in chunk
        except Exception:
            return True

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: Optional[str] = None,
        case_sensitive: bool = True,
        max_results: int = 100,
        context_lines: int = 0,
        **kwargs: Any
    ) -> Dict[str, Any]:
        # Handle parameter aliases gracefully
        if "root_dir" in kwargs and (path == "." or not path):
            path = kwargs["root_dir"]
        if "include" in kwargs and file_pattern is None:
            file_pattern = kwargs["include"]
        if "ignore_case" in kwargs:
            case_sensitive = not bool(kwargs["ignore_case"])

        target_path = path or "."
        if not await self.permission_manager.check_and_request_permission(self.name, target_path):
            return {"error": f"Permission denied for path '{target_path}'."}

        if not os.path.exists(target_path):
            return {"error": f"Path '{target_path}' does not exist."}

        try:
            max_results_int = max(1, int(max_results)) if max_results is not None else 100
        except (ValueError, TypeError):
            max_results_int = 100

        try:
            context_lines_int = max(0, int(context_lines)) if context_lines is not None else 0
        except (ValueError, TypeError):
            context_lines_int = 0

        flags = 0
        if not case_sensitive:
            flags |= re.IGNORECASE

        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return {"error": f"Invalid regular expression pattern '{pattern}': {str(e)}"}

        files_to_search: List[Tuple[str, str]] = []

        if os.path.isfile(target_path):
            rel_name = os.path.relpath(target_path, ".").replace("\\", "/") if os.path.isabs(target_path) else target_path.replace("\\", "/")
            files_to_search.append((target_path, rel_name))
        else:
            for root, dirs, files in os.walk(target_path):
                dirs[:] = filter_dirs(dirs)
                for file in files:
                    if file_pattern and not fnmatch.fnmatch(file, file_pattern):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, ".").replace("\\", "/")
                    files_to_search.append((full_path, rel_path))

        matches: List[Dict[str, Any]] = []
        truncated = False

        for full_path, rel_path in files_to_search:
            if self._is_binary_file(full_path):
                continue

            try:
                with open(full_path, "r", encoding="utf-8", errors="replace", newline="") as f:
                    lines = f.readlines()
            except Exception:
                continue

            for idx, line in enumerate(lines):
                clean_line = line.rstrip("\r\n")
                if regex.search(clean_line):
                    match_item: Dict[str, Any] = {
                        "path": rel_path,
                        "line": idx + 1,
                        "content": clean_line
                    }
                    if context_lines_int > 0:
                        start_c = max(0, idx - context_lines_int)
                        end_c = min(len(lines), idx + context_lines_int + 1)
                        match_item["context"] = [
                            f"L{c_idx + 1}: {lines[c_idx].rstrip(chr(10)).rstrip(chr(13))}"
                            for c_idx in range(start_c, end_c)
                        ]

                    matches.append(match_item)
                    if len(matches) >= max_results_int:
                        truncated = True
                        break

            if truncated:
                break

        return {
            "pattern": pattern,
            "path": target_path,
            "count": len(matches),
            "matches": matches,
            "truncated": truncated
        }


class ShellTool(BaseTool):
    name = "shell"
    description = "Runs a shell command in the system environment and returns stdout/stderr."
    is_proxied = True
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "timeout": {
                "type": "number",
                "description": "Optional timeout in seconds. Omit to use the configured default. Set to 0 for infinite timeout."
            },
            "shell_prefix": {
                "type": "string",
                "description": "Optional shell processor wrapper (e.g. 'powershell -Command', 'cmd /c', 'wsl')."
            }
        },
        "required": ["command"]
    }

    def __init__(self, permission_manager: Optional[PermissionManager] = None, config_mgr: Optional[Any] = None):
        self.permission_manager = permission_manager or default_permission_manager
        self._config_mgr = config_mgr

    async def execute(self, command: str, timeout: Optional[float] = None, shell_prefix: Optional[str] = None) -> Dict[str, Any]:
        if not await self.permission_manager.check_and_request_permission(self.name, os.getcwd()):
            return {"error": "Permission denied for command execution in current working directory."}

        if timeout is None:
            timeout = self._config_mgr.config.timeouts.shell if self._config_mgr is not None else default_timeout("shell")

        full_command = f"{shell_prefix} {command}" if shell_prefix else command

        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                full_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            if timeout and timeout > 0:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            else:
                stdout, stderr = await proc.communicate()

            return {
                "command": full_command,
                "exit_code": proc.returncode,
                "stdout": stdout.decode('utf-8', errors='replace').strip(),
                "stderr": stderr.decode('utf-8', errors='replace').strip()
            }
        except (KeyboardInterrupt, asyncio.CancelledError):
            if proc:
                try:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    else:
                        proc.terminate()
                except Exception:
                    pass
            raise
        except asyncio.TimeoutError:
            if proc:
                try:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    else:
                        proc.terminate()
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            return {"error": f"Command execution timed out after {timeout} seconds."}
        except Exception as e:
            return {"error": f"Command execution failed: {str(e)}"}
