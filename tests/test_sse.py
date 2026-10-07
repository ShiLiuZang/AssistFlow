import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api import graph_chat
from app.api.sse import graph_event_to_sse, make_sse


def _payload(frame: str) -> dict:
    assert frame.startswith("data: ") and frame.endswith("\n\n")
    return json.loads(frame[len("data: "):-2])


def test_make_sse_keeps_chinese_unescaped():
    frame = make_sse({"delta": "你好"})
    assert "你好" in frame
    assert _payload(frame) == {"delta": "你好"}


def test_end_and_error_events_map_to_fixed_frames():
    assert graph_event_to_sse({"event": "end"}, 1) == "data: [DONE]\n\n"
    assert graph_event_to_sse({"event": "error", "message": "x"}, 1).startswith("event: error\n")


def test_citations_are_renamed_to_items():
    payload = _payload(graph_event_to_sse({"event": "citations", "citations": [{"id": 1}]}, 7))
    assert payload == {"event": "citations", "items": [{"id": 1}]}


def test_done_carries_conversation_id():
    payload = _payload(graph_event_to_sse({"event": "done", "request_id": "r1"}, 7))
    assert payload == {"event": "done", "request_id": "r1", "conversation_id": 7}


def test_interrupt_flattens_preview():
    event = {"event": "interrupt", "preview": {"kind": "confirm_ticket", "tool_call_id": "c1"}}
    payload = _payload(graph_event_to_sse(event, 7))
    assert payload == {
        "event": "interrupt",
        "conversation_id": 7,
        "kind": "confirm_ticket",
        "tool_call_id": "c1",
    }


@pytest.mark.parametrize("terminal, completed", [
    ([{"event": "done"}], True),
    ([{"event": "interrupt", "preview": {"kind": "select_order"}}], False),
    ([{"event": "error"}], False),
    ([{"event": "done"}, {"event": "interrupt", "preview": {"kind": "confirm_ticket"}}], False),
    ([{"event": "done"}, {"event": "error"}], False),
    ([], False),
])
def test_shared_finalization_saves_before_summary_and_sse(monkeypatch, terminal, completed):
    """仅正常完成才调度摘要；消息先保存，内部 end 不输出 SSE 结束帧。"""
    order = []
    saved = AsyncMock(side_effect=lambda *_: order.append("saved"))
    scheduled = Mock(side_effect=lambda *_: order.append("summary"))
    monkeypatch.setattr(graph_chat.repository, "persist_graph_messages", saved)
    monkeypatch.setattr(graph_chat, "schedule_persisted_summary", scheduled)
    messages = [object()]
    runtime = SimpleNamespace(get_state=AsyncMock(return_value=SimpleNamespace(values={"messages": messages})))

    async def source():
        order.append("run")
        yield {"delta": "回答"}
        for event in terminal:
            yield event
        yield {"event": "end"}

    async def run():
        frames = []
        async for frame in graph_chat.stream_graph_events(runtime, "u1", 7, source()):
            order.append("frame")
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    saved.assert_awaited_once_with(7, "u1", messages)
    runtime.get_state.assert_awaited_once_with("u1", 7)
    assert order == ["run", "saved"] + (["summary"] if completed else []) + ["frame"] * len(frames)
    if completed:
        scheduled.assert_called_once_with("u1", 7, graph_chat.summarize_dialog)
    else:
        scheduled.assert_not_called()
    assert frames == [graph_event_to_sse(event, 7) for event in [{"delta": "回答"}, *terminal]]
    assert "data: [DONE]\n\n" not in frames
