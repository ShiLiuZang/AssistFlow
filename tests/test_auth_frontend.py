"""模拟 HTTP 的浏览器鉴权测试；不启动服务或连接外部依赖。"""
import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ORIGIN = "http://localhost:18765"
CHAT_HTML = Path("app/static/index.html").read_text(encoding="utf-8")
ADMIN_JS = Path("app/static/admin-auth.js").read_text(encoding="utf-8")


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, channel=os.environ.get("PLAYWRIGHT_CHANNEL", "msedge" if os.name == "nt" else None))
        try:
            yield browser.new_page()
        finally:
            browser.close()


def fulfill_json(route, data, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(data))


@pytest.mark.parametrize("cached", [False, True])
def test_chat_401_refreshes_identity_and_retries_sse_once(page, cached):
    issued, requests, errors = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    if cached:
        page.add_init_script("""localStorage.setItem('minihelp_session_id', 'old');
            localStorage.setItem('minihelp_visitor_token', 'old-token');""")
    else:
        page.add_init_script("localStorage.setItem('minihelp_session_id', 'legacy-random-id');")

    def intercept(route):
        path = route.request.url.removeprefix(ORIGIN).split("?")[0]
        if path == "/":
            route.fulfill(status=200, content_type="text/html", body=CHAT_HTML)
        elif path == "/api/auth/visitor":
            visitor = {"user_id": f"v_{len(issued) + 1}", "token": f"token-{len(issued) + 1}", "expires_at": 9999999999}
            issued.append(route.request.post_data)
            fulfill_json(route, visitor)
        elif path == "/api/graph-chat":
            requests.append((route.request.headers.get("authorization"), route.request.post_data_json))
            if len(requests) == 1:
                fulfill_json(route, {"detail": "expired"}, 401)
            else:
                route.fulfill(status=200, content_type="text/event-stream", body=(
                    'data: {"delta":"认证后回复"}\n\ndata: {"event":"done","conversation_id":7}\n\ndata: [DONE]\n\n'))
        elif path.startswith("/api/"):
            assert route.request.headers.get("authorization", "").startswith("Bearer ")
            fulfill_json(route, [])
        else:
            route.fulfill(status=200, content_type="text/css", body="")

    page.route("**/*", intercept)
    page.goto(ORIGIN)
    page.wait_for_load_state("networkidle")
    page.locator("#send").wait_for(state="visible")
    page.wait_for_function("!document.querySelector('#send').disabled")
    assert len(issued) == (0 if cached else 1)
    page.locator("#input").fill("你好")
    page.locator("#send").click()
    page.wait_for_function("document.querySelector('#messages').innerText.includes('认证后回复')")
    assert len(requests) == 2
    assert len(issued) == (1 if cached else 2)
    assert all(body is None for body in issued)
    latest = 1 if cached else 2
    assert requests[1] == (f"Bearer token-{latest}", {"user_id": f"v_{latest}", "message": "你好", "conversation_id": None})
    assert page.evaluate("localStorage.getItem('minihelp_visitor_token')") == f"token-{latest}"
    assert page.evaluate("getUserId()") == f"v_{latest}"
    assert not errors


def test_chat_query_retry_and_concurrent_401_share_one_refresh(page):
    issued, requests = [], []
    page.add_init_script("""localStorage.setItem('minihelp_session_id', 'old');
        localStorage.setItem('minihelp_visitor_token', 'old-token');""")

    def intercept(route):
        if route.request.url == ORIGIN + "/":
            route.fulfill(status=200, content_type="text/html", body=CHAT_HTML)
        elif route.request.url.endswith("/api/auth/visitor"):
            issued.append(route.request.method)
            fulfill_json(route, {"user_id": "new", "token": "new-token", "expires_at": 9999999999})
        elif "/api/extract" in route.request.url:
            requests.append((route.request.url, route.request.headers["authorization"]))
            fulfill_json(route, {}, 401 if requests[-1][1] == "Bearer old-token" else 200)
        elif "/api/" in route.request.url:
            fulfill_json(route, [])
        else:
            route.fulfill(status=200, body="")

    page.route("**/*", intercept)
    page.goto(ORIGIN)
    page.wait_for_load_state("networkidle")
    result = page.evaluate("""async () => {
        setConversationId(17);
        return await Promise.all([apiFetch('/api/extract?user_id=old'), apiFetch('/api/extract?user_id=old')])
            .then(responses => responses.map(response => response.status));
    }""")
    assert result == [200, 200]
    assert issued == ["POST"]
    assert len(requests) == 4
    assert requests[-2:] == [(ORIGIN + "/api/extract?user_id=new", "Bearer new-token")] * 2
    assert page.evaluate("getConversationId()") is None


