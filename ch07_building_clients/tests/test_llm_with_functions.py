"""Unit tests for the modular helpers extracted from ``chat``.

These tests target each single-responsibility function in isolation so they
do not require a running MCP server or a live OpenAI API key:

* Pure helpers (``mcp_tool_to_openai``, ``build_initial_messages``,
  ``build_assistant_message``, ``build_tool_message``,
  ``extract_tool_result_text``) are exercised with plain objects.
* Async helpers (``fetch_openai_tools``, ``execute_tool_call``,
  ``run_tool_loop``) use ``AsyncMock`` sessions and a small fake OpenAI
  client that replays canned responses.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, ANY

from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion_message_tool_call import Function

from ch07_building_clients.llm_with_functions import (
    SYSTEM_PROMPT,
    build_assistant_message,
    build_initial_messages,
    build_tool_message,
    chat,
    execute_tool_call,
    extract_tool_result_text,
    fetch_openai_tools,
    mcp_tool_to_openai,
    run_tool_loop,
)


def _make_tool_call(call_id: str = "call_1", name: str = "add",
                    arguments: str = '{"a": 1, "b": 2}'):
    """Build a realistic OpenAI tool-call object (a real pydantic model so
    that ``model_dump(exclude_none=True)`` behaves like in production)."""
    return ChatCompletionMessageToolCall(
        id=call_id,
        function=Function(name=name, arguments=arguments),
        type="function",
    )


def _make_mcp_tool(name="add", description="add two numbers",
                   input_schema=None):
    """Build a lightweight fake MCP tool exposing the expected attributes."""
    return SimpleNamespace(
        name=name,
        description=description,
        input_schema=input_schema,
    )


def _make_response(message: ChatCompletionMessage):
    """Wrap a chat message into a fake chat-completion response object."""
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeCompletions:
    """Minimal stand-in for ``client.chat.completions``.

    Records every ``create`` call and replays the supplied responses in
    order, mirroring how the real OpenAI client is awaited.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _make_openai_client(responses):
    """Build a fake ``AsyncOpenAI``-like client returning ``responses``."""
    completions = _FakeCompletions(responses)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


# --------------------------------------------------------------------------- #
# Pure helper functions
# --------------------------------------------------------------------------- #
class TestMcpToolToOpenai(TestCase):
    """``mcp_tool_to_openai`` maps an MCP tool to the OpenAI tools schema."""

    def test_full_tool(self):
        tool = _make_mcp_tool(
            name="add",
            description="add two numbers",
            input_schema={"type": "object"},
        )
        self.assertEqual(
            mcp_tool_to_openai(tool),
            {
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "add two numbers",
                    "parameters": {"type": "object"},
                },
            },
        )

    def test_missing_description_defaults_to_empty(self):
        tool = _make_mcp_tool(name="ping", description=None)
        self.assertEqual(mcp_tool_to_openai(tool)["function"]["description"], "")

    def test_missing_input_schema_defaults_to_empty_object(self):
        tool = _make_mcp_tool(name="ping", input_schema=None)
        self.assertEqual(
            mcp_tool_to_openai(tool)["function"]["parameters"],
            {"type": "object", "properties": {}},
        )


class TestBuildInitialMessages(TestCase):
    """``build_initial_messages`` produces the system + user opening."""

    def test_returns_two_messages(self):
        self.assertEqual(len(build_initial_messages("hi")), 2)

    def test_system_message_uses_module_prompt(self):
        msgs = build_initial_messages("hi")
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[0]["content"], SYSTEM_PROMPT)

    def test_user_message_carries_query(self):
        msgs = build_initial_messages("What is 1+2?")
        self.assertEqual(msgs[1], {"role": "user", "content": "What is 1+2?"})


class TestBuildAssistantMessage(TestCase):
    """``build_assistant_message`` serializes an LLM message for the list."""

    def test_without_tool_calls_omits_key(self):
        msg = ChatCompletionMessage(role="assistant", content="hello")
        result = build_assistant_message(msg)
        self.assertEqual(result, {"role": "assistant", "content": "hello"})
        self.assertNotIn("tool_calls", result)

    def test_with_tool_calls_includes_serialized_calls(self):
        tc = _make_tool_call()
        msg = ChatCompletionMessage(role="assistant", content=None, tool_calls=[tc])
        result = build_assistant_message(msg)
        self.assertEqual(result["role"], "assistant")
        self.assertIsNone(result["content"])
        self.assertEqual(result["tool_calls"], [tc.model_dump(exclude_none=True)])

    def test_tool_calls_round_trip_shape(self):
        tc = _make_tool_call()
        msg = ChatCompletionMessage(role="assistant", content=None, tool_calls=[tc])
        result = build_assistant_message(msg)
        self.assertEqual(result["tool_calls"][0]["function"]["name"], "add")


