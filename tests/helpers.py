"""测试共用的替身与数据构造函数。"""


def make_hit(hit_id, score=None, **extra):
    """构造一条检索命中；score 为 None 时不带 rerank_score。"""
    data = {
        "id": hit_id,
        "question": f"q{hit_id}",
        "answer": f"a{hit_id}",
        "section_path": "售后/退货",
        **extra,
    }
    if score is not None:
        data["rerank_score"] = score
    return data


class FakeStructuredModel:
    """模拟 get_chat_model() 及其 with_structured_output / bind_tools 链。

    include_raw=True 的调用返回 {"raw", "parsed", "parsing_error"}；
    否则直接返回 parsed。所有收到的消息记录在 calls 中。
    """

    def __init__(self, parsed=None, parsing_error=None, raw=None, error=None):
        self.parsed = parsed
        self.parsing_error = parsing_error
        self.raw = raw if raw is not None else object()
        self.error = error
        self.include_raw = False
        self.schema = None
        self.calls = []

    def with_structured_output(self, schema, *, include_raw=False, **kwargs):
        self.schema = schema
        self.include_raw = include_raw
        return self

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        if self.include_raw:
            return {"raw": self.raw, "parsed": self.parsed, "parsing_error": self.parsing_error}
        return self.parsed


def patch_model(monkeypatch, module, model):
    """把 module.get_chat_model 替换成返回固定替身的函数。"""
    monkeypatch.setattr(module, "get_chat_model", lambda **kwargs: model)
    return model
