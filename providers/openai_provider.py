import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from openai import AsyncOpenAI
from config import ModelConfig, ProviderConfig


class OpenAIProvider:
    def __init__(self, model_config: ModelConfig, provider_config: ProviderConfig):
        self.model_config = model_config
        self.provider_config = provider_config
        
        client_kwargs: Dict[str, Any] = {
            "base_url": provider_config.base_url,
            "api_key": provider_config.api_key,
        }
        if provider_config.default_headers:
            client_kwargs["default_headers"] = provider_config.default_headers

        self.client = AsyncOpenAI(**client_kwargs)

    @staticmethod
    async def fetch_available_models(provider_config: ProviderConfig) -> Tuple[bool, List[str], str]:
        """
        Queries the provider's /models REST endpoint to discover models offered by the provider.
        Returns (success, list_of_model_ids, error_message).
        """
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

    async def stream_chat(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams completion responses. Yields dictionary objects containing
        incremental content text, reasoning/CoT tokens, tool call fragments,
        or exact API token usage metadata.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model_config.model_id,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True}
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response_stream = await self.client.chat.completions.create(**kwargs)

        async for chunk in response_stream:
            # Yield usage metadata if returned in final stream chunk
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

            # Extract reasoning/CoT tokens (supported by DeepSeek, Groq, OpenRouter, Ollama)
            reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            if reasoning:
                yield {"type": "reasoning", "value": reasoning}
            
            if delta.content:
                yield {"type": "content", "value": delta.content}
            
            if delta.tool_calls:
                yield {"type": "tool_calls", "value": delta.tool_calls}