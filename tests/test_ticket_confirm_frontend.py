"""
测试前端工单确认卡片功能
覆盖会话ID保持、重试逻辑和前端渲染的完整性
"""
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
