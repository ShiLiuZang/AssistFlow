"""Ch04：基于证据组评估检索效果。"""
from app.core.retrieval import STRATEGIES, search_knowledge
from app.core.evidence import answer_from_hits



def retrieval_metrics(
    hits: list[dict],
    groups: list[list[str]],
    k: int,
) -> dict:
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
    if k < 1:
        raise ValueError("k 必须为正数")
    if not cases:
        raise ValueError("评估集不能为空")
    details, summary = [], {}
    for strategy in sorted(STRATEGIES):
        records = []
        for case in cases:
            row = {"id": case["id"], "strategy": strategy, "query": case["query"],
                   "should_refuse": case["should_refuse"], "error": None,
                   **retrieval_metrics([], case["groups"], k)}
            if generate:
                row.update(coverage=0. if case.get("expected_terms") else None, refusal_correct=False)
            try:
                # 四策略固定问题、K、改写/拆分设置，避免混淆实验变量。
                hits = await search_knowledge(case["query"], strategy, top_k=k, rewrite=False, split=False)
                row.update(retrieval_metrics(hits, case["groups"], k), hits=hits)
                if generate:
                    result = await answer_from_hits(case["query"], hits)
                    terms = case.get("expected_terms", [])
                    row.update(answer=result["answer"], refused=result["refused"],
                               refusal_correct=result["refused"] == case["should_refuse"],
                               coverage=sum(term in result["answer"] for term in terms) / len(terms) if terms else None)
            except Exception as exc:
                row["error"] = type(exc).__name__
            records.append(row)
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
