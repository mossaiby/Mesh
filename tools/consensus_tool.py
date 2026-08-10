from typing import Dict, Any, Optional
from tools.base import BaseTool
import consensus


class ConsensusTool(BaseTool):
    name = "consult_consensus"
    description = (
        "Runs an adversarial multi-model consensus audit before executing critical or high-risk "
        "operations. Models cross-examine proposed solutions to eliminate bugs and security flaws."
    )
    is_proxied = False
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The goal, task, or question being addressed."
            },
            "proposal": {
                "type": "string",
                "description": "The proposed code, command, or architectural plan to audit."
            },
            "auditor_model": {
                "type": "string",
                "description": "Optional: model key for the red-team auditor (defaults to advisor_model)."
            }
        },
        "required": ["question", "proposal"]
    }

    def __init__(self, config_mgr):
        self._config_mgr = config_mgr

    async def execute(self, question: str, proposal: str, auditor_model: Optional[str] = None) -> Dict[str, Any]:
        return await consensus.get_consensus(
            question=question,
            proposal=proposal,
            config_mgr=self._config_mgr,
            auditor_model=auditor_model
        )