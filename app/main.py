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
from app.graph.adapters import make_services
from app.graph.checkpoint import persistent_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with persistent_runtime(
        make_services(),
        settings.graph_checkpoint_path,
    ) as runtime:
        app.state.graph_runtime = runtime
        yield
        app.state.graph_runtime = None


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
