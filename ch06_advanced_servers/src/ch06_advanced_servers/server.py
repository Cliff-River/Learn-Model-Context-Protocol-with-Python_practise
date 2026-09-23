# %% package
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

import mcp_types as types
from starlette.routing import Mount, Route

from .tools import tools

# %% function to convert pydantic model to json schema
def pydamtic_to_json(model_cls: type[BaseModel]) -> dict[str, object]:
    schema = model_cls.model_json_schema()
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

# %% call tool handler
async def handle_call_tool(
    ctx,
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    name = params.name
    arguments = params.arguments
    if name not in tools:
        raise ValueError(f"Tool {name} not found")

    tool = tools[name]
    try:
        result = await tool["handler"](arguments)
    except Exception as e:
        raise ValueError(f"Error in tool {name}: {e}")
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=str(result)),
        ],
    )

# %%  list prompts handler
async def handle_list_prompts(ctx, params) -> types.ListPromptsResult:
    return types.ListPromptsResult(
        prompts=[
            types.Prompt(
                name="Example-Prompt",
                description="An example prompt",
                arguments=[
                    types.PromptArgument(
                        name="input",
                        description="The input to the prompt",
                        required=True,
                    ),
                ]
            ),
        ]
    )

# %% get prompt handler
async def handle_get_prompt(
    ctx,
    params: types.GetPromptRequestParams,
) -> types.GetPromptResult:
    if params.name != "Example-Prompt":
        raise ValueError(f"Prompt {params.name} not found")

    arguments = params.arguments or {}
    return types.GetPromptResult(
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(type="text", text=f"Your input: {arguments['input']}")
            ),
        ]
    )

# %% initialize server
server = Server(
    "low-level server",
    on_list_tools=handle_list_tools,
    on_call_tool=handle_call_tool,
    on_list_prompts=handle_list_prompts,
    on_get_prompt=handle_get_prompt,
)

# %% sse transport
sse = SseServerTransport("/messages/")

async def handle_sse(request: Request):
    async with sse.connect_sse(
        request.scope,
        request.receive,
        request._send,
    ) as streams:
        read_stream, write_stream = streams
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
    # Return empty response to avoid NoneType error on disconnect
    return Response()

starlete_app = Starlette(
    debug=True,
    routes=[
        Route("/sse", handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
)

def main() -> None:
    import uvicorn
    uvicorn.run(starlete_app, host="127.0.0.1", port=8000)

# %% run server
if __name__ == "__main__":
    main()
