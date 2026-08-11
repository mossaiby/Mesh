import asyncio
from typing import Dict, Any
from config import ConfigManager
import delegation
from theme import console


async def run_iterative_test_loop(
    test_command: str,
    tool_registry: Any,
    config_mgr: ConfigManager,
    max_iterations: int = 5
) -> Dict[str, Any]:
    """
    Executes a test/build command in an automated loop:
    Runs command -> captures errors -> spawns repair sub-agent -> re-tests -> repeats until green.
    """
    console.print(f"\n[brand]🔄 Iterative Test Loop Started:[/brand] Executing '[accent]{test_command}[/accent]' (Max Iterations: {max_iterations})\n")

    shell_tool = tool_registry._tools.get("run_shell_command")
    if not shell_tool:
        return {"status": "error", "error": "Shell execution tool 'run_shell_command' is not registered."}

    for iteration in range(1, max_iterations + 1):
        console.print(f"[label]Iteration {iteration}/{max_iterations}:[/label] Running test command...")

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

        # Failure output
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
            max_turns=6,
            verbose=False
        )

        console.print(f"[dim]Sub-agent repair attempt {iteration} complete. Re-testing...[/dim]\n")

    return {
        "status": "failed",
        "message": f"Test command '{test_command}' failed to pass within {max_iterations} iterations.",
        "last_output": error_output[:1000]
    }