import asyncio
import json
import os
import sys
import shutil
import subprocess
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.registry import ToolRegistry
from version import __version__


class MCPServerConfig(BaseModel):
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None


class MCPConfig(BaseModel):
    mcpServers: Dict[str, MCPServerConfig] = Field(default_factory=dict)


class MCPToolAdapter(BaseTool):
    """Adapts a remote MCP tool into Mesh's local BaseTool interface."""
    def __init__(self, server_name: str, name: str, description: str, parameters: Dict[str, Any], session):
        self.server_name = server_name
        self.name = name
        self.description = description or f"MCP tool from server '{server_name}'"
        self.parameters = parameters or {"type": "object", "properties": {}}
        self.session = session
        self.is_proxied = True  # Remote MCP tools route through SubAgentProxy
        self.requires_guard = True  # MCP servers are third-party code with unpredictable
                                     # side effects - always risk-assessed before calling out

    async def execute(self, **kwargs) -> Any:
        return await self.session.call_tool(self.name, kwargs)


class MCPClientSession:
    """Manages stdio subprocess transport and JSON-RPC messaging for a single MCP server."""
    def __init__(self, name: str, config: MCPServerConfig):
        self.name = name
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self.tools: List[Dict[str, Any]] = []
        self.is_connected = False
        self.error_message: Optional[str] = None
        self.stderr_log: List[str] = []
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        if not self.config.command:
            self.error_message = "Only stdio transport ('command') is currently configured."
            return False

        proc_env = os.environ.copy()
        if self.config.env:
            proc_env.update(self.config.env)

        cmd = self.config.command
        args = list(self.config.args)

        if sys.platform == "win32":
            resolved = shutil.which(cmd)
            if resolved:
                cmd = resolved
            if cmd.lower().endswith((".cmd", ".bat")) or not resolved:
                args = ["/c", self.config.command] + args
                cmd = "cmd.exe"

        try:
            self.process = await asyncio.create_subprocess_exec(
                cmd,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env
            )
        except Exception as e:
            self.error_message = f"Failed to launch command '{self.config.command}': {str(e)}"
            return False

        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._read_stderr_loop())

        try:
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "Mesh", "version": __version__}
            }, timeout=60.0)

            await self._send_notification("notifications/initialized", {})

            tools_res = await self._send_request("tools/list", {}, timeout=30.0)
            if "tools" in tools_res:
                self.tools = tools_res["tools"]

            self.is_connected = True
            return True

        except Exception as e:
            stderr_summary = "\n".join(self.stderr_log[-5:]) if self.stderr_log else ""
            err_detail = f": {stderr_summary}" if stderr_summary else f": {str(e)}"
            self.error_message = f"MCP initialization failed{err_detail}"
            await self.close()
            return False

    async def _send_request(self, method: str, params: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        if not self.process or self.process.stdin is None:
            raise RuntimeError("Server process stdin is unavailable.")

        self._request_id += 1
        req_id = self._request_id

        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }

        fut = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = fut

        data = json.dumps(req) + "\n"
        self.process.stdin.write(data.encode('utf-8'))
        await self.process.stdin.drain()

        return await asyncio.wait_for(fut, timeout=timeout)

    async def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        if not self.process or self.process.stdin is None:
            return
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        data = json.dumps(req) + "\n"
        self.process.stdin.write(data.encode('utf-8'))
        await self.process.stdin.drain()

    async def _read_loop(self):
        try:
            while self.process and self.process.stdout:
                line = await self.process.stdout.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='replace').strip()
                if not line_str:
                    continue
                
                if not (line_str.startswith("{") and line_str.endswith("}")):
                    continue

                try:
                    msg = json.loads(line_str)
                    if "id" in msg and msg["id"] in self._pending_requests:
                        req_id = msg["id"]
                        fut = self._pending_requests.pop(req_id)
                        if not fut.done():
                            if "error" in msg:
                                fut.set_exception(RuntimeError(msg["error"].get("message", "MCP Error")))
                            else:
                                fut.set_result(msg.get("result", {}))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    async def _read_stderr_loop(self):
        try:
            while self.process and self.process.stderr:
                line = await self.process.stderr.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='replace').strip()
                if line_str:
                    self.stderr_log.append(line_str)
                    if len(self.stderr_log) > 50:
                        self.stderr_log.pop(0)
        except Exception:
            pass

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        res = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        }, timeout=60.0)
        
        if "content" in res:
            text_parts = [item.get("text", "") for item in res["content"] if item.get("type") == "text"]
            if text_parts:
                return "\n".join(text_parts)
        return res

    async def close(self):
        self.is_connected = False
        
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()

        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
            except Exception:
                pass

            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                else:
                    self.process.terminate()

                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


class MCPManager:
    """Manages parsing of mcps.json, server sessions, tool aggregation, and state toggles."""
    def __init__(self, filepath: str = "mcps.json"):
        self.filepath = filepath
        self.sessions: Dict[str, MCPClientSession] = {}
        self.adapters: Dict[str, List[MCPToolAdapter]] = {}
        self.enabled_servers: Dict[str, bool] = {}
        self.global_enabled: bool = True

    def load_config(self) -> MCPConfig:
        if not os.path.exists(self.filepath):
            return MCPConfig()
        with open(self.filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return MCPConfig(**data)

    async def initialize_all(self, tool_registry: ToolRegistry) -> None:
        """Loads config, establishes MCP connections, builds adapters, and registers them."""
        config = self.load_config()

        for name, server_cfg in config.mcpServers.items():
            session = MCPClientSession(name, server_cfg)
            self.sessions[name] = session
            self.adapters[name] = []
            self.enabled_servers[name] = True
            
            success = await session.connect()
            if success:
                for tool_def in session.tools:
                    adapter = MCPToolAdapter(
                        server_name=name,
                        name=tool_def.get("name", "unnamed"),
                        description=tool_def.get("description", ""),
                        parameters=tool_def.get("inputSchema", {"type": "object", "properties": {}}),
                        session=session
                    )
                    self.adapters[name].append(adapter)
                    if self.global_enabled and self.enabled_servers[name]:
                        tool_registry.register(adapter)

    def set_global_state(self, enabled: bool, tool_registry: ToolRegistry) -> None:
        """Globally enables or disables all MCP tools in the ToolRegistry."""
        self.global_enabled = enabled
        for server_name, adapter_list in self.adapters.items():
            should_enable = enabled and self.enabled_servers.get(server_name, True)
            for adapter in adapter_list:
                if should_enable:
                    tool_registry.register(adapter)
                else:
                    tool_registry.unregister(adapter.name)

    def set_server_state(self, server_name: str, enabled: bool, tool_registry: ToolRegistry) -> bool:
        """Enables or disables a specific MCP server's tools in the ToolRegistry."""
        if server_name not in self.sessions:
            return False

        self.enabled_servers[server_name] = enabled
        adapter_list = self.adapters.get(server_name, [])
        should_enable = enabled and self.global_enabled

        for adapter in adapter_list:
            if should_enable:
                tool_registry.register(adapter)
            else:
                tool_registry.unregister(adapter.name)

        return True

    def get_server_info(self) -> Dict[str, Any]:
        """Provides status and tool metadata for the /mcps command."""
        info = {}
        for name, session in self.sessions.items():
            info[name] = {
                "connected": session.is_connected,
                "enabled": self.enabled_servers.get(name, True),
                "error": session.error_message,
                "command": session.config.command,
                "args": session.config.args,
                "tools": session.tools
            }
        return info

    async def close_all(self):
        for session in self.sessions.values():
            await session.close()