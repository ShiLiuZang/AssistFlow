from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从 .env 读取并校验 Ch01 所需的模型配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )
    chat_model: str
    chat_base_url: str
    chat_api_key: str
    chat_thinking: str = "disabled"


# 模块导入时创建唯一配置对象；缺少必填字段会立即报错。
settings = Settings()
