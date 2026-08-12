import asyncio
from typing import Callable, Awaitable, Dict, List, Tuple
from theme import console

CommandHandler = Callable[[List[str]], Awaitable[None]]


class CommandRegistry:
    def __init__(self):
        self._commands: Dict[str, CommandHandler] = {}
        self._descriptions: Dict[str, str] = {}
        self._categories: Dict[str, str] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: CommandHandler,
        category: str = "General"
    ) -> None:
        cmd_key = f"/{name}"
        self._commands[cmd_key] = handler
        self._descriptions[cmd_key] = description
        self._categories[cmd_key] = category

    def is_command(self, text: str) -> bool:
        return text.strip().startswith("/")

    async def dispatch(self, text: str) -> bool:
        parts = text.strip().split()
        if not parts:
            return False

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in self._commands:
            try:
                await self._commands[cmd](args)
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception as e:
                console.print(f"[error]Error executing command {cmd}:[/error] {e}")
            return True
        return False

    def list_commands(self) -> Dict[str, str]:
        return self._descriptions

    def list_commands_by_category(self) -> Dict[str, List[Tuple[str, str]]]:
        """Groups registered commands by category preserving insertion order."""
        categorized: Dict[str, List[Tuple[str, str]]] = {}
        for cmd, desc in self._descriptions.items():
            cat = self._categories.get(cmd, "General")
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append((cmd, desc))
        return categorized