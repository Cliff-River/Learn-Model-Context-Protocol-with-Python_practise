from starlette.applications import Starlette
from starlette.routing import Mount,  Host
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("SSE Server")
app = Starlette(
    routes=[Mount("/", mcp.sse_app())]
)

@mcp.tool()
def add(a: int, b: int) -> int:
    """
    Add two numbers together.
    """
    return a + b