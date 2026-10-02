"""
数据库模型定义

本模块使用 SQLAlchemy ORM 定义智能客服系统的所有数据表模型。
主要包括：
1. 会话和消息：Conversation、Message、Turn
2. 工单：Ticket
3. 知识库：KnowledgeChunk、QaExtractionStaging
4. 审核流程：LowConfidenceQuestion、Review、TopicClassification
5. 观测数据：ToolAuditLog、TraceSpan、EvalRun
6. 后台账号：StaffUser

数据库技术栈：
- SQLAlchemy 2.0：ORM 框架，使用新的 Mapped 类型注解
- MySQL：主数据库（通过 asyncmy 驱动异步访问）
- 外键约束：确保数据一致性
- 唯一约束：防止重复数据
"""

from datetime import datetime
from sqlalchemy import (
    BigInteger, JSON, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy ORM 基类，所有模型继承此类"""
    pass


class Conversation(Base):
    """
    会话表

    记录用户与客服的完整对话会话，每个会话包含多条消息。
    支持对话摘要功能，用于压缩长对话历史（参考 git commit 22c8248）。
    """
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)  # 用户标识
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 滚动摘要文本
    summary_upto: Mapped[int] = mapped_column(default=0, server_default="0")  # 摘要覆盖到的消息 ID
    summary_version: Mapped[int] = mapped_column(default=0, server_default="0")  # 摘要版本号
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class Message(Base):
    """
    消息表

    记录会话中的每条消息，包括用户消息、助手消息和工具调用结果。
    支持 OpenAI 消息格式（role、content、tool_calls、tool_call_id）。

    参考 git commit daf2eaa (明确消息轮次与工具配对规则)
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20))  # "user", "assistant", "tool"
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # 消息文本内容
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)  # 工具调用请求（assistant 消息）
    tool_call_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )  # 工具调用 ID（tool 消息）
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    turn_message_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
    )  # 轮次消息唯一标识，用于关联 Turn 表

class Ticket(Base):
    """
    工单表

    记录用户创建的售后工单，包括退款、换货、投诉等。
    工单通过 MCP 工具集成外部售后系统（参考 git commit 21557ba）。
    """
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"),
        index=True,
    )
    ticket_no: Mapped[str] = mapped_column(
        String(50),
        unique=True,
    )  # 工单编号，唯一标识
    ticket_type: Mapped[str] = mapped_column(String(20))  # 工单类型：退款、换货、投诉等
    status: Mapped[str] = mapped_column(
        String(20),
        default="待处理",
    )  # 工单状态
    description: Mapped[str] = mapped_column(Text)  # 工单描述
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class KnowledgeChunk(Base):
    """
    知识库分块表

    存储知识库的分块内容，每个分块包含问题、答案和元数据。
    支持向量化检索（存储 Milvus 向量 ID）和链式导航（前后分块链接）。

    分块来源：
    1. 人工录入的 FAQ
    2. 从文档挖掘的 QA 对（参考 git commit 挖掘相关）
    3. 从对话中提取的知识（QaExtractionStaging 审核通过后）
    """
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int | None] = mapped_column(
        ForeignKey("reviews.id"), unique=True, nullable=True,
    )  # 关联审核记录（如果来自审核流程）
    category: Mapped[str] = mapped_column(String(255))  # 分类标签
    questions: Mapped[str] = mapped_column(Text)  # 问题变体（多个问题用换行分隔）
    answer: Mapped[str] = mapped_column(Text)  # 答案内容
    section_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # 文档章节路径
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 内容类型
    is_key_clause: Mapped[int] = mapped_column(default=0)  # 是否为关键条款（0 或 1）
    prev_chunk_id: Mapped[int | None] = mapped_column(nullable=True)  # 前一个分块 ID（链式导航）
    next_chunk_id: Mapped[int | None] = mapped_column(nullable=True)  # 后一个分块 ID
    vector_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Milvus 向量 ID
    vectorize_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # 向量化状态：pending, success, failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class QaExtractionStaging(Base):
    """
    知识挖掘暂存表

    存储从对话中挖掘的 QA 对，等待人工审核后才进入正式知识库。
    这是知识飞轮的一部分：对话 → 挖掘 → 审核 → 知识库。
    """

    __tablename__ = "qa_extraction_staging"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_no: Mapped[str] = mapped_column(String(64))  # 批次编号，标识同一批挖掘任务
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 来源引用（会话 ID 等）
    question: Mapped[str] = mapped_column(Text)  # 挖掘出的问题
    answer: Mapped[str] = mapped_column(Text)  # 挖掘出的答案
    status: Mapped[str] = mapped_column(String(16), default="extracted", server_default="extracted")  # 状态：extracted, approved, rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TopicClassification(Base):
    """
    话题分类表

    存储低置信度问题的话题分类结果。
    每条低置信度问题最多保存一次分类，用于统计意图分布和改进模型。

    """

    __tablename__ = "topic_classifications"
    __table_args__ = (UniqueConstraint("question_id", name="uq_topic_classifications_question_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("low_confidence_questions.id"), nullable=False,
    )  # 关联低置信度问题
    labels: Mapped[list] = mapped_column(JSON, nullable=False)  # 分类标签列表（可能多标签）
    classified_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )


