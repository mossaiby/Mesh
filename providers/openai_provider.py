from typing import List, Dict, Any, Optional, AsyncGenerator
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

    async def stream_chat(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams completion responses. Yields dictionary objects containing
        either incremental content text, reasoning/CoT tokens, or tool call fragments.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model_config.model_id,
            "messages": messages,
            "stream": True
        }
        if tools:
            kwargs["tools"] = tools
            # Explicitly request "auto" tool choice. This is the implicit
            # default per the OpenAI spec when omitted, but several local
            # OpenAI-compatible backends (llama.cpp server, LM Studio, etc.)
            # don't reliably switch on tool-calling/grammar-constrained
            # decoding unless tool_choice is present in the request body.
            kwargs["tool_choice"] = "auto"

        response_stream = await self.client.chat.completions.create(**kwargs)

        async for chunk in response_stream:
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