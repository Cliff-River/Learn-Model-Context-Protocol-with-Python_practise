# %% package
import asyncio

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

# %% server config
SERVER_URL = "http://127.0.0.1:8000/sse"


# %% run client
async def connect() -> None:
    # 1. connect to the server through SSE transport
    async with sse_client(SERVER_URL) as (read_stream, write_stream):
        # 2. create a client session and finish the MCP handshake
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            server_info = getattr(init_result, "server_info", None) or getattr(
                init_result, "serverInfo", None
            )
            print(f"Connected to server: {server_info}")

            # 3. list the tools provided by the server
            tools_result = await session.list_tools()
            print(f"\nAvailable tools ({len(tools_result.tools)}):")
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description}")
                print(f"    input schema: {tool.input_schema}")

            # 4. call the "add" tool
            call_result = await session.call_tool("add", {"a": 1.5, "b": 2.5})
            print("\nCall tool 'add' with {'a': 1.5, 'b': 2.5}:")
            if getattr(call_result, "is_error", False):
                print("  The tool returned an error.")
            for item in call_result.content:
                print(f"  -> {getattr(item, 'text', item)}")

            # 5. list the prompts provided by the server
            prompts_result = await session.list_prompts()
            print(f"\nAvailable prompts ({len(prompts_result.prompts)}):")
            for prompt in prompts_result.prompts:
                print(f"  - {prompt.name}: {prompt.description}")

            # 6. get the "Example-Prompt" prompt
            prompt_result = await session.get_prompt(
                "Example-Prompt", {"input": "Hello MCP"}
            )
            print('\nGet prompt "Example-Prompt" with {"input": "Hello MCP"}:')
            for message in prompt_result.messages:
                content = message.content
                print(f"  [{message.role}] {getattr(content, 'text', content)}")

def main() -> None:
    asyncio.run(connect())

# %% entry point
if __name__ == "__main__":
    main()

# %%
