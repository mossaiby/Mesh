from typing import List
from tools.base import BaseTool


class MCPManager:
    def __init__(self):
        self.connected_servers: List[str] = []

    async def connect_server(self, name: str, endpoint: str) -> bool:
        self.connected_servers.append(name)
        return True

    async def fetch_remote_tools(self, server_name: str) -> List[BaseTool]:
        return []
