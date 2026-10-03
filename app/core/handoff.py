"""
人工坐席闭环：转人工、排队、接入、回复、转交、结束、知识回流

会话的接待状态由 handoffs 表推导（见 docs/phase2-human-handoff.md）：
没有 queued/active 记录时由 AI 接待；有记录时顾客消息不再经过 AI，直接进入坐席工作台。

人工期间的消息用单独的角色保存（handoff_user / staff / staff_note / handoff_event），
不进入 LangGraph 历史，因此不会影响图状态与数据库的一致性校验。

注意：本模块里的函数可能在图执行期间被调用（human / complaint 节点），
那时调用方已经持有进程内会话锁，所以这里只用数据库行锁，不再获取 conversation_lock。
"""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.realtime import STAFF, conversation_channel, hub
from app.core.safety import desensitize
from app.db import database
from app.db.models import Conversation, Handoff, LowConfidenceQuestion, Message, StaffUser

logger = logging.getLogger(__name__)

OPEN = ("queued", "active")
REASONS = {
    "human": "顾客要求人工",
    "complaint": "顾客投诉",
    "customer_request": "顾客点击转人工",
    "staff_takeover": "坐席主动接管",
}
HANDOFF_ROLES = ("handoff_user", "staff", "staff_note", "handoff_event")
# 顾客可见的系统提示
EVENT_QUEUED = "已为您转接人工客服，正在排队"
EVENT_CANCELLED = "已取消排队，继续由智能助手为您服务"
EVENT_ACCEPTED = "人工客服已接入，接下来由客服为您服务"
EVENT_CLOSED = "人工服务已结束，如还有问题可以继续咨询"
# 外部渠道顾客的内部 ID 前缀（见 app/channels）；其余视为网页咨询
CHANNEL_PREFIXES = {"pdd-": "pinduoduo"}


def channel_of(user_id: str) -> str:
    return next((name for prefix, name in CHANNEL_PREFIXES.items() if (user_id or "").startswith(prefix)), "web")
# 回流到问题池时，坐席回复放在 reason 字段，以此前缀标识（归并作业据此取出建议答案）
HARVEST_SOURCE = "human_handoff"
HARVEST_PREFIX = "坐席回复："
MAX_HARVEST = 5

_ANGRY = re.compile(r"投诉|曝光|12315|消协|骗子|垃圾|差评|报警|起诉|律师|退钱|欺诈")
_UPSET = re.compile(r"生气|不满|失望|太慢|怎么还|一直没|几天了|没人管|没人理|气死|无语|离谱|[!！]{2,}|[?？]{2,}")
_SHORT_REPLY = re.compile(r"^(您好|你好|在的|好的|稍等|请稍等|收到|嗯|谢谢|不客气)[，,。.!！~]*$")


class HandoffError(ValueError):
    """当前状态不允许该操作（接口层转为 409）。"""


class HandoffForbidden(PermissionError):
    """不是该会话的接待坐席（接口层转为 403）。"""


def _now() -> datetime:
    # 与数据库 server_default 的 now() 一致，按 UTC 存不带时区的时间（前端按 UTC 解析）
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


# ==================== 交接卡片 ====================

def detect_mood(texts: list[str]) -> dict:
    """关键词规则判断情绪，只作提示；卡片里标明是规则判断。"""
    joined = "\n".join(texts[-6:])
    angry = sorted(set(_ANGRY.findall(joined)))
    upset = sorted(set(_UPSET.findall(joined)))
    if angry:
        return {"level": "angry", "label": "激动", "hits": angry[:5], "method": "keyword"}
    if upset:
        return {"level": "upset", "label": "不满", "hits": upset[:5], "method": "keyword"}
    return {"level": "calm", "label": "平稳", "hits": [], "method": "keyword"}


def _evidence_items(items) -> list[dict]:
    result = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title = item.get("section_path") or item.get("questions") or item.get("category") or item.get("source") or "知识片段"
        text = item.get("answer") or item.get("text") or item.get("content") or ""
        result.append({"title": str(title)[:80], "text": str(text)[:200]})
        if len(result) == 3:
            break
    return result


def _order_view(order) -> dict | None:
    if not isinstance(order, dict) or not order.get("order_id"):
        return None
    keys = ("order_id", "product_name", "status", "amount", "created_at", "logistics_status")
    return {key: order[key] for key in keys if order.get(key) not in (None, "")}


