import asyncio
from typing import AsyncGenerator, Dict, Any, Tuple
from rich.console import Group
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text
from theme import console


class StreamRenderer:
    def __init__(self):
        self.console = console

    async def render_stream(
        self, 
        async_chunk_generator: AsyncGenerator[Dict[str, Any], None],
        debug_mode: bool = False,
        transient_if_empty: bool = True
    ) -> Tuple[str, str]:
        """
        Consumes chunks (reasoning & content) and streams them cleanly.
        Displays "Waiting..." until the first token arrives.
        Displays "Thinking..." in /debug off mode while reasoning models stream CoT tokens,
        and replaces it once response content arrives.

        If no response content is received (e.g. tool call turns), clears the status
        indicator on exit so "Thinking..." / "Waiting..." does not persist on screen.

        Returns: (accumulated_content, accumulated_reasoning)
        """
        accumulated_content = ""
        accumulated_reasoning = ""
        
        try:
            with Live(
                Text("Waiting...", style="dim italic"),
                console=self.console,
                refresh_per_second=12,
                vertical_overflow="visible"
            ) as live:
                async for chunk in async_chunk_generator:
                    ctype = chunk["type"]
                    cval = chunk["value"]
                    
                    if ctype == "reasoning":
                        accumulated_reasoning += cval
                    elif ctype == "content":
                        accumulated_content += cval
                    
                    renderables = []
                    
                    # 1. Reasoning / Thinking indicator logic
                    if accumulated_reasoning:
                        if debug_mode:
                            renderables.append(Text(accumulated_reasoning, style="dim italic"))
                        elif not accumulated_content:
                            renderables.append(Text("Thinking...", style="dim italic"))
                            
                    # 2. Response Markdown content
                    if accumulated_content:
                        renderables.append(Markdown(accumulated_content))
                        
                    # Update Live context atomically
                    if renderables:
                        live.update(Group(*renderables))
                    else:
                        live.update(Text("Waiting...", style="dim italic"))

                # Post-stream handling:
                # If there is no accumulated content (e.g. tool call turn or empty response),
                # mark Live as transient so Rich erases "Thinking..." / "Waiting..." on exit.
                if transient_if_empty and not accumulated_content:
                    live.transient = True

        except (KeyboardInterrupt, asyncio.CancelledError):
            raise

        return accumulated_content, accumulated_reasoning