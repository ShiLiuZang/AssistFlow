"""后台管理页作业运行器:把 make 目标搬到浏览器上按,日志轮询回显,长活能停。

安全边界:只能跑 JOBS 注册表里的目标,argv 全部写死在本模块。前端只传一个 job 名,
传不进任何命令片段、参数或路径——页面有「重跑」按钮,但没有 shell。
命令统一走 scripts.tasks，支持 Windows 与 Unix，页面和终端共用白名单。
"""
import asyncio
import contextlib
import datetime as dt
import logging
import os
import signal
import sys
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "log" / "acceptance"
TAIL_LINES = 400        # 回显窗口上限:日志文件只读尾部,训练几万行也不撑爆响应


@dataclass(frozen=True)
class JobSpec:
    name: str
    title: str
    argv: tuple[str, ...]
    needs: str                    # 前置条件,页面按钮上直接提示,免得点了才发现上游没配好
    heavy: bool = False           # 分钟级重活:页面二次确认才发起


# Minihelp 作业运行器保留；只注册当前项目确实存在的脚本入口。
# Windows 和 Unix 共用 Python 命令，不依赖 make。
JOBS: dict[str, JobSpec] = {
    spec.name: spec for spec in (
        JobSpec("kb-preview", "材料清单与切块预览",
                (sys.executable, "-m", "scripts.tasks", "kb-preview"), "本地运行，不写库"),
        JobSpec("kb-build", "离线建库（文档切块 → pending）",
                (sys.executable, "-m", "scripts.tasks", "kb-build"), "需要 MySQL"),
        JobSpec("kb-vectorize", "向量化（嵌入 → Milvus → done）",
                (sys.executable, "-m", "scripts.tasks", "kb-vectorize"),
                "需要 MySQL、嵌入服务和 Milvus"),
        JobSpec("finetune-golden", "黄金样例校验",
                (sys.executable, "-m", "scripts.tasks", "finetune-golden"),
                "需要聊天模型"),
        JobSpec("finetune-corpus", "构建主题语料",
                (sys.executable, "-m", "scripts.tasks", "finetune-corpus"),
                "需要 MySQL 与聊天模型", heavy=True),
        JobSpec("finetune-dataset", "划分与增强数据集",
                (sys.executable, "-m", "scripts.tasks", "finetune-dataset"),
                "需要主题语料与聊天模型", heavy=True),
        JobSpec("finetune-train", "训练分类器",
                (sys.executable, "-m", "scripts.tasks", "finetune-train"),
                "需要 ml 依赖和训练数据", heavy=True),
        JobSpec("finetune-eval", "测试集评测",
                (sys.executable, "-m", "scripts.tasks", "finetune-eval"),
                "需要 ml 依赖和训练权重", heavy=True),
        JobSpec("finetune-export", "导出 ONNX",
                (sys.executable, "-m", "scripts.tasks", "finetune-export"),
                "需要 ml 依赖和训练权重", heavy=True),
        JobSpec("finetune-threshold-scan", "重演阈值扫描",
                (sys.executable, "-m", "scripts.tasks", "finetune-threshold-scan"),
                "需要验证集与分类服务", heavy=True),
        JobSpec("classifier-up", "启动分类服务",
                (sys.executable, "-m", "scripts.tasks", "classifier-up"),
                "需要 ONNX 产物与 ml 依赖"),
        JobSpec("classify-pool", "批量归类问题池",
                (sys.executable, "-m", "scripts.tasks", "classify-pool"),
                "需要 MySQL 与分类服务", heavy=True),
        JobSpec("classify-pool-force", "强制归类小批次",
                (sys.executable, "-m", "scripts.tasks", "classify-pool-force"),
                "需要 MySQL 与分类服务", heavy=True),
        JobSpec("classify-history", "归类历史用户提问（隔离库）",
                (sys.executable, "-m", "scripts.tasks", "classify-history"),
                "需要历史会话与分类服务，不改业务表", heavy=True),
    )
}


@dataclass
class JobRun:
    """一次运行的状态。进程对象与 watcher 任务留在内存,重启服务后归零——
    但产物里的 ran_at 与日志文件都在盘上,页面照样能说出「上次什么时候跑的、跑成什么样」。"""
    status: str = "idle"          # idle | running | ok | failed | stopped
    pid: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    returncode: int | None = None
    proc: asyncio.subprocess.Process | None = field(default=None, repr=False)
    watcher: asyncio.Task | None = field(default=None, repr=False)


