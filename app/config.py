from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从 .env 读取并校验模型与数据库配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )
    chat_model: str
    chat_base_url: str
    chat_api_key: str
    chat_thinking: str = "disabled"
    handwritten_database_url: str = (
        "mysql+asyncmy://root:root@127.0.0.1:3308/minihelp_handwritten"
    )
    graph_checkpoint_path: str = "data/graph-checkpoints.sqlite"
    embed_model: str
    embed_base_url: str
    embed_api_key: str
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_collection: str = "minihelp_handwritten_knowledge"
    rerank_base_url: str = "https://api.siliconflow.cn/v1"
    rerank_api_key: str = ""
    rerank_api_style: str = "auto"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    recall_top_k: int = 50
    rerank_top_k: int = 10
    rerank_min_score: float = 0.3
    subquery_split: bool = True
    mcp_logistics_url: str = ""
    mcp_aftersales_url: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = ""

    @property
    def langfuse_configured(self) -> bool:
        return all(
            value.strip()
            for value in (
                self.langfuse_public_key,
                self.langfuse_secret_key,
                self.langfuse_base_url,
            )
        )
# 模块导入时创建唯一配置对象；缺少必填字段会立即报错。
settings = Settings()
