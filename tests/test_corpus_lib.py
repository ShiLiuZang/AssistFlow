"""
测试语料处理的纯函数
覆盖脱敏、去重和分层数据集划分
"""
from scripts.finetune.corpus_lib import dedupe, desensitize, split_dataset


def test_desensitize_masks_sensitive_keeps_model_no():
    """测试脱敏：遮蔽敏感信息，保留商品型号"""
    assert desensitize("我手机13812345678帮我查下") == "我手机[手机号]帮我查下"
    assert desensitize("订单202601180001234567还没发") == "订单[单号]还没发"
    assert desensitize("加我微信 cat_lover2026 聊") == "加我微信[账号]聊"
    assert desensitize("邮箱 cat@example.com，身份证 11010119900101123X") == "邮箱 [邮箱]，身份证 [身份证号]"

    assert "MH-LP100" in desensitize("MH-LP100 猫砂盆废砂盒多久倒一次")


def test_dedupe_keeps_first():
    """测试去重：保留首次出现的记录"""
    out = dedupe([{"text": "a", "origin": "pool"}, {"text": "a", "origin": "simulated"},
                  {"text": "b", "origin": "pool"}])
    assert [s["text"] for s in out] == ["a", "b"]
    assert out[0]["origin"] == "pool"


def _make_samples():
    """构造测试样本"""
    samples = []
    for cls, n in (("退换货", 40), ("物流", 40), ("尺码", 30)):
        samples += [{"text": f"{cls}问题{i}", "labels": [cls]} for i in range(n)]
    samples += [{"text": f"多诉求{i}", "labels": ["尺码", "退换货"]} for i in range(12)]
    samples += [{"text": f"小组合{i}", "labels": ["物流", "退换货"]} for i in range(3)]
    return samples


def test_split_ratio_and_no_leakage():
    """测试分层划分：比例正确且无样本泄漏"""
    train, val, test = split_dataset(_make_samples())
    total = len(train) + len(val) + len(test)
    assert total == 125
    assert 0.72 <= len(train) / total <= 0.88
    texts = [s["text"] for s in train + val + test]
    assert len(texts) == len(set(texts))


def test_split_every_class_in_every_split():
    """测试类别覆盖：每个划分都包含所有类别"""
    train, val, test = split_dataset(_make_samples())
    for split in (train, val, test):
        found = {lb for s in split for lb in s["labels"]}
        assert {"退换货", "物流", "尺码"} <= found


def test_split_deterministic():
    """测试确定性：相同种子产生相同划分"""
    a = split_dataset(_make_samples(), seed=42)
    b = split_dataset(_make_samples(), seed=42)
    assert a == b
