"""
智能客服系统主应用入口

本模块是基于 FastAPI + LangGraph 的电商智能客服系统的启动文件，负责：
1. 应用生命周期管理（MCP 工具发现、图运行时初始化、观测配置）
2. 路由注册（聊天、知识库、管理后台等 API 端点）
3. 静态资源服务（前端页面）
4. 健康检查和管理页面

系统架构：
- FastAPI：Web 框架，提供 REST API 和 WebSocket 支持
- LangGraph：对话流程图引擎，支持状态持久化和断点续传
- MCP（Model Context Protocol）：外部工具集成协议，动态发现和调用工具
- Langfuse：LLM 应用观测平台，记录 token 用量和执行追踪
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

# API 路由导入
from app.api.auth import router as auth_router  # 登录与令牌
from app.api.graph_chat import router as graph_chat_router  # LangGraph 驱动的聊天接口
from app.api.extract import router as extract_router  # 信息抽取接口
from app.api.conversations import router as conversations_router  # 会话历史管理
from app.api.actions import router as actions_router  # 用户动作记录
from app.api.knowledge import router as knowledge_router  # 知识库查询
from app.api.feedback import router as feedback_router  # 用户反馈
from app.api.review import router as review_router  # 知识审核
from app.api.kb import router as kb_router  # 知识库管理
from app.api.jobs import router as jobs_router  # 后台任务
from app.api.admin import router as admin_router  # 管理后台
from app.api.acceptance import router as acceptance_router  # 验收测试
from app.api.topics import router as topics_router  # 话题管理
from app.api.observability import router as observability_router  # 观测数据
from app.api.agent import router as agent_router  # 人工坐席工作台
from app.api.channels import router as channels_router  # 外部渠道（拼多多）

# 核心服务导入
from app.channels import service as channels  # 外部渠道接入
from app.config import settings  # 配置管理
from app.core import auth  # 认证配置校验
from app.kb import rerank  # 精排服务（关闭连接池）
from app.core.instance_lock import single_instance  # 单进程保护
from app.core.safety import install_log_redaction  # 日志脱敏
from app.core.realtime import install_shutdown_hook  # 实时推送
from app.core.summarizer import close_persisted_summaries  # 对话摘要持久化
from app.db import trace_repo
from app.graph.adapters import make_services_with_mcp  # 服务容器和 MCP 工具集成
from app.graph.checkpoint import persistent_runtime  # 图运行时和检查点管理
from app.tools.mcp_client import StreamableHTTPTransport  # MCP HTTP 传输层
from app.core.langfuse_client import (
    create_langfuse_client,
    close_langfuse_client,
)  # Langfuse 客户端生命周期
from app.core.observability import configure_langfuse, configure_trace_sink  # 观测配置

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """同一台机器上只允许一个进程运行（见 app.core.instance_lock），再完成启动装配。"""
    with single_instance(settings.graph_checkpoint_path + ".lock"):
        async with _lifespan(app):
            yield


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期管理

    在应用启动时执行以下初始化：
    1. MCP 工具发现：连接配置的 MCP 服务器，动态加载工具定义
    2. 服务容器初始化：注入审计和追踪的数据落库回调
    3. Langfuse 客户端：初始化观测平台，记录 LLM 调用和 token 用量
    4. 图运行时：初始化 LangGraph 运行时，启用会话状态持久化

    在应用关闭时执行清理：
    1. 关闭持久化摘要的后台任务
    2. 清理观测配置
    3. 关闭 Langfuse 客户端，刷新未上报的数据

    参考 git commit 805cba5 (接入执行追踪持久化与 Langfuse 观测)
    参考 git commit 21557ba (增加受控 MCP 发现与调用适配)
    """
    # 0. 认证密钥不满足要求时拒绝启动（开发模式除外）；日志统一脱敏
    auth.check_configuration()
    channels.check_configuration()
    install_log_redaction()
    install_shutdown_hook()  # 退出时结束实时推送长连接

    # 1. 从环境变量收集已配置的 MCP 服务器 URL
    # 仅包含非空 URL，支持逐步启用 MCP 服务器
    server_urls = {
        server: url
        for server, url in {
            "logistics": settings.mcp_logistics_url,  # 物流查询工具
            "aftersales": settings.mcp_aftersales_url,  # 售后工单工具
        }.items()
        if url.strip()
    }

    # 2. 使用 HTTP 传输层连接 MCP 服务器，发现可用工具
    # services: 服务容器，包含工具注册表和执行引擎
    # issues: 发现过程中的警告信息（如工具定义不合法）
    services, issues = await make_services_with_mcp(
        StreamableHTTPTransport(server_urls),
        list(server_urls),
    )

    # 3. 注入数据落库回调
    # audit_sink: 记录工具调用参数和结果，用于审计和重放（git commit ded9aed）
    # trace_sink: 记录执行追踪 span，用于性能分析和调试（git commit 805cba5）
    services.audit_sink = trace_repo.insert_tool_audit
    services.trace_sink = trace_repo.insert_trace_span

    # 4. 记录 MCP 工具发现异常
    for issue in issues:
        logger.warning("MCP 工具发现异常：%s", issue)

    # 5. 初始化 Langfuse 客户端（LLM 观测平台）
    # 全局配置观测客户端，所有 LLM 调用自动上报 token 用量和执行轨迹
    langfuse_client = create_langfuse_client(settings)
    configure_langfuse(langfuse_client)
    configure_trace_sink(services.trace_sink)

    # 将关键对象挂载到 app.state，供路由处理器访问
    app.state.langfuse_client = langfuse_client
    app.state.graph_runtime = None

    try:
        # 6. 初始化图运行时和检查点持久化
        # 支持会话状态断点续传，用户可以中断对话后继续（git commit 89bffc8）
        async with persistent_runtime(
            services,
            settings.graph_checkpoint_path,
        ) as runtime:
            app.state.graph_runtime = runtime

            try:
                # 7. 外部渠道（拼多多）开启时启动消息调度，然后开始接受请求
                async with channels.running(lambda: app.state.graph_runtime):
                    yield
            finally:
                # 8. 应用关闭时，先关闭后台摘要任务
                # 确保滚动摘要写入数据库，避免丢失上下文压缩结果（git commit 22c8248）
                await close_persisted_summaries()
    finally:
        # 9. 清理观测配置和图运行时
        configure_trace_sink(None)
        configure_langfuse(None)
        app.state.graph_runtime = None
        app.state.langfuse_client = None
        # 10. 关闭 Langfuse 客户端，刷新未上报的观测数据
        await close_langfuse_client(langfuse_client)
        await rerank.close_client()  # 精排服务的连接池