class TestBuildToolMessage(TestCase):
    """``build_tool_message`` assembles a tool-role reply."""

    def test_structure(self):
        self.assertEqual(
            build_tool_message("call_1", "3"),
            {"role": "tool", "tool_call_id": "call_1", "content": "3"},
        )


class TestExtractToolResultText(TestCase):
    """``extract_tool_result_text`` flattens MCP result content to text."""

    def test_single_item(self):
        result = SimpleNamespace(content=[SimpleNamespace(text="3")])
        self.assertEqual(extract_tool_result_text(result), "3")

    def test_multiple_items_joined_with_newline(self):
        result = SimpleNamespace(
            content=[SimpleNamespace(text="a"), SimpleNamespace(text="b")]
        )
        self.assertEqual(extract_tool_result_text(result), "a\nb")

    def test_item_without_text_falls_back_to_str(self):
        result = SimpleNamespace(content=[42])
        self.assertEqual(extract_tool_result_text(result), "42")

    def test_empty_content_yields_empty_string(self):
        result = SimpleNamespace(content=[])
        self.assertEqual(extract_tool_result_text(result), "")


# --------------------------------------------------------------------------- #
# Async helpers (use AsyncMock sessions / fake OpenAI client)
# --------------------------------------------------------------------------- #
class TestFetchOpenaiTools(IsolatedAsyncioTestCase):
    """``fetch_openai_tools`` lists server tools and converts them."""

    async def test_returns_converted_tools(self):
        tools = [
            _make_mcp_tool(name="add", description="add", input_schema={"type": "object"}),
            _make_mcp_tool(name="mul", description="mul"),
        ]
        session = AsyncMock()
        session.list_tools.return_value = SimpleNamespace(tools=tools)
        result = await fetch_openai_tools(session)
        self.assertEqual(result, [mcp_tool_to_openai(t) for t in tools])

    async def test_invokes_list_tools_once(self):
        session = AsyncMock()
        session.list_tools.return_value = SimpleNamespace(tools=[])
        await fetch_openai_tools(session)
        session.list_tools.assert_awaited_once()


class TestExecuteToolCall(IsolatedAsyncioTestCase):
    """``execute_tool_call`` parses args, calls the tool, builds a message."""

    async def test_returns_tool_message(self):
        tc = _make_tool_call()
        session = AsyncMock()
        session.call_tool.return_value = SimpleNamespace(
            content=[SimpleNamespace(text="3")]
        )
        result = await execute_tool_call(session, tc)
        self.assertEqual(
            result,
            {"role": "tool", "tool_call_id": "call_1", "content": "3"},
        )

    async def test_calls_tool_with_parsed_arguments(self):
        tc = _make_tool_call(arguments='{"a": 1, "b": 2}')
        session = AsyncMock()
        session.call_tool.return_value = SimpleNamespace(
            content=[SimpleNamespace(text="3")]
        )
        await execute_tool_call(session, tc)
        session.call_tool.assert_awaited_once_with("add", {"a": 1, "b": 2})

    async def test_empty_arguments_resolves_to_empty_dict(self):
        # An empty arguments string is falsy -> the code falls back to "{}".
        tc = _make_tool_call(name="ping", arguments="")
        session = AsyncMock()
        session.call_tool.return_value = SimpleNamespace(
            content=[SimpleNamespace(text="pong")]
        )
        await execute_tool_call(session, tc)
        session.call_tool.assert_awaited_once_with("ping", {})

    async def test_multiline_result_is_concatenated(self):
        tc = _make_tool_call()
        session = AsyncMock()
        session.call_tool.return_value = SimpleNamespace(
            content=[SimpleNamespace(text="line1"), SimpleNamespace(text="line2")]
        )
        result = await execute_tool_call(session, tc)
        self.assertEqual(result["content"], "line1\nline2")


