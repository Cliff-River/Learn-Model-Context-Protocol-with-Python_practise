# - flake8: noqa: B018
# Import required modules
import asyncio
import json
import os

from dotenv import find_dotenv, load_dotenv
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from openai import AsyncOpenAI

load_dotenv(find_dotenv())

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Configuration
SERVER_URL = "http://127.0.0.1:8000/sse"
MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen3.8-27b:free")


# Convert an MCP tool definition to the OpenAI function-calling format
def mcp_tool_to_openai(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema or {"type": "object", "properties": {}},
        },
    }


# Chat with the LLM, letting it call MCP tools when needed
async def chat(query: str) -> str:
    # 1. connect to the MCP server through SSE transport
    async with sse_client(SERVER_URL) as (read_stream, write_stream):  # noqa: SIM117
        # 2. create a client session and finish the MCP handshake
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # 3. fetch the tools exposed by the server
            tools_result = await session.list_tools()
            openai_tools = [mcp_tool_to_openai(tool) for tool in tools_result.tools]

            messages: list[dict] = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant. Use the available tools "
                        "whenever they can help answer the user's question."
                    ),
                },
                {"role": "user", "content": query},
            ]

            # 4. tool-calling loop
            while True:
                response = await client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=openai_tools,
                )
                message = response.choices[0].message

                assistant_message: dict = {
                    "role": "assistant",
                    "content": message.content,
                }
                if message.tool_calls:
                    assistant_message["tool_calls"] = [
                        tool_call.model_dump(exclude_none=True)
                        for tool_call in message.tool_calls
                    ]
                messages.append(assistant_message)

                # no tool calls -> the LLM produced the final answer
                if not message.tool_calls:
                    print(f"Assistant: {message.content}")
                    return message.content

                # 5. execute each requested tool through the MCP session
                for tool_call in message.tool_calls:
                    name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    print(f"Calling tool '{name}' with {arguments}")
                    result = await session.call_tool(name, arguments)
                    text = "\n".join(
                        getattr(item, "text", str(item)) for item in result.content
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": text,
                        }
                    )


# entry point
def main() -> None:
    query = "What is 123.45 plus 678.9?"
    print(f"User: {query}")
    asyncio.run(chat(query))


if __name__ == "__main__":
    main()

