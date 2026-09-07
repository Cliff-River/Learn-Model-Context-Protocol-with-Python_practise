# %% package
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.sse import SseServerTransport

import mcp_types as types

from .tools import tools

# %% function to convert pydantic model to json schema
def pydamtic_to_json(model_cls : type) -> dict:
    schema = model_cls.schema()
    properties = {}
    required = schema.get("required", [])
    for proq, detail in schema.get("properties", {}).items():
        properties[proq] = { "type": detail.get("type", "string") }
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }

# %% list tools handler
async def handle_list_tools(ctx, params):
    tool_list = []
    for tool_def in tools.values():
        tool_list.append(types.Tool(
            name=tool_def["name"],
            description=tool_def["description"],
            input_schema=pydamtic_to_json(tool_def["args_schema"]),
        ))
    return types.ListToolsResult(tools=tool_list)

# %% initialize server
server = Server("low-level server", on_list_tools=handle_list_tools)

# %% call tool handler
@server.call_tool()
async def handle_call_tool(
    name : str,
    arguments : dict[str, str] | None,
) -> list[types.TextContent]:
    if name not in tools:
        raise ValueError(f"Tool {name} not found")
    
    tool = tools[name]
    result = "default"
    try:
        result = await tool["handler"](arguments)
    except Exception as e:
        raise ValueError(f"Error in tool {name}: {e}")
    return [
        types.TextContent(type="text", text=str(result)),
    ]

# %%