# 模块：检索与生成评估
# 对检索召回效果和答案生成质量进行离线评测
# 支持多种检索策略对比、召回率计算、关键词覆盖度统计
# 核心职责：量化检索和生成质量，指导策略优化

from app.core.retrieval import STRATEGIES, search_knowledge
from app.core.evidence import answer_from_hits


def retrieval_metrics(
    hits: list[dict],
    groups: list[list[str]],
    k: int,
) -> dict:
    """
    计算检索指标

    参数:
        hits: 检索召回的知识块列表
        groups: 标准答案的章节路径分组（每组是同义路径列表）
        k: 取前k条计算指标

    返回:
        包含recall（召回率）和rr（倒数排名）的字典

    召回率计算:
        覆盖的标准答案组数 / 总组数
        一组中任意路径被召回即视为覆盖

    倒数排名（Reciprocal Rank）:
        首次命中标准答案的位置的倒数
        第1位命中rr=1.0，第2位rr=0.5，未命中rr=0.0

    设计说明:
        groups为空说明该问题不可回答，返回None确保不计入平均
        section_path是知识块的章节路径，同一章节不同切块视为同义
    """
    if k < 1:
        raise ValueError("k 必须为正数")

    if not groups:
        return {"recall": None, "rr": None}

    paths = [
        hit["section_path"]
        for hit in hits[:k]
    ]

    covered = sum(
        any(path in group for path in paths)
        for group in groups
    )
    recall = covered / len(groups)

    relevant = {
        path
        for group in groups
        for path in group
    }

    rr = 0.0
    for rank, path in enumerate(paths, start=1):
        if path in relevant:
            rr = 1 / rank
            break

    return {"recall": recall, "rr": rr}



async def evaluate(cases, k=5, generate=True):
    """
    评估检索和生成质量

    参数:
        cases: 评估用例列表，每个用例包含query、groups、should_refuse、expected_terms
        k: 取前k条知识块计算召回率
        generate: 是否评估答案生成（检索+生成），False时仅评估检索

    返回:
        包含详细记录和策略汇总的评估报告字典

    用例字段:
        - id: 用例标识
        - query: 用户问题
        - groups: 标准答案章节路径分组
        - should_refuse: 是否应该拒答
        - expected_terms: 期望出现的关键词列表（可选）

    评估策略:
        对每个检索策略（vector/bm25/hybrid/hybrid_rerank）分别评估

    检索指标:
        - recall: 召回率（覆盖了多少个标准答案组）
        - rr: 倒数排名（首次命中的位置倒数）

    生成指标（generate=True时）:
        - refusal_correct: 拒答判断是否正确
        - coverage: 关键词覆盖率（答案中出现的期望关键词比例）

    汇总指标:
        - recall_at_k: 平均召回率
        - mrr: 平均倒数排名
        - refusal_accuracy: 拒答准确率
        - keyword_coverage: 平均关键词覆盖率

    设计说明:
        rewrite=False, split=False确保评估的是原始检索能力
        错误不中断评估，记录error字段用于定位问题用例
    """
    if k < 1:
        raise ValueError("k 必须为正数")
    if not cases:
        raise ValueError("评估集不能为空")
    details, summary = [], {}
    for strategy in sorted(STRATEGIES):
        records = []
        for case in cases:
            # 初始化记录，预设检索失败的默认值
            row = {"id": case["id"], "strategy": strategy, "query": case["query"],
                   "should_refuse": case["should_refuse"], "error": None,
                   **retrieval_metrics([], case["groups"], k)}
            if generate:
                row.update(coverage=0. if case.get("expected_terms") else None, refusal_correct=False)
            try:
                # 执行检索
                hits = await search_knowledge(case["query"], strategy, top_k=k, rewrite=False, split=False)
                row.update(retrieval_metrics(hits, case["groups"], k), hits=hits)
                if generate:
                    # 执行答案生成
                    result = await answer_from_hits(case["query"], hits)
                    terms = case.get("expected_terms", [])
                    row.update(answer=result["answer"], refused=result["refused"],
                               refusal_correct=result["refused"] == case["should_refuse"],
                               coverage=sum(term in result["answer"] for term in terms) / len(terms) if terms else None)
            except Exception as exc:
                row["error"] = type(exc).__name__
            records.append(row)
        # 计算该策略的汇总指标
        relevant = [row for row in records if row["recall"] is not None]
        summary[strategy] = {
            "cases": len(records), "answerable_cases": len(relevant),
            "failures": sum(row["error"] is not None for row in records),
            "recall_at_k": sum(row["recall"] for row in relevant) / len(relevant) if relevant else None,
            "mrr": sum(row["rr"] for row in relevant) / len(relevant) if relevant else None,
        }
        if generate:
            summary[strategy]["refusal_accuracy"] = sum(row["refusal_correct"] for row in records) / len(records) if records else None
            coverage = [row["coverage"] for row in records if not row["should_refuse"] and row["coverage"] is not None]
            summary[strategy]["keyword_coverage"] = sum(coverage) / len(coverage) if coverage else None
        details.extend(records)
    return {"status": "evaluated", "k": k, "generation": generate,
            "rewrite": False, "split": False, "summary": summary, "details": details}
