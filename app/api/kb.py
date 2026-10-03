# 模块：知识库录入API
# 提供知识库建设的完整流程接口：材料清单、切块预览、录入入库、向量化、检索自测
# 支持手工录入和离线建库两条路径，确保查重准确性和双写一致性
# 核心职责：将建库链路搬上页面，让非技术人员也能维护知识库

import datetime as dt
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.core import jobs, retrieval
from app.db import knowledge_repo, staging_repo
from app.kb import chunking, dedup, documents, dualwrite, milvus_client
from app.kb.sources import CONTENT_TYPE_DESC, CONTENT_TYPES, KB_DIR, SOURCE_TYPES
from app.core.trusted_sources import validate_review_source
from app.core.auth import current_staff, require_admin, require_reviewer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kb", dependencies=[Depends(current_staff)])

# 单次手工录入的正文字数上限，避免超大文档阻塞接口
MAX_TEXT_CHARS = 40000

# 检索策略：纯向量、纯BM25、混合、混合+重排序
STRATEGIES = ("vector", "bm25", "hybrid", "hybrid_rerank")

# 知识库相关的后台作业名称
KB_JOBS = ("kb-preview", "kb-build", "kb-vectorize")


def _fingerprint(questions: str, answer: str) -> str:
    """
    生成查重指纹

    参数:
        questions: 问法文本
        answer: 答案正文

    返回:
        指纹字符串，用于判断是否重复录入

    设计说明:
        查重按「问法+正文」而非仅问法：
        - 表格按行拆分后，多块共用相同的节标题作为问法
        - 超长散文递归切块后，多块共用相同的节标题
        仅按问法查重会误杀这些合理的多块

        同一份正文重复录入时，指纹完全相同，自然幂等
    """
    return dedup.normalize_question(questions) + "|" + dedup.normalize_question(answer)


def _chunk_view(seq: int, c: documents.Chunk, dup: bool | None) -> dict:
    """
    生成切块的展示视图

    参数:
        seq: 切块序号
        c: 切块对象
        dup: 是否重复（None表示查重状态未知）

    返回:
        包含切块关键信息的字典，用于前端展示
    """
    return {
        "seq": seq,
        "section_path": c.section_path or "(无标题层级)",
        "category": c.category,
        "questions": c.questions,
        "answer": c.answer,
        "chars": len(c.answer),
        "is_key_clause": bool(c.is_key_clause),
        "is_table": chunking.is_table_block(c.answer),
        "duplicate": dup,
    }


def _features(chunks: list[documents.Chunk]) -> dict:
    """
    统计切块特性

    参数:
        chunks: 切块列表

    返回:
        包含切块特性统计的字典

    统计维度:
        - sections: 按标题层级切分出的节数
        - table_split: 是否触发了表格按行拆分
        - overlap: 是否触发了句末重叠（长文本切块）
        - multi_piece_sections: 被切成多块的节路径列表

    设计说明:
        一节被切成多块才谈得上重叠或拆表
        按section_path分组即可判断
    """
    groups: dict[str, list[documents.Chunk]] = {}
    for c in chunks:
        groups.setdefault(c.section_path, []).append(c)

    # 表格拆分：某节被切成多块且第一块是表格
    table_split = any(len(g) > 1 and chunking.is_table_block(g[0].answer) for g in groups.values())
    # 句末重叠：某节被切成多块且第一块不是表格（说明是长文本切块）
    overlap = any(len(g) > 1 and not chunking.is_table_block(g[0].answer) for g in groups.values())

    return {
        "sections": len(groups),
        "table_split": table_split,
        "overlap": overlap,
        "multi_piece_sections": [p for p, g in groups.items() if len(g) > 1],
    }


async def _existing_fingerprints() -> set[str] | None:
    """
    获取库中已有的指纹集合

    返回:
        指纹集合，库连不上返回None

    设计说明:
        库连不上不阻塞预览功能，只是查重状态显示为未知
        前端会在duplicate列显示"未知"而非"重复/不重复"
    """
    try:
        return {_fingerprint(q, a) for q, a in await knowledge_repo.list_chunk_pairs()}
    except Exception:
        return None


