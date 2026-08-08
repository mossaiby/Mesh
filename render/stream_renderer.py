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
        debug_mode: bool = False
    ) -> Tuple[str, str]:
        """
        Consumes chunks (reasoning & content) and streams them cleanly.
        Unifies rendering through rich.console.Group inside Live context
        to avoid screen corruption and cursor overwrites.

        Returns: (accumulated_content, accumulated_reasoning)
        """
        accumulated_content = ""
        accumulated_reasoning = ""
        
        with Live(
            Text(""),
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
                
                # Render Chain of Thought in debug mode without borders
                if debug_mode and accumulated_reasoning:
                    renderables.append(Text(accumulated_reasoning, style="dim italic"))
                    
                # Render response Markdown
                if accumulated_content:
                    renderables.append(Markdown(accumulated_content))
                    
                # Update Live context atomically
                if renderables:
                    live.update(Group(*renderables))
                else:
                    live.update(Text(""))

        return accumulated_content, accumulated_reasoning