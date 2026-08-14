"""
Mesh unified color theme.

Every part of the application prints through the single shared `console`
instance defined here instead of instantiating its own `rich.console.Console()`.
This guarantees one consistent, semantic color palette across the entire CLI.

Semantic styles:
    brand    - Mesh branding / startup & shutdown banners
    success  - successful operations, "enabled"/"connected" states
    error    - failures, denials, "disabled"/"disconnected" states
    warning  - cautions, hints, destructive-ish actions (clear, disable)
    label    - field labels / keys in status & listing output
    accent   - highlighted values, active selections, secondary emphasis
    info     - informational headers (e.g. the assistant reply header)
    text     - plain emphasized text
    muted    - de-emphasized/secondary text (maps to rich's built-in "dim")
    tool     - highlighted tool names during tool call dispatch and result display
"""
from rich.console import Console
from rich.theme import Theme

MESH_THEME = Theme(
    {
        "brand": "bold magenta",
        "success": "bold green",
        "error": "bold red",
        "warning": "yellow",
        "label": "bold yellow",
        "accent": "bold cyan",
        "info": "bold blue",
        "text": "bold white",
        "muted": "dim",
        "tool": "bold yellow",
    }
)

# Single shared console instance
console = Console(theme=MESH_THEME)