async def milvus_state() -> dict:
    """
    探测Milvus向量库状态

    返回:
        包含在线状态、集合名称、条数的字典

    设计说明:
        Milvus离线不视为错误，而是返回状态描述
        前端根据此状态决定双写一致性检查的结论
        离线时不下一致性判断，避免误报
    """
    try:
        def work():
            c = milvus_client.get_client()
            if not c.has_collection(milvus_client.COLLECTION):
                return 0
            return milvus_client.count(c)
        return {"online": True, "count": await milvus_client.acall(work),
                "collection": milvus_client.COLLECTION}
    except Exception as e:
        return {"online": False, "count": None, "collection": milvus_client.COLLECTION,
                "detail": f"{type(e).__name__}: {e}"}


def _sources() -> list[dict]:
    """
    获取建库材料清单并就地切块预览

    返回:
        包含每个材料文件基本信息和切块统计的列表

    处理流程:
        1. 遍历SOURCE_TYPES中配置的所有材料文件
        2. 检查文件是否存在
        3. 存在时读取文件并调用build_chunks切块
        4. 统计字符数、行数、切块数、关键条款数、切块特性

    设计说明:
        这是干运行（dry-run），不写库、不碰Milvus、不调上游服务
        仅用于页面展示材料清单和预估切块效果
    """
    out = []
    for fname, ctype in SOURCE_TYPES.items():
        path = KB_DIR / fname
        item = {"file": fname, "content_type": ctype, "present": path.exists(),
                "path": f"data/kb/{fname}"}
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            chunks = documents.build_chunks(raw, content_type=ctype)
            st = path.stat()
            item.update({
                "chars": len(raw), "lines": raw.count("\n") + 1,
                "mtime": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "chunks": len(chunks),
                "key_clause": sum(c.is_key_clause for c in chunks),
                "features": _features(chunks),
            })
        out.append(item)
    return out


@router.get("/overview")
async def overview() -> dict:
    """
    知识库录入页总览

    返回:
        包含库存统计、双写一致性、暂存表、材料清单、作业状态的完整字典

    数据内容:
        - chunks: MySQL中的知识块统计（总数、待向量化、已完成、按类型分组）
        - recent: 最近录入的12条知识块
        - staging: QA暂存表统计（挖知识功能的待审队列）
        - milvus: 向量库状态和条数
        - consistent: 双写一致性判断（pending=0且MySQL数=Milvus数）
        - sources: 建库材料清单及切块预览
        - jobs: 知识库相关后台作业的状态

    容错设计:
        MySQL不可用时返回None值，不阻塞页面加载
        Milvus离线时consistent保持None，不下结论
    """
    milvus = await milvus_state()
    try:
        stats = await knowledge_repo.knowledge_stats()
        recent = [{"id": r.id, "questions": r.questions, "answer": r.answer[:120],
                   "category": r.category, "section_path": r.section_path,
                   "content_type": r.content_type, "is_key_clause": bool(r.is_key_clause),
                   "status": r.vectorize_status,
                   "created_at": r.created_at.isoformat(timespec="seconds") if r.created_at else None}
                  for r in await knowledge_repo.list_recent_chunks(12)]
        db_err = None
    except Exception as e:
        stats = {"total": None, "pending": None, "done": None,
                 "by_content_type": {}, "key_clause": None}
        recent, staging, db_err = [], None, f"{type(e).__name__}: {e}"
    else:
        try:
            staging = await staging_repo.staging_stats()
        except Exception:
            logger.warning("对话暂存表尚不可用", exc_info=True)
            staging = None

    # 双写一致性检查：pending=0且MySQL完成数=Milvus条数
    consistent = None
    if db_err is None and milvus["online"]:
        consistent = stats["pending"] == 0 and stats["done"] == milvus["count"]

    return {
        "chunks": stats, "recent": recent, "staging": staging, "db_error": db_err,
        "milvus": milvus, "consistent": consistent,
        "sources": _sources(),
        "content_types": [{"key": k, "desc": CONTENT_TYPE_DESC[k]} for k in CONTENT_TYPES],
        "jobs": [jobs.status(n) for n in KB_JOBS],
    }