def build_card(*, reason: str, dialog: list[tuple[str, str]], summary_text: str = "",
               evidence=None, order=None, intent: str | None = None) -> dict:
    """dialog 为 [(customer|bot, 文本)]，按时间顺序。"""
    customer_texts = [text for role, text in dialog if role == "customer"]
    return {
        "reason": reason,
        "reason_label": REASONS.get(reason, reason),
        "summary": (summary_text or "")[:400],
        "last_question": customer_texts[-1][:300] if customer_texts else "",
        "recent": [{"role": role, "content": text[:200]} for role, text in dialog[-6:]],
        "intent": intent,
        "evidence": _evidence_items(evidence),
        "order": _order_view(order),
        "mood": detect_mood(customer_texts),
    }


def card_from_state(state: dict, reason: str) -> dict:
    """在图节点里使用：从当前图状态生成交接卡片。"""
    dialog = []
    for message in state.get("messages", []):
        content = str(getattr(message, "content", "") or "")
        if not content:
            continue
        if message.type == "human":
            dialog.append(("customer", content))
        elif message.type == "ai" and not getattr(message, "tool_calls", None):
            dialog.append(("bot", content))
    query = state.get("query")
    if query and (not dialog or dialog[-1] != ("customer", query)):
        dialog.append(("customer", query))
    return build_card(
        reason=reason, dialog=dialog, summary_text=state.get("summary_text", ""),
        evidence=state.get("evidence") or state.get("retrieved_snapshot"),
        order=state.get("order"), intent=state.get("intent_detail"),
    )


async def _card_from_db(session, conversation: Conversation, reason: str, values: dict | None = None) -> dict:
    rows = list(await session.scalars(select(Message).where(
        Message.conversation_id == conversation.id,
        Message.role.in_(("user", "assistant", "handoff_user", "staff")),
    ).order_by(Message.id.desc()).limit(20)))
    dialog = []
    for row in reversed(rows):
        if not row.content or row.tool_calls:
            continue
        dialog.append(("customer" if row.role in ("user", "handoff_user") else "bot", row.content))
    values = values or {}
    return build_card(
        reason=reason, dialog=dialog, summary_text=conversation.summary_text or "",
        evidence=values.get("evidence") or values.get("retrieved_snapshot"),
        order=values.get("order"), intent=values.get("intent_detail"),
    )


# ==================== 视图 ====================

def message_view(row: Message, *, audience: str) -> dict | None:
    """把消息转成工作台或顾客页面使用的结构；不该给该受众看的返回 None。"""
    if row.role == "user":
        role = "customer"
    elif row.role == "assistant":
        if row.tool_calls or not row.content:
            return None
        role = "bot"
    elif row.role == "handoff_user":
        role = "customer"
    elif row.role == "staff":
        role = "staff"
    elif row.role == "staff_note":
        if audience != "staff":
            return None
        role = "note"
    elif row.role == "handoff_event":
        role = "system"
    else:
        return None
    data = {"id": row.id, "role": role, "content": row.content or "", "created_at": _iso(row.created_at)}
    if audience == "staff" and row.author:
        data["author"] = row.author
    if audience == "customer" and row.role == "assistant":
        data["message_id"] = row.turn_message_id
    return data


async def _position(session, handoff: Handoff) -> int | None:
    if handoff.status != "queued":
        return None
    ahead = await session.scalar(select(func.count()).select_from(Handoff).where(
        Handoff.status == "queued", Handoff.id < handoff.id))
    return int(ahead or 0) + 1


def handoff_view(handoff: Handoff | None, position: int | None = None, *, audience: str = "staff") -> dict | None:
    if handoff is None:
        return None
    data = {
        "id": handoff.id,
        "conversation_id": handoff.conversation_id,
        "status": handoff.status,
        "reason": handoff.reason,
        "reason_label": REASONS.get(handoff.reason, handoff.reason),
        "position": position,
        "created_at": _iso(handoff.created_at),
        "accepted_at": _iso(handoff.accepted_at),
        "closed_at": _iso(handoff.closed_at),
    }
    if audience == "staff":
        data.update(user_id=handoff.user_id, assignee=handoff.assignee, card=handoff.card,
                    closed_by=handoff.closed_by)
    return data


# ==================== 内部工具 ====================

