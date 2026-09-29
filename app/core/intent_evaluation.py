# 模块：意图分类评估
# 对意图分类模型的准确率进行离线评测
# 计算准确率、混淆矩阵、错误样例，指导模型优化
# 核心职责：量化意图分类质量，发现误判模式

from collections import Counter

from app.core.intent import Intent, Prediction


def evaluate_intent(cases, predictions):
    """
    评估意图分类准确率

    参数:
        cases: 评估用例列表，每个包含query和expected字段
        predictions: 预测结果列表，每个包含intent字段

    返回:
        包含准确率、混淆矩阵、错误样例的评估报告

    报告结构:
        - count: 样本总数
        - accuracy: 准确率（正确数/总数）
        - confusion: 混淆矩阵（期望意图-预测意图-出现次数）
        - errors: 错误样例列表（包含query、期望、预测）

    异常:
        ValueError: 样本为空或预测数与样本数不一致

    设计说明:
        使用Intent枚举规范化意图值，确保合法性
        混淆矩阵按字典序排列，方便对比不同版本
        错误样例用于人工分析，定位误判原因
    """
    if not cases or len(cases) != len(predictions):
        raise ValueError("样本不能为空，预测数必须与样本一致")

    # 提取标准标签
    labels = [
        Intent(case["expected"]).value
        for case in cases
    ]
    # 提取预测标签
    predicted = [
        Prediction.model_validate(item).intent.value
        for item in predictions
    ]

    correct = sum(
        expected == actual
        for expected, actual in zip(labels, predicted)
    )

    # 统计混淆对：(期望, 预测) -> 出现次数
    confusion = Counter(zip(labels, predicted))
    errors = []

    for case, expected, actual in zip(cases, labels, predicted):
        if expected != actual:
            error = {
                "query": case["query"],
                "expected": expected,
                "predicted": actual,
            }
            errors.append(error)
    return {
        "count": len(cases),
        "accuracy": correct / len(cases),
        "confusion": [
            {
                "expected": expected,
                "predicted": actual,
                "count": count,
            }
            for (expected, actual), count in sorted(confusion.items())
        ],
        "errors": errors,
    }