def _stored_chunk_view(row, *, full: bool = False) -> dict:
    result = {
        "id": row.id, "questions": row.questions,
        "answer": row.answer if full else row.answer[:160],
        "answer_chars": len(row.answer), "category": row.category,
        "section_path": row.section_path, "content_type": row.content_type,
        "is_key_clause": bool(row.is_key_clause), "status": row.vectorize_status,
        "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
    }
    if full:
        result.update(vector_id=row.vector_id, review_id=row.review_id,
                      prev_chunk_id=row.prev_chunk_id, next_chunk_id=row.next_chunk_id)
    return result


@router.get("/chunks")
async def chunks(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    q: str = Query("", max_length=200),
    status: Literal["pending", "done", "failed"] | None = None,
    content_type: Literal["faq", "policy", "manual", "spec", "mined", "unmarked"] | None = None,
) -> dict:
    try:
        result = await knowledge_repo.list_knowledge_chunks(
            page=page, size=size, q=q, status=status, content_type=content_type,
        )
    except Exception as exc:
        raise HTTPException(503, "知识库存暂时无法读取") from exc
    return {**result, "items": [_stored_chunk_view(row) for row in result["items"]]}


@router.get("/chunks/{chunk_id}")
async def chunk_detail(chunk_id: int = Path(ge=1)) -> dict:
    try:
        row = await knowledge_repo.get_knowledge_chunk(chunk_id)
    except Exception as exc:
        raise HTTPException(503, "知识块暂时无法读取") from exc
    if row is None:
        raise HTTPException(404, "知识块不存在或已移除，请刷新列表")
    return _stored_chunk_view(row, full=True)


class PreviewIn(BaseModel):
    """切块预览请求体"""
    text: str | None = None
    file: str | None = None
    content_type: str = "faq"


def _resolve_preview(body: PreviewIn) -> tuple[str, str, str]:
    """
    解析预览请求，获取正文、类型、来源

    参数:
        body: 预览请求体

    返回:
        (正文, content_type, 来源标注)的三元组

    处理逻辑:
        - 优先处理file参数：从data/kb/读取材料文件
        - 否则处理text参数：用户手工粘贴的正文

    安全设计:
        file参数走白名单精确匹配，无法传入任意路径
        防止路径遍历攻击
    """
    if body.file:
        if body.file not in SOURCE_TYPES:
            raise HTTPException(status_code=400, detail=f"不在建库材料清单里:{body.file}")
        path = KB_DIR / body.file
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"材料文件不存在:data/kb/{body.file}")
        return path.read_text(encoding="utf-8"), SOURCE_TYPES[body.file], f"data/kb/{body.file}"

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="正文是空的,贴一段 Markdown 再预览")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(status_code=400,
                            detail=f"正文 {len(text)} 字,超过单次上限 {MAX_TEXT_CHARS} 字,拆开录")
    if body.content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"content_type 只能是 {'/'.join(CONTENT_TYPES)}")
    return text, body.content_type, "手工录入"


@router.post("/preview", dependencies=[Depends(require_admin)])
async def preview(body: PreviewIn) -> dict:
    """
    切块预览接口（干运行）

    参数:
        body: 预览请求体，包含正文或文件名

    返回:
        包含切块列表、查重结果、特性统计的完整字典

    核心功能:
        1. 解析请求获取正文和类型
        2. 调用build_chunks切块
        3. 对每个切块计算指纹并查重
        4. 返回切块详情供前端展示

    设计说明:
        这是干运行（dry-run）：不写库、不碰Milvus、不调上游
        预览什么样，入库就是什么样
        切块逻辑与离线CLI完全一致，确保行为可预期
    """
    text, ctype, source = _resolve_preview(body)
    chunks = documents.build_chunks(text, content_type=ctype)
    seen = await _existing_fingerprints()

    views, dups, batch = [], 0, set()
    for i, c in enumerate(chunks, 1):
        fp = _fingerprint(c.questions, c.answer)
        # 查重：检查是否在库中或本批次中已出现
        dup = None if seen is None else (fp in seen or fp in batch)
        dups += bool(dup)
        batch.add(fp)
        views.append(_chunk_view(i, c, dup))

    return {"source": source, "content_type": ctype, "chars": len(text),
            "total": len(chunks), "duplicates": dups,
            "key_clause": sum(c.is_key_clause for c in chunks),
            "features": _features(chunks), "chunks": views,
            "dedup_known": seen is not None}


