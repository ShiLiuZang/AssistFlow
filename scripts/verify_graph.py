"""端到端验收：使用当前配置，创建新会话及一个本地演示工单。"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright
from sqlalchemy import func, select

from app.config import settings
from app.db import database
from app.db.database import engine
from app.db.models import Ticket
from app.graph.adapters import make_services
from app.graph.checkpoint import persistent_runtime

BASE = "http://127.0.0.1:8000"
REPORT = Path("reports/05_live.json")


def parse(response):
    response.raise_for_status()
    assert "event: error" not in response.text, "服务返回 SSE 错误"
    assert "data: [DONE]" in response.text
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: {")]


async def count_tickets(cid):
    async with database.SessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(Ticket).where(Ticket.conversation_id == cid))


async def verify(report):
    async with httpx.AsyncClient(base_url=BASE, timeout=180) as client:
        assert (await client.get("/api/health")).json()["status"] == "ok"
        cases = [
            ("chat", "你好", "chat"),
            ("knowledge", "七天无理由退货的条件是什么？", "knowledge"),
            ("complaint", "我要投诉，客服态度太差了", "complaint"),
            ("order", "请查询我的订单 ORD-1001 的商品和物流状态", "business"),
            ("refund", "请为订单 ORD-1001 创建退款工单，原因是商品破损。这是本地验收工单。", "business"),
        ]
        for name, query, intent in cases:
            events = parse(await client.post("/api/graph-chat", json={"user_id": "u1", "message": query}))
            cid = next(e["conversation_id"] for e in events if "conversation_id" in e)
            async with persistent_runtime(make_services(), settings.graph_checkpoint_path) as runtime:
                snapshot = await runtime.get_state("u1", cid)
            state = snapshot.values
            row = {"case": name, "query": query, "conversation_id": cid,
                   "intent": state["intent"], "trace": state["trace"],
                   "answer": state.get("answer", ""), "citation_count": len(state.get("citations", []))}
            report["cases"].append(row)
            assert state["intent"] == intent, row
            expected_path = {"chat": ["classify", "chat", "finish"],
                             "knowledge": ["classify", "retrieve", "answer", "finish"],
                             "complaint": ["classify", "complaint", "finish"]}
            if name in expected_path:
                assert state["trace"] == expected_path[name], row
            if name == "knowledge":
                assert state["citations"] and "[" in row["answer"], row
                row["sources"] = [c.get("section_path") for c in state["citations"]]
            if name == "order":
                assert "tools" in state["trace"] and "保温杯" in row["answer"] and "已发货" in row["answer"], row
            if name != "refund":
                assert any(e.get("event") == "done" for e in events)
            else:
                preview = next(e for e in events if e.get("event") == "interrupt")
                assert not any(e.get("event") == "done" for e in events)
                assert await count_tickets(cid) == 0
                params = {"user_id": "u1", "conversation_id": cid}
                assert (await client.post("/api/graph-chat", json={**params, "message": "继续"})).status_code == 409
                for url in ("/api/actions/pending", f"/api/conversations/{cid}/messages"):
                    assert (await client.get(url, params={**params, "user_id": "u2"})).status_code == 404
                assert (await client.post("/api/graph-chat", json={**params, "user_id": "u2", "message": "你好"})).status_code == 404
                body = {**params, "tool_call_id": preview["tool_call_id"], "confirmed": True}
                assert (await client.post("/api/actions/resume", json={**body, "user_id": "u2"})).status_code == 404
                responses = await asyncio.gather(*[client.post("/api/actions/resume", json=body) for _ in range(2)])
                for response in responses:
                    assert any(e.get("event") == "done" for e in parse(response))
                assert await count_tickets(cid) == 1
                row["tickets_before_confirmation"] = 0
                row["tickets_after_concurrent_confirmation"] = 1
                row["ownership_checks"] = "passed"
            row["passed"] = True
            REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"PASS {name}: conversation={cid}", flush=True)

        events = parse(await client.post("/api/graph-chat", json={"user_id": "u1", "message": "请为订单 ORD-1001 创建退款工单，原因是商品破损。这是本地验收工单。"}))
        pending = next(e for e in events if e.get("event") == "interrupt")
        report["browser_conversation_id"] = pending["conversation_id"]
        assert await count_tickets(pending["conversation_id"]) == 0
    await engine.dispose()


def verify_browser(report):
    cid = report["browser_conversation_id"]
    errors, graph_requests = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=os.environ.get("PLAYWRIGHT_CHANNEL", "msedge" if os.name == "nt" else None))
        try:
            page = browser.new_page()
            page.set_default_timeout(180000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda req: graph_requests.append(req.url) if req.url.endswith("/api/graph-chat") else None)
            page.goto(BASE)
            page.wait_for_load_state("networkidle")
            page.evaluate("cid => { localStorage.setItem('minihelp_session_id', 'u1'); localStorage.setItem('minihelp_conversation_id', String(cid)); }", cid)
            page.reload()
            page.wait_for_load_state("networkidle")
            page.get_by_role("button", name="取消", exact=True).wait_for()
            assert page.locator(".conv-item").count() > 0
            page.screenshot(path="reports/05_pending.png", full_page=True)
            page.get_by_role("button", name="取消", exact=True).click()
            page.wait_for_function("document.querySelector('#send').disabled === false")
            assert "已取消" in page.locator("#messages").inner_text()
            page.reload()
            page.wait_for_load_state("networkidle")
            page.wait_for_function("document.querySelector('#messages').innerText.includes('取消')")
            assert page.get_by_role("button", name="确认提交", exact=True).count() == 0
            page.locator("#new-chat").click()
            page.locator("#input").fill("你好")
            page.locator("#send").click()
            page.wait_for_function("document.querySelector('#send').disabled === false")
            assert graph_requests and "你好，可以咨询" in page.locator("#messages").inner_text()
            page.screenshot(path="reports/05_browser.png", full_page=True)
            assert not errors, errors
            report["browser"] = {"reload_pending": True, "cancel": True, "reload_history": True,
                                 "graph_chat": True, "javascript_errors": errors}
        finally:
            browser.close()


async def verify_cancel(report):
    assert await count_tickets(report["browser_conversation_id"]) == 0
    report["browser"]["tickets_after_cancel"] = 0
    await engine.dispose()


def main():
    report = {"executed_at": datetime.now(timezone.utc).isoformat(), "passed": False,
              "chat_model": settings.chat_model, "embed_model": settings.embed_model,
              "milvus_collection": settings.milvus_collection, "cases": []}
    REPORT.parent.mkdir(exist_ok=True)
    try:
        asyncio.run(verify(report))
        verify_browser(report)
        asyncio.run(verify_cancel(report))
        report["passed"] = True
    finally:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS live acceptance and browser", flush=True)


if __name__ == "__main__":
    main()
