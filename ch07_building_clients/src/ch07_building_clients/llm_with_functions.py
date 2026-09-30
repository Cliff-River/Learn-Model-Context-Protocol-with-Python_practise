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
MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-0731")


# System prompt steering the assistant toward tool use
SYSTEM_PROMPT = (
    "You are a helpful assistant. Use the available tools "
    "whenever they can help answer the user's question."
)


def mcp_tool_to_openai(tool) -> dict:
    """Convert an MCP tool definition to the OpenAI function-calling format.

    Maps the ``name``, ``description`` and ``input_schema`` attributes of an
    MCP tool to the ``tools`` schema expected by the OpenAI chat completions
    API. Missing descriptions/schemas fall back to safe empty defaults.

    Args:
        tool: An MCP tool object exposing ``name``, ``description`` and
            ``input_schema`` attributes.

    Returns:
        A dict of shape ``{"type": "function", "function": {...}}`` ready to
        be passed as an element of the ``tools`` parameter.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema or {"type": "object", "properties": {}},
        },
    }


def build_initial_messages(query: str) -> list[dict]:
    """Build the starting conversation with a system prompt and the user query.

    Args:
        query: The user's question to send to the LLM.

    Returns:
        A list of message dicts with roles ``"system"`` and ``"user"`` that
        can be passed directly to the OpenAI chat completions API.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]


def build_assistant_message(message) -> dict:
    """Convert an OpenAI chat-completion message into the dict stored in the
    conversation's running message list.

    Args:
        message: The ``choices[0].message`` object returned by the OpenAI
            chat completions API.

    Returns:
        A dict with ``role`` set to ``"assistant"`` and the message
        ``content``. When the model requested tools, a ``tool_calls`` list —
        each serialized via ``model_dump(exclude_none=True)`` — is included.
    """
    assistant_message: dict = {
        "role": "assistant",
        "content": message.content,
    }
    if message.tool_calls:
        assistant_message["tool_calls"] = [
            tool_call.model_dump(exclude_none=True)
            for tool_call in message.tool_calls
        ]
    return assistant_message


def build_tool_message(tool_call_id: str, text: str) -> dict:
    """Build a ``"tool"`` role message from a tool execution result.

    Args:
        tool_call_id: The id of the assistant tool call this result answers.
        text: The textual content produced by the tool.

    Returns:
        A dict suitable for appending to the conversation's message list.
    """
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": text,
    }


def extract_tool_result_text(result) -> str:
    """Extract a single text string from an MCP tool call result.

    Each content item's ``text`` attribute is used when available, otherwise
    the item is stringified. Items are joined with newlines.

    Args:
        result: The result object returned by ``ClientSession.call_tool``;
            expected to expose a ``content`` iterable of items.

    Returns:
        The concatenated text of all content items.
    """
    return "\n".join(
        getattr(item, "text", str(item)) for item in result.content
    )


async def fetch_openai_tools(session: ClientSession) -> list[dict]:
    """Fetch the tools exposed by the MCP server and convert them to the
    OpenAI function-calling format.

    Args:
        session: An initialized MCP ``ClientSession``.

    Returns:
        A list of tool dicts in the OpenAI ``tools`` schema.
    """
    tools_result = await session.list_tools()
    return [mcp_tool_to_openai(tool) for tool in tools_result.tools]


async def execute_tool_call(session: ClientSession, tool_call) -> dict:
    """Execute a single tool call through the MCP session and return the
    corresponding ``"tool"`` message.

    Parses the tool name and JSON arguments from the OpenAI tool call,
    invokes the tool on the MCP session, then assembles a tool-role message
    containing the textual result.

    Args:
        session: An initialized MCP ``ClientSession``.
        tool_call: The OpenAI tool call object to execute; expected to expose
            ``id`` and a ``function`` with ``name`` and ``arguments``.

    Returns:
        A ``"tool"`` role message dict containing the tool's textual result.
    """
    name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments or "{}")
    print(f"Calling tool '{name}' with {arguments}")
    result = await session.call_tool(name, arguments)
    return build_tool_message(tool_call.id, extract_tool_result_text(result))


async def run_tool_loop(
    client: AsyncOpenAI,
    session: ClientSession,
    openai_tools: list[dict],
    messages: list[dict],
) -> str:
    """Run the LLM tool-calling loop until the model produces a final answer.

    Each iteration calls the LLM, appends the assistant message, and — when
    the model requests tools — executes every requested tool through the MCP
    session and appends the results. The loop terminates once the model
    replies without any tool calls.

    Args:
        client: The OpenAI async client used to call the LLM.
        session: An initialized MCP ``ClientSession`` for tool execution.
        openai_tools: The available tools in OpenAI format.
        messages: The running conversation message list (mutated in place).

    Returns:
        The final textual answer produced by the assistant.
    """
    while True:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=openai_tools,
        )
        message = response.choices[0].message
        messages.append(build_assistant_message(message))

        # no tool calls -> the LLM produced the final answer
        if not message.tool_calls:
            print(f"Assistant: {message.content}")
            return message.content

        # execute each requested tool through the MCP session
        for tool_call in message.tool_calls:
            messages.append(await execute_tool_call(session, tool_call))


async def chat(query: str) -> str:
    """Chat with the LLM, letting it call MCP tools when needed.

    Connects to the MCP server over SSE, initializes a client session,
    fetches the server's tools, builds the opening messages, and runs the
    tool-calling loop until the model returns a final answer.

    Args:
        query: The user's question to send to the LLM.

    Returns:
        The final textual answer produced by the assistant.
    """
    # 1. connect to the MCP server through SSE transport
    async with sse_client(SERVER_URL) as (read_stream, write_stream):  # noqa: SIM117
        # 2. create a client session and finish the MCP handshake
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            # 3. fetch the tools and build the opening messages
            openai_tools = await fetch_openai_tools(session)
            messages = build_initial_messages(query)
            # 4. run the LLM tool-calling loop to a final answer
            return await run_tool_loop(client, session, openai_tools, messages)


# entry point
def main() -> None:
    query = "What is 123.45 plus 678.9?"
    print(f"User: {query}")
    asyncio.run(chat(query))


if __name__ == "__main__":
    main()

