"""SSE 帧编码：把聊天与动作接口的事件字典编码为 Server-Sent Events 文本。"""

import json


def make_sse(data: dict) -> str:
    """
    将字典编码为Server-Sent Events (SSE)格式的数据帧

    参数:
        data: 要发送的数据字典

    返回:
        格式化的SSE字符串，包含"data: "前缀和双换行符结尾
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"data: {payload}\n\n"


def graph_event_to_sse(
    event: dict,
    conversation_id: int,
) -> str:
    """
    将图运行时事件转换为聊天SSE协议格式

    参数:
        event: 图运行时产生的事件字典
        conversation_id: 当前会话ID

    返回:
        SSE格式的事件字符串

    处理特殊事件类型：citations转换为items，interrupt附加预览信息
    """
    if event.get("event") == "end":
        return "data: [DONE]\n\n"

    if event.get("event") == "error":
        return 'event: error\ndata: {"message":"图执行失败，请重试"}\n\n'

    payload = dict(event)
    if payload.get("event") == "citations":
        payload["items"] = payload.pop("citations", [])
    if payload.get("event") in {"done", "interrupt"}:
        payload["conversation_id"] = conversation_id

    if payload.get("event") == "interrupt":
        payload.update(payload.pop("preview"))

    return make_sse(payload)
