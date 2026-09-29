# 模块：成本报表生成
# 从可观测性系统的模型调用记录中提取token使用量，按意图分组统计
# 结合模型价格表计算成本，生成完整的成本明细报表
# 核心职责：让AI调用成本可见、可归因、可优化

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import math

@dataclass(frozen=True)
class Price:
    """模型价格定义"""
    input_per_million: Decimal  # 输入token单价（每百万token）
    output_per_million: Decimal  # 输出token单价（每百万token）
    currency: str  # 币种（如USD、CNY）
    as_of: str  # 价格版本标识（如"2024-01"）
def build_intent_index(observations: list[dict]) -> dict[str, str]:
    """
    从观测记录中提取意图索引

    参数:
        observations: 可观测性系统的观测记录列表

    返回:
        trace_id -> intent 的映射字典，仅包含单一意图的trace

    处理逻辑:
        1. 遍历所有观测记录，找出名为"classify"的意图分类记录
        2. 提取每个trace的所有意图候选
        3. 只保留整个trace中意图唯一的记录

    设计说明:
        同一个trace可能有多次意图分类（如重试或多轮），只有意图一致时才算有效
        意图不一致说明用户诉求变化或分类不稳定，此时不强行归类
    """
    candidates: dict[str, set[str]] = {}
    for observation in observations:
        # 只关注意图分类节点
        if observation.get("name") != "classify":
            continue

        trace_id = observation.get("traceId")
        metadata = observation.get("metadata")
        if not isinstance(trace_id, str) or not trace_id.strip():
            continue
        if not isinstance(metadata, dict):
            continue

        intent = metadata.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            continue
        candidates.setdefault(trace_id, set()).add(intent.strip())

    result = {}
    # 只保留意图唯一的trace
    for trace_id, intents in candidates.items():
        if len(intents) == 1:
            intent = next(iter(intents))
            result[trace_id] = intent

    return result
def reported_total_tokens(observation: dict) -> int | None:
    """
    从观测记录中提取token总数

    参数:
        observation: 单条观测记录

    返回:
        token总数，提取失败返回None

    设计说明:
        metadata.token_usage.total_tokens是观测记录中上报的token计数
        缺失或格式错误时返回None，不抛异常，确保报表生成容错
    """
    metadata = observation.get("metadata")

    if not isinstance(metadata, dict):
        return None

    usage = metadata.get("token_usage")

    if not isinstance(usage, dict):
        return None

    total = usage.get("total_tokens")

    if type(total) is not int or total < 0:
        return None

    return total
def unique_observations(observations: list[dict]) -> list[dict]:
    """
    观测记录去重

    参数:
        observations: 观测记录列表

    返回:
        去重后的观测记录列表

    异常:
        ValueError: 记录缺少有效id，或同一id对应不同内容

    设计说明:
        可观测性系统可能重复导出同一条记录（如分批查询重叠）
        按id去重确保统计准确，发现内容冲突时报错而非静默
    """
    by_id: dict[str, dict] = {}

    for observation in observations:
        observation_id = observation.get("id")

        if (
            not isinstance(observation_id, str)
            or not observation_id.strip()
        ):
            raise ValueError("观测记录缺少有效的 id")

        if observation_id in by_id:
            if by_id[observation_id] != observation:
                raise ValueError("同一观测 id 对应不同内容")

            continue

        by_id[observation_id] = observation

    return list(by_id.values())
