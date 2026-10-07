"""
测试前端订单选择卡片功能
覆盖待选订单的持久化、页面重载后恢复、会话ID绑定
"""
import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from tests.conftest import issue_visitor_token


@pytest.mark.parametrize("cancelled", [False, True])
def test_pending_order_survives_reload_and_uses_bound_identity(cancelled):
    """测试待选订单：重载后恢复，提交时使用绑定的会话ID"""
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    requests, errors = [], []
    pending = {"kind": "select_order", "conversation_id": 17, "request_id": "selection-a",
               "orders": [{"order_id": "ORD-1001", "product_name": "杯子"}]}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, channel=os.environ.get("PLAYWRIGHT_CHANNEL", "msedge" if os.name == "nt" else None))
        try:
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))

            def intercept(route):
                if route.request.url.endswith("/api/auth/visitor"):
                    token, expires_at = issue_visitor_token("frontend-visitor")
                    route.fulfill(status=200, content_type="application/json", body=json.dumps({
                        "user_id": "frontend-visitor", "token": token, "expires_at": expires_at,
                    }))
                    return
                url = route.request.url
                if url == "http://localhost:18765/":
                    route.fulfill(status=200, content_type="text/html", body=html)
                elif "/api/actions/pending?" in url:
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(pending))
                elif url.endswith("/api/actions/select-order"):
                    requests.append(route.request.post_data_json)
                    route.fulfill(status=200, content_type="text/event-stream", body=(
                        'data: {"delta":"完成"}\n\ndata: {"event":"done","conversation_id":17}\n\ndata: [DONE]\n\n'))
                else:
                    route.fulfill(status=200, content_type="application/json", body='{"items":[]}')

            page.route("**/*", intercept)
            page.goto("http://localhost:18765/")
            page.wait_for_load_state("networkidle")
            user = page.evaluate("getUserId()")
            page.evaluate("setConversationId(17)")
            page.reload()
            page.wait_for_load_state("networkidle")
            assert page.locator(".order-card").count() == 1
            assert page.get_by_role("button", name="取消选择", exact=True).count() == 1

            page.evaluate("setConversationId(99)")
            if cancelled:
                page.get_by_role("button", name="取消选择", exact=True).click()
            else:
                page.locator(".order-card").click()
            page.wait_for_function("getConversationId() === 17")
            assert requests == [{"conversation_id": 17, "user_id": user, "kind": "select_order",
                                 "request_id": "selection-a",
                                 **({"cancelled": True} if cancelled else {"order_id": "ORD-1001"})}]
            assert page.locator(".order-cards button:enabled").count() == 0
            assert not errors
        finally:
            browser.close()


@pytest.mark.parametrize("answer, rendered", [("最终**答案**", "最终答案"), ("", "")])
def test_sse_replace_overwrites_streamed_bubble(answer, rendered):
    """浏览器先展示 delta；replace 替换文字和 Markdown，保留工具徽章。"""
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, channel=os.environ.get("PLAYWRIGHT_CHANNEL", "msedge" if os.name == "nt" else None))
        try:
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))

            def intercept(route):
                if route.request.url.endswith("/api/auth/visitor"):
                    token, expires_at = issue_visitor_token("frontend-visitor")
                    route.fulfill(status=200, content_type="application/json", body=json.dumps({
                        "user_id": "frontend-visitor", "token": token, "expires_at": expires_at,
                    }))
                    return
                if route.request.url == "http://localhost:18765/":
                    route.fulfill(status=200, content_type="text/html", body=html)
                elif "/api/actions/pending?" in route.request.url:
                    route.fulfill(status=200, content_type="application/json", body="null")
                else:
                    route.fulfill(status=200, content_type="application/json", body='{"items":[]}')

            page.route("**/*", intercept)
            page.goto("http://localhost:18765/")
            page.wait_for_load_state("networkidle")
            page.evaluate("""() => {
              window.testBubble = addRow("bot");
              const stream = new ReadableStream({start(controller) { window.testController = controller; }});
              window.streamFinished = streamInto(window.testBubble, () => Promise.resolve(new Response(stream)));
              const frames = 'data: {"event":"tool","name":"query_order"}\\n\\n'
                + 'data: {"delta":"原始"}\\n\\ndata: {"delta":"回答"}\\n\\n';
              window.testController.enqueue(new TextEncoder().encode(frames));
            }""")
            page.wait_for_function('window.testBubble.querySelector(".bubble-text").textContent === "原始回答"')
            frames = (f'data: {json.dumps({"event": "replace", "answer": answer}, ensure_ascii=False)}\n\n'
                      'data: {"event":"done","conversation_id":17}\n\ndata: [DONE]\n\n')
            page.evaluate("""async (frames) => {
              window.testController.enqueue(new TextEncoder().encode(frames));
              window.testController.close();
              await window.streamFinished;
            }""", frames)
            assert page.locator(".bubble-text").inner_text() == rendered
            assert page.locator(".tool-badge").inner_text() == "🔧 调用了 query_order"
            assert page.locator(".bubble-text strong").count() == int(bool(answer))
            assert page.evaluate("getConversationId()") == 17
            assert not errors
        finally:
            browser.close()
