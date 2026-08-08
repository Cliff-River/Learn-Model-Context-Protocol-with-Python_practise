import asyncio

from mcp.server.mcpserver import MCPServer, Context
from typing import Optional, Any, Dict, AsyncGenerator

mcp = MCPServer("Streamable Server")

@mcp.tool(description="A simple tool returning file content")
async def echo(message : str, context : Context) -> str:
    await context.info("Processing file 1/3")
    await asyncio.sleep(2)
    await context.report_progress(2, 3, "Processing file 2/3")
    await asyncio.sleep(2)
    await context.report_progress(3, 3, "Processing file 3/3")
    await asyncio.sleep(2)
    await context.report_progress(3, 3, "File processing completed")
    await asyncio.sleep(2)
    return f"Here is the file conent: {message}"

def main():
    mcp.run(transport="streamable-http")