import asyncio
from typing import AsyncGenerator, Dict, Any, Tuple
from rich.console import Group
from rich.live import Live
from rich.markdown import Markdown
from rich.styled import Styled
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
        Displays "Thinking..." in /debug off mode while reasoning models stream CoT tokens.

        In debug mode, the Chain-of-Thought (CoT) reasoning is rendered in dim Markdown
        and is ALWAYS preserved on screen, even when directly followed by tool execution.

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
                    
                    # 1. Reasoning / Thinking indicator logic (dimmed Markdown in debug_mode)
                    if accumulated_reasoning:
                        if debug_mode:
                            renderables.append(Styled(Markdown(accumulated_reasoning), "dim"))
                        elif not accumulated_content:
                            renderables.append(Text("Thinking...", style="dim italic"))
                            
                    # Blank line separator between CoT and final response content
                    if accumulated_reasoning and debug_mode and accumulated_content:
                        renderables.append(Text(""))

                    # 2. Response Markdown content
                    if accumulated_content:
                        renderables.append(Markdown(accumulated_content))
                        
                    # Update Live context atomically
                    if renderables:
                        live.update(Group(*renderables))
                    else:
                        live.update(Text("Waiting...", style="dim italic"))

                # Post-stream handling:
                # Permanent output that must NOT be removed on Live exit:
                # - Any accumulated response content.
                # - Any rendered CoT reasoning when debug_mode is enabled.
                has_permanent_output = bool(accumulated_content) or (debug_mode and bool(accumulated_reasoning))

                if transient_if_empty and not has_permanent_output:
                    live.transient = True
                else:
                    live.transient = False

        except (KeyboardInterrupt, asyncio.CancelledError):
            raise

        return accumulated_content, accumulated_reasoning
