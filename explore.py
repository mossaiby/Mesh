import asyncio
import json
from typing import Dict, Any, List, Optional
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
from render.stream_renderer import StreamRenderer
import delegation
from theme import console


STRATEGY_GENERATOR_SYSTEM_PROMPT = (
    "You are Mesh's Speculative Strategy Generator. Given a task, generate distinct, "
    "non-overlapping, highly concrete strategies or hypotheses to solve or investigate "
    "the task. Each strategy must be a clear, actionable mission statement for an autonomous sub-agent.\n\n"
    "Respond with ONLY a single JSON object in this exact shape:\n"
    '{"strategies": ["Strategy 1 description...", "Strategy 2 description...", ...]}\n\n'
    "No markdown fences, no extra text."
)

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


def _safe_parse_json(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(raw[start:end + 1])
            except Exception:
                return {}
        else:
            return {}
    return data if isinstance(data, dict) else {}


async def generate_dynamic_strategies(
    task: str,
    config_mgr: ConfigManager,
    num_branches: Optional[int] = None
) -> List[str]:
    branches = num_branches if num_branches is not None else config_mgr.config.turns.branches
    prompt = [
        {"role": "system", "content": STRATEGY_GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": f"Task: {task}\nNumber of distinct strategies requested: {branches}"}
    ]

    try:
        model_cfg, provider_cfg = config_mgr.get_active_model_and_provider()
        provider = OpenAIProvider(model_cfg, provider_cfg)
        renderer = StreamRenderer()

        raw_text, _ = await renderer.render_stream(provider.stream_chat(prompt))
        data = _safe_parse_json(raw_text)
        strategies = data.get("strategies") or []
        if isinstance(strategies, list) and len(strategies) > 0:
            return [str(s).strip() for s in strategies if str(s).strip()][:branches]
    except Exception:
        pass

    return [
        f"Approach 1 (Direct): Investigate and solve '{task}' directly using standard conventions.",
        f"Approach 2 (Defensive / Validation): Investigate '{task}' focusing on edge-case validation and error bounds.",
        f"Approach 3 (Alternative Structural): Investigate '{task}' exploring alternative architecture patterns."
    ][:branches]


async def explore_branches(
    task: str,
    strategies: Optional[List[str]],
    tool_registry: Any,
    config_mgr: ConfigManager,
    num_branches: Optional[int] = None,
    max_turns: Optional[int] = None,
    debug_mode: bool = False
) -> Dict[str, Any]:
    branches_count = num_branches if num_branches is not None else config_mgr.config.turns.branches
    num_branches = min(max(2, branches_count), 5)
    turns_limit = max_turns if max_turns is not None else config_mgr.config.turns.agent

    if not strategies:
        console.print(f"[brand]🧠 Strategy Generator:[/brand] Synthesizing {num_branches} custom mission statements for task...")
        strategies = await generate_dynamic_strategies(task, config_mgr, num_branches=num_branches)

    console.print(f"\n[brand]🌳 Speculative Exploration Swarm:[/brand] Launching {len(strategies)} parallel branches:\n")

    for i, strat in enumerate(strategies, 1):
        console.print(f"  [accent]▶ Branch {i}:[/accent] {strat}")
    console.print()

    async def run_branch(idx: int, strategy: str) -> Dict[str, Any]:
        branch_task = f"Overall Objective: {task}\n\nYour Assigned Branch Strategy/Mission: {strategy}"
        
        res = await delegation.run_delegated_task(
            task=branch_task,
            tool_registry=tool_registry,
            config_mgr=config_mgr,
            max_turns=turns_limit,
            verbose=debug_mode
        )
        res["strategy"] = strategy
        res["branch_id"] = idx + 1

        if debug_mode:
            console.print(f"\n[brand]🔧 DEBUG - Branch {idx + 1} Output:[/brand]")
            console.print(f"[dim]Turns Used: {res.get('turns_used', 0)} | Tool Calls: {len(res.get('tool_calls', []))}[/dim]")
            if res.get("report"):
                console.print(f"[dim]{res['report']}[/dim]\n")

        return res

    branch_results = await asyncio.gather(*(run_branch(i, strat) for i, strat in enumerate(strategies)))

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
        renderer = StreamRenderer()

        synthesis_text, _ = await renderer.render_stream(provider.stream_chat(messages))

        return {
            "status": "success",
            "task": task,
            "strategies": strategies,
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
