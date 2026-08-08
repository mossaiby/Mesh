import asyncio
import sys
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.live import Live
from rich.text import Text
from tools.base import BaseTool

console = Console()


def _read_single_key() -> str:
    """Reads a single keypress or arrow key event cross-platform without requiring Enter."""
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            ch2 = msvcrt.getch()
            if ch2 == b'H':
                return "up"
            elif ch2 == b'P':
                return "down"
        elif ch in (b'\r', b'\n'):
            return "enter"
        elif ch == b'\x03':
            raise KeyboardInterrupt()
        return ch.decode('utf-8', errors='ignore')
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A':
                        return "up"
                    elif ch3 == 'B':
                        return "down"
                return "escape"
            elif ch in ('\r', '\n'):
                return "enter"
            elif ch == '\x03':
                raise KeyboardInterrupt()
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


class AskUserTool(BaseTool):
    name = "ask_user"
    description = "Asks the human user a question with interactive arrow-key option selection or free-form text input."
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question or decision prompt to present to the user."
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of pre-defined choices for the user (e.g. ['Approve', 'Reject', 'Modify'])."
            },
            "allow_custom": {
                "type": "boolean",
                "description": "Whether to allow free-form custom text input (default: true)."
            }
        },
        "required": ["question"]
    }

    async def execute(self, question: str, options: Optional[List[str]] = None, allow_custom: bool = True) -> Dict[str, Any]:
        console.print(f"\n[bold yellow]❓ AI Decision Prompt:[/bold yellow] {question}")

        # If no options provided, fallback to standard text input
        if not options:
            loop = asyncio.get_running_loop()
            user_response = await loop.run_in_executor(None, lambda: input("Your Answer > ").strip())
            return {"question": question, "user_response": user_response}

        # Prepare menu options
        choices = list(options)
        custom_marker = "[ Type Custom Answer ]"
        if allow_custom:
            choices.append(custom_marker)

        current_idx = 0

        def render_menu(selected_idx: int) -> Text:
            lines = ["[dim]Use ↑/↓ Arrow Keys to navigate, Enter to select:[/dim]\n"]
            for idx, choice in enumerate(choices):
                if idx == selected_idx:
                    lines.append(f"  [bold cyan]❯ 🔘 {choice}[/bold cyan]")
                else:
                    lines.append(f"    [dim]⚪ {choice}[/dim]")
            return Text.from_markup("\n".join(lines))

        def interactive_menu() -> str:
            # Fallback for non-interactive / piped terminals
            if not sys.stdin.isatty():
                console.print("[cyan]Options:[/cyan]")
                for i, o in enumerate(choices, 1):
                    console.print(f"  {i}. {o}")
                raw = input("Choice > ").strip()
                if raw.isdigit() and 1 <= int(raw) <= len(choices):
                    selected = choices[int(raw) - 1]
                    if selected == custom_marker:
                        return input("Custom Answer > ").strip()
                    return selected
                return raw

            nonlocal current_idx
            with Live(render_menu(current_idx), console=console, auto_refresh=False, vertical_overflow="visible") as live:
                while True:
                    live.update(render_menu(current_idx), refresh=True)
                    try:
                        key = _read_single_key()
                    except Exception:
                        break

                    if key == "up":
                        current_idx = (current_idx - 1) % len(choices)
                    elif key == "down":
                        current_idx = (current_idx + 1) % len(choices)
                    elif key == "enter":
                        break

            selected_choice = choices[current_idx]
            if selected_choice == custom_marker:
                console.print("[bold yellow]Custom Choice Selected:[/bold yellow]")
                return input("Custom Answer > ").strip()
            else:
                console.print(f"[bold green]Selected:[/bold green] {selected_choice}")
                return selected_choice

        loop = asyncio.get_running_loop()
        user_response = await loop.run_in_executor(None, interactive_menu)

        return {
            "question": question,
            "user_response": user_response
        }