# Vue 前端构建产物（frontend/web 下执行 npm run build 生成）
WEB_DIST = Path(__file__).resolve().parents[1] / "frontend" / "web" / "dist"


# 创建 FastAPI 应用实例
app = FastAPI(
    title="AssistFlow",
    version="0.1.0",
    lifespan=lifespan,  # 应用生命周期管理
)

# 注册 API 路由
app.include_router(auth_router)  # 登录与令牌（无需鉴权）
app.include_router(graph_chat_router)  # LangGraph 聊天（主要接口）

# 辅助功能接口
app.include_router(extract_router)  # 信息抽取
app.include_router(conversations_router)  # 会话历史
app.include_router(actions_router)  # 用户动作记录
app.include_router(knowledge_router)  # 知识库查询

# 观测和反馈接口
app.include_router(observability_router)  # 观测数据（token 用量、追踪）
app.include_router(feedback_router)  # 用户反馈

# 知识库管理接口
app.include_router(review_router)  # 知识审核
app.include_router(kb_router)  # 知识库管理

# 后台任务和管理接口
app.include_router(jobs_router)  # 后台任务（摘要、挖掘等）
app.include_router(admin_router)  # 管理后台

# 测试和话题管理接口
app.include_router(acceptance_router)  # 验收测试
app.include_router(topics_router)  # 话题管理
app.include_router(agent_router)  # 人工坐席工作台与工单
app.include_router(channels_router)  # 外部渠道（拼多多）


@app.get("/api/health")
async def health() -> dict[str, str]:
    """
    健康检查接口

    返回进程存活状态，不检查模型、数据库或其他外部服务。
    用于 Kubernetes liveness probe 或负载均衡器健康检查。
    """
    return {"status": "ok", "service": "assistflow"}


@app.get("/", include_in_schema=False, response_model=None)
async def web_index() -> FileResponse | PlainTextResponse:
    """
    前端入口

    Vue 使用 hash 路由（#/overview、#/client …），只需返回 index.html；
    尚未构建时给出提示，而不是 404。
    """
    index = WEB_DIST / "index.html"
    if not index.is_file():
        return PlainTextResponse(
            "前端尚未构建：请在 frontend/web 下执行 npm install && npm run build",
            status_code=503,
        )
    return FileResponse(index, headers={"Cache-Control": "no-store"})


# 构建产物中的静态资源（JS、CSS、图片）；目录不存在时不挂载，避免启动失败
if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")