def aggregate_usage(observations: list[dict]) -> list[dict]:
    """
    按意图聚合token使用量

    参数:
        observations: 观测记录列表

    返回:
        按意图分组的使用量统计列表，按已知token数降序排列

    统计维度:
        - count: 涉及的trace（请求）数量
        - generation_count: 模型生成次数（一个trace可能多次生成）
        - measured_count: 有token计数的生成次数
        - missing_usage_count: 缺失token计数的生成次数
        - known_tokens: 已知token总数

    意图分类:
        - 后台摘要: name为"summary_model"的生成
        - 具体意图: 从意图索引中查询
        - 未归类: 无法确定意图的生成

    设计说明:
        观测记录的type字段区分GENERATION（模型生成）和其他类型
        只统计GENERATION类型确保准确计算成本
    """
    observations = unique_observations(observations)
    intent_index = build_intent_index(observations)
    groups: dict[str, dict] = {}

    for observation in observations:
        # 只统计模型生成节点
        if observation.get("type") != "GENERATION":
            continue

        trace_id = observation.get("traceId")
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise ValueError("模型观测缺少有效的 traceId")

        # 特殊处理后台摘要任务
        if observation.get("name") == "summary_model":
            intent = "后台摘要"
        else:
            intent = intent_index.get(trace_id, "未归类")

        group = groups.setdefault(
            intent,
            {
                "traces": set(),
                "generation_count": 0,
                "measured_count": 0,
                "missing_usage_count": 0,
                "known_tokens": 0,
            },
        )

        group["traces"].add(trace_id)
        group["generation_count"] += 1

        total = reported_total_tokens(observation)

        if total is None:
            group["missing_usage_count"] += 1
        else:
            group["measured_count"] += 1
            group["known_tokens"] += total

    rows = []

    for intent, group in groups.items():
        rows.append({
            "intent": intent,
            "count": len(group["traces"]),
            "generation_count": group["generation_count"],
            "measured_count": group["measured_count"],
            "missing_usage_count": group["missing_usage_count"],
            "known_tokens": group["known_tokens"],
        })

    # 按token数降序排列，方便快速定位成本大头
    return sorted(
        rows,
        key=lambda row: (-row["known_tokens"], row["intent"]),
    )
def build_cost_report(observations: list[dict]) -> dict:
    """
    构建成本报表（不含价格）

    参数:
        observations: 观测记录列表

    返回:
        包含行明细和汇总的报表字典

    报表结构:
        - rows: 按意图分组的使用量明细
        - known_tokens: 已知token总数
        - total_tokens: token总数（有缺失时为None）
        - total_requests: 请求（trace）总数
        - generation_count: 模型生成总次数
        - missing_usage_count: 缺失token计数的生成次数
        - usage_complete: 是否所有生成都有token计数

    行字段:
        - tokens: 该意图的token总数（有缺失时为None）
        - avg_tokens: 该意图的平均每请求token数（有缺失时为None）
        - share: 该意图占总token的比例（全局有缺失时为None）

    设计说明:
        缺失token计数时相关字段显示None而非估算值
        避免用不准确的数据误导成本决策
    """
    observations = unique_observations(observations)
    groups = aggregate_usage(observations)

    total_known_tokens = sum(
        group["known_tokens"]
        for group in groups
    )
    missing_usage_count = sum(
        group["missing_usage_count"]
        for group in groups
    )

    trace_ids = {
        observation["traceId"]
        for observation in observations
        if observation.get("type") == "GENERATION"
    }

    rows = []

    for group in groups:
        complete = group["missing_usage_count"] == 0

        rows.append({
            **group,
            "tokens": (
                group["known_tokens"]
                if complete
                else None
            ),
            "avg_tokens": (
                round(group["known_tokens"] / group["count"], 2)
                if complete
                else None
            ),
            "share": (
                round(
                    group["known_tokens"] / total_known_tokens,
                    4,
                )
                if missing_usage_count == 0
                and total_known_tokens > 0
                else None
            ),
        })

    return {
        "rows": rows,
        "known_tokens": total_known_tokens,
        "total_tokens": (
            total_known_tokens
            if missing_usage_count == 0
            else None
        ),
        "total_requests": len(trace_ids),
        "generation_count": sum(
            group["generation_count"]
            for group in groups
        ),
        "missing_usage_count": missing_usage_count,
        "usage_complete": missing_usage_count == 0,
    }