class IngestIn(BaseModel):
    """录入请求体"""
    text: str
    content_type: str = "faq"
    vectorize: bool = True


@router.post("/ingest", dependencies=[Depends(require_admin)])
async def ingest(body: IngestIn) -> dict:
    """
    知识录入接口

    参数:
        body: 录入请求体

    返回:
        包含录入结果、向量化结果、库统计的完整字典

    处理流程:
        1. 切块：调用build_chunks将正文切分
        2. 查重：按指纹过滤已存在的块
        3. 写MySQL：将新块写入knowledge_chunks表，状态为pending
        4. 向量化：可选立即调用向量化，写入Milvus

    写入顺序:
        先写MySQL再进Milvus，顺序不能反
        MySQL是原文权威源，先落地再向量化
        中间挂了重跑时，捡pending块补齐即可

    容错设计:
        向量化失败时保留pending状态
        前端提示用户"已入库但未向量化"
        后续可通过"向量化待补块"按钮补齐
    """
    text, ctype, _ = _resolve_preview(PreviewIn(text=body.text, content_type=body.content_type))
    chunks = documents.build_chunks(text, content_type=ctype)
    if not chunks:
        raise HTTPException(status_code=400, detail="这段正文切不出块,检查是不是只有标题没有正文")

    # 查重：获取库中已有指纹
    seen = await _existing_fingerprints()
    if seen is None:
        raise HTTPException(status_code=503, detail="连不上 MySQL,录入这条路走不通(查重与落库都要它)")

    kept, skipped = [], []
    for c in chunks:
        fp = _fingerprint(c.questions, c.answer)
        if fp in seen:
            skipped.append({"questions": c.questions, "answer": c.answer[:80]})
            continue
        seen.add(fp)  # 避免本批次内重复
        kept.append(c)

    # 写入MySQL，状态为pending
    ids = await dualwrite.write_pending(kept) if kept else []

    # 可选立即向量化
    vectorized = None
    if body.vectorize and ids:
        try:
            vectorized = await dualwrite.vectorize_pending()
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=(f"已入库 {len(ids)} 块(pending),向量化失败:{type(e).__name__}: {e}。"
                        "修好嵌入服务后按「向量化待补块」补齐,不必重录")) from e

    return {"content_type": ctype, "chunks": len(chunks), "inserted": len(ids),
            "skipped": len(skipped), "skipped_samples": skipped[:5], "ids": ids,
            "vectorized": vectorized, "milvus": await milvus_state(),
            "chunk_stats": await knowledge_repo.knowledge_stats()}


@router.post("/vectorize", dependencies=[Depends(require_admin)])
async def vectorize() -> dict:
    """
    向量化待补块接口

    返回:
        包含向量化数量、库统计、Milvus状态的字典

    核心功能:
        把knowledge_chunks表中所有pending状态的块补齐向量
        幂等可重跑，不会重复向量化

    使用场景:
        - 录入时向量化失败，留下pending块
        - 故意中断建库流程，手工补齐
        - 嵌入服务修复后，批量补齐历史遗留

    设计说明:
        与命令行 `make kb-vectorize` 调用同一函数
        确保行为一致，不存在两套逻辑
    """
    try:
        n = await dualwrite.vectorize_pending()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"向量化失败:{type(e).__name__}: {e}") from e
    return {"vectorized": n, "chunk_stats": await knowledge_repo.knowledge_stats(),
            "milvus": await milvus_state()}


