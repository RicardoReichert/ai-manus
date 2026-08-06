"""Unit tests for the LangChain LLM gateway message translation.

Ensures the infrastructure gateway correctly converts between domain
:class:`LLMMessage` objects and LangChain message objects in both directions,
which is the boundary that keeps LangChain out of the domain.
"""
from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.domain.models.message import LLMMessage, Role, ToolCall
from app.infrastructure.external.llm.langchain_llm import (
    LangchainLLM,
    _sanitize_json_schema,
)


def _gateway() -> LangchainLLM:
    # init_chat_model only constructs the client; no network call is made here.
    return LangchainLLM()


class TestToLangChain:
    def test_all_roles_converted(self):
        gw = _gateway()
        msgs = [
            LLMMessage.system("sys"),
            LLMMessage.user("hi"),
            LLMMessage.assistant("", tool_calls=[ToolCall(id="c1", name="shell_exec", args={"cmd": "ls"})]),
            LLMMessage.tool(tool_call_id="c1", name="shell_exec", content="{}"),
        ]
        lc = gw._to_langchain(msgs)
        assert isinstance(lc[0], SystemMessage)
        assert isinstance(lc[1], HumanMessage)
        assert isinstance(lc[2], AIMessage)
        assert lc[2].tool_calls[0]["name"] == "shell_exec"
        assert lc[2].tool_calls[0]["args"] == {"cmd": "ls"}
        assert isinstance(lc[3], ToolMessage)
        assert lc[3].tool_call_id == "c1"


class TestFromLangChain:
    def test_ai_message_with_tool_calls(self):
        gw = _gateway()
        ai = AIMessage(
            content="",
            tool_calls=[{"name": "file_read", "args": {"file": "/a"}, "id": "c2", "type": "tool_call"}],
        )
        m = gw._from_langchain(ai)
        assert m.role == Role.ASSISTANT
        assert m.tool_calls[0].name == "file_read"
        assert m.tool_calls[0].args == {"file": "/a"}
        assert m.tool_calls[0].id == "c2"

    def test_plain_ai_message(self):
        gw = _gateway()
        m = gw._from_langchain(AIMessage(content="hello"))
        assert m.role == Role.ASSISTANT and m.content == "hello" and m.tool_calls == []

    def test_gemini_thinking_block_list_extracts_text_only(self):
        # Regression: Gemini 2.5 extended-thinking responses return content as
        # a list of blocks carrying an opaque "extras.signature" blob. Before
        # the fix this was stringified verbatim into the chat bubble.
        gw = _gateway()
        ai = AIMessage(content=[
            {
                "type": "text",
                "text": "Hey. I just came online. Who am I? Who are you?",
                "extras": {"signature": "CoUCARFNMg+3JmGJbw83oFIEjrVzSMkS..."},
            }
        ])
        m = gw._from_langchain(ai)
        assert m.content == "Hey. I just came online. Who am I? Who are you?"
        assert "signature" not in m.content
        assert "extras" not in m.content

    def test_multiple_text_blocks_are_concatenated(self):
        gw = _gateway()
        ai = AIMessage(content=[{"type": "text", "text": "Hello, "}, {"type": "text", "text": "world."}])
        m = gw._from_langchain(ai)
        assert m.content == "Hello, world."

    def test_non_text_blocks_contribute_nothing(self):
        gw = _gateway()
        ai = AIMessage(content=[{"type": "thinking", "thinking": "reasoning...", "extras": {}}])
        m = gw._from_langchain(ai)
        assert m.content == ""

    def test_string_list_items_are_joined(self):
        gw = _gateway()
        m = gw._from_langchain(AIMessage(content=["part1", "part2"]))
        assert m.content == "part1part2"


class TestRoundTrip:
    def test_domain_to_lc_to_domain_preserves_tool_calls(self):
        gw = _gateway()
        original = LLMMessage.assistant(
            "text", tool_calls=[ToolCall(id="c3", name="info_search_web", args={"query": "x"})]
        )
        lc = gw._to_langchain([original])[0]
        back = gw._from_langchain(lc)
        assert back.content == "text"
        assert back.tool_calls[0].name == "info_search_web"
        assert back.tool_calls[0].args == {"query": "x"}
        assert back.tool_calls[0].id == "c3"


