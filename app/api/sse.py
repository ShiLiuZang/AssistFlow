"""
聊天事件的 SSE 编码

一轮对话的执行在 app.graph.turns，这里只负责把事件字典编码成 SSE 帧，供 graph_chat 与 actions 共用。
"""

import json

DONE_SSE = "data: [DONE]\n\n"


def make_sse(data: dict) -> str:
    """字典编码为 SSE 数据帧：data: <json>\\n\\n。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"data: {payload}\n\n"


def event_to_sse(event: dict) -> str:
    """对外事件编码为 SSE；错误用 event: error 帧，只带 message。"""
    if event.get("event") == "error":
        message = json.dumps({"message": event.get("message", "")}, ensure_ascii=False, separators=(",", ":"))
        return f"event: error\ndata: {message}\n\n"
    return make_sse(event)
