from contextlib import asynccontextmanager
from pathlib import Path

from .build import build_graph
from .runtime import Runtime


@asynccontextmanager
async def persistent_runtime(services, path):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    async with AsyncSqliteSaver.from_conn_string(str(database_path)) as saver:
        yield Runtime(build_graph(services, checkpointer=saver))