class TestSanitizeJsonSchema:
    """Regression coverage for the "agent lifecycle error" reported when
    chatting through Manus Claw against a local LM Studio model. Root cause
    was three separate JSON Schema constructs in OpenClaw's own built-in
    tools that llama.cpp's grammar compiler can't handle — each alone fails
    the *entire* request (not just the one offending tool), so real chat
    stayed broken until all three were found (each isolated by bisecting an
    actual failing request against the live engine down to a single-key
    repro, not guessed):

    1. ``cron``'s unanchored ``pattern: "\\S"`` ("Pattern must start with
       '^' and end with '$'").
    2. ``exec``'s ``patternProperties`` on its ``env`` parameter ("failed
       to parse grammar" — not supported at all).
    3. ``cron``'s ``job.trigger.script``, a plain ``minLength``/
       ``maxLength``-constrained string with no pattern involved, three
       ``properties`` levels below the root schema ("failed to parse
       grammar" — the identical constraint one level up works fine).
    """

    def test_unanchored_pattern_one_level_deep_gets_wrapped(self):
        tools = [{
            "type": "function",
            "function": {
                "name": "cron",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "declarationKey": {"type": "string", "pattern": r"\S"},
                    },
                },
            },
        }]
        out = _sanitize_json_schema(tools)
        pattern = out[0]["function"]["parameters"]["properties"]["declarationKey"]["pattern"]
        assert pattern == r"^(?:\S)$"

    def test_pattern_two_levels_deep_is_dropped_entirely(self):
        tools = [{
            "type": "function",
            "function": {
                "name": "cron",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job": {
                            "type": "object",
                            "properties": {
                                "declarationKey": {
                                    "type": "string",
                                    "description": "kept",
                                    "pattern": r"\S",
                                },
                            },
                        },
                    },
                },
            },
        }]
        out = _sanitize_json_schema(tools)
        decl = out[0]["function"]["parameters"]["properties"]["job"]["properties"]["declarationKey"]
        assert "pattern" not in decl
        assert decl["description"] == "kept"
        assert decl["type"] == "string"

    def test_already_anchored_pattern_is_left_alone(self):
        tools = [{"function": {"parameters": {"properties": {"id": {"pattern": "^[a-z]+$"}}}}}]
        out = _sanitize_json_schema(tools)
        assert out[0]["function"]["parameters"]["properties"]["id"]["pattern"] == "^[a-z]+$"

    def test_min_max_length_one_level_deep_are_kept(self):
        tools = [{"function": {"parameters": {"properties": {
            "id": {"type": "string", "minLength": 1, "maxLength": 200},
        }}}}]
        out = _sanitize_json_schema(tools)
        prop = out[0]["function"]["parameters"]["properties"]["id"]
        assert prop["minLength"] == 1
        assert prop["maxLength"] == 200

    def test_min_max_length_deeply_nested_are_dropped(self):
        """Reproduces the third and last piece of the real bug: OpenClaw's
        cron tool's job.trigger.script is a string constrained by
        minLength/maxLength, three ``properties`` levels below the root
        schema — confirmed live against LM Studio that this alone (no
        pattern involved at all) fails the same way declarationKey's
        pattern did."""
        tools = [{"function": {"parameters": {"properties": {
            "job": {"type": "object", "properties": {
                "trigger": {"type": "object", "required": ["script"], "properties": {
                    "script": {"type": "string", "minLength": 1, "maxLength": 65536, "description": "kept"},
                    "once": {"type": "boolean"},
                }, "additionalProperties": False},
            }},
        }}}}]
        out = _sanitize_json_schema(tools)
        script = out[0]["function"]["parameters"]["properties"]["job"]["properties"]["trigger"]["properties"]["script"]
        assert "minLength" not in script
        assert "maxLength" not in script
        assert script["description"] == "kept"
        assert script["type"] == "string"

    def test_non_pattern_fields_and_nested_lists_are_untouched(self):
        tools = [{
            "function": {
                "name": "keep_me",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tags": {"type": "array", "items": {"type": "string", "pattern": "a|b"}},
                    },
                },
            },
        }]
        out = _sanitize_json_schema(tools)
        assert out[0]["function"]["name"] == "keep_me"
        assert out[0]["function"]["parameters"]["properties"]["tags"]["items"]["pattern"] == "^(?:a|b)$"

    def test_does_not_mutate_the_caller_list(self):
        original_pattern = r"\S"
        tools = [{"function": {"parameters": {"properties": {"x": {"pattern": original_pattern}}}}}]
        _sanitize_json_schema(tools)
        assert tools[0]["function"]["parameters"]["properties"]["x"]["pattern"] == original_pattern

    def test_empty_pattern_and_missing_tools_are_safe(self):
        assert _sanitize_json_schema(None) is None
        assert _sanitize_json_schema([]) == []
        tools = [{"function": {"parameters": {"properties": {"x": {"pattern": ""}}}}}]
        out = _sanitize_json_schema(tools)
        assert out[0]["function"]["parameters"]["properties"]["x"]["pattern"] == ""

    def test_pattern_properties_becomes_additional_properties(self):
        tools = [{
            "function": {
                "name": "exec",
                "parameters": {
                    "properties": {
                        "env": {
                            "type": "object",
                            "patternProperties": {"^.*$": {"type": "string"}},
                        },
                    },
                },
            },
        }]
        out = _sanitize_json_schema(tools)
        env = out[0]["function"]["parameters"]["properties"]["env"]
        assert "patternProperties" not in env
        assert env["additionalProperties"] == {"type": "string"}
        assert env["type"] == "object"

    def test_pattern_properties_merges_multiple_pattern_schemas(self):
        tools = [{
            "function": {
                "parameters": {
                    "properties": {
                        "env": {
                            "patternProperties": {
                                "^A_": {"type": "string"},
                                "^B_": {"minLength": 1},
                            },
                        },
                    },
                },
            },
        }]
        out = _sanitize_json_schema(tools)
        merged = out[0]["function"]["parameters"]["properties"]["env"]["additionalProperties"]
        assert merged == {"type": "string", "minLength": 1}

    def test_existing_additional_properties_takes_precedence_over_pattern_properties(self):
        tools = [{
            "function": {
                "parameters": {
                    "properties": {
                        "env": {
                            "patternProperties": {"^.*$": {"type": "string"}},
                            "additionalProperties": {"type": "boolean"},
                        },
                    },
                },
            },
        }]
        out = _sanitize_json_schema(tools)
        env = out[0]["function"]["parameters"]["properties"]["env"]
        assert "patternProperties" not in env
        assert env["additionalProperties"] == {"type": "boolean"}