async def _lock_conversation(session, conversation_id: int, user_id: str | None = None) -> Conversation:
    statement = select(Conversation).where(Conversation.id == conversation_id)
    if user_id is not None:
        statement = statement.where(Conversation.user_id == user_id)
    conversation = await session.scalar(statement.with_for_update())
    if conversation is None:
        raise LookupError("会话不存在")
    return conversation


async def _open_handoff(session, conversation_id: int, *, lock: bool = False) -> Handoff | None:
    statement = select(Handoff).where(
        Handoff.conversation_id == conversation_id, Handoff.status.in_(OPEN),
    ).order_by(Handoff.id.desc())
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


def _event(conversation_id: int, text: str, author: str | None = None) -> Message:
    return Message(conversation_id=conversation_id, role="handoff_event", content=text, author=author)


def _publish_state(handoff: Handoff, position: int | None, messages: list[Message] = ()) -> None:
    hub.publish(STAFF, {"type": "handoff", "conversation_id": handoff.conversation_id,
                        "handoff": handoff_view(handoff, position)})
    hub.publish(conversation_channel(handoff.conversation_id), {
        "type": "handoff", "handoff": handoff_view(handoff, position, audience="customer")})
    for message in messages:
        _publish_message(message)


def _publish_message(message: Message) -> None:
    staff_view = message_view(message, audience="staff")
    if staff_view:
        hub.publish(STAFF, {"type": "message", "conversation_id": message.conversation_id, "message": staff_view})
    customer_view = message_view(message, audience="customer")
    if customer_view:
        hub.publish(conversation_channel(message.conversation_id), {"type": "message", "message": customer_view})


# ==================== 顾客侧 ====================

async def request(conversation_id: int, user_id: str, reason: str, card: dict | None = None,
                  values: dict | None = None) -> dict:
    """顾客转人工（幂等）：已有未结束记录时直接返回它。card 为空时根据会话历史生成。"""
    if reason not in REASONS or reason == "staff_takeover":
        raise ValueError("转人工原因不正确")
    async with database.SessionLocal() as session:
        async with session.begin():
            conversation = await _lock_conversation(session, conversation_id, user_id)
            existing = await _open_handoff(session, conversation_id, lock=True)
            if existing is not None:
                return {**handoff_view(existing, await _position(session, existing), audience="customer"),
                        "created": False}
            handoff = Handoff(
                conversation_id=conversation_id, user_id=user_id, status="queued", reason=reason,
                card=card or await _card_from_db(session, conversation, reason, values),
            )
            session.add(handoff)
            event = _event(conversation_id, EVENT_QUEUED)
            session.add(event)
            await session.flush()
            position = await _position(session, handoff)
        _publish_state(handoff, position, [event])
        logger.info("转人工 conversation_id=%s reason=%s", conversation_id, reason)
        return {**handoff_view(handoff, position, audience="customer"), "created": True}


def queue_reply(result: dict, lead: str = "") -> str:
    """转人工后告诉顾客的话术（排队位置或已接入）。"""
    if result.get("status") == "active":
        return f"{lead}人工客服正在为您服务，请直接描述您的问题。"
    ahead = max(int(result.get("position") or 1) - 1, 0)
    queue = f"前面还有 {ahead} 位顾客" if ahead else "您是下一位"
    return f"{lead}已为您转接人工客服，{queue}，客服接入后会在这里回复您。"


async def request_from_graph(state: dict, reason: str) -> dict:
    """供图里的 human / complaint 节点调用。"""
    return await request(int(state["conversation_id"]), state["user_id"], reason, card_from_state(state, reason))


async def customer_status(conversation_id: int, user_id: str) -> dict | None:
    async with database.SessionLocal() as session:
        owner = await session.scalar(select(Conversation.id).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id))
        if owner is None:
            raise LookupError("会话不存在")
        handoff = await _open_handoff(session, conversation_id)
        if handoff is None:
            return None
        return handoff_view(handoff, await _position(session, handoff), audience="customer")


async def open_status(conversation_id: int) -> dict | None:
    """不校验归属，供已经校验过会话的调用方使用。"""
    async with database.SessionLocal() as session:
        handoff = await _open_handoff(session, conversation_id)
        if handoff is None:
            return None
        return handoff_view(handoff, await _position(session, handoff), audience="customer")


