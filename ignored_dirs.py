"""
Canonical set of directory names that every directory-walking tool in Mesh
should prune before descending into them.

This used to be defined independently (and inconsistently) in a couple of
places - `symbol_search.py`'s indexer and `tools/native_tools.py`'s
`GrepTool` each had their own slightly different copy of this list, which is
exactly the kind of drift that lets a directory slip through unnoticed by one
tool but not another. Everything that walks a directory tree should import
`IGNORED_DIRS` from here instead of hardcoding its own copy.

Why this matters: Mesh's own `bootstrap` script creates the project's virtual
environment *inside* the repository (`Mesh/.venv`), so any tool - or any
ad-hoc script the model writes with `execute_python` - that walks the project
root without excluding `.venv` will also walk every installed dependency's
`site-packages`, often thousands of extra files. That's a real failure mode
Mesh has hit in practice, not a hypothetical: it inflates results with noise
at best, and at worst runs a script long enough to blow through its own
timeout.
"""

IGNORED_DIRS = frozenset({
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "target",
    "build",
    "dist",
    ".mesh",
    ".tox",
    ".pytest_cache",
    ".hypothesis",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "custom_tools",
})


def should_skip_dir(name: str) -> bool:
    """Whether a directory (by basename, not full path) should be pruned
    from a walk. Covers the explicit ignore list above plus any other
    dot-directory (matching the convention already used by every walker
    in this codebase)."""
    return name in IGNORED_DIRS or (name.startswith(".") and name not in (".", ".."))


def filter_dirs(dirs):
    """Convenience helper for the `os.walk()` in-place-pruning idiom:

        for root, dirs, files in os.walk(path):
            dirs[:] = filter_dirs(dirs)
    """
    return [d for d in dirs if not should_skip_dir(d)]


def path_is_ignored(path: str) -> bool:
    """Whether any component of a (relative or absolute) path is an
    ignored directory. Useful for post-filtering results that were
    produced by something that can't prune mid-walk, like `glob.glob()`."""
    import os
    parts = path.replace("\\", "/").split("/")
    return any(should_skip_dir(p) for p in parts)
