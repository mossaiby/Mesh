from typing import Callable, Awaitable, Dict, List

CommandHandler = Callable[[List[str]], Awaitable[None]]


class CommandRegistry:
    def __init__(self):
        self._commands: Dict[str, CommandHandler] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, name: str, description: str, handler: CommandHandler) -> None:
        self._commands[f"/{name}"] = handler
        self._descriptions[f"/{name}"] = description

    def is_command(self, text: str) -> bool:
        return text.strip().startswith("/")

    async def dispatch(self, text: str) -> bool:
        parts = text.strip().split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in self._commands:
            await self._commands[cmd](args)
            return True
        return False

    def list_commands(self) -> Dict[str, str]:
        return self._descriptions