class ToolAuditLog(Base):
    """
    工具审计日志表

    记录所有工具调用的参数和结果，用于：
    1. 审计：追溯工具调用历史，排查问题
    2. 重放：基于审计日志重现工具调用场景（参考 git commit 658119b）
    3. 分析：统计工具使用频率和成功率

    参考 git commit ded9aed (完成工具结果格式化与审计落库)
    """
    __tablename__ = "tool_audit_logs"
    __table_args__ = (
        UniqueConstraint(
            "audit_key",
            name="uq_tool_audit_logs_audit_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_key: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )  # 审计键，防止重复记录
    tool_call_id: Mapped[str] = mapped_column(String(100))  # 工具调用唯一 ID
    conversation_id: Mapped[str] = mapped_column(
        String(64), index=True,
    )  # 所属会话 ID
    tool_name: Mapped[str] = mapped_column(String(128))  # 工具名称
    source: Mapped[str] = mapped_column(String(16))  # 来源：local（本地工具）或 mcp（MCP 工具）
    server: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
    )  # MCP 服务器名称（仅 MCP 工具）
    status: Mapped[str] = mapped_column(String(32))  # 状态：success, error, timeout 等
    duration_ms: Mapped[int] = mapped_column(Integer)  # 执行耗时（毫秒）
    retry_count: Mapped[int] = mapped_column(Integer)  # 重试次数
    argument_fields: Mapped[list[str]] = mapped_column(JSON)  # 参数字段名列表（不记录值，避免敏感信息）
    result_chars: Mapped[int] = mapped_column(Integer)  # 结果字符数
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )


class TraceSpan(Base):
    """
    执行追踪 Span 表

    记录系统执行的追踪 span，用于性能分析和调试。
    每个 span 代表一个操作单元（如 LLM 调用、工具执行、检索查询）。

    Span 结构：
    - trace_id：追踪 ID，同一次请求的所有 span 共享
    - span_id：当前 span 唯一 ID
    - parent_id：父 span ID，构成调用树

    参考 git commit 805cba5 (接入执行追踪持久化与 Langfuse 观测)
    """
    __tablename__ = "trace_spans"

    span_id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
    )
    trace_id: Mapped[str] = mapped_column(
        String(32),
        index=True,
    )  # 追踪 ID，用于关联同一请求的所有 span
    parent_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )  # 父 span ID，构成调用层级
    name: Mapped[str] = mapped_column(String(64))  # Span 名称（如 "llm_call", "retrieval"）
    kind: Mapped[str] = mapped_column(
        String(16), server_default="span",
    )  # Span 类型：span, generation（LLM 生成）
    intent: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
    )  # 用户意图（如 "查询订单", "退款申请"）
    model: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )  # 使用的模型名称（如 "gpt-4"）

    # Token 用量统计（仅 LLM 调用）
    input_tokens: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
    )  # 输入 token 数
    output_tokens: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
    )  # 输出 token 数
    total_tokens: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
    )  # 总 token 数

    status: Mapped[str] = mapped_column(String(16))  # 状态：success, error
    duration_ms: Mapped[float] = mapped_column(Float(precision=53))  # 执行耗时（毫秒）
    error_type: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )  # 错误类型（如果失败）
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )
class Turn(Base):
    """
    回答快照表

    记录每次回答时的原始问题和检索结果，用于：
    1. 历史追溯：查看某次回答时的检索上下文
    2. 问题分析：统计用户问题分布
    3. 效果评估：评估检索质量和答案准确性

    参考 git commit 4d1384a (记录意图与选单接入审查并生成长对话教学包)
    """
    __tablename__ = "turns"
    __table_args__ = (
        {"comment": "Conversation turn snapshots for historical reference"},
    )

    owner: Mapped[str] = mapped_column(String(64), primary_key=True)  # 所有者标识
    conversation: Mapped[str] = mapped_column(String(64), primary_key=True)  # 会话 ID
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 消息 ID
    turn_id: Mapped[str] = mapped_column(String(64))  # 轮次 ID
    question: Mapped[str] = mapped_column(Text)  # 用户问题
    snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # 检索结果快照（JSON 格式）
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class LowConfidenceQuestion(Base):
    """
    低置信度问题池

    收集检索置信度低或无法回答的问题，等待人工审核。
    这是知识飞轮的起点：低置信度问题 → 人工审核 → 补充知识库。

    低置信度来源：
    1. 检索结果置信度低于阈值
    2. 用户反馈答案不准确
    3. 系统无法理解用户意图

    参考 git commit 4d1384a (记录意图与选单接入审查并生成长对话教学包)
    """
    __tablename__ = "low_confidence_questions"
    __table_args__ = (
        UniqueConstraint(
            "owner",
            "conversation",
            "message_id",
            "source",
            name="uq_pool_message_source",
        ),  # 防止同一问题重复记录
        {"comment": "Low confidence questions pool for review"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)  # 所有者标识
    conversation: Mapped[str] = mapped_column(String(64), index=True)  # 会话 ID
    message_id: Mapped[str] = mapped_column(String(64))  # 消息 ID
    question: Mapped[str] = mapped_column(Text)  # 用户问题
    snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # 上下文快照（检索结果等）
    source: Mapped[str] = mapped_column(String(32))  # 来源：retrieval（检索低置信度）、feedback（用户反馈）
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # 低置信度原因说明
    review_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("reviews.id"),
        nullable=True,
    )  # 关联的审核记录（如已归并）
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )


