from typing import Dict, Any, Optional
from config import ConfigManager
from providers import get_provider
from render.stream_renderer import StreamRenderer
from theme import console


AUDITOR_SYSTEM_PROMPT = (
    "You are Mesh's Red-Team Security & Correctness Auditor. Another model proposed "
    "a solution or plan. Your job is to critically examine it for security bugs, "
    "unhandled edge cases, performance flaws, or logical assumptions.\n\n"
    "Be direct and rigorous. Highlight any vulnerabilities, side-effects, or flaw risks."
)

REFEREE_SYSTEM_PROMPT = (
    "You are Mesh's Consensus Referee. Review the original Proposal and the Auditor's critique. "
    "Produce a final, verified consensus recommendation incorporating all fixes."
)


async def get_consensus(
    question: str,
    proposal: str,
    config_mgr: ConfigManager,
    proposer_model: Optional[str] = None,
    auditor_model: Optional[str] = None
) -> Dict[str, Any]:
    p_model = proposer_model or config_mgr.config.active_model
    a_model = auditor_model or config_mgr.config.advisor_model or config_mgr.config.active_model

    console.print(f"\n[brand]⚖️  Multi-Model Consensus Loop:[/brand] Auditing proposal using [accent]{a_model}[/accent]...")

    renderer = StreamRenderer()

    # Stage 1: Auditor Pass
    try:
        a_model_cfg, a_provider_cfg = config_mgr.get_model_and_provider(a_model)
        auditor_provider = get_provider(a_model_cfg, a_provider_cfg, config_mgr)

        audit_prompt = [
            {"role": "system", "content": AUDITOR_SYSTEM_PROMPT},
            {"role": "user", "content": f"Task/Question: {question}\n\nProposed Solution:\n{proposal}"}
        ]

        critique_text, _ = await renderer.render_stream(auditor_provider.stream_chat(audit_prompt))

    except Exception as e:
        return {"status": "error", "error": f"Auditor model failed: {e}"}

    # Stage 2: Referee Synthesis
    try:
        referee_prompt = [
            {"role": "system", "content": REFEREE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Task: {question}\n\nOriginal Proposal:\n{proposal}\n\nAuditor Critique:\n{critique_text}"
            }
        ]

        p_model_cfg, p_provider_cfg = config_mgr.get_model_and_provider(p_model)
        referee_provider = get_provider(p_model_cfg, p_provider_cfg, config_mgr)

        consensus_text, _ = await renderer.render_stream(referee_provider.stream_chat(referee_prompt))

        return {
            "status": "success",
            "proposer_model": p_model,
            "auditor_model": a_model,
            "original_proposal": proposal,
            "critique": critique_text.strip(),
            "consensus_recommendation": consensus_text.strip()
        }

    except Exception as e:
        return {"status": "error", "error": f"Referee synthesis failed: {e}"}
