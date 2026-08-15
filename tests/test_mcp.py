import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from mcp.client import MCPServerConfig, MCPConfig, MCPClientSession, MCPManager, MCPToolAdapter
from tools.registry import ToolRegistry


class MockStreamResponse:
    def __init__(self, lines, status_code=200, reason_phrase="OK"):
        self.lines = lines
        self.status_code = status_code
        self.reason_phrase = reason_phrase
        self.text = ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def aiter_lines(self):
        for line in self.lines:
            await asyncio.sleep(0.001)
            yield line


class MockHTTPResponse:
    def __init__(self, status_code=200, text="", reason_phrase="OK"):
        self.status_code = status_code
        self.text = text
        self.reason_phrase = reason_phrase


def test_mcp_server_config_parsing():
    # stdio configuration
    cfg_stdio = MCPServerConfig(
        command="npx",
        args=["-y", "mcp-server-sqlite"],
        env={"DB_PATH": "test.db"}
    )
    assert cfg_stdio.command == "npx"
    assert cfg_stdio.args == ["-y", "mcp-server-sqlite"]
    assert cfg_stdio.url is None

    # SSE configuration
    cfg_sse = MCPServerConfig(
        url="http://localhost:8000/sse",
        headers={"Authorization": "Bearer secret-token-123"}
    )
    assert cfg_sse.url == "http://localhost:8000/sse"
    assert cfg_sse.headers == {"Authorization": "Bearer secret-token-123"}
    assert cfg_sse.command is None


@pytest.mark.asyncio
async def test_mcp_client_session_sse_connect_and_tool_call(mock_engine):
    cfg = MCPServerConfig(
        url="http://localhost:8000/sse",
        headers={"Authorization": "Bearer test-key"}
    )
    session = MCPClientSession("weather_service", cfg, config_mgr=mock_engine.config_mgr)

    sse_events = [
        "event: endpoint\n",
        "data: /messages?sessionId=session_xyz\n",
        "\n",
        ": keepalive\n",
        "\n",
        "event: message\n",
        'data: {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "WeatherService"}}}\n',
        "\n",
        "event: message\n",
        'data: {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "get_current_weather", "description": "Fetches current temperature", "inputSchema": {"type": "object", "properties": {"location": {"type": "string"}}}}]}}\n',
        "\n",
        "event: message\n",
        'data: {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "24°C Sunny"}]}}\n',
        "\n"
    ]

    mock_stream = MockStreamResponse(sse_events)
    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream)
    mock_client.post = AsyncMock(return_value=MockHTTPResponse(status_code=202, text="Accepted"))
    mock_client.is_closed = False

    session._http_client = mock_client

    # Connect to mock SSE server
    success = await session.connect()
    assert success is True
    assert session.is_connected is True
    assert session.transport_type == "sse"
    assert session._post_url == "http://localhost:8000/messages?sessionId=session_xyz"
    assert len(session.tools) == 1
    assert session.tools[0]["name"] == "get_current_weather"

    # Call tool via adapter
    adapter = MCPToolAdapter(
        server_name="weather_service",
        name="get_current_weather",
        description="Fetches current temperature",
        parameters={"type": "object", "properties": {"location": {"type": "string"}}},
        session=session
    )
    result = await adapter.execute(location="San Francisco")
    assert result == "24°C Sunny"

    await session.close()
    assert session.is_connected is False


@pytest.mark.asyncio
async def test_mcp_client_session_sse_direct_post_response(mock_engine):
    cfg = MCPServerConfig(url="http://localhost:8000/sse")
    session = MCPClientSession("direct_service", cfg, config_mgr=mock_engine.config_mgr)

    sse_events = [
        "event: endpoint\n",
        "data: http://localhost:8000/api/messages\n",
        "\n"
    ]

    mock_stream = MockStreamResponse(sse_events)
    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream)

    # Return JSON-RPC response directly in POST body
    direct_json = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "DirectServer"}}
    })
    mock_client.post = AsyncMock(return_value=MockHTTPResponse(status_code=200, text=direct_json))
    mock_client.is_closed = False

    session._http_client = mock_client

    # Connect and verify direct body parsing
    session._sse_task = asyncio.create_task(session._sse_reader_loop({}))
    await asyncio.wait_for(session._endpoint_event.wait(), timeout=2.0)
    assert session._post_url == "http://localhost:8000/api/messages"

    init_res = await session._send_request("initialize", {"protocolVersion": "2024-11-05"})
    assert init_res["serverInfo"]["name"] == "DirectServer"

    await session.close()


@pytest.mark.asyncio
async def test_mcp_manager_state_toggles(mock_engine, temp_workspace):
    registry = ToolRegistry()
    mcps_file = os.path.join(temp_workspace, "mcps.json")

    with open(mcps_file, "w", encoding="utf-8") as f:
        json.dump({
            "mcpServers": {
                "mock_sse": {
                    "url": "http://localhost:8000/sse"
                }
            }
        }, f)

    manager = MCPManager(filepath=mcps_file, config_mgr=mock_engine.config_mgr)
    config = manager.load_config()
    assert "mock_sse" in config.mcpServers
    assert config.mcpServers["mock_sse"].url == "http://localhost:8000/sse"

    # Create manual mock session & adapter
    session = MCPClientSession("mock_sse", config.mcpServers["mock_sse"], config_mgr=mock_engine.config_mgr)
    session.is_connected = True
    adapter = MCPToolAdapter("mock_sse", "test_tool", "Description", {}, session)
    manager.sessions["mock_sse"] = session
    manager.adapters["mock_sse"] = [adapter]

    # Global Enable
    manager.set_global_state(True, registry)
    assert "test_tool" in registry._tools

    # Per-server Disable
    manager.set_server_state("mock_sse", False, registry)
    assert "test_tool" not in registry._tools

    # Per-server Enable
    manager.set_server_state("mock_sse", True, registry)
    assert "test_tool" in registry._tools

    # Global Disable
    manager.set_global_state(False, registry)
    assert "test_tool" not in registry._tools

    await manager.close_all()
