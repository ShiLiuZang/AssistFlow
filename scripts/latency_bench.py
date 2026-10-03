"""
回复时延基准：用模拟耗时的模型和检索跑真实的对话图，对比开关时延优化前后的耗时。

不连模型、Milvus 和数据库；每类调用的耗时取自下面的 LATENCY（秒），可按自己的线上监控改。
用法：uv run python -m scripts.latency_bench [--scale 0.1]
"""

import argparse
import asyncio
import os
import time

# 设置必填配置，避免读取本地 .env 里的真实密钥
for name in ("CHAT_MODEL", "CHAT_BASE_URL", "CHAT_API_KEY", "EMBED_MODEL", "EMBED_BASE_URL", "EMBED_API_KEY"):
    os.environ.setdefault(name, "bench")

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from app.core import intent  # noqa: E402
from app.graph.adapters import Services  # noqa: E402
from app.graph.build import build_graph  # noqa: E402
from app.graph.runtime import Runtime  # noqa: E402

LATENCY = {
    "classify": 1.0,  # 意图识别（模型）
    "retrieve": 0.6,  # 向量化 + 召回 + 精排
    "check": 1.0,  # 证据充分性检查（模型）
    "answer": 2.0,  # 生成回答（模型）
    "expand": 1.0,  # 政策查询改写（模型）
    "rerank_all": 0.3,  # 政策候选统一精排
    "order": 0.1,  # 订单查询
}
HIT = {"id": 1, "question": "退货运费", "answer": "七天无理由退货的运费由买家承担。", "section_path": "售后/退货",
       "rerank_score": 0.9}
ORDER = {"order_id": "ORD-1001", "user_id": "u1", "product_name": "保温杯", "status": "已签收"}
INTENTS = {"退货运费谁出": intent.Intent.PRODUCT, "ORD-1001 能退吗": intent.Intent.REFUND}
SCENARIOS = [("问候", "在吗"), ("转人工", "转人工"), ("知识咨询", "退货运费谁出"), ("退款政策", "ORD-1001 能退吗")]


def make_services(scale: float, optimized: bool, serial_policy: bool = False) -> Services:
    """serial_policy：复现优化前的政策检索顺序（先改写，再逐个检索）。"""
    expanded = asyncio.Event()
    one_at_a_time = asyncio.Lock()

    async def wait(name):
        await asyncio.sleep(LATENCY[name] * scale)

    async def predict(query):
        await wait("classify")
        return intent.Prediction(intent=INTENTS.get(query, intent.Intent.CHAT), confidence=0.9)

    async def classify(query, *, summary_text="", recent_context=None):
        if optimized:
            quick = intent.quick_intent(query)
            if quick is not None:
                return quick, intent.ROUTES[quick.intent]
        return await intent.classify(query, predict)

    async def retrieve_detailed(query):
        if serial_policy:
            await expanded.wait()
            async with one_at_a_time:
                await wait("retrieve")
        else:
            await wait("retrieve")
        return {"candidates": [dict(HIT)], "evidence": [dict(HIT)]}

    async def check_sufficient(question, evidence):
        await wait("check")
        return {"useful": True}

    async def answer(query, evidence, *, order=None, summary_text=""):
        await wait("answer")
        return {"answer": "运费由买家承担[1]", "refused": False, "citations": [{**evidence[0], "n": 1}],
                "reason": None}

    async def expand_policy(query):
        await wait("expand")
        expanded.set()
        return ["退货运费承担规则", "七天无理由退货条件"]

    async def rerank_policy(query, hits, top_k):
        await wait("rerank_all")
        return [{**hit, "rerank_score": 0.9} for hit in hits][:top_k]

    async def get_order(order_id):
        await wait("order")
        return dict(ORDER)

    async def list_orders(user_id):
        return [dict(ORDER)]

    async def unused(*args, **kwargs):
        raise RuntimeError("基准场景不会走到这里")

    return Services(
        classify=classify, retrieve=unused, answer=answer, agent=unused, tools={}, list_orders=list_orders,
        get_order=get_order, expand_policy=expand_policy, retrieve_detailed=retrieve_detailed,
        check_sufficient=check_sufficient, rerank_policy=rerank_policy,
        speculative_retrieve=optimized, speculative_answer=optimized,  # 不注入 save_turn：不写数据库
    )


async def run(scale: float) -> list[tuple[str, float, float]]:
    rows = []
    for label, query in SCENARIOS:
        timings = []
        for optimized in (False, True):
            services = make_services(scale, optimized, serial_policy=not optimized and label == "退款政策")
            runtime = Runtime(build_graph(services, checkpointer=InMemorySaver()))
            started = time.perf_counter()
            await runtime.run_turn(query, "u1", f"bench-{label}-{optimized}")
            timings.append(time.perf_counter() - started)
        rows.append((label, *timings))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--scale", type=float, default=1.0, help="把所有耗时乘以这个系数，加快运行")
    args = parser.parse_args()
    print("模拟耗时（秒）：" + "，".join(f"{k} {v}" for k, v in LATENCY.items()))
    print(f"{'场景':<8}{'优化前':>8}{'优化后':>8}{'节省':>8}")
    for label, before, after in asyncio.run(run(args.scale)):
        before, after = before / args.scale, after / args.scale
        print(f"{label:<8}{before:>8.2f}{after:>8.2f}{before - after:>8.2f}")


if __name__ == "__main__":
    main()