def to_generation_rows(observations: list[dict]) -> list[dict]:
    """
    将观测记录转换为模型生成明细行

    参数:
        observations: 观测记录列表

    返回:
        模型生成明细列表，每行包含trace_id、generation_id、意图、模型、token数、耗时

    行字段:
        - trace_id: 请求追踪ID
        - generation_id: 观测记录ID
        - intent: 意图分类
        - model: 模型名称（如"gpt-4o-mini"）
        - input_tokens: 输入token数
        - output_tokens: 输出token数
        - duration_ms: 生成耗时（毫秒）

    设计说明:
        这是成本计算的基础数据，将观测记录展开为平面表
        缺失input/output时两者都设为None，避免部分缺失导致错算
    """
    observations = unique_observations(observations)
    intent_index = build_intent_index(observations)
    rows = []

    for observation in observations:
        if observation.get("type") != "GENERATION":
            continue

        trace_id = observation.get("traceId")
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise ValueError("模型观测缺少有效的 traceId")

        metadata = observation.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        usage = metadata.get("token_usage")
        if not isinstance(usage, dict):
            usage = {}

        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")

        # 输入输出必须同时有效，否则都设为None
        if any(
            type(value) is not int or value < 0
            for value in (input_tokens, output_tokens)
        ):
            input_tokens = None
            output_tokens = None

        model = observation.get("model")
        if isinstance(model, str) and model.strip():
            model = model.strip()
        else:
            model = None

        if observation.get("name") == "summary_model":
            intent = "后台摘要"
        else:
            intent = intent_index.get(trace_id, "unknown")

        rows.append({
            "trace_id": trace_id,
            "generation_id": observation["id"],
            "intent": intent,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_ms": metadata.get("duration_ms"),
        })

    return rows
def estimate_generation_cost(
    row: dict,
    prices: dict[str, Price],
) -> dict | None:
    """
    估算单次模型生成的成本

    参数:
        row: 模型生成明细行
        prices: 模型名称 -> 价格定义的映射

    返回:
        包含金额、币种、价格版本的字典，无法估算时返回None

    估算逻辑:
        成本 = (输入token数 × 输入单价 + 输出token数 × 输出单价) / 1000000

    返回None的情况:
        - 缺少输入或输出token数
        - 缺少模型名称
        - 价格表中没有该模型

    设计说明:
        使用Decimal确保货币计算精度
        价格版本（as_of）用于追溯成本变化，价格调整后可对比不同版本
    """
    input_tokens = row.get("input_tokens")
    output_tokens = row.get("output_tokens")

    if any(
        type(value) is not int or value < 0
        for value in (input_tokens, output_tokens)
    ):
        return None

    model = row.get("model")
    if not isinstance(model, str) or not model.strip():
        return None

    price = prices.get(model)
    if price is None:
        return None

    for rate in (
        price.input_per_million,
        price.output_per_million,
    ):
        if (
            not isinstance(rate, Decimal)
            or not rate.is_finite()
            or rate < 0
        ):
            raise ValueError("模型价格必须是有限的非负 Decimal")

    if not price.currency.strip() or not price.as_of.strip():
        raise ValueError("模型价格必须包含币种和价格版本")

    amount = (
        input_tokens * price.input_per_million
        + output_tokens * price.output_per_million
    ) / Decimal("1000000")

    return {
        "amount": amount,
        "currency": price.currency,
        "price_version": price.as_of,
    }