class SearchIn(BaseModel):
    """检索请求体"""
    q: str
    strategy: str = "vector"
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/search")
async def search(body: SearchIn) -> dict:
    """
    知识检索自测接口

    参数:
        body: 检索请求体

    返回:
        包含问题、策略、召回结果的完整字典

    核心功能:
        用不同的检索策略测试召回效果
        前端用于演示"换个说法问，看召回的是不是该召回的那块"

    检索策略:
        - vector: 纯向量检索（语义相似）
        - bm25: 纯关键词检索（词面匹配）
        - hybrid: 向量+BM25混合
        - hybrid_rerank: 混合后用重排序模型精排

    使用场景:
        「邮费是多少」召回运费说明
        靠的是语义相近而非词面命中
        这一条在页面上现场看得见
    """
    q = body.q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="问一句话再检索")
    if body.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail=f"strategy 只能是 {'/'.join(STRATEGIES)}")

    try:
        hits = await retrieval.search_knowledge(q, strategy=body.strategy, top_k=body.top_k)
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"检索失败({type(e).__name__}: {e});嵌入上游与 Milvus 都要在") from e

    return {"q": q, "strategy": body.strategy, "top_k": body.top_k,
            "hits": [{"id": h.get("id"), "question": h.get("question"),
                      "answer": h.get("answer"), "score": h.get("score"),
                      "rerank_score": h.get("rerank_score"),
                      "section_path": h.get("section_path"),
                      "content_type": h.get("content_type"),
                      "category": h.get("category")} for h in hits]}


@router.get("/staging")
async def staging(limit: int = Query(30, ge=1, le=100)) -> dict:
    """
    QA暂存表查询接口

    参数:
        limit: 每个状态返回的最大行数

    返回:
        包含暂存表统计和各状态样本的字典

    数据内容:
        - stats: 各状态的总计数
        - rows: 按状态分组的样本行
          - extracted: 从对话中提取出的原始QA对
          - kept: 整体去重后保留的待审核QA对
          - discarded: 去重时丢弃的重复QA对
          - approved: 人工采纳并已入库的QA对
          - rejected: 人工弃用的QA对

    工作流程:
        分批抽出 → 整体去重 → kept待人审
        kept列是待审队列，人工审核后变为approved或rejected
    """
    try:
        stats = await staging_repo.staging_stats()
        rows = {}
        for st in ("extracted", "kept", "discarded", "approved", "rejected"):
            rows[st] = [{"id": r.id, "batch_no": r.batch_no, "source_ref": r.source_ref,
                         "question": r.question, "answer": r.answer[:160]}
                        for r in await staging_repo.list_staging_by_status(st, limit=limit)]
    except Exception as exc:
        raise HTTPException(status_code=503, detail="对话暂存表尚未迁移或无法读取") from exc
    return {"stats": stats, "rows": rows, "limit": limit}


def _candidate_material(question: str, answer: str, source_ref: str | None) -> dict:
    """只读核对当前白名单材料；不将来源标记当成审核结论。"""
    result = {"file": source_ref, "text": None, "sha256": None,
              "valid": None, "reason": None}
    if not source_ref:
        return {**result, "status": "missing", "reason": "未标注材料来源"}
    if source_ref not in SOURCE_TYPES:
        return {**result, "status": "untrusted", "reason": "来源不在材料白名单中"}
    try:
        result["text"] = (KB_DIR / source_ref).read_text(encoding="utf-8")
        result["status"] = "available"
        try:
            result["sha256"] = validate_review_source(question, answer, source_ref)
            result["valid"] = True
        except ValueError as exc:
            result.update(valid=False, reason=str(exc))
    except FileNotFoundError:
        result.update(status="missing", reason="可信材料文件尚不存在", text=None)
    except (OSError, UnicodeError):
        result.update(status="read_error", reason="可信材料暂时无法读取", text=None)
    return result


