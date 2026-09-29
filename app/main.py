import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.chat import router as chat_router
from app.api.graph_chat import router as graph_chat_router
from app.api.extract import router as extract_router
from app.api.conversations import router as conversations_router
from app.api.actions import router as actions_router
from app.api.knowledge import router as knowledge_router
from app.config import settings
from app.core.summarizer import close_persisted_summaries
from app.db import repository
from app.graph.adapters import make_services_with_mcp
from app.graph.checkpoint import persistent_runtime
from app.tools.mcp_client import StreamableHTTPTransport
from app.core.langfuse_client import (
    create_langfuse_client,
    close_langfuse_client,
)
from app.api.feedback import router as feedback_router
from app.api.review import router as review_router
from app.api.kb import router as kb_router
from app.api.jobs import router as jobs_router
from app.api.admin import router as admin_router
from app.api.acceptance import router as acceptance_router
from app.api.topics import router as topics_router
from app.core.observability import configure_langfuse, configure_trace_sink
from app.api.observability import router as observability_router
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    server_urls = {
        server: url
        for server, url in {
            "logistics": settings.mcp_logistics_url,
            "aftersales": settings.mcp_aftersales_url,
        }.items()
        if url.strip()
    }
    services, issues = await make_services_with_mcp(
        StreamableHTTPTransport(server_urls),
        list(server_urls),
    )
    services.audit_sink = repository.insert_tool_audit
    services.trace_sink = repository.insert_trace_span

    for issue in issues:
        logger.warning("MCP 工具发现异常：%s", issue)

    langfuse_client = create_langfuse_client(settings)
    configure_langfuse(langfuse_client)
    configure_trace_sink(services.trace_sink)
    app.state.langfuse_client = langfuse_client
    app.state.graph_runtime = None

    try:
        async with persistent_runtime(
            services,
            settings.graph_checkpoint_path,
        ) as runtime:
            app.state.graph_runtime = runtime

            try:
                yield
            finally:
                await close_persisted_summaries()
    finally:
        configure_trace_sink(None)
        configure_langfuse(None)
        app.state.graph_runtime = None
        app.state.langfuse_client = None
        await close_langfuse_client(langfuse_client)


STATIC_DIR = Path(__file__).parent / "static"

# 主应用负责把各业务路由和静态前端组装成一个可启动的 Web 服务。
app = FastAPI(
    title="Minihelp Handwritten",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(chat_router)
app.include_router(graph_chat_router)
app.include_router(extract_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(conversations_router)
app.include_router(actions_router)
app.include_router(knowledge_router)
app.include_router(observability_router)
app.include_router(feedback_router)
app.include_router(review_router)
app.include_router(kb_router)
app.include_router(jobs_router)
app.include_router(admin_router)
app.include_router(acceptance_router)
app.include_router(topics_router)
@app.get("/api/health")
async def health() -> dict[str, str]:
    """返回进程存活状态；不检查模型、数据库或其他外部服务。"""
    return {
        "status": "ok",
        "service": "minihelp-handwritten",
        "chapter": "ch05",
    }


@app.get("/", include_in_schema=False)
async def chat_page() -> FileResponse:
    """返回聊天首页，页面随后通过 /api/graph-chat 调用后端。"""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/observability", include_in_schema=False)
async def observability_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "observability.html")


@app.get("/admin", include_in_schema=False)
async def admin_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


# 管理后台的 HTML 不会因为放在 static 目录中自动获得页面路由，
# 统一在这里声明入口，避免文档入口和实际服务路径不一致。
ADMIN_PAGES = {
    "/kb": "kb.html",
    "/rag-eval": "rageval.html",
    "/review": "review.html",
    "/topics": "topics.html",
    "/topic-questions": "topic-questions.html",
    "/topics/questions": "topic-questions.html",
    "/acceptance": "acceptance.html",
    "/acceptance-eval": "acceptance-eval.html",
    "/acceptance-data": "acceptance-data.html",
    "/acceptance-errors": "acceptance-errors.html",
    "/acceptance/eval": "acceptance-eval.html",
    "/acceptance/data": "acceptance-data.html",
    "/acceptance/errors": "acceptance-errors.html",
}


def _admin_page(path: str) -> FileResponse:
    return FileResponse(
        STATIC_DIR / ADMIN_PAGES[path],
        headers={"Cache-Control": "no-store"},
    )


for _path in ADMIN_PAGES:
    app.add_api_route(
        _path,
        lambda path=_path: _admin_page(path),
        methods=["GET"],
        include_in_schema=False,
    )
