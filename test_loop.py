import asyncio
from typing import Dict, Any, Optional
from config import ConfigManager
import delegation
from theme import console


async def run_iterative_test_loop(
    test_command: str,
    tool_registry: Any,
    config_mgr: ConfigManager,
    max_iterations: Optional[int] = None
) -> Dict[str, Any]:
    """
    Executes a test/build command in an automated loop:
    Runs command -> captures errors -> spawns repair sub-agent -> re-tests -> repeats until green.
    """
    iterations_limit = max_iterations if max_iterations is not None else config_mgr.config.turns.loop
    console.print(f"\n[brand]🔄 Iterative Test Loop Started:[/brand] Executing '[accent]{test_command}[/accent]' (Max Iterations: {iterations_limit})\n")

    shell_tool = tool_registry._tools.get("shell")
    if not shell_tool:
        return {"status": "error", "error": "Shell execution tool 'shell' is not registered."}

    agent_turns = config_mgr.config.turns.agent

    for iteration in range(1, iterations_limit + 1):
        console.print(f"[label]Iteration {iteration}/{iterations_limit}:[/label] Running test command...")

        exec_res = await shell_tool.execute(command=test_command)
        exit_code = exec_res.get("exit_code", 1)
        stdout = exec_res.get("stdout", "")
        stderr = exec_res.get("stderr", "")

        if exit_code == 0:
            console.print(f"\n[success]🎉 All tests passed green on iteration {iteration}![/success]\n")
            return {
                "status": "success",
                "iterations_used": iteration,
                "test_command": test_command,
                "output": stdout or stderr
            }

        error_output = (stdout + "\n" + stderr).strip()
        console.print(f"[warning]⚠️ Tests failed on iteration {iteration} (Exit Code: {exit_code}).[/warning] Spawning repair sub-agent...")

        repair_task = (
            f"The test command '{test_command}' failed with exit code {exit_code}.\n\n"
            f"Error Logs:\n{error_output[:2500]}\n\n"
            f"Objective: Investigate the code and tests using your tools, modify the codebase to fix the errors, "
            f"and make sure '{test_command}' will pass."
        )

        repair_res = await delegation.run_delegated_task(
            task=repair_task,
            tool_registry=tool_registry,
            config_mgr=config_mgr,
            max_turns=agent_turns,
            verbose=False
        )

        if repair_res.get("status") == "error":
            console.print(f"[error]Repair sub-agent failed on iteration {iteration}: {repair_res.get('error', 'unknown error')}[/error]\n")
            return {
                "status": "failed",
                "message": f"Repair sub-agent errored on iteration {iteration}: {repair_res.get('error', 'unknown error')}",
                "last_output": error_output[:1000]
            }

        console.print(f"[dim]Sub-agent repair attempt {iteration} complete. Re-testing...[/dim]\n")

    return {
        "status": "failed",
        "message": f"Test command '{test_command}' failed to pass within {iterations_limit} iterations.",
        "last_output": error_output[:1000]
    }
