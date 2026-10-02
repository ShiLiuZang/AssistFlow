"""微调 数据流水线纯函数:脱敏、去重、分层划分。不碰网络与 DB,可单测。"""
import random
import re

from app.core.safety import desensitize as _desensitize
from app.core.taxonomy import LABEL2ID



def desensitize(text: str) -> str:
    """脱敏:手机号、邮箱、身份证号、长单号、微信/QQ 账号、收货地址和标注出的姓名。
    规则与应用日志共用，定义在 app.core.safety。商品型号(如 MH-LP100)不受影响。"""
    return _desensitize(text)


def dedupe(samples: list[dict]) -> list[dict]:
    """按 text 精确去重,保序取首见;顺带 strip 掉首尾空白。"""
    seen: set[str] = set()
    out: list[dict] = []
    for s in samples:
        t = s["text"].strip()
        if t and t not in seen:
            seen.add(t)
            out.append({**s, "text": t})
    return out


def split_dataset(samples: list[dict], seed: int = 42) -> tuple[list, list, list]:
    """80/10/10 分层划分:按标签组合分层;组合样本 <10 条的并进其 label id 最小
    标签的单标签层,保证小类目不至于在验证/测试里绝迹。层内 <3 条全给训练集。"""
    rng = random.Random(seed)
    combos: dict[tuple, list[dict]] = {}
    for s in samples:
        key = tuple(sorted(s["labels"], key=LABEL2ID.get))
        combos.setdefault(key, []).append(s)
    strata: dict[tuple, list[dict]] = {}
    for key, items in combos.items():
        target = key if len(items) >= 10 else (min(key, key=LABEL2ID.get),)
        strata.setdefault(target, []).extend(items)
    train: list[dict] = []
    val: list[dict] = []
    test: list[dict] = []
    for key in sorted(strata):
        items = strata[key]
        rng.shuffle(items)
        n = len(items)
        n_test = max(1, round(n * 0.1)) if n >= 3 else 0
        n_val = max(1, round(n * 0.1)) if n >= 3 else 0
        test.extend(items[:n_test])
        val.extend(items[n_test:n_test + n_val])
        train.extend(items[n_test + n_val:])
    return train, val, test
