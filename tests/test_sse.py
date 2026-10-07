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
def test_shared_finalization_saves_before_summary_and_terminal_sse(monkeypatch, terminal, completed):
    """文字实时交付，保存后交付终结事件；仅正常完成调度摘要。"""
    order = []
    received = asyncio.Event()
    saved = AsyncMock(side_effect=lambda *_: order.append("saved"))
    scheduled = Mock(side_effect=lambda *_: order.append("summary"))
    monkeypatch.setattr(graph_chat.conversation_repo, "persist_graph_messages", saved)
    monkeypatch.setattr(graph_chat, "schedule_persisted_summary", scheduled)
    messages = [object()]
    runtime = SimpleNamespace(get_state=AsyncMock(return_value=SimpleNamespace(values={"messages": messages})))

    async def source():
        order.append("run")
        yield {"delta": "回答"}
        await received.wait()
        for event in terminal:
            yield event
        yield {"event": "end"}

    async def run():
        frames = []
        async for frame in graph_chat.stream_graph_events(runtime, "u1", 7, source()):
            order.append("frame")
            frames.append(frame)
            received.set()
        return frames

    frames = asyncio.run(run())
    saved.assert_awaited_once_with(7, "u1", messages)
    runtime.get_state.assert_awaited_once_with("u1", 7)
    assert order == ["run", "frame", "saved"] + (["summary"] if completed else []) + ["frame"] * (len(frames) - 1)
    if completed:
        scheduled.assert_called_once_with("u1", 7, graph_chat.summarize_dialog)
    else:
        scheduled.assert_not_called()
    assert frames == [graph_event_to_sse(event, 7) for event in [{"delta": "回答"}, *terminal]]
    assert "data: [DONE]\n\n" not in frames


@pytest.mark.parametrize("entrypoint", ["events", "chat", "selection"])
@pytest.mark.parametrize("disconnect", ["close", "cancel"])
def test_disconnect_keeps_graph_persistence_summary_and_lock_lifetime(monkeypatch, entrypoint, disconnect):
    from app.api import actions
    from app.core.conversation_lock import conversation_lock, owns_conversation_lock
    from app.schemas.chat import ChatRequest

    async def run():
        graph_release, saving, save_release, acquired = [asyncio.Event() for _ in range(4)]
        producer = None

        async def source(*args, **kwargs):
            nonlocal producer
            producer = asyncio.current_task()
            assert owns_conversation_lock("u1", 7)
            yield {"event": "node", "name": "agent"}
            await graph_release.wait()
            yield {"delta": "完成"}
            yield {"event": "done"}
            yield {"event": "end"}

        async def persist(*args):
            assert owns_conversation_lock("u1", 7)
            assert asyncio.current_task() is producer
            saving.set()
            await save_release.wait()

        saved, scheduled = AsyncMock(side_effect=persist), Mock()
        monkeypatch.setattr(graph_chat, "_persist_graph_messages", saved)
        monkeypatch.setattr(graph_chat, "schedule_graph_summary", scheduled)
        runtime = SimpleNamespace(stream_turn=source)
        if entrypoint == "events":
            stream = graph_chat.stream_graph_events(runtime, "u1", 7, source())
        elif entrypoint == "chat":
            monkeypatch.setattr(graph_chat, "_chat_events", source)
            stream = graph_chat.stream_graph_chat(ChatRequest(user_id="u1", message="问题"), 7, runtime)
            assert _payload(await anext(stream)) == {"event": "conversation", "conversation_id": 7}
        else:
            request = actions.SelectOrderRequest(user_id="u1", conversation_id=7, request_id="r", cancelled=True)
            stream = actions.stream_order_selection(request, runtime)
        assert _payload(await asyncio.wait_for(anext(stream), 2)) == {"event": "node", "name": "agent"}

        async def next_turn():
            async with conversation_lock("u1", 7):
                acquired.set()

        contender = asyncio.create_task(next_turn())
        await asyncio.sleep(0)
        assert not acquired.is_set()
        if disconnect == "cancel":
            waiting = asyncio.create_task(anext(stream))
            await asyncio.sleep(0)
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
        await stream.aclose()
        assert not producer.done()
        saved.assert_not_awaited()
        graph_release.set()
        await asyncio.wait_for(saving.wait(), 2)
        assert not acquired.is_set()
        scheduled.assert_not_called()
        save_release.set()
        await asyncio.wait_for(producer, 2)
        await asyncio.wait_for(contender, 2)
        assert acquired.is_set()
        saved.assert_awaited_once_with(runtime, "u1", 7)
        scheduled.assert_called_once_with("u1", 7)
        assert not producer.cancelled()
    asyncio.run(run())


def test_graph_source_failure_emits_error_and_one_done_marker(monkeypatch):
    async def source(*args):
        yield {"event": "node", "name": "agent"}
        raise RuntimeError("private")

    monkeypatch.setattr(graph_chat, "_chat_events", source)
    saved, scheduled = AsyncMock(), Mock()
    monkeypatch.setattr(graph_chat, "_persist_graph_messages", saved)
    monkeypatch.setattr(graph_chat, "schedule_graph_summary", scheduled)

    async def run():
        from app.schemas.chat import ChatRequest
        return [frame async for frame in graph_chat.stream_graph_chat(
            ChatRequest(user_id="u1", message="问题"), 7, object())]

    frames = asyncio.run(run())
    assert _payload(frames[1]) == {"event": "node", "name": "agent"}
    assert frames[-2] == 'event: error\ndata: {"message":"图执行或消息保存失败，请重试"}\n\n'
    assert frames[-1] == "data: [DONE]\n\n"
    assert sum("[DONE]" in frame for frame in frames) == 1
    assert "private" not in "".join(frames)
    saved.assert_not_awaited()
    scheduled.assert_not_called()
