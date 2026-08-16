from typing import Dict, Any, Optional
from tools.base import BaseTool
import git_workflow


class GitInitTool(BaseTool):
    name = "git_init"
    description = "Initializes a new Git repository in the current workspace directory."
    is_proxied = False
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "initial_branch": {
                "type": "string",
                "description": "Optional initial default branch name (default: 'main')."
            }
        }
    }

    async def execute(self, initial_branch: str = "main") -> Dict[str, Any]:
        success, output = git_workflow.run_git_init(initial_branch=initial_branch, root_dir=".")
        if success:
            return {"status": "success", "message": output, "branch": initial_branch}
        return {"status": "error", "error": output}


class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Gets the current Git branch and list of modified/untracked files."
    is_proxied = True
    parameters = {"type": "object", "properties": {}}

    async def execute(self) -> Dict[str, Any]:
        return git_workflow.get_git_status(".")


class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Gets the current Git diff (staged or unstaged) for the workspace repository."
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "Whether to get staged (--cached) diff instead of unstaged diff (default: false)."
            }
        }
    }

    async def execute(self, staged: bool = False) -> Dict[str, Any]:
        diff_text = git_workflow.get_git_diff(staged=staged, root_dir=".")
        return {"staged": staged, "diff": diff_text}


class GitCommitTool(BaseTool):
    name = "git_commit"
    description = "Stages all modified files and creates a Git commit with a commit message."
    is_proxied = False
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Conventional commit message."
            }
        },
        "required": ["message"]
    }

    async def execute(self, message: str) -> Dict[str, Any]:
        success, output = git_workflow.run_git_commit(message=message, add_all=True)
        if success:
            return {"status": "success", "message": message, "output": output}
        return {"status": "error", "error": output}


class GitPushTool(BaseTool):
    name = "git_push"
    description = "Pushes committed changes to a remote Git repository."
    is_proxied = False
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "remote": {
                "type": "string",
                "description": "Git remote name (default: 'origin')."
            },
            "branch": {
                "type": "string",
                "description": "Optional target branch name (defaults to active branch)."
            },
            "force": {
                "type": "boolean",
                "description": "Whether to use --force-with-lease (default: false)."
            }
        }
    }

    async def execute(self, remote: str = "origin", branch: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        success, output = git_workflow.run_git_push(remote=remote, branch=branch, force=force)
        if success:
            return {"status": "success", "remote": remote, "branch": branch, "output": output}
        return {"status": "error", "error": output}


class GitBranchTool(BaseTool):
    name = "git_branch"
    description = "Creates or switches to a Git feature branch."
    is_proxied = False
    requires_guard = True
    parameters = {
        "type": "object",
        "properties": {
            "branch_name": {
                "type": "string",
                "description": "Name of the git branch to create or switch to."
            }
        },
        "required": ["branch_name"]
    }

    async def execute(self, branch_name: str) -> Dict[str, Any]:
        success, msg = git_workflow.create_or_switch_branch(branch_name=branch_name)
        if success:
            return {"status": "success", "message": msg, "branch": branch_name}
        return {"status": "error", "error": msg}
