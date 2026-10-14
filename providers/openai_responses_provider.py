import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncGenerator
from providers.openai_chat_provider import OpenAIProvider
from providers.retry import get_retry_params, compute_backoff_delay, is_transient_error
from theme import console
from glyphs import HOURGLASS


class OpenAIResponsesProvider(OpenAIProvider):
    """
    Provider for the OpenAI Responses API (POST /v1/responses).

    Mesh keeps its conversation in Chat Completions message format, so this class
    converts messages/tools to Responses items on the way out and maps streaming
    events back to the same {"type": content|reasoning|tool_calls|usage} events the
    other providers emit. Client construction and model discovery are inherited.
    """

    # ------------------------------------------------------------------ conversion
    @staticmethod
    def _convert_content(content: Any, role: str) -> Any:
        """Converts chat message content (str or list of parts) to Responses content."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content

        text_type = "output_text" if role == "assistant" else "input_text"
        parts: List[Dict[str, Any]] = []
        for part in content:
            if isinstance(part, str):
                parts.append({"type": text_type, "text": part})
                continue
            ptype = part.get("type")
            if ptype in ("text", "input_text", "output_text"):
                parts.append({"type": text_type, "text": part.get("text", "")})
            elif ptype == "image_url" and role != "assistant":
                image = part.get("image_url")
                url = image.get("url") if isinstance(image, dict) else image
                if url:
                    parts.append({"type": "input_image", "image_url": url})
            elif ptype == "input_image" and role != "assistant":
                parts.append(part)
        return parts or ""

    def _convert_messages(self, messages: List[Dict[str, Any]]):
        instructions: List[str] = []
        items: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role")

            if role == "system":
                content = msg.get("content")
                if isinstance(content, list):
                    content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
                if content:
                    instructions.append(content)

            elif role == "user":
                items.append({"role": "user", "content": self._convert_content(msg.get("content"), "user") or " "})

            elif role == "assistant":
                text = self._convert_content(msg.get("content"), "assistant")
                if text:
                    items.append({"role": "assistant", "content": text})
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function", {}) or {}
                    args = fn.get("arguments", "{}")
                    if not isinstance(args, str):
                        args = json.dumps(args)
                    items.append({
                        "type": "function_call",
                        "call_id": tc.get("id") or "call_1",
                        "name": fn.get("name", ""),
                        "arguments": args or "{}",
                    })

            elif role == "tool":
                output = msg.get("content")
                if not isinstance(output, str):
                    output = json.dumps(output) if output is not None else ""
                items.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id", ""),
                    "output": output,
                })

        return "\n\n".join(instructions), items

    @staticmethod
    def _convert_tools(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        converted = []
        for t in tools or []:
            fn = t.get("function", {}) or {}
            converted.append({
                "type": "function",
                "name": fn.get("name", "unnamed"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return converted

    # ------------------------------------------------------------------ streaming
    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        instructions, items = self._convert_messages(messages)

        kwargs: Dict[str, Any] = {
            "model": self.model_config.model_id,
            "input": items,
            "stream": True,
        }
        if instructions:
            kwargs["instructions"] = instructions

        converted_tools = self._convert_tools(tools)
        if converted_tools:
            kwargs["tools"] = converted_tools
            kwargs["tool_choice"] = "auto"

        cfg = self.config_mgr.config if self.config_mgr else None
        if cfg and cfg.thinking and self._is_reasoning_model():
            kwargs["reasoning"] = {"effort": cfg.effort.lower()}

        max_retries, initial_delay, max_delay, backoff_factor, jitter = get_retry_params(self.config_mgr)
        attempt = 0

        while True:
            attempt += 1
            yielded_any = False
            try:
                stream = await self.client.responses.create(**kwargs)

                call_index: Dict[int, int] = {}   # output_index -> tool call index
                args_sent: set = set()            # tool call indexes that already streamed arguments

                def register_call(output_index: int, item: Any) -> Dict[str, Any]:
                    idx = len(call_index)
                    call_index[output_index] = idx
                    return {
                        "type": "tool_calls",
                        "value": [{
                            "index": idx,
                            "id": getattr(item, "call_id", None) or getattr(item, "id", None) or f"call_{idx}",
                            "function": {"name": getattr(item, "name", "") or "", "arguments": ""},
                        }],
                    }

                def args_event(idx: int, arguments: str) -> Dict[str, Any]:
                    return {
                        "type": "tool_calls",
                        "value": [{"index": idx, "id": None, "function": {"name": None, "arguments": arguments}}],
                    }

                async for event in stream:
                    etype = getattr(event, "type", "")

                    if etype == "response.output_text.delta":
                        if event.delta:
                            yielded_any = True
                            yield {"type": "content", "value": event.delta}

                    elif etype in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
                        if event.delta:
                            yielded_any = True
                            yield {"type": "reasoning", "value": event.delta}

                    elif etype == "response.output_item.added":
                        if getattr(event.item, "type", "") == "function_call":
                            yielded_any = True
                            yield register_call(event.output_index, event.item)

                    elif etype == "response.function_call_arguments.delta":
                        idx = call_index.get(event.output_index)
                        if idx is not None and event.delta:
                            args_sent.add(idx)
                            yielded_any = True
                            yield args_event(idx, event.delta)

                    elif etype in ("response.function_call_arguments.done", "response.output_item.done"):
                        item = getattr(event, "item", None)
                        if etype == "response.output_item.done" and getattr(item, "type", "") != "function_call":
                            continue
                        arguments = getattr(item, "arguments", None) if item is not None else getattr(event, "arguments", None)
                        if event.output_index not in call_index and item is not None:
                            # Server never sent output_item.added; emit the whole call now.
                            yielded_any = True
                            yield register_call(event.output_index, item)
                        idx = call_index.get(event.output_index)
                        if idx is not None and idx not in args_sent and arguments:
                            args_sent.add(idx)
                            yielded_any = True
                            yield args_event(idx, arguments)

                    elif etype in ("response.completed", "response.incomplete"):
                        u = getattr(event.response, "usage", None)
                        if u:
                            cached = 0
                            details = getattr(u, "input_tokens_details", None)
                            if details:
                                cached = (details.get("cached_tokens", 0) if isinstance(details, dict)
                                          else getattr(details, "cached_tokens", 0)) or 0
                            yielded_any = True
                            yield {
                                "type": "usage",
                                "value": {
                                    "prompt_tokens": getattr(u, "input_tokens", 0) or 0,
                                    "completion_tokens": getattr(u, "output_tokens", 0) or 0,
                                    "cached_tokens": cached,
                                },
                            }

                    elif etype == "response.failed":
                        err = getattr(event.response, "error", None)
                        raise RuntimeError(f"Responses API request failed: {getattr(err, 'message', err) or 'unknown error'}")

                    elif etype == "error":
                        raise RuntimeError(f"Responses API error: {getattr(event, 'message', None) or event}")

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
                    f"[warning]{HOURGLASS} Provider rate limit/transient error ({exc.__class__.__name__}): "
                    f"retrying in {delay:.1f}s (attempt {attempt}/{max_retries})...[/warning]"
                )
                await asyncio.sleep(delay)
