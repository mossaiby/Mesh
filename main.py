import asyncio
import sys
from rich.console import Console
from rich.panel import Panel
from config import ConfigManager
from providers.openai_provider import OpenAIProvider
from render.stream_renderer import StreamRenderer
from tools.registry import ToolRegistry, CalculatorTool
from commands.registry import CommandRegistry

console = Console()


class AIHarness:
    def __init__(self):
        self.config_mgr = ConfigManager()
        self.renderer = StreamRenderer()
        self.tool_registry = ToolRegistry()
        self.cmd_registry = CommandRegistry()
        self.debug_mode: bool = False
        
        self.messages = [
            {"role": "system", "content": "You are a helpful text-based AI assistant inside an interactive terminal CLI harness."}
        ]
        
        self.setup_defaults()

    def setup_defaults(self):
        self.tool_registry.register(CalculatorTool())
        
        self.cmd_registry.register("help", "Show available slash commands", self.cmd_help)
        self.cmd_registry.register("models", "List configured models and providers", self.cmd_models)
        self.cmd_registry.register("switch", "Switch active model (e.g., /switch llama3-openrouter)", self.cmd_switch)
        self.cmd_registry.register("clear", "Clear conversation context window", self.cmd_clear)
        self.cmd_registry.register("context", "Display current context window content", self.cmd_context)
        self.cmd_registry.register("debug", "Toggle or set debug mode (/debug on|off)", self.cmd_debug)
        self.cmd_registry.register("exit", "Exit the AI Harness application", self.cmd_exit)

    async def cmd_help(self, args):
        console.print("[bold green]Available Slash Commands:[/bold green]")
        for cmd, desc in self.cmd_registry.list_commands().items():
            console.print(f"  [bold yellow]{cmd}[/bold yellow] - {desc}")

    async def cmd_models(self, args):
        active = self.config_mgr.config.active_model
        console.print("[bold green]Configured Models:[/bold green]")
        for key, model_cfg in self.config_mgr.config.models.items():
            provider_cfg = self.config_mgr.config.providers.get(model_cfg.provider)
            provider_name = provider_cfg.name if provider_cfg else model_cfg.provider
            
            mark = "[bold cyan]*[/bold cyan]" if key == active else " "
            console.print(
                f"{mark} [bold yellow]{key}[/bold yellow] -> {model_cfg.name} via "
                f"[magenta]{provider_name}[/magenta] ([dim]{model_cfg.model_id}[/dim])"
            )

    async def cmd_switch(self, args):
        if not args:
            console.print("[red]Usage: /switch <model_key>[/red]")
            return
        try:
            self.config_mgr.set_active_model(args[0])
            console.print(f"[green]Switched active model to: {args[0]}[/green]")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")

    async def cmd_clear(self, args):
        self.messages = [self.messages[0]]
        console.print("[yellow]Conversation context cleared.[/yellow]")

    async def cmd_context(self, args):
        console.print(f"\n[bold green]Current Context Window ({len(self.messages)} messages):[/bold green]")
        for idx, msg in enumerate(self.messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", None)
            tool_call_id = msg.get("tool_call_id", None)

            header = f"[{idx}] Role: [bold yellow]{role}[/bold yellow]"
            if tool_call_id:
                header += f" | ID: {tool_call_id}"

            body_parts = []
            if content:
                body_parts.append(str(content))
            if tool_calls:
                body_parts.append(f"[dim italic]Tool Calls: {tool_calls}[/dim italic]")

            body = "\n".join(body_parts) if body_parts else "[dim]<empty>[/dim]"
            console.print(Panel(body, title=header, expand=False))
        console.print()

    async def cmd_debug(self, args):
        if not args:
            state_str = "[bold green]ON[/bold green]" if self.debug_mode else "[bold red]OFF[/bold red]"
            console.print(f"Debug mode is currently {state_str}. Usage: [yellow]/debug on[/yellow] or [yellow]/debug off[/yellow]")
            return

        arg = args[0].lower()
        if arg == "on":
            self.debug_mode = True
            console.print("[bold green]Debug mode enabled.[/bold green] CoT and Tool execution details will be shown.")
        elif arg == "off":
            self.debug_mode = False
            console.print("[yellow]Debug mode disabled.[/yellow] CoT will be hidden.")
        else:
            console.print("[red]Invalid debug option. Use '/debug on' or '/debug off'.[/red]")

    async def cmd_exit(self, args):
        console.print("[yellow]Exiting AI Harness. Goodbye![/yellow]")
        sys.exit(0)

    async def run(self):
        console.print("[bold magenta]AI Harness CLI Started.[/bold magenta] Type [yellow]/help[/yellow] for commands or start chatting.\n")
        
        while True:
            try:
                user_input = input("User > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ["exit", "quit", "/exit"]:
                    await self.cmd_exit([])

                if self.cmd_registry.is_command(user_input):
                    handled = await self.cmd_registry.dispatch(user_input)
                    if not handled:
                        console.print("[red]Unknown command. Type /help for options.[/red]")
                    continue

                self.messages.append({"role": "user", "content": user_input})
                await self.process_inference()

            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Exiting...[/yellow]")
                break

    async def process_inference(self):
        max_turns = 10
        current_turn = 0

        while current_turn < max_turns:
            current_turn += 1
            model_cfg, provider_cfg = self.config_mgr.get_active_model_and_provider()
            provider = OpenAIProvider(model_cfg, provider_cfg)
            schemas = self.tool_registry.get_schemas()

            console.print(f"\n[bold blue]Assistant ({model_cfg.name} via {provider_cfg.name})[/bold blue] >")

            tool_calls_to_run = []

            # Generator that routes tool call chunks while streaming content/reasoning to StreamRenderer
            async def chunk_generator():
                async for chunk in provider.stream_chat(self.messages, tools=schemas or None):
                    ctype = chunk["type"]
                    cval = chunk["value"]

                    if ctype == "tool_calls":
                        for tc in cval:
                            idx = tc.index
                            while len(tool_calls_to_run) <= idx:
                                tool_calls_to_run.append({"id": "", "name": "", "args": ""})
                            if tc.id:
                                tool_calls_to_run[idx]["id"] = tc.id
                            if tc.function and tc.function.name:
                                tool_calls_to_run[idx]["name"] = tc.function.name
                            if tc.function and tc.function.arguments:
                                tool_calls_to_run[idx]["args"] += tc.function.arguments
                    else:
                        yield chunk

            # StreamRenderer handles clean Live display of reasoning and response
            response_text, reasoning_text = await self.renderer.render_stream(
                chunk_generator(), 
                debug_mode=self.debug_mode
            )

            # Build Assistant Message object
            assistant_msg = {"role": "assistant"}
            if response_text:
                assistant_msg["content"] = response_text

            formatted_tool_calls = []
            if tool_calls_to_run:
                for i, tool_call in enumerate(tool_calls_to_run):
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

            self.messages.append(assistant_msg)

            if not tool_calls_to_run:
                break

            # Execute Tool / MCP Calls
            for tool_call in tool_calls_to_run:
                if self.debug_mode:
                    console.print(f"\n[bold magenta]🔧 [DEBUG] Tool Execution Request:[/bold magenta] {tool_call['name']}({tool_call['args']})")
                else:
                    console.print(f"\n[dim cyan]⚡ Tool Execution Request: {tool_call['name']}({tool_call['args']})[/dim cyan]")

                tool_result = await self.tool_registry.execute(tool_call["name"], tool_call["args"])

                if self.debug_mode:
                    console.print(f"[bold magenta]🔧 [DEBUG] Tool Execution Result:[/bold magenta]\n{tool_result}")
                
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result
                })


if __name__ == "__main__":
    harness = AIHarness()
    asyncio.run(harness.run())