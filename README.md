

Ch01：FastAPI、请求校验、SSE 增量输出、结构化提取。
Ch02：订单工具、会话历史、工单预览确认、工具消息配对。
Ch03：Markdown 分块、原文建库恢复、Embedding、Milvus Dense 检索与聊天接入。
Ch04：在原项目手写检索、引用和评测；验收见 [记录](docs/CH04_ACCEPTANCE.md)。
Ch05：Workflow + Agent 混合架构及网页接入已完成，真实模型、MySQL、Milvus 验收见 [验收记录](docs/CH05_LIVE_ACCEPTANCE.md)，流程说明见 [学习进度](docs/CH05_PROGRESS.md)。完整参考代码独立保存。

Ch05 链路和架构见 [架构文档](docs/CH05_ARCHITECTURE.md)，包含普通请求、图节点、工单确认、检查点、消息同步和 SSE 事件。

Ch06：退款、选单恢复、政策检索和网页接入已完成本地真实联调；当前结果和限制见 [学习进度](docs/CH06_PROGRESS.md) 与 [审查报告](docs/CH06_REVIEW.md)。教学课时见 [课时安排](teaching-package/ch06/docs/LESSONS.md)。

Ch07：长对话上下文管理独立教学包已生成，包含源码快照、参考实现和六课文档。入口见 [教学包](teaching-package/ch07/docs/README.md)、[每课内容](teaching-package/ch07/docs/LESSONS.md)；主项目接入状态见 [学习进度](docs/CH07_PROGRESS.md)。

约束见 [教学约束](docs/TEACHING_RULES.md)，实际修复和验证边界见 [修复记录](docs/REPAIR_STATUS.md)。

## 启动项目

在项目根目录配置 `.env`（参考 `.env.example`）。当前 compose 会在本机启动 MySQL、Milvus 及其依赖，端口固定为 MySQL `3308`、Milvus `19531`。

### 1. 启动基础服务

```powershell
# 在项目根目录运行
docker compose up -d mysql etcd minio milvus
docker compose ps
```

### 2. 初始化数据库和知识库

首次启动或迁移表结构时运行：

```powershell
.venv\Scripts\python.exe -B -m alembic upgrade head
```

固定材料建库和向量化：

```powershell
.venv\Scripts\python.exe -B -m scripts.preview_kb  # 只读预览，可选
.venv\Scripts\python.exe -B -m scripts.build_kb
.venv\Scripts\python.exe -B -m scripts.vectorize_kb
```

`build_kb` 写入 MySQL，`vectorize_kb` 调用 Embedding 服务并写入 Milvus。失败后可重跑这两个命令；它们只针对当前版本的固定材料，不负责旧材料迁移。

### 3. 启动网页服务

```powershell
.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000/>，健康检查地址为 <http://127.0.0.1:8000/api/health>。

### 4. 验证知识检索和网页链路

```powershell
.venv\Scripts\python.exe -B -m scripts.verify_03
```

Ch06 的真实联调结果、退款选单恢复和验收边界记录在 [CH06_PROGRESS.md](docs/CH06_PROGRESS.md)。旧 `scripts.verify_05` 仍包含 Ch05 路径断言，不能直接作为 Ch06 的最终验收入口。

### 停止服务

停止容器：

```powershell
docker compose stop
```

停止网页服务：在运行 Uvicorn 的终端按 `Ctrl+C`。

## 测试

离线测试明确指定 tests，避免收集独立教学副本：

```powershell
.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider
```

历史知识审核（输入为自行脱敏的对话 JSON 数组）：

```powershell
uv run python -m scripts.kb_review mine --input dialogue.json
uv run python -m scripts.kb_review list
uv run python -m scripts.kb_review approve --index 0 --reviewer teacher
uv run python -m scripts.vectorize_kb
```

mine 仅生成暂存候选；approve 才将白名单材料支持的候选写为 pending。未审核候选不进入正式知识库。审核队列不提交 Git。