class TestRunToolLoop(IsolatedAsyncioTestCase):
    """``run_tool_loop`` drives the call→(tool)→call cycle to a final answer."""

    async def test_immediate_final_answer(self):
        final = ChatCompletionMessage(role="assistant", content="The answer is 3")
        client, completions = _make_openai_client([_make_response(final)])
        session = AsyncMock()
        messages = build_initial_messages("What is 1+2?")

        result = await run_tool_loop(client, session, [], messages)

        self.assertEqual(result, "The answer is 3")
        # No tool was needed.
        session.call_tool.assert_not_called()
        # The assistant message was appended to the conversation.
        self.assertEqual(messages[-1], {"role": "assistant", "content": "The answer is 3"})
        # The LLM was called exactly once.
        self.assertEqual(len(completions.calls), 1)
        # Tools and the growing message list were forwarded to the LLM.
        self.assertEqual(completions.calls[0]["messages"], messages)

    async def test_tool_call_then_final_answer(self):
        tc = _make_tool_call()
        tool_msg = ChatCompletionMessage(
            role="assistant", content=None, tool_calls=[tc]
        )
        final_msg = ChatCompletionMessage(role="assistant", content="The answer is 3")
        client, completions = _make_openai_client(
            [_make_response(tool_msg), _make_response(final_msg)]
        )
        session = AsyncMock()
        session.call_tool.return_value = SimpleNamespace(
            content=[SimpleNamespace(text="3")]
        )
        openai_tools = [mcp_tool_to_openai(_make_mcp_tool())]
        messages = build_initial_messages("What is 1+2?")

        result = await run_tool_loop(client, session, openai_tools, messages)

        self.assertEqual(result, "The answer is 3")
        # The tool was executed once with parsed arguments.
        session.call_tool.assert_awaited_once_with("add", {"a": 1, "b": 2})
        # The LLM was called twice (tool request, then final answer).
        self.assertEqual(len(completions.calls), 2)
        # The conversation grew to: system, user, assistant(tool), tool, final.
        self.assertEqual(len(messages), 5)
        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(
            messages[2]["tool_calls"], [tc.model_dump(exclude_none=True)]
        )
        self.assertEqual(
            messages[3], {"role": "tool", "tool_call_id": "call_1", "content": "3"}
        )
        self.assertEqual(messages[4], {"role": "assistant", "content": "The answer is 3"})
        # The available tools were passed on every LLM call.
        for call in completions.calls:
            self.assertEqual(call["tools"], openai_tools)

    async def test_multiple_tool_calls_in_one_turn(self):
        tc1 = _make_tool_call(call_id="c1", name="add", arguments='{"a": 1, "b": 2}')
        tc2 = _make_tool_call(call_id="c2", name="add", arguments='{"a": 3, "b": 4}')
        tool_msg = ChatCompletionMessage(
            role="assistant", content=None, tool_calls=[tc1, tc2]
        )
        final_msg = ChatCompletionMessage(role="assistant", content="done")
        client, _completions = _make_openai_client(
            [_make_response(tool_msg), _make_response(final_msg)]
        )
        session = AsyncMock()
        # Two tool results, returned in order.
        session.call_tool.side_effect = [
            SimpleNamespace(content=[SimpleNamespace(text="3")]),
            SimpleNamespace(content=[SimpleNamespace(text="7")]),
        ]
        messages = build_initial_messages("add twice")

        result = await run_tool_loop(client, session, [], messages)

        self.assertEqual(result, "done")
        self.assertEqual(session.call_tool.await_count, 2)
        # Both tool results are appended before the next LLM turn.
        tool_messages = [m for m in messages if m["role"] == "tool"]
        self.assertEqual(
            tool_messages,
            [
                {"role": "tool", "tool_call_id": "c1", "content": "3"},
                {"role": "tool", "tool_call_id": "c2", "content": "7"},
            ],
        )

    async def test_model_passed_to_every_call(self):
        from ch07_building_clients.llm_with_functions import MODEL

        final = ChatCompletionMessage(role="assistant", content="ok")
        client, completions = _make_openai_client([_make_response(final)])
        session = AsyncMock()
        await run_tool_loop(client, session, [], build_initial_messages("hi"))
        for call in completions.calls:
            self.assertEqual(call["model"], MODEL)


class TestChatInterface(TestCase):
    """The public ``chat`` entry point keeps its original contract."""

    def test_is_async_function(self):
        self.assertTrue(inspect.iscoroutinefunction(chat))

    def test_signature_unchanged(self):
        sig = inspect.signature(chat)
        self.assertEqual(list(sig.parameters), ["query"])
        self.assertIs(sig.parameters["query"].annotation, str)
        self.assertIs(sig.return_annotation, str)


if __name__ == "__main__":
    import unittest

    unittest.main()
