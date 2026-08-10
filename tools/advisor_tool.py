from typing import Dict, Any, Optional
from tools.base import BaseTool
import advisor


class AdvisorTool(BaseTool):
    name = "consult_advisor"
    description = (
        "Consults an advisor for a candid second opinion before you proceed - use this "
        "when you're genuinely unsure between approaches, want a sanity check on a risky "
        "or hard-to-reverse plan, or want a different perspective before committing. The "
        "advisor has no tools and takes no action; it only gives an opinion. Don't use "
        "this for questions you can just answer yourself, or as a substitute for actually "
        "doing the task."
    )
    is_proxied = False  # A single focused opinion, not heavy output needing distillation.
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The specific question or decision you want advice on."
            },
            "context": {
                "type": "string",
                "description": "Optional background the advisor needs to give a useful answer (what you're trying to do, constraints, what you've already considered)."
            },
            "advisor_model": {
                "type": "string",
                "description": "Optional: a specific configured model key to consult instead of the default advisor model, if you want an opinion from a particular model."
            }
        },
        "required": ["question"]
    }

    def __init__(self, config_mgr):
        self._config_mgr = config_mgr

    async def execute(self, question: str, context: str = "", advisor_model: Optional[str] = None) -> Dict[str, Any]:
        return await advisor.get_advice(
            question=question,
            config_mgr=self._config_mgr,
            context=context,
            advisor_model=advisor_model
        )