@router.get("/staging/{candidate_id}")
async def staging_detail(candidate_id: int = Path(ge=1)) -> dict:
    try:
        rows = await staging_repo.list_staging_by_ids([candidate_id])
    except Exception as exc:
        raise HTTPException(503, "候选问答暂时无法读取") from exc
    if not rows:
        raise HTTPException(404, "候选问答不存在或已移除，请刷新列表")
    row = rows[0]
    return {
        "id": row.id, "question": row.question, "answer": row.answer,
        "status": row.status, "source_ref": row.source_ref, "batch_no": row.batch_no,
        "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
        "material": _candidate_material(row.question, row.answer, row.source_ref),
    }


class StagingReviewIn(BaseModel):
    """暂存表审核请求体"""
    ids: list[int] = Field(min_length=1, description="要处理的暂存行 id")


@router.post("/staging/approve", dependencies=[Depends(require_reviewer)])
async def staging_approve(body: StagingReviewIn) -> dict:
    """
    人工采纳QA对入库接口

    参数:
        body: 包含待采纳行ID列表的请求体

    返回:
        包含采纳数量和生成的知识块ID列表的字典

    处理流程:
        1. 查询指定ID的kept状态行
        2. 验证每条QA对的可信材料来源
        3. 转换为知识块并写入knowledge_chunks
        4. 立即向量化写入Milvus
        5. 更新暂存行状态为approved

    设计说明:
        这是挖知识功能唯一的入库口
        kb-mine脚本本身不写库，只是从对话中提取QA对到暂存表
        模型归纳的问答对质量参差不齐，必须人工过目

    质量问题示例:
        - 只对单笔订单成立，缺乏通用性
        - 夹带订单号等隐私信息
        - 把"稍等我看看"当成答案

    幂等设计:
        只认status='kept'的行，重复点击或拿已处理的行不会重复入库

    容错设计:
        向量化失败时保留pending块，可重试
        重试时复用同一知识块，不会重复写MySQL
    """
    rows = await staging_repo.list_staging_by_ids(body.ids, status="kept")
    if not rows:
        raise HTTPException(status_code=409, detail="这些行不在待审状态(可能已被处理过)")

    # 验证每条QA对都有可核对的可信材料
    for row in rows:
        try:
            validate_review_source(row.question, row.answer, row.source_ref)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail="待审问答缺少可核对的可信材料") from exc

    # 转换为知识块格式
    chunks = [documents.Chunk(category="历史对话", questions=r.question, answer=r.answer,
                              section_path="mined", content_type="mined",
                              is_key_clause=documents.is_key(r.question, r.answer))
              for r in rows]

    # 写库并向量化
    try:
        ids = await dualwrite.write_pending(chunks)
        await dualwrite.vectorize_pending()
    except Exception as e:
        logger.exception("采纳写回知识库失败 staging=%s(状态不变,可重试)", [r.id for r in rows])
        raise HTTPException(
            status_code=502,
            detail=f"写回知识库失败({type(e).__name__}),已写块保留 pending,修好嵌入/Milvus 后可重试") from e

    # 更新暂存表状态
    await staging_repo.set_staging_status([r.id for r in rows], "approved")
    logger.info("挖知识人工采纳 staging=%s → knowledge_chunks %s", [r.id for r in rows], ids)
    return {"approved": len(rows), "chunk_ids": ids}


@router.post("/staging/reject", dependencies=[Depends(require_reviewer)])
async def staging_reject(body: StagingReviewIn) -> dict:
    """
    人工弃用QA对接口

    参数:
        body: 包含待弃用行ID列表的请求体

    返回:
        包含弃用数量的字典

    处理逻辑:
        不入库，只更新状态为rejected

    设计说明:
        弃用的行保留不删除，batch_no和source_ref用于溯源
        后续可追查为什么提取出这条QA对，改进提取逻辑

    幂等设计:
        只认status='kept'的行，重复点击不会报错
    """
    rows = await staging_repo.list_staging_by_ids(body.ids, status="kept")
    if not rows:
        raise HTTPException(status_code=409, detail="这些行不在待审状态(可能已被处理过)")
    await staging_repo.set_staging_status([r.id for r in rows], "rejected")
    return {"rejected": len(rows)}
