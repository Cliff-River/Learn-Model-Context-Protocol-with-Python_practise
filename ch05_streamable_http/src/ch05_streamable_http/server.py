from mcp.server.mcpserver import MCPServer
from typing import Optional, Any, Dict, AsyncGenerator

mcp = MCPServer("Streamable Server")

@mcp.tool(description="A simple tool returning file content")
async def echo(message : str) -> str:
    return f""