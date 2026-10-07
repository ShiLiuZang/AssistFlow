import json
from types import SimpleNamespace

from app.api.graph_chat import restore_messages, restored_tool_status


def _record(role, content="", tool_calls=None, tool_call_id=None, turn_message_id=None):
    return SimpleNamespace(
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        turn_message_id=turn_message_id,
    )


def test_restore_messages_maps_roles_and_skips_internal_records():
    call = {"id": "c1", "name": "query_order", "args": {"order_id": "ORD-1"}}
    records = [
        _record("user", "查订单"),
        _record("assistant", "", tool_calls=[call], turn_message_id="msg_1_t1"),
        _record("tool", json.dumps({"found": True}), tool_call_id="c1"),
        _record("graph_sync", "3"),
        _record("ticket_decision", "{}", tool_call_id="c2"),
    ]

    messages = restore_messages(records)

    assert [m.type for m in messages] == ["human", "ai", "tool"]
    assert messages[0].content == "查订单"
    assert messages[1].id == "msg_1_t1"
    assert messages[1].tool_calls[0]["id"] == "c1"
    assert messages[2].tool_call_id == "c1"


def test_restored_tool_status_treats_unparseable_content_as_error():
    assert restored_tool_status("not json") == "error"
    assert restored_tool_status(None) == "error"