async def customer_message(conversation_id: int, user_id: str, text: str) -> dict | None:
    """人工接待期间的顾客消息：保存并推送给坐席。没有未结束的转人工记录时返回 None。"""
    async with database.SessionLocal() as session:
        async with session.begin():
            await _lock_conversation(session, conversation_id, user_id)
            handoff = await _open_handoff(session, conversation_id, lock=True)
            if handoff is None:
                return None
            message = Message(conversation_id=conversation_id, role="handoff_user", content=text)
            session.add(message)
            await session.flush()
            position = await _position(session, handoff)
        _publish_message(message)
        return {"handoff": handoff_view(handoff, position, audience="customer"),
                "message": message_view(message, audience="customer")}


async def cancel(conversation_id: int, user_id: str) -> dict:
    """顾客取消排队；坐席已接入后不能取消。"""
    async with database.SessionLocal() as session:
        async with session.begin():
            await _lock_conversation(session, conversation_id, user_id)
            handoff = await _open_handoff(session, conversation_id, lock=True)
            if handoff is None:
                raise HandoffError("当前没有排队中的人工服务")
            if handoff.status != "queued":
                raise HandoffError("客服已接入，不能取消排队")
            handoff.status = "cancelled"
            handoff.closed_at = _now()
            handoff.closed_by = f"customer:{user_id}"
            event = _event(conversation_id, EVENT_CANCELLED)
            session.add(event)
            await session.flush()
        _publish_state(handoff, None, [event])
        return handoff_view(handoff, audience="customer")


# ==================== 坐席侧 ====================

async def accept(conversation_id: int, staff_name: str, values: dict | None = None) -> dict:
    """接入排队中的会话；没有转人工记录时视为主动接管 AI 接待中的会话。"""
    async with database.SessionLocal() as session:
        async with session.begin():
            conversation = await _lock_conversation(session, conversation_id)
            handoff = await _open_handoff(session, conversation_id, lock=True)
            if handoff is not None and handoff.status == "active":
                if handoff.assignee == staff_name:
                    return handoff_view(handoff)
                raise HandoffError(f"该会话已由 {handoff.assignee} 接待")
            if handoff is None:
                handoff = Handoff(
                    conversation_id=conversation_id, user_id=conversation.user_id, status="active",
                    reason="staff_takeover",
                    card=await _card_from_db(session, conversation, "staff_takeover", values),
                )
                session.add(handoff)
            handoff.status = "active"
            handoff.assignee = staff_name
            handoff.accepted_at = _now()
            event = _event(conversation_id, EVENT_ACCEPTED, staff_name)
            session.add(event)
            await session.flush()
        _publish_state(handoff, None, [event])
        return handoff_view(handoff)


async def post(conversation_id: int, staff_name: str, text: str, kind: str = "reply") -> dict:
    """坐席回复顾客（必须是接待坐席）或写内部备注（任何坐席，顾客不可见）。"""
    if kind not in ("reply", "note"):
        raise ValueError("消息类型不正确")
    async with database.SessionLocal() as session:
        async with session.begin():
            await _lock_conversation(session, conversation_id)
            if kind == "reply":
                handoff = await _open_handoff(session, conversation_id, lock=True)
                if handoff is None or handoff.status != "active":
                    raise HandoffError("请先接入会话再回复顾客")
                if handoff.assignee != staff_name:
                    raise HandoffForbidden(f"该会话由 {handoff.assignee} 接待")
            message = Message(conversation_id=conversation_id, role="staff" if kind == "reply" else "staff_note",
                              content=text, author=staff_name)
            session.add(message)
            await session.flush()
        _publish_message(message)
        return message_view(message, audience="staff")


async def transfer(conversation_id: int, staff_name: str, target: str, *, is_admin: bool = False) -> dict:
    async with database.SessionLocal() as session:
        async with session.begin():
            await _lock_conversation(session, conversation_id)
            handoff = await _open_handoff(session, conversation_id, lock=True)
            if handoff is None or handoff.status != "active":
                raise HandoffError("只有人工接待中的会话可以转交")
            if handoff.assignee != staff_name and not is_admin:
                raise HandoffForbidden(f"该会话由 {handoff.assignee} 接待")
            if target == handoff.assignee:
                raise HandoffError("目标坐席就是当前接待人")
            user = await session.scalar(select(StaffUser).where(StaffUser.username == target))
            if user is None or not user.active or user.role not in ("agent", "admin"):
                raise HandoffError("目标账号不存在、已停用或不是坐席")
            previous = handoff.assignee
            handoff.assignee = target
            note = Message(conversation_id=conversation_id, role="staff_note", author=staff_name,
                           content=f"会话由 {previous} 转交给 {target}")
            session.add(note)
            await session.flush()
        _publish_state(handoff, None, [note])
        return handoff_view(handoff)


