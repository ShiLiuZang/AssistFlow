import json

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
