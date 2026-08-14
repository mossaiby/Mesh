import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from config import ModelConfig, ProviderConfig, ConfigManager
from providers.retry import get_retry_params, compute_backoff_delay, is_transient_error
from theme import console

try:
    import anthropic
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class AnthropicProvider:
    def __init__(self, model_config: ModelConfig, provider_config: ProviderConfig, config_mgr: Optional[ConfigManager] = None):
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("The 'anthropic' Python SDK is required for Anthropic support. Run 'pip install anthropic'.")

        self.model_config = model_config
        self.provider_config = provider_config
        self.config_mgr = config_mgr

        client_kwargs: Dict[str, Any] = {
            "api_key": provider_config.api_key,
        }
        if provider_config.base_url and "api.anthropic.com" not in provider_config.base_url:
            client_kwargs["base_url"] = provider_config.base_url
        if provider_config.default_headers:
            client_kwargs["default_headers"] = provider_config.default_headers

        self.client = AsyncAnthropic(**client_kwargs)

    @staticmethod
    async def fetch_available_models_details(
        provider_config: ProviderConfig,
        timeout: float = 12.0,
        config_mgr: Optional[ConfigManager] = None
    ) -> Tuple[bool, List[Dict[str, Any]], str]:
        if not ANTHROPIC_AVAILABLE:
            return False, [], "The 'anthropic' Python SDK is required. Run 'pip install anthropic'."

        max_retries, initial_delay, max_delay, backoff_factor, jitter = get_retry_params(config_mgr)
        attempt = 0

        while True:
            attempt += 1
            try:
                client_kwargs: Dict[str, Any] = {
                    "api_key": provider_config.api_key,
                }
                if provider_config.base_url and "api.anthropic.com" not in provider_config.base_url:
                    client_kwargs["base_url"] = provider_config.base_url
                if provider_config.default_headers:
                    client_kwargs["default_headers"] = provider_config.default_headers

                client = AsyncAnthropic(**client_kwargs)
                response = await asyncio.wait_for(client.models.list(), timeout=timeout)
                
                models_details = []
                async for m in response:
                    m_id = m.id
                    m_name = getattr(m, "display_name", None) or m_id
                    models_details.append({
                        "id": m_id,
                        "name": m_name,
                        "context_window": 200000,
                        "description": f"{m_name} via Anthropic Official"
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

    def _convert_tools(self, tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        if not tools:
            return []

        converted = []
        for t in tools:
            fn = t.get("function", {})
            converted.append({
                "name": fn.get("name", "unnamed"),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}})
            })

        if converted:
            converted[-1]["cache_control"] = {"type": "ephemeral"}

        return converted

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        system_blocks = []
        anthropic_msgs = []

        for msg in messages:
            role = msg.get("role")

            if role == "system":
                content = msg.get("content") or ""
                if content:
                    system_blocks.append({
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"}
                    })

            elif role == "user":
                content = msg.get("content") or ""
                blocks = [{"type": "text", "text": content}] if content else [{"type": "text", "text": " "}]
                if anthropic_msgs and anthropic_msgs[-1]["role"] == "user":
                    if content:
                        anthropic_msgs[-1]["content"].append({"type": "text", "text": content})
                else:
                    anthropic_msgs.append({"role": "user", "content": blocks})

            elif role == "assistant":
                blocks = []
                text_content = msg.get("content")
                if text_content:
                    blocks.append({"type": "text", "text": text_content})

                tool_calls = msg.get("tool_calls") or []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    try:
                        parsed_args = json.loads(args) if isinstance(args, str) else args
                    except Exception:
                        parsed_args = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", "call_1"),
                        "name": fn.get("name", ""),
                        "input": parsed_args
                    })

                if not blocks:
                    blocks = [{"type": "text", "text": " "}]

                if anthropic_msgs and anthropic_msgs[-1]["role"] == "assistant":
                    anthropic_msgs[-1]["content"].extend(blocks)
                else:
                    anthropic_msgs.append({"role": "assistant", "content": blocks})

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                res_content = msg.get("content") or ""
                block = {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": res_content
                }
                if anthropic_msgs and anthropic_msgs[-1]["role"] == "user":
                    anthropic_msgs[-1]["content"].append(block)
                else:
                    anthropic_msgs.append({"role": "user", "content": [block]})

        return system_blocks, anthropic_msgs

    async def stream_chat(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        system_blocks, anthropic_msgs = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools)

        cfg = self.config_mgr.config if self.config_mgr else None
        thinking_enabled = cfg.thinking if cfg else True
        effort = cfg.effort if cfg else "medium"

        kwargs: Dict[str, Any] = {
            "model": self.model_config.model_id,
            "messages": anthropic_msgs,
        }

        if system_blocks:
            kwargs["system"] = system_blocks

        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        is_thinking_model = "3-7" in self.model_config.model_id or "thinking" in self.model_config.model_id
        if is_thinking_model and thinking_enabled:
            budget_map = {"low": 2048, "medium": 8192, "high": 16384}
            budget = budget_map.get(effort.lower(), 8192)
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            kwargs["max_tokens"] = max(20480, budget + 4096)
        else:
            kwargs["max_tokens"] = 8192

        max_retries, initial_delay, max_delay, backoff_factor, jitter = get_retry_params(self.config_mgr)
        attempt = 0

        while True:
            attempt += 1
            yielded_any = False
            try:
                prompt_tokens = 0
                completion_tokens = 0
                cache_read_tokens = 0
                cache_creation_tokens = 0

                async with self.client.messages.stream(**kwargs) as stream:
                    async for event in stream:
                        if event.type == "content_block_start":
                            block = event.content_block
                            if block.type == "tool_use":
                                yielded_any = True
                                yield {
                                    "type": "tool_calls",
                                    "value": [{
                                        "index": event.index,
                                        "id": block.id,
                                        "function": {"name": block.name, "arguments": ""}
                                    }]
                                }

                        elif event.type == "content_block_delta":
                            delta = event.delta
                            if delta.type == "text_delta":
                                yielded_any = True
                                yield {"type": "content", "value": delta.text}
                            elif delta.type == "thinking_delta":
                                yielded_any = True
                                yield {"type": "reasoning", "value": delta.thinking}
                            elif delta.type == "input_json_delta":
                                yielded_any = True
                                yield {
                                    "type": "tool_calls",
                                    "value": [{
                                        "index": event.index,
                                        "id": None,
                                        "function": {"name": None, "arguments": delta.partial_json}
                                    }]
                                }

                        elif event.type == "message_start":
                            if hasattr(event.message, "usage") and event.message.usage:
                                u = event.message.usage
                                prompt_tokens = getattr(u, "input_tokens", 0) or 0
                                cache_read_tokens = getattr(u, "cache_read_input_tokens", 0) or 0
                                cache_creation_tokens = getattr(u, "cache_creation_input_tokens", 0) or 0
                                yielded_any = True
                                yield {
                                    "type": "usage",
                                    "value": {
                                        "prompt_tokens": prompt_tokens,
                                        "completion_tokens": completion_tokens,
                                        "cached_tokens": cache_read_tokens,
                                        "cache_creation_tokens": cache_creation_tokens
                                    }
                                }

                        elif event.type == "message_delta":
                            if hasattr(event, "usage") and event.usage:
                                u = event.usage
                                completion_tokens = getattr(u, "output_tokens", 0) or 0
                                yielded_any = True
                                yield {
                                    "type": "usage",
                                    "value": {
                                        "prompt_tokens": prompt_tokens,
                                        "completion_tokens": completion_tokens,
                                        "cached_tokens": cache_read_tokens,
                                        "cache_creation_tokens": cache_creation_tokens
                                    }
                                }

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
