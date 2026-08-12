import asyncio
from typing import Dict, Any, List, Optional
from config import ConfigManager
import delegation
from theme import console


SQUAD_ROLES = [
    {
        "role": "Architect",
        "prompt": "Role: Software Architect. Analyze the task, design the technical solution, specify file structures, and create a clear step-by-step implementation plan."
    },
    {
        "role": "Coder",
        "prompt": "Role: Senior Developer. Execute the implementation plan using file tools (write_file, edit_file) to write clean, maintainable, working code."
    },
    {
        "role": "Test Engineer",
        "prompt": "Role: QA & Test Engineer. Write unit tests or test scripts and verify execution to ensure the implementation works correctly."
    },
    {
        "role": "Security Auditor",
        "prompt": "Role: Security Auditor. Review the implemented code and test results for security vulnerabilities, edge cases, or performance issues, and present the final verified report."
    }
]


async def run_squad_pipeline(
    task: str,
    tool_registry: Any,
    config_mgr: ConfigManager,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Coordinates 4 specialized sub-agent personas (Architect -> Coder -> Test Engineer -> Security Auditor)
    in an automated sequential pipeline to complete a task.
    """
    console.print(f"\n[brand]👥 Multi-Role Autonomous Task Squad:[/brand] Starting 4-stage pipeline for:\n  [italic]{task}[/italic]\n")

    pipeline_outputs: List[Dict[str, Any]] = []
    accumulated_context = f"Main Task: {task}\n"
    turns_limit = config_mgr.config.turns.agent

    for step in SQUAD_ROLES:
        role_name = step["role"]
        role_prompt = step["prompt"]

        console.print(f"  [accent]▶ Stage [{role_name}]:[/accent] Executing stage...")

        stage_task = f"{role_prompt}\n\nPipeline Context So Far:\n{accumulated_context}\n\nDeliverable for {role_name}: Perform your specific role for the task."

        res = await delegation.run_delegated_task(
            task=stage_task,
            tool_registry=tool_registry,
            config_mgr=config_mgr,
            max_turns=turns_limit,
            verbose=verbose
        )

        report = res.get("report", "No output generated.")
        pipeline_outputs.append({
            "role": role_name,
            "status": res.get("status", "unknown"),
            "report": report
        })

        accumulated_context += f"\n--- Output from {role_name} ---\n{report}\n"

    final_report = pipeline_outputs[-1]["report"] if pipeline_outputs else "Squad pipeline failed."

    return {
        "status": "success",
        "task": task,
        "final_report": final_report,
        "stages": pipeline_outputs
    }