class Review(Base):
    """
    待审核队列表

    存储标准化后的待审核问题，支持归并相似问题。
    多个低置信度问题可以归并为同一个审核记录，避免重复审核。

    审核流程：
    1. 低置信度问题进入问题池（LowConfidenceQuestion）
    2. 系统标准化问题并归并相似问题到审核队列（Review）
    3. 人工审核并补充答案
    4. 发布到知识库（KnowledgeChunk）

    参考 git commit 相关审核流程提交
    """
    __tablename__ = "reviews"
    __table_args__ = (
        {"comment": "Review queue for normalized questions"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)  # 标准化后的问题
    suggestion: Mapped[str] = mapped_column(Text)  # 系统建议的答案（供审核参考）
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")  # 归并频次（相似问题数量）
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")  # 状态：pending, approved, rejected
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 审核人
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)  # 审核通过的答案
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 来源引用
    source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 来源摘要（用于去重）
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 审核时间
    publish_error: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 发布失败错误信息
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class EvalRun(Base):
    """
    评估运行记录表

    存储固定测试集的一次完整评测记录，用于跟踪系统性能变化。

    评估流程：
    1. 使用固定测试集（dataset_version）
    2. 在特定知识库版本（kb_revision）上运行
    3. 记录检索策略和参数（strategy, top_k）
    4. 计算指标（metrics）：召回率、准确率等
    5. 保存每个测试用例的详细结果（details）

    用途：
    - 对比不同配置的效果（调整 top_k、rerank 阈值等）
    - 追踪知识库更新后的性能变化
    - A/B 测试不同检索策略

    """
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(128))  # 测试集版本（如 "v1.0"）
    case_ids: Mapped[list] = mapped_column(JSON)  # 测试用例 ID 列表
    config_version: Mapped[str] = mapped_column(String(128))  # 配置版本（如 "baseline", "optimized"）
    kb_revision: Mapped[str] = mapped_column(String(128))  # 知识库版本（如 git commit hash）
    strategy: Mapped[str] = mapped_column(String(32))  # 检索策略（如 "vector", "hybrid"）
    top_k: Mapped[int] = mapped_column(Integer)  # 检索返回文档数
    triggered_by: Mapped[str] = mapped_column(String(64))  # 触发人或系统
    status: Mapped[str] = mapped_column(String(16))  # 状态：running, completed, failed
    metrics: Mapped[dict] = mapped_column(JSON)  # 聚合指标（如 {"recall": 0.85, "precision": 0.90}）
    details: Mapped[list] = mapped_column(JSON)  # 每个测试用例的详细结果
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True,
    )


class StaffUser(Base):
    """
    后台员工账号表

    顾客身份由电商主站签发的令牌确定，不落库；这里只存后台员工。
    角色：admin（管理员）、reviewer（审核员）、agent（坐席）。
    """
    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # scrypt 哈希，见 app.core.auth
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
