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

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


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
    chat_timeout_seconds: float = Field(default=20, gt=0)  # 单次模型请求超时
    chat_max_retries: int = Field(default=1, ge=0)  # 单次模型请求失败后的重试次数
    chat_turn_timeout_seconds: float = Field(default=60, gt=0)  # 一轮对话（整张图）最长执行时间

    # ==================== 数据库配置 ====================
    handwritten_database_url: str = (
        "mysql+asyncmy://root:root@127.0.0.1:3308/minihelp_handwritten"
    )  # MySQL 异步连接 URL（使用 asyncmy 驱动）
    graph_checkpoint_path: str = "data/graph-checkpoints.sqlite"  # LangGraph 检查点存储路径

    # ==================== 嵌入模型配置 ====================
    embed_model: str  # 嵌入模型名称，如 "text-embedding-3-small"
    embed_base_url: str  # 嵌入 API 基础 URL
    embed_api_key: str  # 嵌入 API 密钥

    # ==================== Milvus 向量库配置 ====================
    milvus_uri: str = "http://127.0.0.1:19530"  # Milvus 服务地址
    milvus_collection: str = "minihelp_handwritten_knowledge"  # 知识库集合名称

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

    # ==================== 认证配置 ====================
    auth_secret: str = ""  # 员工令牌签名密钥（至少 32 字符）
    customer_token_secret: str = ""  # 与电商主站共享的顾客令牌密钥（至少 32 字符）
    auth_dev_mode: bool = False  # 开发模式：开放模拟顾客接口，未配置密钥时自动生成
    staff_token_ttl_minutes: int = Field(default=480, ge=5)  # 员工令牌有效期

    # ==================== 限流配置（每分钟次数） ====================
    rate_chat_per_minute: int = Field(default=20, ge=1)  # 每个顾客发消息
    rate_login_per_minute: int = Field(default=10, ge=1)  # 每个 IP 登录
    rate_staff_model_per_minute: int = Field(default=30, ge=1)  # 每个员工调用模型的试用接口

    # ==================== 外部渠道：拼多多 ====================
    # 见 docs/phase3-pinduoduo-channel.md。消息经“渠道桥”收发：桥负责对接拼多多客服消息，
    # 用 HMAC 签名把买家消息推给本服务，并接收本服务的回复。
    pdd_enabled: bool = False
    pdd_bridge_secret: str = ""  # 与渠道桥共享的签名密钥（至少 32 字符）
    pdd_bridge_send_url: str = ""  # 渠道桥的发送接口；为空时只记录不发送（演练模式）
    pdd_client_id: str = ""  # 拼多多开放平台应用（查订单用，可选）
    pdd_client_secret: str = ""
    pdd_access_token: str = ""  # 店铺授权令牌
    pdd_gateway_url: str = "https://gw-api.pinduoduo.com/api/router"
    pdd_max_message_chars: int = Field(default=500, ge=50)  # 单条回复最长字数，超出按句子拆分

    # 渠道消息处理
    channel_merge_seconds: float = Field(default=1.5, ge=0)  # 买家连发多条时，静默多久后合并成一轮
    channel_merge_max_seconds: float = Field(default=6, ge=0)  # 合并最多等待多久
    channel_hold_seconds: float = Field(default=8, ge=0)  # 超过这个时间还没答完，先发一句安抚（0 关闭）
    channel_idle_minutes: int = Field(default=1440, ge=1)  # 买家隔多久再来算新会话

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


# 全局配置实例，应用启动时自动从 .env 读取
settings = Settings()
