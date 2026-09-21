from collections import Counter

from app.core.intent import Intent, Prediction


def evaluate_intent(cases, predictions):
    if not cases or len(cases) != len(predictions):
        raise ValueError("样本不能为空，预测数必须与样本一致")

    labels = [
        Intent(case["expected"]).value
        for case in cases
    ]
    predicted = [
        Prediction.model_validate(item).intent.value
        for item in predictions
    ]

    correct = sum(
        expected == actual
        for expected, actual in zip(labels, predicted)
    )

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