async def close(conversation_id: int, staff_name: str, *, is_admin: bool = False) -> dict:
    """结束人工接待，恢复 AI 接待，并把本次问答回流到问题池。"""
    async with database.SessionLocal() as session:
        async with session.begin():
            await _lock_conversation(session, conversation_id)
            handoff = await _open_handoff(session, conversation_id, lock=True)
            if handoff is None:
                raise HandoffError("该会话当前没有人工接待")
            if handoff.status == "active" and handoff.assignee != staff_name and not is_admin:
                raise HandoffForbidden(f"该会话由 {handoff.assignee} 接待")
            handoff.status = "closed"
            handoff.closed_at = _now()
            handoff.closed_by = staff_name
            event = _event(conversation_id, EVENT_CLOSED, staff_name)
            session.add(event)
            await session.flush()
        _publish_state(handoff, None, [event])
    try:
        harvested = await harvest(handoff.id)
    except Exception:
        logger.exception("人工问答回流失败 handoff_id=%s", handoff.id)
        harvested = 0
    return {**handoff_view(handoff), "harvested": harvested}


async def list_for_staff(view: str, staff_name: str, limit: int = 50) -> list[dict]:
    async with database.SessionLocal() as session:
        if view == "ai":
            open_ids = select(Handoff.conversation_id).where(Handoff.status.in_(OPEN))
            latest = (select(Message.conversation_id, func.max(Message.id).label("last_id"))
                      .where(Message.role.in_(("user", "handoff_user")))
                      .group_by(Message.conversation_id).subquery())
            rows = (await session.execute(
                select(Conversation, latest.c.last_id)
                .join(latest, latest.c.conversation_id == Conversation.id)
                .where(Conversation.id.not_in(open_ids))
                .order_by(latest.c.last_id.desc()).limit(limit))).all()
            items = []
            for conversation, _ in rows:
                items.append({"conversation_id": conversation.id, "user_id": conversation.user_id,
                              "channel": channel_of(conversation.user_id), "status": "ai", "handoff": None,
                              "last_message": await _last_message(session, conversation.id)})
            return items

        statement = select(Handoff)
        if view == "queued":
            statement = statement.where(Handoff.status == "queued").order_by(Handoff.id)
        elif view == "mine":
            statement = statement.where(Handoff.status == "active", Handoff.assignee == staff_name).order_by(Handoff.id)
        elif view == "active":
            statement = statement.where(Handoff.status.in_(OPEN)).order_by(Handoff.id)
        elif view == "closed":
            statement = statement.where(Handoff.status.in_(("closed", "cancelled"))).order_by(Handoff.id.desc())
        else:
            raise ValueError("列表类型不正确")
        items = []
        for handoff in await session.scalars(statement.limit(limit)):
            items.append({"conversation_id": handoff.conversation_id, "user_id": handoff.user_id,
                          "channel": channel_of(handoff.user_id), "status": handoff.status,
                          "handoff": handoff_view(handoff, await _position(session, handoff)),
                          "last_message": await _last_message(session, handoff.conversation_id)})
        return items


async def _last_message(session, conversation_id: int) -> dict | None:
    rows = await session.scalars(select(Message).where(
        Message.conversation_id == conversation_id,
        Message.role.in_(("user", "assistant", "handoff_user", "staff")),
    ).order_by(Message.id.desc()).limit(5))
    for row in rows:
        view = message_view(row, audience="staff")
        if view:
            return {**view, "content": view["content"][:80]}
    return None


async def counts(staff_name: str) -> dict:
    async with database.SessionLocal() as session:
        queued = await session.scalar(select(func.count()).select_from(Handoff).where(Handoff.status == "queued"))
        mine = await session.scalar(select(func.count()).select_from(Handoff).where(
            Handoff.status == "active", Handoff.assignee == staff_name))
        active = await session.scalar(select(func.count()).select_from(Handoff).where(Handoff.status == "active"))
    return {"queued": int(queued or 0), "mine": int(mine or 0), "active": int(active or 0)}


