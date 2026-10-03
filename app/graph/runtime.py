# 模块：LangGraph运行时封装
# 封装图的执行逻辑，处理会话状态管理、中断恢复、流式输出
# 支持订单选择等人机交互场景，确保状态一致性和并发安全
# 核心职责：提供统一的图执行接口，隔离LangGraph复杂性

from langchain_core.messages import HumanMessage
from langgraph.types import Command
from collections.abc import AsyncIterator
from app.core.conversation_lock import conversation_lock
from uuid import uuid4
from app.core.observability import span
from app.graph import prefetch

class Runtime:
    """图运行时"""
    def __init__(self, graph, *, trace_sink=None):
        """
        初始化运行时

        参数:
            graph: LangGraph图实例
            trace_sink: trace导出函数（可选）
        """
        self.graph = graph
        self.trace_sink = trace_sink

    async def run_turn(
            self,
            query: str,
            user_id: str,
            conversation_id: str,
            *,
            resume=None,
            summary_text: str = "",
            summary_upto: int = 0,
            covered_count: int = 0,
    ):
        """执行一轮对话（见 _run_turn）；结束时取消本轮没用上的预取（见 app.graph.prefetch）。"""
        async with conversation_lock(user_id, conversation_id):  # 可重入，_run_turn 里再次获取不会阻塞
            try:
                return await self._run_turn(
                    query, user_id, conversation_id, resume=resume, summary_text=summary_text,
                    summary_upto=summary_upto, covered_count=covered_count,
                )
            finally:
                prefetch.discard(str(conversation_id))

    async def _run_turn(
            self,
            query: str,
            user_id: str,
            conversation_id: str,
            *,
            resume=None,
            summary_text: str = "",
            summary_upto: int = 0,
            covered_count: int = 0,
    ):
        """
        执行一轮对话

        参数:
            query: 用户问题
            user_id: 用户ID
            conversation_id: 会话ID
            resume: 恢复数据（订单选择、错误重试）
            summary_text: 对话摘要文本
            summary_upto: 摘要覆盖到的消息ID
            covered_count: 已覆盖的消息数

        返回:
            图执行结果字典

        执行模式:
            1. 新问题：query非空，resume=None
            2. 恢复中断：resume非空（订单选择结果）
            3. 重试失败：query为空，图状态有next

        中断处理:
            订单选择：图中断等待用户选择，客户端调用resume恢复

        并发控制:
            按user_id:conversation_id加锁，确保同一会话串行执行

        异常:
            ValueError: 参数不合法、状态冲突

        设计说明:
            使用LangGraph的检查点机制管理状态
            thread_id = user_id:conversation_id，隔离不同会话
            递归上限64防止无限循环
        """
        async with (
            span("graph_turn", self.trace_sink),
            conversation_lock(user_id, conversation_id),
        ):
            config = {
                "configurable": {
                    "thread_id": f"{user_id}:{conversation_id}",
                },
                "recursion_limit": 64
            }
            snapshot = await self.graph.aget_state(config)
            # 提取待处理的中断项
            pending = [
                item.value
                for task in snapshot.tasks
                for item in task.interrupts
            ]

            # 校验：有中断必须先处理
            if resume is None and pending:
                raise ValueError("请先确认或取消待处理操作")

            # 校验：恢复时必须有中断
            if resume is not None and not pending:
                raise ValueError("没有待恢复的操作")

            # 重试失败的问题
            if resume is None and snapshot.next:
                if query != snapshot.values.get("query"):
                    raise ValueError("请先重试失败的问题")

                return await self.graph.ainvoke(None, config=config)

            # 恢复中断
            if resume is not None:
                current = pending[0]

                if current.get("kind") == "select_order":
                    if query:
                        raise ValueError("选择订单时不能同时发送新问题")

                    if not isinstance(resume, dict):
                        raise ValueError("选单恢复参数必须是字典")

                    if resume.get("kind") != "select_order":
                        raise ValueError("恢复类型不匹配")

                    if (
                            not current.get("request_id")
                            or resume.get("request_id") != current["request_id"]
                    ):
                        raise ValueError("选单请求已过期或不匹配")

                    cancelled = resume.get("cancelled", False)

                    if type(cancelled) is not bool:
                        raise ValueError("cancelled 必须为布尔值")

                    if cancelled:
                        if resume.get("order_id") is not None:
                            raise ValueError("取消不能同时选择订单")
                    else:
                        selected = resume.get("order_id")
                        offered = {
                            item["order_id"]
                            for item in current["orders"]
                        }

                        if not isinstance(selected, str) or selected not in offered:
                            raise ValueError("必须选择当前卡片中的订单")

                elif (
                        isinstance(resume, dict)
                        and resume.get("kind") == "select_order"
                ):
                    raise ValueError("当前等待的不是订单选择")

                payload = Command(resume=resume)
            else:
                # 新问题：初始化图状态
                payload = {
                    "query": query,
                    "request_id": uuid4().hex,
                    "message_id": None,
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "messages": [HumanMessage(content=query)],
                    "intent": "",
                    "intent_detail": "",
                    "intent_confidence": 0.0,
                    "route": "",
                    "resolved_query": query,
                    "needs_clarification": False,
                    "order": None,
                    "queries": [],
                    "evidence": [],
                    "evidence_confidence": None,
                    "confidence_signals": None,
                    "retrieved_snapshot": None,
                    "evidence_allowed": False,
                    "fallback_source": None,
                    "fallback_reason": None,
                    "citations": [],
                    "answer": "",
                    "steps": 0,
                    "trace": [],
                    "summary_text": summary_text,
                    "summary_upto": summary_upto,
                    "covered_count": covered_count,
                }
            return await self.graph.ainvoke(payload, config=config)

    async def stream_turn(
            self,
            query: str,
            user_id: str,
            conversation_id: str,
            *,
            resume: bool | dict | None = None,
            summary_text: str = "",
            summary_upto: int = 0,
            covered_count: int = 0,
    ) -> AsyncIterator[dict]:
        """
        流式执行一轮对话

        参数:
            query: 用户问题
            user_id: 用户ID
            conversation_id: 会话ID
            resume: 恢复数据
            summary_text: 对话摘要文本
            summary_upto: 摘要覆盖到的消息ID
            covered_count: 已覆盖的消息数

        返回:
            异步迭代器，逐步返回事件字典

        事件类型:
            - node: 节点执行（name字段）
            - interrupt: 中断等待（preview字段）
            - citations: 引用列表
            - delta: 答案内容（流式分块）
            - done: 执行完成（request_id、message_id）
            - error: 执行失败（message字段）
            - end: 流结束标记

        设计说明:
            内部调用run_turn执行图，将结果转换为流式事件
            trace节点逐个yield，让前端展示执行进度
            中断时只返回预览，客户端需调用resume恢复
            异常时返回error事件，不抛异常，确保end事件必达
        """
        try:
            result = await self.run_turn(
                query,
                user_id,
                conversation_id,
                resume=resume,
                summary_text=summary_text,
                summary_upto=summary_upto,
                covered_count=covered_count,
            )

            # 逐个发送节点执行事件
            for name in result.get("trace", []):
                yield {
                    "event": "node",
                    "name": name,
                }

            # 中断事件：等待用户操作
            if result.get("__interrupt__"):
                yield {
                    "event": "interrupt",
                    "preview": result["__interrupt__"][0].value,
                }
                return

            # 引用列表
            if result.get("citations"):
                yield {
                    "event": "citations",
                    "citations": result["citations"],
                }

            # 答案内容
            yield {
                "delta": result["answer"],
            }

            # 完成事件
            yield {
                "event": "done",
                "request_id": result.get("request_id"),
                "message_id": result.get("message_id"),
            }

        except Exception:
            # 异常转换为error事件
            yield {
                "event": "error",
                "message": "图执行失败",
            }

        finally:
            # 确保流结束标记必达
            yield {
                "event": "end",
            }
