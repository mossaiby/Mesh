import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from openai import AsyncOpenAI
from config import ModelConfig, ProviderConfig, ConfigManager


class OpenAIProvider:
    def __init__(self, model_config: ModelConfig, provider_config: ProviderConfig, config_mgr: Optional[ConfigManager] = None):
        self.model_config = model_config
        self.provider_config = provider_config
        self.config_mgr = config_mgr
        
        client_kwargs: Dict[str, Any] = {
            "base_url": provider_config.base_url,
            "api_key": provider_config.api_key,
        }
        if provider_config.default_headers:
            client_kwargs["default_headers"] = provider_config.default_headers

        self.client = AsyncOpenAI(**client_kwargs)

    def _is_reasoning_model(self) -> bool:
        """Determines if the current model is a reasoning model that accepts reasoning_effort."""
        tags = [t.lower() for t in getattr(self.model_config, "tags", [])]
        if "reasoning" in tags or "thinking" in tags:
            return True
        
        m_id = (getattr(self.model_config, "model_id", "") or "").lower()
        m_name = (getattr(self.model_config, "name", "") or "").lower()
        
        reasoning_keywords = ("o1", "o3", "r1", "reasoning", "thinking", "nemotron")
        return any(k in m_id or k in m_name for k in reasoning_keywords)

    @staticmethod
    async def fetch_available_models(provider_config: ProviderConfig) -> Tuple[bool, List[str], str]:
        try:
            client_kwargs: Dict[str, Any] = {
                "base_url": provider_config.base_url,
                "api_key": provider_config.api_key,
            }
            if provider_config.default_headers:
                client_kwargs["default_headers"] = provider_config.default_headers

            client = AsyncOpenAI(**client_kwargs)
            response = await asyncio.wait_for(client.models.list(), timeout=12.0)
            model_ids = [m.id for m in response.data if hasattr(m, "id")]
            return True, sorted(model_ids), ""
        except Exception as e:
            return False, [], str(e)

    @staticmethod
    async def fetch_available_models_details(provider_config: ProviderConfig) -> Tuple[bool, List[Dict[str, Any]], str]:
        try:
            client_kwargs: Dict[str, Any] = {
                "base_url": provider_config.base_url,
                "api_key": provider_config.api_key,
            }
            if provider_config.default_headers:
                client_kwargs["default_headers"] = provider_config.default_headers

            client = AsyncOpenAI(**client_kwargs)
            response = await asyncio.wait_for(client.models.list(), timeout=12.0)
            
            models_details = []
            for m in response.data:
                m_id = getattr(m, "id", None)
                if not m_id:
                    continue
                
                ctx = getattr(m, "context_length", None) or getattr(m, "context_window", None)
                desc = getattr(m, "description", None)
                name = getattr(m, "name", None)

                models_details.append({
                    "id": m_id,
                    "name": name or m_id.split("/")[-1].replace("-", " ").title(),
                    "context_window": int(ctx) if ctx and str(ctx).isdigit() else None,
                    "description": desc or ""
                })

            models_details.sort(key=lambda x: x["id"])
            return True, models_details, ""
        except Exception as e:
            return False, [], str(e)

    async def stream_chat(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        kwargs: Dict[str, Any] = {
            "model": self.model_config.model_id,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True}
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # Apply reasoning effort controls ONLY for reasoning models
        cfg = self.config_mgr.config if self.config_mgr else None
        if cfg and cfg.thinking and self._is_reasoning_model():
            kwargs["reasoning_effort"] = cfg.effort.lower()

        response_stream = await self.client.chat.completions.create(**kwargs)

        async for chunk in response_stream:
            if hasattr(chunk, "usage") and chunk.usage:
                yield {
                    "type": "usage",
                    "value": {
                        "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(chunk.usage, "completion_tokens", 0)
                    }
                }

            if not chunk.choices:
                continue
            
            delta = chunk.choices[0].delta

            reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            if reasoning:
                yield {"type": "reasoning", "value": reasoning}
            
            if delta.content:
                yield {"type": "content", "value": delta.content}
            
            if delta.tool_calls:
                yield {"type": "tool_calls", "value": delta.tool_calls}