def cost_by_intent(
    rows: list[dict],
    prices: dict[str, Price] | None = None,
) -> dict:
    """
    按意图统计token使用量和成本

    参数:
        rows: 模型生成明细行列表
        prices: 模型价格表（可选）

    返回:
        意图 -> 统计信息的映射字典

    统计维度:
        - requests: 请求数（去重的trace数量）
        - generations: 模型生成次数
        - input_tokens: 输入token总数
        - output_tokens: 输出token总数
        - unknown_usage: 缺失token计数的生成次数
        - unpriced: 无法定价的生成次数（缺模型名或价格表无该模型）
        - priced_subtotals: 按币种分组的成本小计
        - price_versions: 使用的价格版本集合
        - p95_generation_ms: 生成耗时的95分位数
        - estimate_complete: 是否所有生成都有价格估算

    设计说明:
        同一个generation_id重复出现时检查内容一致性，确保统计准确
        支持多币种分别小计，适配国内外模型混用场景
        P95耗时用于识别慢查询，帮助定位性能瓶颈
    """
    prices = prices if prices is not None else {}
    groups = {}
    seen = {}

    for row in rows:
        trace_id = row.get("trace_id")
        generation_id = row.get("generation_id")

        if any(
            not isinstance(value, str) or not value.strip()
            for value in (trace_id, generation_id)
        ):
            raise ValueError("模型调用缺少有效的 trace_id 或 generation_id")

        key = (trace_id, generation_id)

        if key in seen:
            if seen[key] != row:
                raise ValueError("同一模型调用对应不同内容")
            continue

        seen[key] = row

        intent = row.get("intent") or "unknown"
        group = groups.setdefault(
            intent,
            {
                "traces": set(),
                "generations": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "unknown_usage": 0,
                "unpriced": 0,
                "priced_subtotals": {},
                "price_versions": set(),
                "durations": [],
            },
        )

        group["traces"].add(trace_id)
        group["generations"] += 1
        duration = row.get("duration_ms")

        if (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and math.isfinite(duration)
            and duration >= 0
        ):
            group["durations"].append(duration)
        input_tokens = row.get("input_tokens")
        output_tokens = row.get("output_tokens")

        if any(
            type(value) is not int or value < 0
            for value in (input_tokens, output_tokens)
        ):
            group["unknown_usage"] += 1
        else:
            group["input_tokens"] += input_tokens
            group["output_tokens"] += output_tokens

        estimate = estimate_generation_cost(row, prices)

        if estimate is None:
            group["unpriced"] += 1
            continue

        currency = estimate["currency"]
        subtotals = group["priced_subtotals"]

        subtotals[currency] = (
            subtotals.get(currency, Decimal("0"))
            + estimate["amount"]
        )
        group["price_versions"].add(estimate["price_version"])

    # 后处理：计算聚合指标
    for group in groups.values():
        group["requests"] = len(group.pop("traces"))
        durations = sorted(group.pop("durations"))

        group["duration_samples"] = len(durations)
        # P95分位数：95%的生成都快于此值
        group["p95_generation_ms"] = (
            durations[math.ceil(len(durations) * 0.95) - 1]
            if durations
            else None
        )
        group["price_versions"] = sorted(group["price_versions"])
        # Decimal转字符串，避免JSON序列化问题
        group["priced_subtotals"] = {
            currency: str(amount)
            for currency, amount in group["priced_subtotals"].items()
        }
        group["estimate_complete"] = group["unpriced"] == 0

    return groups


def make_cost_report(
    generation_rows: list[dict],
    prices: dict[str, Price] | None = None,
    *,
    source: str,
) -> dict:
    """
    生成完整成本报表

    参数:
        generation_rows: 模型生成明细行列表
        prices: 模型价格表（可选）
        source: 数据来源标识（必需，如"langfuse_2024-01-15"）

    返回:
        包含元信息、行明细、汇总的完整报表字典

    报表结构:
        - schema_version: 报表格式版本号
        - meta: 元信息（数据来源、生成时间、统计范围、定价依据）
        - rows: 按意图分组的明细行（按token数降序排列）
        - summary: 全局汇总（请求数、生成数、token数、完整性标记）

    完整性标记:
        - usage_complete: 所有生成都有token计数
        - estimate_complete: 所有生成都有价格估算

    设计说明:
        source必填确保报表可溯源，避免混淆不同时间段的数据
        schema_version为未来格式演进预留版本管理能力
        pricing_basis注明只考虑输入输出token，不含缓存、批处理等特殊定价
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError("报表必须说明数据来源")

    groups = cost_by_intent(generation_rows, prices)

    rows = [
        {"intent": intent, **group}
        for intent, group in groups.items()
    ]
    # 按token数降序排列，方便快速定位成本大头
    rows.sort(
        key=lambda row: (
            -(row["input_tokens"] + row["output_tokens"]),
            row["intent"],
        )
    )

    trace_ids = {row["trace_id"] for row in generation_rows}
    unknown_usage = sum(row["unknown_usage"] for row in rows)
    unpriced = sum(row["unpriced"] for row in rows)

    return {
        "schema_version": 1,
        "meta": {
            "source": source.strip(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": "provided_generations",
            "pricing_basis": "input_output_only",
        },
        "rows": rows,
        "summary": {
            "requests": len(trace_ids),
            "generations": sum(row["generations"] for row in rows),
            "known_input_tokens": sum(row["input_tokens"] for row in rows),
            "known_output_tokens": sum(row["output_tokens"] for row in rows),
            "unknown_usage": unknown_usage,
            "unpriced": unpriced,
            "usage_complete": unknown_usage == 0,
            "estimate_complete": unpriced == 0,
        },
    }
