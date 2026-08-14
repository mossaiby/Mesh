import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from openai import AsyncOpenAI
from config import ModelConfig, ProviderConfig, ConfigManager
from providers.retry import get_retry_params, compute_backoff_delay, is_transient_error
from theme import console


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
    async def fetch_available_models(provider_config: ProviderConfig, timeout: float = 12.0) -> Tuple[bool, List[str], str]:
        try:
            client_kwargs: Dict[str, Any] = {
                "base_url": provider_config.base_url,
                "api_key": provider_config.api_key,
            }
            if provider_config.default_headers:
                client_kwargs["default_headers"] = provider_config.default_headers

            client = AsyncOpenAI(**client_kwargs)
            response = await asyncio.wait_for(client.models.list(), timeout=timeout)
            model_ids = [m.id for m in response.data if hasattr(m, "id")]
            return True, sorted(model_ids), ""
        except Exception as e:
            return False, [], str(e)

    @staticmethod
    async def fetch_available_models_details(
        provider_config: ProviderConfig,
        timeout: float = 12.0,
        config_mgr: Optional[ConfigManager] = None
    ) -> Tuple[bool, List[Dict[str, Any]], str]:
        max_retries, initial_delay, max_delay, backoff_factor, jitter = get_retry_params(config_mgr)
        attempt = 0

        while True:
            attempt += 1
            try:
                client_kwargs: Dict[str, Any] = {
                    "base_url": provider_config.base_url,
                    "api_key": provider_config.api_key,
                }
                if provider_config.default_headers:
                    client_kwargs["default_headers"] = provider_config.default_headers

                client = AsyncOpenAI(**client_kwargs)
                response = await asyncio.wait_for(client.models.list(), timeout=timeout)
                
                models_details = []
                for m in response.data:
                    m_dict = {}
                    if hasattr(m, "model_dump"):
                        try:
                            m_dict = m.model_dump()
                        except Exception:
                            m_dict = {}
                    elif isinstance(m, dict):
                        m_dict = m
                    elif hasattr(m, "__dict__"):
                        m_dict = getattr(m, "__dict__", {})

                    m_id = getattr(m, "id", None) or m_dict.get("id")
                    if not m_id:
                        continue

                    ctx = None
                    for k in ("context_length", "context_window", "max_context_length", "max_input_tokens", "max_tokens"):
                        if k in m_dict and m_dict[k]:
                            try:
                                ctx = int(m_dict[k])
                                if ctx > 0:
                                    break
                            except (ValueError, TypeError):
                                pass

                    if not ctx and "top_provider" in m_dict and isinstance(m_dict["top_provider"], dict):
                        tp_ctx = m_dict["top_provider"].get("context_length")
                        if tp_ctx:
                            try:
                                ctx = int(tp_ctx)
                            except (ValueError, TypeError):
                                pass

                    desc = m_dict.get("description", "")
                    name = m_dict.get("name") or getattr(m, "name", None)

                    models_details.append({
                        "id": m_id,
                        "name": name or m_id.split("/")[-1].replace("-", " ").title(),
                        "context_window": ctx,
                        "description": desc or ""
                    })

                models_details.sort(key=lambda x: x["id"])
                return True, models_details, ""
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception as e:
                if not is_transient_error(e) or attempt > max_retries:
                    return False, [], str(e)
                delay = compute_backoff_delay(
                    attempt=attempt,
                    initial_delay=initial_delay,
                    max_delay=max_delay,
                    backoff_factor=backoff_factor,
                    jitter=jitter
                )
                await asyncio.sleep(delay)

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

        cfg = self.config_mgr.config if self.config_mgr else None
        if cfg and cfg.thinking and self._is_reasoning_model():
            kwargs["reasoning_effort"] = cfg.effort.lower()

        max_retries, initial_delay, max_delay, backoff_factor, jitter = get_retry_params(self.config_mgr)
        attempt = 0

        while True:
            attempt += 1
            yielded_any = False
            try:
                response_stream = await self.client.chat.completions.create(**kwargs)

                async for chunk in response_stream:
                    if hasattr(chunk, "usage") and chunk.usage:
                        u = chunk.usage
                        prompt_tokens = getattr(u, "prompt_tokens", 0) or 0
                        completion_tokens = getattr(u, "completion_tokens", 0) or 0

                        cached_tokens = 0
                        ptd = getattr(u, "prompt_tokens_details", None)
                        if ptd:
                            if isinstance(ptd, dict):
                                cached_tokens = ptd.get("cached_tokens", 0) or 0
                            else:
                                cached_tokens = getattr(ptd, "cached_tokens", 0) or 0

                        yielded_any = True
                        yield {
                            "type": "usage",
                            "value": {
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                                "cached_tokens": cached_tokens
                            }
                        }

                    if not chunk.choices:
                        continue
                    
                    delta = chunk.choices[0].delta

                    reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                    if reasoning:
                        yielded_any = True
                        yield {"type": "reasoning", "value": reasoning}
                    
                    if delta.content:
                        yielded_any = True
                        yield {"type": "content", "value": delta.content}
                    
                    if delta.tool_calls:
                        yielded_any = True
                        yield {"type": "tool_calls", "value": delta.tool_calls}

                return  # Stream completed successfully

            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception as exc:
                if not is_transient_error(exc) or attempt > max_retries or yielded_any:
                    raise

                delay = compute_backoff_delay(
                    attempt=attempt,
                    initial_delay=initial_delay,
                    max_delay=max_delay,
                    backoff_factor=backoff_factor,
                    jitter=jitter
                )
                console.print(
                    f"[warning]⏳ Provider rate limit/transient error ({exc.__class__.__name__}): "
                    f"retrying in {delay:.1f}s (attempt {attempt}/{max_retries})...[/warning]"
                )
                await asyncio.sleep(delay)
