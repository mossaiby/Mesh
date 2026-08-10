import asyncio
import json
from typing import Dict, Any, List, Optional
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
import delegation
from theme import console


JUDGE_SYSTEM_PROMPT = (
    "You are Mesh's Speculative Branching Judge. Multiple autonomous sub-agents were "
    "spun up in parallel with distinct strategies to attempt the same task.\n\n"
    "Your job is to evaluate their reports and tool outputs, select the winning strategy "
    "or combine the best insights from multiple branches, and produce a unified final solution.\n\n"
    "Respond with concise Markdown containing:\n"
    "1. **Winning Branch / Strategy**: Name which approach worked best and why.\n"
    "2. **Key Insights & Tradeoffs**: Key findings discovered across all branches.\n"
    "3. **Synthesized Solution**: The unified, verified answer or code patch for the user."
)


async def explore_branches(
    task: str,
    strategies: Optional[List[str]],
    tool_registry: Any,
    config_mgr: ConfigManager,
    max_turns: int = 6
) -> Dict[str, Any]:
    """
    Spawns multiple parallel sub-agents with distinct strategies to attempt `task`.
    Evaluates branch reports using a Judge pass and synthesizes the winning solution.
    """
    if not strategies:
        # Auto-generate 3 distinct strategies using the active model
        strategies = [
            f"Approach 1 (Direct Implementation): Solve '{task}' using the most straightforward direct approach.",
            f"Approach 2 (Defensive / Edge-Case Heavy): Solve '{task}' with strict validation and edge-case handling.",
            f"Approach 3 (Alternative / Structural): Solve '{task}' using an alternative structural pattern or algorithm."
        ]

    console.print(f"\n[brand]🌲 Speculative Exploration Swarm:[/brand] Launching {len(strategies)} parallel branches for task:\n  [italic]{task}[/italic]\n")

    async def run_branch(idx: int, strategy: str) -> Dict[str, Any]:
        branch_task = f"Task: {task}\n\nAssigned Strategy for this Branch: {strategy}"
        console.print(f"  [accent]▶ Branch {idx + 1}:[/accent] [dim]{strategy}[/dim]")
        res = await delegation.run_delegated_task(
            task=branch_task,
            tool_registry=tool_registry,
            config_mgr=config_mgr,
            max_turns=max_turns,
            verbose=False
        )
        res["strategy"] = strategy
        res["branch_id"] = idx + 1
        return res

    branch_results = await asyncio.gather(*(run_branch(i, strat) for i, strat in enumerate(strategies)))

    # Format branch reports for Judge evaluation
    judge_input_lines = [f"Original Task: {task}\n"]
    for res in branch_results:
        b_id = res.get("branch_id", 0)
        strat = res.get("strategy", "")
        status = res.get("status", "unknown")
        report = res.get("report", "No report.")
        judge_input_lines.append(f"### Branch {b_id} [{status.upper()}]\nStrategy: {strat}\nReport:\n{report}\n")

    judge_content = "\n---\n".join(judge_input_lines)

    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": judge_content}
    ]

    try:
        model_cfg, provider_cfg = config_mgr.get_active_model_and_provider()
        provider = OpenAIProvider(model_cfg, provider_cfg)

        synthesis_text = ""
        async for chunk in provider.stream_chat(messages):
            if chunk["type"] == "content":
                synthesis_text += chunk["value"]

        return {
            "status": "success",
            "task": task,
            "synthesis": synthesis_text.strip(),
            "branches_evaluated": len(branch_results),
            "branch_reports": branch_results
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Branch evaluation failed: {str(e)}",
            "branch_reports": branch_results
        }