async def detail(conversation_id: int) -> dict:
    async with database.SessionLocal() as session:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise LookupError("会话不存在")
        handoff = await _open_handoff(session, conversation_id)
        if handoff is None:
            handoff = await session.scalar(select(Handoff).where(
                Handoff.conversation_id == conversation_id).order_by(Handoff.id.desc()))
        rows = await session.scalars(select(Message).where(
            Message.conversation_id == conversation_id).order_by(Message.id))
        messages = [view for row in rows if (view := message_view(row, audience="staff"))]
        position = await _position(session, handoff) if handoff is not None else None
    status = handoff.status if handoff is not None and handoff.status in OPEN else "ai"
    return {"conversation_id": conversation_id, "user_id": conversation.user_id,
            "channel": channel_of(conversation.user_id), "status": status,
            "handoff": handoff_view(handoff, position), "messages": messages}


async def staff_users() -> list[dict]:
    async with database.SessionLocal() as session:
        rows = await session.scalars(select(StaffUser).where(
            StaffUser.active.is_(True), StaffUser.role.in_(("agent", "admin"))).order_by(StaffUser.username))
        return [{"username": row.username, "role": row.role} for row in rows]


# ==================== 知识回流 ====================

def pair_dialog(rows: list[Message]) -> list[tuple[str, str]]:
    """把人工接待期间的“顾客问题 → 坐席回复”配对；连续多条顾客消息合并成一个问题。"""
    pairs, question = [], []
    for row in rows:
        text = (row.content or "").strip()
        if not text:
            continue
        if row.role in ("user", "handoff_user"):
            question.append(text)
        elif row.role == "staff" and question:
            if len(text) >= 8 and not _SHORT_REPLY.match(text):
                pairs.append(("\n".join(question[-3:]), text))
                question = []
    return pairs


def _clean(text: str) -> str:
    return re.sub(r"ORD-[\w-]+", "[订单号]", desensitize(text), flags=re.I)


async def harvest(handoff_id: int) -> int:
    """把本次人工接待的问答（脱敏后）写入问题池，来源 human_handoff；幂等。

    坐席回复只作为建议答案进入知识缺口队列，仍需审核员对照可信材料核准后才能发布。
    """
    async with database.SessionLocal() as session:
        async with session.begin():
            handoff = await session.scalar(select(Handoff).where(Handoff.id == handoff_id).with_for_update())
            if handoff is None or handoff.harvested:
                return 0
            # 从触发转人工的那条顾客消息开始（它是 AI 没能解决的问题）
            trigger_id = await session.scalar(select(func.max(Message.id)).where(
                Message.conversation_id == handoff.conversation_id, Message.role == "user",
                Message.created_at <= handoff.created_at))
            statement = select(Message).where(
                Message.conversation_id == handoff.conversation_id,
                Message.role.in_(("user", "handoff_user", "staff")),
            ).order_by(Message.id)
            if trigger_id is not None:
                statement = statement.where(Message.id >= trigger_id)
            rows = [row for row in await session.scalars(statement)
                    if row.role != "user" or trigger_id is None or row.id == trigger_id]
            added = 0
            for index, (question, answer) in enumerate(pair_dialog(rows)[:MAX_HARVEST]):
                session.add(LowConfidenceQuestion(
                    owner=handoff.user_id, conversation=str(handoff.conversation_id),
                    message_id=f"handoff-{handoff.id}-{index}", question=_clean(question)[:1000],
                    snapshot=None, source=HARVEST_SOURCE, reason=HARVEST_PREFIX + _clean(answer)[:1500],
                ))
                added += 1
            handoff.harvested = True
    return added


def harvested_answer(row: dict) -> str | None:
    """从问题池记录里取出坐席回复（非人工回流记录返回 None）。"""
    reason = row.get("reason") or ""
    if row.get("source") == HARVEST_SOURCE and reason.startswith(HARVEST_PREFIX):
        return reason[len(HARVEST_PREFIX):]
    return None


async def conversation_owner(conversation_id: int) -> str | None:
    async with database.SessionLocal() as session:
        return await session.scalar(select(Conversation.user_id).where(Conversation.id == conversation_id))
