import asyncio
from typing import List, Dict, Any, Tuple
from rich.markup import escape
import reflexion
from theme import console


class ToolOrchestrator:
    """
    Orchestrates turn-level tool execution:
    1. Partitions requested tool calls into contiguous read-only vs. mutating batches.
    2. Concurrently executes read-only tool batches using asyncio.gather().
    3. Sequentially executes mutating and interactive tool calls.
    4. Logs tool calls, prints debug execution traces, and records reflexion failure events.
    5. Appends formatted tool response messages to the conversation history.
    """
    def __init__(self, engine: Any):
        self.engine = engine

    @property
    def tool_registry(self):
        return self.engine.tool_registry

    @property
    def session_logger(self):
        return self.engine.session_logger

    @property
    def debug_mode(self) -> bool:
        return getattr(self.engine, "debug_mode", False)

    def partition_tool_calls(
        self, active_calls: List[Dict[str, str]]
    ) -> List[Tuple[bool, List[Dict[str, str]]]]:
        """
        Partitions active_calls into contiguous groups:
        Contiguous read-only tool calls are batched together to run concurrently.
        Mutating / non-read-only calls are kept as individual sequential batches.
        """
        batches: List[Tuple[bool, List[Dict[str, str]]]] = []
        current_readonly_batch: List[Dict[str, str]] = []

        for tool_call in active_calls:
            if self.tool_registry.is_read_only(tool_call["name"], tool_call["args"]):
                current_readonly_batch.append(tool_call)
            else:
                if current_readonly_batch:
                    batches.append((True, current_readonly_batch))
                    current_readonly_batch = []
                batches.append((False, [tool_call]))

        if current_readonly_batch:
            batches.append((True, current_readonly_batch))

        return batches

    async def execute_tool_calls(
        self,
        active_calls: List[Dict[str, str]],
        messages: List[Dict[str, Any]]
    ) -> None:
        """
        Executes a list of active tool calls in batched/partitioned order,
        logging actions and appending tool responses directly to messages.
        """
        batches = self.partition_tool_calls(active_calls)

        for is_readonly, call_batch in batches:
            for tool_call in call_batch:
                name_escaped = escape(str(tool_call.get("name", "")))
                args_escaped = escape(str(tool_call.get("args", "")))
                if self.debug_mode:
                    console.print(f"[brand]🔧 DEBUG - Tool Request:[/brand] [tool]{name_escaped}[/tool]([dim]{args_escaped}[/dim])")
                else:
                    console.print(f"[accent]⚡ Tool Request:[/accent] [tool]{name_escaped}[/tool]([dim]{args_escaped}[/dim])")

            if is_readonly and len(call_batch) > 1:
                results = await asyncio.gather(*(self.tool_registry.execute(tc["name"], tc["args"]) for tc in call_batch))
            else:
                results = [await self.tool_registry.execute(call_batch[0]["name"], call_batch[0]["args"])]

            for tool_call, tool_result in zip(call_batch, results):
                self.session_logger.log_tool_call(tool_call["name"], tool_call["args"], tool_result)

                if self.debug_mode:
                    name_escaped = escape(str(tool_call.get("name", "")))
                    console.print(f"[brand]🔧 DEBUG - Tool Result ([tool]{name_escaped}[/tool]):[/brand]")
                    console.print(tool_result, markup=False)

                if isinstance(tool_result, str) and '"error":' in tool_result:
                    reflexion.record_reflexion_event(
                        event_type="tool_failure",
                        details=f"Tool '{tool_call['name']}' failed with args {tool_call['args']}: {tool_result[:300]}"
                    )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result
                })
