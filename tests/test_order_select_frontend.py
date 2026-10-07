"""
测试前端订单选择卡片功能
覆盖待选订单的持久化、页面重载后恢复、会话ID绑定
"""
import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


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