def test_chat_does_not_loop_after_retry_returns_401(page):
    issued, requests = [], []

    def intercept(route):
        if route.request.url == ORIGIN + "/":
            route.fulfill(status=200, content_type="text/html", body=CHAT_HTML)
        elif route.request.url.endswith("/api/auth/visitor"):
            issued.append(1)
            fulfill_json(route, {"user_id": "v", "token": f"token-{len(issued)}", "expires_at": 9999999999})
        elif route.request.url.endswith("/api/extract"):
            requests.append(1)
            fulfill_json(route, {}, 401)
        elif "/api/" in route.request.url:
            fulfill_json(route, [])
        else:
            route.fulfill(status=200, body="")

    page.route("**/*", intercept)
    page.goto(ORIGIN)
    page.wait_for_load_state("networkidle")
    assert page.evaluate("async () => (await apiFetch('/api/extract')).status") == 401
    assert len(requests) == 2 and len(issued) == 2


def test_admin_503_is_returned_without_prompt(page):
    """503 可能是依赖未就绪或服务端未配置 ADMIN_TOKEN，重新输入令牌无济于事。"""
    requests, prompts = [], []

    def intercept(route):
        if route.request.url == ORIGIN + "/":
            route.fulfill(status=200, content_type="text/html", body=f"<script>{ADMIN_JS}</script>")
        else:
            requests.append(route.request.headers.get("authorization"))
            fulfill_json(route, {"detail": "未配置 ADMIN_TOKEN"}, 503)

    page.on("dialog", lambda dialog: (prompts.append(dialog.message), dialog.dismiss()))
    page.route("**/*", intercept)
    page.goto(ORIGIN)
    status = page.evaluate("""async () => {
        localStorage.setItem('minihelp_admin_token', 'stored-token');
        return (await fetch('/api/kb/staging')).status;
    }""")
    assert status == 503
    assert requests == ["Bearer stored-token"]
    assert prompts == []


@pytest.mark.parametrize("status", [401])
@pytest.mark.parametrize("request_object", [False, True])
def test_admin_prompt_retries_once_and_preserves_body_and_headers(page, status, request_object):
    requests, prompts = [], []

    def intercept(route):
        if route.request.url == ORIGIN + "/":
            route.fulfill(status=200, content_type="text/html", body=f"<script>{ADMIN_JS}</script>")
        elif "/api/" in route.request.url:
            requests.append((route.request.headers, route.request.post_data_json))
            fulfill_json(route, {"ok": True}, status if len(requests) == 1 else 200)
        else:
            route.fulfill(status=200, body="")

    def dialog(dialog):
        prompts.append(dialog.message)
        dialog.accept("configured-admin-token")

    page.on("dialog", dialog)
    page.route("**/*", intercept)
    page.goto(ORIGIN)
    response = page.evaluate("""async requestObject => {
        localStorage.setItem('minihelp_admin_token', 'old-token');
        const init = {method:'POST', headers:{'Content-Type':'application/json', 'X-Test':'preserve'}, body:JSON.stringify({ids:[7]})};
        const result = requestObject ? await fetch(new Request(location.origin + '/api/kb/staging/approve', init))
                                    : await fetch('/api/kb/staging/approve', init);
        return result.status;
    }""", request_object)
    assert response == 200 and len(requests) == 2 and len(prompts) == 1
    assert "ADMIN_TOKEN" in prompts[0]
    assert requests[0][0]["authorization"] == "Bearer old-token"
    assert requests[1][0]["authorization"] == "Bearer configured-admin-token"
    assert all(headers["x-test"] == "preserve" and body == {"ids": [7]} for headers, body in requests)
    assert page.evaluate("localStorage.getItem('minihelp_admin_token')") == "configured-admin-token"


@pytest.mark.parametrize("cancelled", [False, True])
def test_admin_retry_is_bounded_and_external_requests_receive_no_token(page, cancelled):
    requests, prompts = [], []

    def intercept(route):
        if route.request.url == ORIGIN + "/":
            route.fulfill(status=200, content_type="text/html", body=f"<script>{ADMIN_JS}</script>")
        else:
            requests.append((route.request.url, route.request.headers.get("authorization")))
            route.fulfill(status=401 if route.request.url.startswith(ORIGIN + "/api/") else 200,
                          headers={"Access-Control-Allow-Origin": "*"}, body="{}")

    def dialog(dialog):
        prompts.append(dialog.message)
        dialog.dismiss() if cancelled else dialog.accept("still-wrong")

    page.on("dialog", dialog)
    page.route("**/*", intercept)
    page.goto(ORIGIN)
    assert page.evaluate("async () => (await fetch('/api/jobs')).status") == 401
    assert len(prompts) == 1 and len(requests) == (1 if cancelled else 2)
    page.evaluate("""async () => {
        localStorage.setItem('minihelp_admin_token', 'private');
        await fetch('http://external.example/api/jobs');
        await fetch('/static/admin-theme.css');
    }""")
    assert requests[-2:] == [("http://external.example/api/jobs", None), (ORIGIN + "/static/admin-theme.css", None)]
    assert len(prompts) == 1


def test_all_admin_pages_load_auth_before_other_scripts():
    for path in Path("app/static").glob("*.html"):
        if path.name != "index.html":
            html = path.read_text(encoding="utf-8")
            assert html[html.index("<script"):].startswith('<script src="/static/admin-auth.js"></script>')
