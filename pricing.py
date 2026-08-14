import fnmatch
import json
import os
from typing import Dict, Tuple


class PricingManager:
    """
    Loads pricing.json pricing tables (input/output cost per 1M tokens)
    and computes real-time USD costs per turn and session.
    Applies prompt cache read discounts when cached tokens are present.
    """
    def __init__(self, filepath: str = "pricing.json"):
        self.filepath = filepath
        self.prices: Dict[str, Dict[str, float]] = {}
        self.load_pricing()

    def load_pricing(self) -> None:
        if not os.path.exists(self.filepath):
            self.prices = {"default": {"input": 0.0, "output": 0.0}}
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.prices = data.get("prices_per_1m_tokens", {})
        except Exception:
            self.prices = {"default": {"input": 0.0, "output": 0.0}}

    def get_token_cost(
        self,
        model_key: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0
    ) -> Tuple[float, float, float]:
        """
        Calculates (input_cost, output_cost, total_cost) in $ USD for token usage.
        Rates are specified in pricing.json per 1,000,000 tokens.
        Applies prompt cache discounts for cached input tokens.
        """
        rates = None
        m_key_lower = model_key.lower()

        if model_key in self.prices:
            rates = self.prices[model_key]
        else:
            for pattern, r_dict in self.prices.items():
                if fnmatch.fnmatch(m_key_lower, pattern.lower()):
                    rates = r_dict
                    break

        if not rates:
            rates = self.prices.get("default", {"input": 0.0, "output": 0.0})

        input_rate = rates.get("input", 0.0)
        output_rate = rates.get("output", 0.0)

        default_discount = 0.10 if ("anthropic" in m_key_lower or "deepseek" in m_key_lower) else 0.50
        cache_factor = rates.get("cache_read_factor", default_discount)

        actual_cached = min(prompt_tokens, max(0, cached_tokens))
        uncached_prompt_tokens = max(0, prompt_tokens - actual_cached)

        uncached_input_cost = (uncached_prompt_tokens / 1_000_000.0) * input_rate
        cached_input_cost = (actual_cached / 1_000_000.0) * input_rate * cache_factor
        input_cost = uncached_input_cost + cached_input_cost

        output_cost = (completion_tokens / 1_000_000.0) * output_rate
        total_cost = input_cost + output_cost

        return input_cost, output_cost, total_cost


# Global pricing manager instance
pricing_manager = PricingManager()
