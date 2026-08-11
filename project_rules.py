import os
from typing import Optional, Tuple
from theme import console

PROJECT_RULE_FILENAMES = ["PROJECT.md", "MESH.md", "AGENTS.md", ".mesh/rules.md"]


def find_and_read_project_rules(root_dir: str = ".") -> Tuple[Optional[str], str]:
    """
    Scans root_dir for project rule files (PROJECT.md, MESH.md, AGENTS.md, .mesh/rules.md).
    Returns (filename_found, content).
    """
    for filename in PROJECT_RULE_FILENAMES:
        path = os.path.join(root_dir, filename)
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                    if content:
                        return filename, content
            except Exception:
                pass
    return None, ""


def get_project_rules_instructions(root_dir: str = ".") -> str:
    """Renders project rules into a Markdown section suitable for system prompt injection."""
    filename, content = find_and_read_project_rules(root_dir)
    if not filename or not content:
        return ""

    return f"## Project Instructions & Architecture Rules ({filename})\n{content}"