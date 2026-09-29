# 模块：工具上下文
# 定义工具调用时需要的上下文信息
# 包含用户ID和会话ID，用于权限校验和数据隔离
# 核心职责：提供工具调用的身份标识

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolContext:
    """
    工具调用上下文

    字段:
        user_id: 用户ID（用于权限校验，确保只能查询自己的数据）
        conversation_id: 会话ID（用于日志追踪和会话隔离）

    设计说明:
        frozen=True确保上下文不可变
        slots=True减少内存占用
        工具函数通过context参数获取调用者身份
    """
    user_id: str
    conversation_id: str
