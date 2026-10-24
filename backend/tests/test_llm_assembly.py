import pytest

from backend.llm import RoundAccumulator, feed_chunk, finalize_round


def text_chunk(content: str, finish: str | None = None) -> dict:
    return {"choices": [{"delta": {"content": content}, "finish_reason": finish}]}


def tool_chunk(
    index: int = 0,
    id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
    finish: str | None = None,
) -> dict:
    tc: dict = {"index": index}
    if id is not None:
        tc["id"] = id
    fn: dict = {}
    if name is not None:
        fn["name"] = name
    if arguments is not None:
        fn["arguments"] = arguments
    if fn:
        tc["function"] = fn
    return {"choices": [{"delta": {"tool_calls": [tc]}, "finish_reason": finish}]}


def test_text_deltas_collected_in_order() -> None:
    acc = RoundAccumulator()
    events = []
    for c in (text_chunk("Hello "), text_chunk("there"), text_chunk("!", finish="stop")):
        events.extend(feed_chunk(acc, c))
    assert [e["delta"] for e in events] == ["Hello ", "there", "!"]
    text, tools = finalize_round(acc)
    assert text == "Hello there!"
    assert tools == []


def test_fragmented_tool_call_assembles_single_call() -> None:
    acc = RoundAccumulator()
    events = []
    events.extend(feed_chunk(acc, tool_chunk(id="call_abc", name="get_order_details")))
    events.extend(feed_chunk(acc, tool_chunk(arguments='{"order_')))
    events.extend(feed_chunk(acc, tool_chunk(arguments='id": "ORD-101"}', finish="tool_calls")))
    assert events == []  # tool fragments produce no text events
    text, tools = finalize_round(acc)
    assert text == ""
    assert tools == [
        {"id": "call_abc", "name": "get_order_details", "args": {"order_id": "ORD-101"}}
    ]


def test_text_before_tool_in_same_round_kept() -> None:
    acc = RoundAccumulator()
    ev1 = feed_chunk(acc, text_chunk("Let me check "))
    ev2 = feed_chunk(acc, tool_chunk(id="c1", name="get_order_details", arguments='{"order_id":"ORD-101"}'))
    assert [e["delta"] for e in ev1] == ["Let me check "]
    assert ev2 == []
    text, tools = finalize_round(acc)
    assert text == "Let me check "
    assert len(tools) == 1


def test_name_fragments_concatenate() -> None:
    acc = RoundAccumulator()
    feed_chunk(acc, tool_chunk(id="c1", name="get_order_"))
    feed_chunk(acc, tool_chunk(name="details", arguments="{}"))
    _, tools = finalize_round(acc)
    assert tools[0]["name"] == "get_order_details"


def test_two_tool_calls_by_index() -> None:
    acc = RoundAccumulator()
    feed_chunk(acc, tool_chunk(index=0, id="c1", name="a", arguments="{}"))
    feed_chunk(acc, tool_chunk(index=1, id="c2", name="b", arguments='{"x": 1}'))
    _, tools = finalize_round(acc)
    assert [t["id"] for t in tools] == ["c1", "c2"]
    assert tools[1]["args"] == {"x": 1}


def test_malformed_args_raise_clear_error() -> None:
    acc = RoundAccumulator()
    feed_chunk(acc, tool_chunk(id="c1", name="a", arguments="{not json"))
    with pytest.raises(ValueError):
        finalize_round(acc)


def test_object_style_chunks_supported() -> None:
    class Fn:
        name = "end_call"
        arguments = "{}"

    class TC:
        index = 0
        id = "c9"
        function = Fn()

    class Delta:
        tool_calls = [TC()]
        content = None

    class Choice:
        delta = Delta()
        finish_reason = "tool_calls"

    class Chunk:
        choices = [Choice()]

    acc = RoundAccumulator()
    assert feed_chunk(acc, Chunk()) == []
    _, tools = finalize_round(acc)
    assert tools[0]["name"] == "end_call"
