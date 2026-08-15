import asyncio
import atexit
import json
import os
import sys
import shutil
import subprocess
import urllib.parse
from typing import Dict, List, Any, Optional
import httpx
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.registry import ToolRegistry
from version import __version__

# Global registry of active MCP sessions for automatic cleanup on process termination
_ACTIVE_MCP_SESSIONS: List["MCPClientSession"] = []


def _cleanup_all_mcp_sessions():
    """Cleanly terminates all background stdio MCP server processes and closes connections on exit."""
    global _ACTIVE_MCP_SESSIONS
    for session in list(_ACTIVE_MCP_SESSIONS):
        if session.process and session.process.returncode is None:
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(session.process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                else:
                    session.process.terminate()
            except Exception:
                pass


atexit.register(_cleanup_all_mcp_sessions)


class MCPServerConfig(BaseModel):
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    type: Optional[str] = None


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
        self.is_proxied = True  # Remote MCP tools route through SubAgentDistiller
        self.requires_guard = True  # MCP servers are third-party code with unpredictable side effects

    async def execute(self, **kwargs) -> Any:
        return await self.session.call_tool(self.name, kwargs)


class MCPClientSession:
    """Manages stdio subprocess or SSE HTTP transport and JSON-RPC messaging for an MCP server."""
    def __init__(self, name: str, config: MCPServerConfig, config_mgr: Optional[Any] = None):
        self.name = name
        self.config = config
        self._config_mgr = config_mgr
        self.process: Optional[asyncio.subprocess.Process] = None
        self.transport_type: str = "sse" if config.url else "stdio"
        self._http_client: Optional[httpx.AsyncClient] = None
        self._post_url: Optional[str] = None
        self._endpoint_event: asyncio.Event = asyncio.Event()
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self.tools: List[Dict[str, Any]] = []
        self.is_connected = False
        self.error_message: Optional[str] = None
        self.stderr_log: List[str] = []
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._sse_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        if self.config.url:
            self.transport_type = "sse"
            return await self._connect_sse()
        elif self.config.command:
            self.transport_type = "stdio"
            return await self._connect_stdio()
        else:
            self.error_message = "MCP server configuration must provide either 'command' (stdio) or 'url' (SSE)."
            return False

    async def _connect_stdio(self) -> bool:
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
            _ACTIVE_MCP_SESSIONS.append(self)
        except Exception as e:
            self.error_message = f"Failed to launch command '{self.config.command}': {str(e)}"
            return False

        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._read_stderr_loop())

        mcp_timeout = self._config_mgr.config.timeouts.mcp if self._config_mgr else 60.0

        try:
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "Mesh", "version": __version__}
            }, timeout=mcp_timeout)

            await self._send_notification("notifications/initialized", {})

            tools_res = await self._send_request("tools/list", {}, timeout=mcp_timeout / 2.0)
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

    async def _connect_sse(self) -> bool:
        if not self.config.url:
            self.error_message = "SSE transport requires 'url' in server configuration."
            return False

        _ACTIVE_MCP_SESSIONS.append(self)

        headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
        if self.config.headers:
            headers.update(self.config.headers)

        self._endpoint_event.clear()
        self._post_url = None

        mcp_timeout = self._config_mgr.config.timeouts.mcp if self._config_mgr else 60.0
        stream_timeout = httpx.Timeout(connect=mcp_timeout, read=None, write=mcp_timeout, pool=mcp_timeout)

        if not self._http_client or getattr(self._http_client, "is_closed", False):
            self._http_client = httpx.AsyncClient(timeout=stream_timeout, follow_redirects=True)

        self._sse_task = asyncio.create_task(self._sse_reader_loop(headers))

        try:
            # Wait for the initial 'endpoint' SSE event
            try:
                await asyncio.wait_for(self._endpoint_event.wait(), timeout=mcp_timeout / 2.0)
            except asyncio.TimeoutError:
                if not self.error_message:
                    self.error_message = f"Timed out waiting for initial SSE 'endpoint' event from {self.config.url}"
                await self.close()
                return False

            if not self._post_url:
                if not self.error_message:
                    self.error_message = f"Failed to establish SSE endpoint for {self.config.url}"
                await self.close()
                return False

            # Initialize MCP handshake over the established SSE post endpoint
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "Mesh", "version": __version__}
            }, timeout=mcp_timeout)

            await self._send_notification("notifications/initialized", {})

            tools_res = await self._send_request("tools/list", {}, timeout=mcp_timeout / 2.0)
            if "tools" in tools_res:
                self.tools = tools_res["tools"]

            self.is_connected = True
            return True

        except Exception as e:
            if not self.error_message:
                self.error_message = f"MCP SSE initialization failed: {str(e)}"
            await self.close()
            return False

    async def _sse_reader_loop(self, headers: Dict[str, str]):
        mcp_timeout = self._config_mgr.config.timeouts.mcp if self._config_mgr else 60.0
        stream_timeout = httpx.Timeout(connect=mcp_timeout, read=None, write=mcp_timeout, pool=mcp_timeout)

        try:
            if not self._http_client or getattr(self._http_client, "is_closed", False):
                self._http_client = httpx.AsyncClient(timeout=stream_timeout, follow_redirects=True)

            async with self._http_client.stream("GET", self.config.url, headers=headers) as response:
                if response.status_code >= 400:
                    self.error_message = f"SSE connection failed with HTTP {response.status_code}: {response.reason_phrase}"
                    self._endpoint_event.set()
                    return

                event_type = "message"
                data_lines = []

                async for line in response.aiter_lines():
                    line = line.rstrip("\r\n")
                    if not line:
                        if data_lines:
                            data_str = "\n".join(data_lines)
                            await self._handle_sse_event(event_type, data_str)
                        event_type = "message"
                        data_lines = []
                    elif line.startswith(":"):
                        # SSE keep-alive ping or comment
                        continue
                    elif line.startswith("event:"):
                        c = line[6:]
                        if c.startswith(" "):
                            c = c[1:]
                        event_type = c.strip()
                    elif line.startswith("data:"):
                        c = line[5:]
                        if c.startswith(" "):
                            c = c[1:]
                        data_lines.append(c)

                if data_lines:
                    data_str = "\n".join(data_lines)
                    await self._handle_sse_event(event_type, data_str)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self.error_message:
                self.error_message = f"SSE stream error: {str(e)}"
        finally:
            if not self._endpoint_event.is_set():
                self._endpoint_event.set()

    async def _handle_sse_event(self, event_type: str, data_str: str):
        if event_type == "endpoint":
            endpoint_uri = data_str.strip()
            if endpoint_uri.startswith("{"):
                try:
                    parsed = json.loads(endpoint_uri)
                    if isinstance(parsed, dict):
                        endpoint_uri = parsed.get("url", parsed.get("uri", endpoint_uri))
                except Exception:
                    pass
            self._post_url = urllib.parse.urljoin(self.config.url, endpoint_uri)
            self._endpoint_event.set()
            return

        if not data_str.strip():
            return

        try:
            msg = json.loads(data_str)
        except json.JSONDecodeError:
            return

        if isinstance(msg, dict):
            if "id" in msg and msg["id"] in self._pending_requests:
                req_id = msg["id"]
                fut = self._pending_requests.pop(req_id)
                if not fut.done():
                    if "error" in msg and msg["error"] is not None:
                        fut.set_exception(RuntimeError(msg["error"].get("message", "MCP Error")))
                    else:
                        fut.set_result(msg.get("result", {}))

    async def _send_request(self, method: str, params: Dict[str, Any], timeout: float = 60.0) -> Dict[str, Any]:
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

        if self.transport_type == "stdio":
            if not self.process or self.process.stdin is None:
                self._pending_requests.pop(req_id, None)
                raise RuntimeError("Server process stdin is unavailable.")

            data = json.dumps(req) + "\n"
            self.process.stdin.write(data.encode('utf-8'))
            await self.process.stdin.drain()

        elif self.transport_type == "sse":
            if not self._post_url:
                self._pending_requests.pop(req_id, None)
                raise RuntimeError(f"Cannot send request: SSE post endpoint is not initialized for server '{self.name}'.")

            post_headers = {"Content-Type": "application/json"}
            if self.config.headers:
                post_headers.update(self.config.headers)

            if not self._http_client or getattr(self._http_client, "is_closed", False):
                self._http_client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

            try:
                resp = await self._http_client.post(
                    self._post_url,
                    json=req,
                    headers=post_headers,
                    timeout=timeout
                )
                if resp.status_code >= 400:
                    self._pending_requests.pop(req_id, None)
                    raise RuntimeError(f"HTTP POST to MCP endpoint failed with status {resp.status_code}: {resp.text}")

                resp_text = resp.text.strip() if hasattr(resp, "text") else ""
                if resp_text and (resp_text.startswith("{") and resp_text.endswith("}")):
                    try:
                        resp_json = json.loads(resp_text)
                        if isinstance(resp_json, dict) and resp_json.get("id") == req_id:
                            if req_id in self._pending_requests:
                                self._pending_requests.pop(req_id)
                                if "error" in resp_json and resp_json["error"] is not None:
                                    raise RuntimeError(resp_json["error"].get("message", "MCP Error"))
                                return resp_json.get("result", {})
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                self._pending_requests.pop(req_id, None)
                raise

        return await asyncio.wait_for(fut, timeout=timeout)

    async def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }

        if self.transport_type == "stdio":
            if not self.process or self.process.stdin is None:
                return
            data = json.dumps(req) + "\n"
            self.process.stdin.write(data.encode('utf-8'))
            await self.process.stdin.drain()

        elif self.transport_type == "sse":
            if not self._post_url:
                return
            post_headers = {"Content-Type": "application/json"}
            if self.config.headers:
                post_headers.update(self.config.headers)

            if not self._http_client or getattr(self._http_client, "is_closed", False):
                self._http_client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)

            try:
                await self._http_client.post(
                    self._post_url,
                    json=req,
                    headers=post_headers,
                    timeout=10.0
                )
            except Exception:
                pass

    async def _read_loop(self):
        try:
            while self.process and self.process.stdout:
                line = await self.process.stdout.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='replace').strip()
                if not line_str or not (line_str.startswith("{") and line_str.endswith("}")):
                    continue

                try:
                    msg = json.loads(line_str)
                    if "id" in msg and msg["id"] in self._pending_requests:
                        req_id = msg["id"]
                        fut = self._pending_requests.pop(req_id)
                        if not fut.done():
                            if "error" in msg and msg["error"] is not None:
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
        mcp_timeout = self._config_mgr.config.timeouts.mcp if self._config_mgr else 60.0
        res = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        }, timeout=mcp_timeout)

        if isinstance(res, dict) and "content" in res:
            text_parts = [item.get("text", "") for item in res["content"] if isinstance(item, dict) and item.get("type") == "text"]
            if text_parts:
                return "\n".join(text_parts)
        return res

    async def close(self):
        self.is_connected = False

        if self in _ACTIVE_MCP_SESSIONS:
            _ACTIVE_MCP_SESSIONS.remove(self)

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
        if self._sse_task and not self._sse_task.done():
            self._sse_task.cancel()

        for req_id, fut in list(self._pending_requests.items()):
            if not fut.done():
                fut.cancel()
        self._pending_requests.clear()

        if self._http_client and not getattr(self._http_client, "is_closed", False):
            try:
                await self._http_client.aclose()
            except Exception:
                pass

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
    def __init__(self, filepath: str = "mcps.json", config_mgr: Optional[Any] = None):
        self.filepath = filepath
        self._config_mgr = config_mgr
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
        """Loads config, establishes MCP connections (stdio & SSE), builds adapters, and registers them."""
        config = self.load_config()

        for name, server_cfg in config.mcpServers.items():
            session = MCPClientSession(name, server_cfg, config_mgr=self._config_mgr)
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
            effective_enabled = self.global_enabled and self.enabled_servers.get(name, True)
            info[name] = {
                "connected": session.is_connected,
                "enabled": effective_enabled,
                "server_enabled": self.enabled_servers.get(name, True),
                "global_enabled": self.global_enabled,
                "error": session.error_message,
                "transport": getattr(session, "transport_type", "stdio" if session.config.command else "sse"),
                "url": session.config.url,
                "command": session.config.command,
                "args": session.config.args,
                "tools": session.tools
            }
        return info

    async def close_all(self):
        for session in list(self.sessions.values()):
            await session.close()
