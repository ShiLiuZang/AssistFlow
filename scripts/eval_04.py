"""Ch04：比较四种检索策略的 Recall@K、MRR 和证据覆盖度。"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from app.kb.documents import build_chunks
from app.kb.sources import KB_DIR, SOURCE_TYPES

ROOT = Path(__file__).resolve().parents[1]


def validate_cases(cases):
    paths = {chunk.section_path for name, kind in SOURCE_TYPES.items()
             for chunk in build_chunks((KB_DIR / name).read_text(encoding="utf-8"), kind)}
    seen = set()
    for case in cases:
        if case["id"] in seen or not case["query"].strip():
            raise ValueError("题目 ID 重复或问题为空")
        seen.add(case["id"])
        if bool(case["groups"]) == case["should_refuse"]:
            raise ValueError("应拒题不可标注相关证据，普通题必须标注证据")
        for group in case["groups"]:
            if not group or any(path not in paths for path in group):
                raise ValueError(f"{case['id']} 标注来源不存在")
    if not cases:
        raise ValueError("评估集不能为空")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="只校验本地题目和来源，不调用模型或数据库")
    parser.add_argument("--skip-gen", action="store_true", help="跳过生成，仍调用 Embedding/Milvus/Rerank")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("top-k 必须为正")
    dataset = ROOT / "tests/data/eval_04.jsonl"
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    validate_cases(cases)
    if args.local:
        print(f"本地标注检查通过：{len(cases)} 题；未运行真实检索")
        return
    from app.core.evaluation import evaluate
    report = await evaluate(cases, k=args.top_k, generate=not args.skip_gen)
    report.update(created_at=datetime.now(timezone.utc).isoformat(), dataset=cases)
    output = ROOT / "reports/04.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(output)


if __name__ == "__main__":
    asyncio.run(main())
