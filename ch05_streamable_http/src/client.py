# %% packages
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import asyncio
from mcp.shared.session import RequestResponder
from mcp import types 

# %% define a message handler
port = 8000
def handle_message(
    message : RequestResponder[types.ServerRequest, types.ClientResult]
        | types.ServerNotification
        | Exception
    ) -> None:
    print(f"Received: {message}")
    if isinstance(message, Exception):
        print(f"Error: {message}")

# %%
async def main() -> None:
    print("Strting client...")

    async with streamable_http_client(
        f"http://localhost:{port}/mcp",
    ) as (
        read_stream,
        write_stream,
        session_callback
    ):
        async with ClientSession(
            read_stream,
            write_stream,
            message_handler = session_callback,
        ) as session:
            await session.initialize()

            result = []
            tool_result = session.call_tool("echo", {"message": "Hello, World!"})
            result.append(tool_result)
            print("tool_result:", tool_result)

asyncio.run(main())
# %%
