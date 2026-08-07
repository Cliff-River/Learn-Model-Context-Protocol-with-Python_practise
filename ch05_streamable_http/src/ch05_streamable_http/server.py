from mcp.server.context import Context
from mcp.server.mcpserver import MCPServer
from typing import Optional, Any, Dict, AsyncGenerator

mcp = MCPServer("Streamable Server")

@mcp.tool(description="A simple tool returning file content")
async def echo(message : str, context : Context) -> str:
    await context.notify("Processing file 1/3")
    await context.notify("Processing file 2/3")
    await context.notify("Processing file 3/3")
    await context.notify("File processing completed")
    return f"Here is the file conent: {message}"

mcp.run(transport="streamable_http")
