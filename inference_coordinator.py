import asyncio
import time
from typing import Optional, List, Dict, Any
from providers import get_provider
from pricing import pricing_manager
from compaction import maybe_auto_compact, estimate_tokens
import router
from theme import console


class InferenceCoordinator:
    """
    Coordinates multi-turn inference and response generation:
    1. Resolves active or dynamic router model.
    2. Checks and applies semantic auto-compaction.
    3. Streams provider responses, accumulating content, reasoning, usage, and tool calls.
    4. Computes per-turn and session metrics (tokens, costs, TTFT, tok/s).
    5. Formats assistant messages and delegates tool execution to ToolOrchestrator.
    6. Manages turn loops and rolls back on cancellation.
    """
    def __init__(self, engine: Any, tool_orchestrator: Any = None):
        self.engine = engine
        self.tool_orchestrator = tool_orchestrator

    @property
    def config_mgr(self):
        return self.engine.config_mgr

    @property
    def renderer(self):
        return self.engine.renderer

    @property
    def tool_registry(self):
        return self.engine.tool_registry

    @property
    def session_logger(self):
        return self.engine.session_logger

    async def process_inference(self, pre_prompt_count: Optional[int] = None) -> None:
        max_turns = self.config_mgr.config.turns.engine
        current_turn = 0
        rollback_count = pre_prompt_count if pre_prompt_count is not None else max(0, len(self.engine.messages) - 1)

        try:
            while current_turn < max_turns and self.engine.is_running:
                current_turn += 1

                # 1. Model resolution (auto-routing vs. static)
                if self.config_mgr.config.active_model == "auto":
                    latest_user_prompt = ""
                    for msg in reversed(self.engine.messages):
                        if msg.get("role") == "user":
                            latest_user_prompt = msg.get("content", "")
                            break

                    try:
                        chosen_key, route_reason = await router.select_model_for_prompt(
                            prompt=latest_user_prompt,
                            messages=self.engine.messages,
                            config_mgr=self.config_mgr
                        )
                        model_cfg, provider_cfg = self.config_mgr.get_model_and_provider(chosen_key)
                        console.print(f"[brand]🔀 Auto-routed prompt to [label]{chosen_key}[/label] ({model_cfg.name}):[/brand] [dim]{route_reason}[/dim]")
                    except Exception as e:
                        console.print(f"[error]Model Routing Error:[/error] {e}")
                        return
                else:
                    try:
                        model_cfg, provider_cfg = self.config_mgr.get_active_model_and_provider()
                    except Exception as e:
                        console.print(f"[error]Configuration Error:[/error] {e}")
                        return

                # 2. Semantic context auto-compaction
                self.engine.messages, auto_compacted, compact_details = await maybe_auto_compact(self.engine.messages, self.config_mgr)
                if auto_compacted:
                    console.print(f"[warning]📑   {compact_details}[/warning]")
                    self.session_logger.log_system_event(compact_details)

                # 3. Prepare tool schemas
                provider = get_provider(model_cfg, provider_cfg, self.config_mgr)
                schemas = self.tool_registry.get_schemas() if self.engine.tools_enabled else None
                if schemas and self.tool_registry.mode_blocked_tools:
                    schemas = [s for s in schemas if s["function"]["name"] not in self.tool_registry.mode_blocked_tools]

                tool_calls_to_run = []
                turn_prompt_tokens = 0
                turn_completion_tokens = 0
                turn_cached_tokens = 0

                t_start = time.perf_counter()
                t_first_token = None

                # 4. Stream response and capture tool calls / usage
                async def chunk_generator():
                    nonlocal turn_prompt_tokens, turn_completion_tokens, turn_cached_tokens, t_first_token
                    async for chunk in provider.stream_chat(self.engine.messages, tools=schemas):
                        ctype = chunk["type"]
                        cval = chunk["value"]

                        if t_first_token is None and ctype in ("content", "reasoning", "tool_calls"):
                            t_first_token = time.perf_counter()

                        if ctype == "usage":
                            turn_prompt_tokens = cval.get("prompt_tokens", 0)
                            turn_completion_tokens = cval.get("completion_tokens", 0)
                            turn_cached_tokens = cval.get("cached_tokens", 0)
                        elif ctype == "tool_calls" and self.engine.tools_enabled:
                            for tc in cval:
                                idx = tc.get("index", 0) if isinstance(tc, dict) else getattr(tc, "index", 0)
                                while len(tool_calls_to_run) <= idx:
                                    tool_calls_to_run.append({"id": "", "name": "", "args": ""})

                                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                                if tc_id:
                                    tool_calls_to_run[idx]["id"] = tc_id

                                fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
                                if fn:
                                    fn_name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)
                                    fn_args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", None)
                                    if fn_name:
                                        tool_calls_to_run[idx]["name"] = fn_name
                                    if fn_args:
                                        tool_calls_to_run[idx]["args"] += fn_args
                        else:
                            yield chunk

                console.print(f"\n[info]Assistant ({model_cfg.name} via {provider_cfg.name}) >[/info]")

                try:
                    response_text, reasoning_text = await self.renderer.render_stream(
                        chunk_generator(),
                        debug_mode=self.engine.debug_mode
                    )
                except Exception as e:
                    console.print(
                        f"\n[error]API/Provider Error ({provider_cfg.name}):[/error] "
                        f"Could not connect to [dim]{provider_cfg.base_url}[/dim].\n"
                        f"[error]Details: {str(e)}[/error]\n"
                        f"[warning]Tip: Ensure your local server (e.g. LM Studio / Ollama) is running, or switch models using /switch.[/warning]"
                    )
                    return

                t_end = time.perf_counter()

                if response_text:
                    self.session_logger.log_assistant_response(response_text, model_name=model_cfg.name)

                if turn_prompt_tokens == 0:
                    turn_prompt_tokens = estimate_tokens(self.engine.messages)
                if turn_completion_tokens == 0 and response_text:
                    turn_completion_tokens = max(1, len(response_text) // 4)

                turn_model_key = chosen_key if self.config_mgr.config.active_model == "auto" else self.config_mgr.config.active_model
                _, _, turn_cost = pricing_manager.get_token_cost(
                    turn_model_key,
                    turn_prompt_tokens,
                    turn_completion_tokens,
                    cached_tokens=turn_cached_tokens
                )

                self.engine.session_prompt_tokens += turn_prompt_tokens
                self.engine.session_completion_tokens += turn_completion_tokens
                self.engine.session_cached_tokens += turn_cached_tokens
                self.engine.session_cost_usd += turn_cost

                ttft_sec = (t_first_token - t_start) if t_first_token is not None else (t_end - t_start)
                gen_sec = (t_end - t_first_token) if t_first_token is not None else 0.0
                tps = (turn_completion_tokens / gen_sec) if gen_sec > 0.001 else 0.0

                cfg = self.config_mgr.config
                metrics_parts = []

                if cfg.show_tokens:
                    if turn_cached_tokens > 0:
                        metrics_parts.append(f"{turn_prompt_tokens} in ({turn_cached_tokens} cached), {turn_completion_tokens} out")
                    else:
                        metrics_parts.append(f"{turn_prompt_tokens} in, {turn_completion_tokens} out")

                if cfg.show_cost:
                    metrics_parts.append(f"${turn_cost:.4f} turn, ${self.engine.session_cost_usd:.4f} session")

                if cfg.show_statistics:
                    ttft_fmt = f"{ttft_sec*1000:.0f}ms" if ttft_sec < 1.0 else f"{ttft_sec:.2f}s"
                    metrics_parts.append(f"TTFT: {ttft_fmt}, {tps:.1f} tok/s")

                if metrics_parts:
                    console.print(f"[dim][{' | '.join(metrics_parts)}][/dim]\n")

                assistant_msg = {"role": "assistant"}
                if response_text:
                    assistant_msg["content"] = response_text

                # Filter out empty placeholder tool call slots from streaming gaps
                active_calls = [tc for tc in tool_calls_to_run if tc.get("name")]

                formatted_tool_calls = []
                if active_calls and self.engine.tools_enabled:
                    for i, tool_call in enumerate(active_calls):
                        tool_call_id = tool_call["id"] or f"call_{i+1}"
                        tool_call["id"] = tool_call_id

                        formatted_tool_calls.append({
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_call["name"],
                                "arguments": tool_call["args"]
                            }
                        })
                    assistant_msg["tool_calls"] = formatted_tool_calls

                self.engine.messages.append(assistant_msg)

                if not active_calls or not self.engine.tools_enabled:
                    break

                # 5. Delegate tool execution to ToolOrchestrator
                orchestrator = self.tool_orchestrator or getattr(self.engine, "tool_orchestrator", None)
                if orchestrator:
                    await orchestrator.execute_tool_calls(active_calls, self.engine.messages)
                else:
                    for tool_call in active_calls:
                        tool_result = await self.tool_registry.execute(tool_call["name"], tool_call["args"])
                        self.engine.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": tool_result
                        })

        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[warning]⛔ Turn cancelled by user.[/warning]\n")
            self.engine.messages = self.engine.messages[:rollback_count]
