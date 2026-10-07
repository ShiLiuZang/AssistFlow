"""
配置管理模块

使用 Pydantic Settings 从 .env 文件读取并校验应用配置。
配置项包括：
1. LLM 模型配置（聊天模型、嵌入模型）
2. 数据库连接（MySQL、Milvus 向量库）
3. RAG 检索参数（召回数、重排序阈值）
4. MCP 工具服务器 URL
5. Langfuse 观测平台配置

配置优先级：环境变量 > .env 文件 > 默认值
"""

import logging
from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    应用配置类

    从 .env 文件读取并校验模型与数据库配置。
    使用 Pydantic 进行类型校验和默认值设置。
    """

    model_config = SettingsConfigDict(
        env_file=".env",  # 从项目根目录的 .env 文件读取
        extra="ignore",  # 忽略未定义的环境变量
    )

    # ==================== LLM 聊天模型配置 ====================
    chat_model: str  # 模型名称，如 "gpt-4" 或 "claude-3-5-sonnet-20241022"
    chat_base_url: str  # API 基础 URL，如 "https://api.openai.com/v1"
    chat_api_key: str  # API 密钥
    chat_thinking: str = "disabled"  # 思考模式，"disabled" 或 "enabled"（仅部分模型支持）

    # ==================== 数据库配置 ====================
    mysql_database_url: str  # MySQL 异步连接 URL（使用 asyncmy 驱动，必填）
    graph_checkpoint_path: str = "data/graph-checkpoints.sqlite"  # LangGraph 检查点存储路径

    # ==================== 分类服务配置 ====================
    classifier_url: str = "http://127.0.0.1:8110"  # ONNX 分类服务基础 URL

    # ==================== 嵌入模型配置 ====================
    embed_model: str  # 嵌入模型名称，如 "text-embedding-3-small"
    embed_base_url: str  # 嵌入 API 基础 URL
    embed_api_key: str  # 嵌入 API 密钥

    # ==================== Milvus 向量库配置 ====================
    milvus_uri: str = "http://127.0.0.1:19530"  # Milvus 服务地址
    milvus_collection: str = "minihelp_knowledge"  # 知识库集合名称

    # ==================== 重排序模型配置 ====================
    rerank_base_url: str = "https://api.siliconflow.cn/v1"  # 重排序 API 基础 URL
    rerank_api_key: str = ""  # 重排序 API 密钥（可选）
    rerank_api_style: str = "auto"  # API 风格，"auto" 自动检测或 "openai"/"cohere"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"  # 重排序模型名称

    # ==================== RAG 检索参数 ====================
    recall_top_k: int = 50  # 向量检索召回文档数量
    rerank_top_k: int = 10  # 重排序后保留文档数量
    rerank_min_score: float = 0.3  # 重排序最低分数阈值（低于此分数的文档被过滤）

    # 证据置信度阈值（用于判断检索结果是否足够回答问题）
    evidence_min_confidence: float = Field(
        default=0.5,  # 默认 0.5
        ge=0,  # 大于等于 0
        le=1,  # 小于等于 1
        allow_inf_nan=False,  # 不允许无穷大或 NaN
    )

    subquery_split: bool = True  # 是否启用子查询拆分（复杂问题拆分为多个子查询）

    # ==================== MCP 工具配置 ====================
    # MCP（Model Context Protocol）是外部工具集成协议
    mcp_logistics_url: str = ""  # 物流查询工具服务器 URL（空字符串表示未启用）
    mcp_aftersales_url: str = ""  # 售后工单工具服务器 URL

    # ==================== Langfuse 观测配置 ====================
    # Langfuse 是 LLM 应用观测平台，记录 token 用量和执行轨迹
    langfuse_public_key: str = ""  # Langfuse 公钥
    langfuse_secret_key: str = ""  # Langfuse 私钥
    langfuse_base_url: str = ""  # Langfuse 服务地址

    # ==================== 其他配置 ====================
    review_admin_name: str = "local-reviewer"  # 知识审核管理员名称

    @property
    def langfuse_configured(self) -> bool:
        """
        检查 Langfuse 是否已配置

        Returns:
            bool: 如果 public_key、secret_key 和 base_url 都非空则返回 True
        """
        return all(
            value.strip()
            for value in (
                self.langfuse_public_key,
                self.langfuse_secret_key,
                self.langfuse_base_url,
            )
        )


def warn_unknown_env_keys(env_file: str | Path = ".env") -> None:
    """告警未定义的配置键；不插值、不记录配置值。"""
    path = Path(env_file)
    if not path.is_file():
        return
    known_keys = {name.lower() for name in Settings.model_fields}
    unknown_keys = sorted(
        key
        for key in dotenv_values(path, encoding="utf-8", interpolate=False)
        if key.lower() not in known_keys
    )
    if unknown_keys:
        logger.warning("未知配置键：%s", ", ".join(unknown_keys))


# 全局配置实例，应用启动时自动从 .env 读取
settings = Settings()