_runs: dict[str, JobRun] = {}


def _stop_windows_tree(pid: int) -> None:
    """结束本作业启动的 Python 子进程树，不依赖 taskkill。"""
    import psutil

    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for child in reversed(children):
        with contextlib.suppress(psutil.NoSuchProcess):
            child.terminate()
    with contextlib.suppress(psutil.NoSuchProcess):
        parent.terminate()


def _run(name: str) -> JobRun:
    return _runs.setdefault(name, JobRun())


def log_path(name: str) -> Path:
    return LOG_DIR / f"{name}.log"


async def start(name: str) -> JobRun:
    """发起一次运行。同名作业未结束时拒绝重入(返回 RuntimeError),避免两份进程抢同一批产物。"""
    spec = JOBS[name]
    run = _run(name)
    if run.status == "running":
        raise RuntimeError(f"{spec.title}正在运行中(pid {run.pid}),等它跑完再发起")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = log_path(name)
    header = (f"$ {' '.join(spec.argv)}\n"
              f"# {dt.datetime.now().isoformat(timespec='seconds')} 由后台页发起\n\n")
    path.write_text(header, encoding="utf-8")          # 每次覆盖:窗口里只看本次
    fh = path.open("a", encoding="utf-8", buffering=1)
    try:
        proc = await asyncio.create_subprocess_exec(
            *spec.argv, cwd=REPO_ROOT, stdout=fh, stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1",
                 "UV_CACHE_DIR": str(REPO_ROOT / ".uv-cache")},
            # 独立会话:kill 时能连 make → uv → python 整条链一起收,不留孤儿进程
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt"
               else {"start_new_session": True}),
        )
    except Exception:
        fh.close()
        raise

    run.status, run.pid = "running", proc.pid
    run.started_at = dt.datetime.now().isoformat(timespec="seconds")
    run.finished_at = run.returncode = None
    run.proc = proc
    run.watcher = asyncio.create_task(_watch(name, run, proc, fh))
    logger.info("验收页发起作业 %s pid=%s argv=%s", name, proc.pid, " ".join(spec.argv))
    return run


async def _watch(name: str, run: JobRun, proc: asyncio.subprocess.Process, fh) -> None:
    try:
        rc = await proc.wait()
    finally:
        with contextlib.suppress(Exception):
            fh.close()
    run.returncode = rc
    run.finished_at = dt.datetime.now().isoformat(timespec="seconds")
    # stopped 保留:人为 kill 的退出码也是非 0,别报成「作业失败」冤枉它
    if run.status != "stopped":
        run.status = "ok" if rc == 0 else "failed"
    run.proc = None
    logger.info("验收页作业 %s 结束 rc=%s status=%s", name, rc, run.status)


async def stop(name: str) -> None:
    run = _run(name)
    proc = run.proc
    if run.status != "running" or proc is None:
        raise RuntimeError("该作业当前没有在运行")
    run.status = "stopped"
    if os.name == "nt":
        try:
            await asyncio.to_thread(_stop_windows_tree, proc.pid)
            await asyncio.wait_for(proc.wait(), timeout=10)
        except Exception:
            if proc.returncode is None:
                run.status = "running"
            raise
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), timeout=10)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


def tail(name: str, lines: int = TAIL_LINES) -> str:
    path = log_path(name)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = text.splitlines()
    return "\n".join(rows[-lines:])


def status(name: str, with_log: bool = False) -> dict:
    spec, run = JOBS[name], _run(name)
    path = log_path(name)
    out = {
        "name": name, "title": spec.title, "cmd": " ".join(spec.argv),
        "needs": spec.needs, "heavy": spec.heavy,
        "status": run.status, "pid": run.pid,
        "started_at": run.started_at, "finished_at": run.finished_at,
        "returncode": run.returncode,
        # 服务重启后内存状态归零,但日志文件的 mtime 还在:据此告知「上次跑过,时间是…」
        "log_mtime": (dt.datetime.fromtimestamp(path.stat().st_mtime)
                      .isoformat(timespec="seconds") if path.exists() else None),
    }
    if with_log:
        out["log"] = tail(name)
    return out


def status_all() -> list[dict]:
    return [status(n) for n in JOBS]
