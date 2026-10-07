# 模块：LangGraph运行时封装
# 封装图的执行逻辑，处理会话状态管理、中断恢复、流式输出
# 支持订单选择等人机交互场景，确保状态一致性和并发安全
# 核心职责：提供统一的图执行接口，隔离LangGraph复杂性

import asyncio

from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, StateSnapshot
from collections.abc import AsyncIterator
from app.core.conversation_lock import conversation_lock, owns_conversation_lock
from uuid import uuid4
from app.core.observability import span

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
        # 强引用后台轮次，消费者断连后任务仍执行到检查点保存完成。
        self._stream_tasks: set[asyncio.Task] = set()

    def config(self, user_id: str, conversation_id: int | str) -> RunnableConfig:
        """统一会话线程配置；整数与字符串会话 ID 指向同一检查点。"""
        return {
            "configurable": {"thread_id": f"{user_id}:{str(conversation_id)}"},
            "recursion_limit": 64,
        }

    async def get_state(self, user_id: str, conversation_id: int | str) -> StateSnapshot:
        """读取指定会话的图状态快照。"""
        return await self.graph.aget_state(self.config(user_id, conversation_id))

    async def pending_interrupt(self, user_id: str, conversation_id: int | str) -> dict | None:
        """返回会话中第一个待处理中断的 value；没有中断时返回 None。"""
        snapshot = await self.get_state(user_id, conversation_id)
        return next((item.value for task in snapshot.tasks for item in task.interrupts), None)

    async def seed_messages(
        self, user_id: str, conversation_id: int | str, messages: list[BaseMessage],
    ) -> None:
        """将恢复的历史消息作为已完成的 finish 节点状态写入会话。"""
        await self.graph.aupdate_state(
            self.config(user_id, conversation_id), {"messages": messages}, as_node="finish",
        )

    async def continue_turn(self, user_id: str, conversation_id: int | str) -> dict:
        """在会话锁和 graph_turn span 内继续执行尚未完成的图轮次。"""
        async with (
            span("graph_turn", self.trace_sink),
            conversation_lock(user_id, conversation_id),
        ):
            return await self.graph.ainvoke(None, config=self.config(user_id, conversation_id))

    async def run_turn(
            self,
            query: str,
            user_id: str,
            conversation_id: int | str,
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
            resume: 恢复数据（订单选择、工单确认）
            summary_text: 对话摘要文本
            summary_upto: 摘要覆盖到的消息ID
            covered_count: 已覆盖的消息数

        返回:
            图执行结果字典

        执行模式:
            1. 新问题：query非空，resume=None
            2. 恢复中断：resume非空（订单选择或工单决策）
            3. 重试失败：query与原问题一致，图状态有next

        中断处理:
            订单选择或工单确认：图中断等待用户操作，客户端调用resume恢复

        并发控制:
            按user_id:conversation_id加锁，确保同一会话串行执行

        异常:
            ValueError: 参数不合法、状态冲突

        设计说明:
            使用LangGraph的检查点机制管理状态
            thread_id = user_id:conversation_id，隔离不同会话
            递归上限64防止无限循环
        """
        conversation_id = str(conversation_id)
        async with (
            span("graph_turn", self.trace_sink),
            conversation_lock(user_id, conversation_id),
        ):
            config = self.config(user_id, conversation_id)
            payload = await self._prepare_turn(
                query, user_id, conversation_id, resume=resume,
                summary_text=summary_text, summary_upto=summary_upto,
                covered_count=covered_count,
            )
            return await self.graph.ainvoke(payload, config=config)

    async def _prepare_turn(
        self, query: str, user_id: str, conversation_id: int | str, *,
        resume=None, summary_text: str = "", summary_upto: int = 0,
        covered_count: int = 0,
    ) -> dict | Command | None:
        """在会话锁内校验轮次，返回新状态、恢复命令或失败重试的 None。"""
        conversation_id = str(conversation_id)
        snapshot = await self.get_state(user_id, conversation_id)
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

            return None

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
        return payload

    async def stream_turn(
            self,
            query: str,
            user_id: str,
            conversation_id: int | str,
            *,
            resume: bool | dict | None = None,
            summary_text: str = "",
            summary_upto: int = 0,
            covered_count: int = 0,
    ) -> AsyncIterator[dict]:
        """实时输出节点进度和 agent 文本，完成后输出 interrupt/答案/done/end。

        API 已在独立任务中持有会话锁时复用该任务，使图与消息持久化
        处于同一锁内；单独消费本方法时另起后台任务，关闭生成器不取消图。
        RAG answer 先生成再校验依据，失败会替换为拒答模板，禁止逐 token
        输出未校验的答案；其它非 agent 路由也只在轮次结束后输出整段答案。
        """
        events = self._stream_turn(
            query, user_id, conversation_id, resume=resume,
            summary_text=summary_text, summary_upto=summary_upto,
            covered_count=covered_count,
        )
        if owns_conversation_lock(user_id, conversation_id):
            async for event in events:
                yield event
            return

        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def produce():
            async for event in events:
                queue.put_nowait(event)

        task = asyncio.create_task(produce())
        self._stream_tasks.add(task)
        task.add_done_callback(self._stream_tasks.discard)
        while True:
            event = await queue.get()
            yield event
            if event.get("event") == "end":
                break

    async def _stream_turn(
        self, query: str, user_id: str, conversation_id: int | str, *,
        resume=None, summary_text: str = "", summary_upto: int = 0,
        covered_count: int = 0,
    ) -> AsyncIterator[dict]:
        """持锁执行 astream；仅完成的节点和 agent 的纯文本分块可实时公开。"""
        try:
            async with (
                span("graph_turn", self.trace_sink),
                conversation_lock(user_id, conversation_id),
            ):
                payload = await self._prepare_turn(
                    query, user_id, conversation_id, resume=resume,
                    summary_text=summary_text, summary_upto=summary_upto,
                    covered_count=covered_count,
                )
                result = {}
                interrupts = ()
                streamed_answer = ""
                tool_message_ids = set()
                async for mode, data in self.graph.astream(
                    payload, config=self.config(user_id, conversation_id),
                    stream_mode=["updates", "messages", "values"],
                ):
                    if mode == "updates":
                        for name, values in data.items():
                            if name == "__interrupt__":
                                interrupts = values
                            else:
                                yield {"event": "node", "name": name}
                                if name == "agent":
                                    # 无消息 ID 的模型分块按每次 agent 调用隔离。
                                    tool_message_ids.discard(None)
                    elif mode == "values":
                        # 使用图 reducer 合并后的状态，兼容恢复、重试及无 checkpointer。
                        result = data
                    elif mode == "messages":
                        chunk, metadata = data
                        if metadata.get("langgraph_node") != "agent" or not isinstance(chunk, AIMessageChunk):
                            continue
                        if (
                            chunk.tool_calls or chunk.tool_call_chunks or chunk.invalid_tool_calls
                            or chunk.additional_kwargs.get("tool_calls")
                        ):
                            tool_message_ids.add(chunk.id)
                        if chunk.id in tool_message_ids:
                            continue
                        text = chunk.text
                        if text:
                            streamed_answer += text
                            yield {"delta": text}

                if interrupts or result.get("__interrupt__"):
                    yield {
                        "event": "interrupt",
                        "preview": (interrupts or result["__interrupt__"])[0].value,
                    }
                    return
                if result.get("citations"):
                    yield {"event": "citations", "citations": result["citations"]}
                answer = result["answer"]
                if streamed_answer:
                    if streamed_answer != answer:
                        yield {"event": "replace", "answer": answer}
                else:
                    yield {"delta": answer}
                yield {
                    "event": "done",
                    "request_id": result.get("request_id"),
                    "message_id": result.get("message_id"),
                }
        except Exception:
            yield {"event": "error", "message": "图执行失败"}
        finally:
            yield {"event": "end"}
