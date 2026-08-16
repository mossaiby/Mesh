import subprocess
import os
from typing import Dict, Any, List, Optional, Tuple
from config import ConfigManager
from providers import get_provider
from theme import console


COMMIT_MSG_SYSTEM_PROMPT = (
    "You are an expert Git Commit Message Generator. You will be given a `git diff` "
    "of changes in a repository. Generate a concise, professional Conventional Commit "
    "message (e.g., 'feat(cli): add git native workflow and /commit command' or "
    "'fix(guard): prevent infinite repair loop on guard blocks').\n\n"
    "Respond with ONLY the commit message text. No quotes, no markdown fences, no extra commentary."
)


def is_git_repository(root_dir: str = ".") -> bool:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_dir
        )
        return res.returncode == 0 and "true" in res.stdout.lower()
    except Exception:
        return False


def run_git_init(initial_branch: Optional[str] = "main", root_dir: str = ".") -> Tuple[bool, str]:
    """Initializes a new Git repository with a default initial branch (default: 'main')."""
    branch = initial_branch.strip() if initial_branch and initial_branch.strip() else "main"
    try:
        # Try modern git init -b <branch> (Git >= 2.28)
        res = subprocess.run(
            ["git", "init", "-b", branch],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_dir
        )
        if res.returncode != 0:
            # Fallback for older git versions
            res = subprocess.run(
                ["git", "init"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=root_dir
            )
            if res.returncode == 0 and branch:
                subprocess.run(
                    ["git", "checkout", "-B", branch],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=root_dir
                )

        if res.returncode == 0:
            output = res.stdout.strip() or f"Initialized empty Git repository on branch '{branch}'."
            return True, output
        return False, res.stderr.strip() or res.stdout.strip()
    except Exception as e:
        return False, f"Git init failed: {str(e)}"


def get_git_branch(root_dir: str = ".") -> str:
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_dir
        )
        return res.stdout.strip() or "HEAD"
    except Exception:
        return "unknown"


def get_git_status(root_dir: str = ".") -> Dict[str, Any]:
    if not is_git_repository(root_dir):
        return {"error": "Current directory is not a Git repository."}

    try:
        branch = get_git_branch(root_dir)
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_dir
        )
        lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
        return {
            "branch": branch,
            "changed_files_count": len(lines),
            "changes": lines
        }
    except Exception as e:
        return {"error": f"Failed to get git status: {str(e)}"}


def get_git_diff(staged: bool = False, root_dir: str = ".") -> str:
    if not is_git_repository(root_dir):
        return "Error: Not a Git repository."

    cmd = ["git", "diff", "--cached"] if staged else ["git", "diff"]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_dir
        )
        return res.stdout.strip() or "<no git diff output>"
    except Exception as e:
        return f"Error executing git diff: {str(e)}"


async def generate_commit_message(config_mgr: ConfigManager, root_dir: str = ".") -> str:
    diff_text = get_git_diff(staged=False, root_dir=root_dir)
    if not diff_text or diff_text == "<no git diff output>":
        diff_text = get_git_diff(staged=True, root_dir=root_dir)

    if not diff_text or diff_text == "<no git diff output>":
        return "chore: update workspace files"

    budget_chars = config_mgr.config.budgets.git_diff
    truncated_diff = diff_text[:budget_chars]

    messages = [
        {"role": "system", "content": COMMIT_MSG_SYSTEM_PROMPT},
        {"role": "user", "content": f"Git Diff:\n{truncated_diff}"}
    ]

    try:
        model_cfg, provider_cfg = config_mgr.get_active_model_and_provider()
        provider = get_provider(model_cfg, provider_cfg, config_mgr)

        msg_text = ""
        async for chunk in provider.stream_chat(messages):
            if chunk["type"] == "content":
                msg_text += chunk["value"]

        clean_msg = msg_text.strip().strip('"').strip("'")
        return clean_msg if clean_msg else "chore: update project files"
    except Exception:
        return "chore: update project files"


def run_git_commit(message: str, add_all: bool = True, root_dir: str = ".") -> Tuple[bool, str]:
    if not is_git_repository(root_dir):
        return False, "Directory is not a Git repository."

    try:
        if add_all:
            subprocess.run(
                ["git", "add", "-A"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=root_dir
            )

        res = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_dir
        )
        if res.returncode == 0:
            return True, res.stdout.strip()
        else:
            return False, res.stderr.strip() or res.stdout.strip()
    except Exception as e:
        return False, f"Git commit failed: {str(e)}"


def run_git_push(
    remote: str = "origin",
    branch: Optional[str] = None,
    force: bool = False,
    root_dir: str = "."
) -> Tuple[bool, str]:
    if not is_git_repository(root_dir):
        return False, "Directory is not a Git repository."

    target_branch = branch or get_git_branch(root_dir)
    cmd = ["git", "push", "-u", remote, target_branch]
    if force:
        cmd.append("--force-with-lease")

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_dir
        )
        if res.returncode == 0:
            output = res.stdout.strip() or res.stderr.strip() or "Pushed successfully."
            return True, output
        return False, res.stderr.strip() or res.stdout.strip()
    except Exception as e:
        return False, f"Git push failed: {str(e)}"


def create_or_switch_branch(branch_name: str, root_dir: str = ".") -> Tuple[bool, str]:
    if not is_git_repository(root_dir):
        return False, "Directory is not a Git repository."

    try:
        res = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root_dir
        )
        if res.returncode != 0:
            res = subprocess.run(
                ["git", "checkout", branch_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=root_dir
            )
        if res.returncode == 0:
            return True, f"Switched to branch '{branch_name}'."
        return False, res.stderr.strip()
    except Exception as e:
        return False, f"Branch operation failed: {str(e)}"
