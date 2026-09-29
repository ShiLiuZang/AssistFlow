# 模块：图运行时检查点管理
# 提供带持久化检查点的图运行时创建函数
# 使用SQLite存储对话状态，支持中断恢复和多轮对话
# 核心职责：封装LangGraph检查点机制，确保对话状态可靠持久化

from contextlib import asynccontextmanager
from pathlib import Path

from .build import build_graph
from .runtime import Runtime


@asynccontextmanager
async def persistent_runtime(services, path):
    """
    创建带持久化检查点的图运行时

    参数:
        services: 服务容器（包含LLM、数据库等依赖）
        path: SQLite数据库文件路径

    返回:
        Runtime实例，退出时自动关闭检查点连接

    设计说明:
        使用AsyncSqliteSaver存储图状态到SQLite
        支持中断恢复：订单选择等待、错误重试
        自动创建数据库文件的父目录
        上下文管理器确保数据库连接正确关闭
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    async with AsyncSqliteSaver.from_conn_string(str(database_path)) as saver:
        yield Runtime(
            build_graph(services, checkpointer=saver),
            trace_sink=getattr(services, "trace_sink", None),
        )