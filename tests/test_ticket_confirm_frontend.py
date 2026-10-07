"""
测试前端工单确认卡片功能
覆盖会话ID保持、重试逻辑和前端渲染的完整性
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright


def test_ticket_card_keeps_identity_and_retries_same_call():
    """测试工单卡片：保持会话ID，失败后重试携带相同参数"""
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    requests = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, channel=os.environ.get("PLAYWRIGHT_CHANNEL", "msedge" if os.name == "nt" else None),
        )
        try:
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            def route_request(route):
                if route.request.url.endswith("/api/actions/resume"):
                    requests.append(route.request.post_data_json)
                    data = ('event: error\ndata: {"message":"retry"}\n\ndata: [DONE]\n\n'
                            if len(requests) == 1 else
                            'data: {"delta":"完成"}\n\ndata: {"event":"done","conversation_id":17}\n\ndata: [DONE]\n\n')
                    route.fulfill(status=200, content_type="text/event-stream", body=data)
                elif route.request.url == "http://localhost:18765/":
                    route.fulfill(status=200, content_type="text/html", body=html)
                else:
                    route.fulfill(status=200, content_type="application/json", body='{"items":[]}')
            page.route("**/*", route_request)
            page.goto("http://localhost:18765/")
            page.wait_for_load_state("networkidle")
            user_id = page.evaluate("getUserId()")
            page.evaluate("""() => {
                setConversationId(17);
                const bubble = addRow('bot');
                renderTicketConfirm(bubble, {ticket_type:'退款', description:'测试'}, 'call-a');
                setConversationId(99);
            }""")
            button = page.get_by_role("button", name="确认提交", exact=True)
            button.click()
            page.wait_for_function("document.querySelector('.tc-btns button').disabled === false")
            assert requests[0] == {"conversation_id": 17, "user_id": user_id,
                                   "tool_call_id": "call-a", "confirmed": True}
            button.click()
            page.wait_for_function("getConversationId() === 17")
            assert requests[1] == requests[0]
            assert not errors
        finally:
            browser.close()


def test_replayed_ticket_button_uses_graph_interrupt_and_resume():
    """历史消息的建工单入口走图中断确认，不调用已删除的直接创建接口。"""
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    history = "非常抱歉给您带来了不好的体验,我理解您的心情。您可以选择转接人工客服,或让我为您登记一张工单跟进处理。"
    requests, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, channel=os.environ.get("PLAYWRIGHT_CHANNEL", "msedge" if os.name == "nt" else None),
        )
        try:
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))

            def route_request(route):
                path = route.request.url.removeprefix("http://localhost:18765").split("?")[0]
                if path == "/":
                    route.fulfill(status=200, content_type="text/html", body=html)
                    return
                if path == "/static/warm-theme.css":
                    route.fulfill(status=200, content_type="text/css",
                                  body=Path("app/static/warm-theme.css").read_text(encoding="utf-8"))
                    return
                if path == "/api/conversations":
                    data = {"items": [{"id": 17, "preview": "投诉"}]}
                elif path == "/api/conversations/17/messages":
                    data = {"items": [{"role": "assistant", "content": history}]}
                elif path == "/api/actions/pending":
                    data = None
                elif path in ("/api/graph-chat", "/api/actions/resume"):
                    requests.append((path, route.request.post_data_json))
                    frame = ({"event": "interrupt", "kind": "confirm_ticket", "conversation_id": 17,
                              "preview": {"ticket_type": "投诉", "description": "测试"}, "tool_call_id": "call-replay"}
                             if path == "/api/graph-chat" else {"event": "done", "conversation_id": 17})
                    route.fulfill(status=200, content_type="text/event-stream",
                                  body=f"data: {json.dumps(frame)}\n\ndata: [DONE]\n\n")
                    return
                else:
                    errors.append(f"Unexpected request: {path}")
                    route.fulfill(status=404, content_type="application/json", body="{}")
                    return
                route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

            page.route("**/*", route_request)
            page.goto("http://localhost:18765/")
            page.wait_for_load_state("networkidle")
            user_id = page.evaluate("getUserId()")
            page.locator(".conv-item").click()
            page.get_by_role("button", name="建工单", exact=True).click()
            confirm = page.get_by_role("button", name="确认提交", exact=True)
            confirm.wait_for(state="visible")
            assert requests == [("/api/graph-chat", {"user_id": user_id, "conversation_id": 17,
                                                    "message": "请根据上述问题为我登记工单"})]
            assert page.locator("#ticketMask, #refundMask").count() == 0
            confirm.click()
            page.wait_for_function("document.querySelector('.ticket-confirm').classList.contains('decided')")
            assert requests[1:] == [("/api/actions/resume", {"user_id": user_id, "conversation_id": 17,
                                                           "tool_call_id": "call-replay", "confirmed": True})]
            assert not errors
        finally:
            browser.close()
