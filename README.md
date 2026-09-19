# Minihelp 手敲学习版

Ch01：FastAPI、请求校验、SSE 增量输出、结构化提取。
Ch02：订单工具、会话历史、工单预览确认、工具消息配对。
Ch03：Markdown 分块、原文建库恢复、Embedding、Milvus Dense 检索与聊天接入。
Ch04：独立实现和教案见 [教学代码包](teaching-package/README.md)，不写回原项目。

约束见 [教学约束](docs/TEACHING_RULES.md)，实际修复和验证边界见 [修复记录](docs/REPAIR_STATUS.md)。

## 运行

在本项目根目录配置 `.env`（参考 `.env.example`），准备独立 MySQL 数据库和 Milvus，然后执行：

```powershell
uv sync
uv run alembic upgrade head
uv run python -m scripts.preview_kb
uv run python -m scripts.build_kb
uv run python -m scripts.vectorize_kb
uv run python -m scripts.verify_03
uv run uvicorn app.main:app --reload
```

预览只读；建库写 MySQL；向量化调用 Embedding 并写 Milvus。失败后重跑 build/vectorize 即可补齐固定材料。更新旧材料不属于此重跑语义。

离线测试明确指定 tests，避免收集独立教学副本：

```powershell
uv run pytest tests -q -p no:cacheprovider
```

历史知识审核（输入为自行脱敏的对话 JSON 数组）：

```powershell
uv run python -m scripts.kb_review mine --input dialogue.json
uv run python -m scripts.kb_review list
uv run python -m scripts.kb_review approve --index 0 --reviewer teacher
uv run python -m scripts.vectorize_kb
```

mine 仅生成暂存候选；approve 才将白名单材料支持的候选写为 pending。未审核候选不进入正式知识库。审核队列不提交 Git。
