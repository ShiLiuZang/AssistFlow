# 智能客服

这是一个用于学习和验证的电商智能客服项目。它用 FastAPI 提供聊天与管理接口，用 LangGraph 组织对话流程，用 MySQL 保存业务数据，用 Milvus 检索知识，并提供观测、知识审核和主题分类页面。仓库中的模型权重、真实会话数据和运行数据库不随源码分发。

当前实现面向本地开发与验收。
## 主要功能
- 聊天：流式回复、会话历史、意图判断、政策检索、订单工具、工单确认与失败恢复。
- 知识库：将固定材料切块、写入 MySQL、向量化到 Milvus；管理页支持预览、录入、审核和检索自测。
- 观测与飞轮：记录执行追踪和可用的模型用量，收集低置信度问题与反馈，审核后再发布知识。
- 主题分类：使用 17 类多标签分类器，展示问题分布、错例和验收指标。ONNX 推理服务独立运行在 8110 端口。
请求主链路为：浏览器 → FastAPI 路由 → 对话图或业务服务 → MySQL / Milvus / 模型与 MCP 服务。
## 代码结构
| 路径 | 用途 |
| --- | --- |
| app/api/ | 聊天、会话、知识库、审核、观测、主题和验收接口 |
| app/graph/ | LangGraph 状态、节点、路由及检查点 |
| app/core/ | 检索、模型、置信度、观测、分类和作业逻辑 |
| app/db/ | SQLAlchemy 模型及数据库访问 |
| app/kb/ | 文档切块、建库、向量化和审核发布 |
| app/tools/ | 订单、工单及 MCP 工具 |
| app/static/ | 聊天页与管理后台页面 |
| migrations/ | Alembic 数据库迁移 |
| scripts/ | 建库、验证和主题分类作业；scripts/tasks.py 是统一入口 |
| data/kb/ | 随仓库提供的示例知识材料 |

## 本地启动

需要 Python 3.12 或更新版本、uv、Docker，以及可用的聊天和嵌入模型接口。以下命令在项目根目录执行，示例使用 PowerShell；其他系统可将虚拟环境与复制文件的命令替换为本机等价命令。

### 1. 配置环境

    Copy-Item .env.example .env
    uv sync --group dev

编辑 .env，至少填写 CHAT_MODEL、CHAT_BASE_URL、CHAT_API_KEY、EMBED_MODEL、EMBED_BASE_URL 和 EMBED_API_KEY。可选的重排、MCP 和 Langfuse 配置见 .env.example。

本仓库的 docker-compose.yml 会创建名为 minihelp_complete 的本地 MySQL 数据库，监听 127.0.0.1:3308；Milvus 监听 127.0.0.1:19531。若使用这份 compose，请将 HANDWRITTEN_DATABASE_URL 的数据库名设为 minihelp_complete，并将用户名、密码改成 compose 中的本地开发值。若连接已有独立数据库，以实际连接参数为准。不要把填写了真实密钥的 .env 提交到 Git。

### 2. 启动依赖并初始化空库

    docker compose up -d mysql etcd minio milvus
    docker compose ps
    uv run alembic upgrade head

迁移命令只应对新建的、可处置的项目数据库运行；不要直接拿现有业务库做初始化试验。

### 3. 建立示例知识库

    uv run python -m scripts.tasks kb-preview
    uv run python -m scripts.tasks kb-build
    uv run python -m scripts.tasks kb-vectorize

预览不写库；建库将 data/kb/ 中的材料写入 MySQL 待向量化队列；向量化调用嵌入服务并写入 Milvus。后两步需要正确的数据库、模型与 Milvus 配置。

### 4. 启动网页

    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

| 地址 | 页面 |
| --- | --- |
| http://127.0.0.1:8000/ | 聊天 |
| http://127.0.0.1:8000/admin | 管理后台 |
| http://127.0.0.1:8000/kb | 知识库 |
| http://127.0.0.1:8000/review | 审核队列 |
| http://127.0.0.1:8000/observability | 观测 |
| http://127.0.0.1:8000/topics | 主题分布 |
| http://127.0.0.1:8000/acceptance | 分类器验收 |
| http://127.0.0.1:8000/docs | FastAPI 接口文档 |


## 可选：主题分类器

训练和导出还需要机器学习依赖及本地基础模型。先安装 ml 依赖，并将兼容的中文 RoBERTa-wwm-ext 基础权重放在 data/finetune/pretrained/；

    uv sync --group dev --group ml
    uv run --group ml python -m scripts.tasks finetune-golden
    uv run --group ml python -m scripts.tasks finetune-corpus
    uv run --group ml python -m scripts.tasks finetune-dataset
    uv run --group ml python -m scripts.tasks finetune-train
    uv run --group ml python -m scripts.tasks finetune-eval
    uv run --group ml python -m scripts.tasks finetune-export

语料作业需要聊天模型和数据库；训练需要前一步生成的数据。导出 ONNX 后，可在验收页启动分类服务，也可运行：

    uv run --group ml python -m scripts.tasks classifier-up

分类服务监听 127.0.0.1:8110。验收页读取本地评测产物，按严档 F1 ≥ 0.9、中档 F1 ≥ 0.8 判断红线。未通过会显示错例和修复方向。
