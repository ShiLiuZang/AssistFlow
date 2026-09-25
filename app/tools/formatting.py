"""工具结果的纯格式化函数，不执行网络请求或业务操作。"""


LOGISTICS_STATUS_LABELS = {
    "IN_TRANSIT": "运输中",
}


def format_logistics_result(data: dict) -> dict[str, str]:
    """格式化成功的物流结果，只返回允许展示的字段。"""
    code = data.get("status_code")

    if not isinstance(code, str) or not code.strip():
        raise ValueError("物流结果缺少有效的状态码")

    result = {
        "status_code": code,
        "status": LOGISTICS_STATUS_LABELS.get(code, code),
    }

    tracking_no = data.get("tracking_no")
    if tracking_no is not None:
        if not isinstance(tracking_no, str):
            raise ValueError("物流号必须是字符串")

        result["tracking_no"] = tracking_no

    return result
