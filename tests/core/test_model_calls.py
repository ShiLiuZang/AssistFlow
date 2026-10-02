"""依赖 LLM 的小模块：充分性检查、问题改写、意图识别、LLM/嵌入客户端（模型全部为替身）。"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.core import embeddings, intent, llm, query_understanding, sufficiency
from app.core.intent import Intent, Prediction
from tests.helpers import FakeStructuredModel, patch_model


class TestCheckSufficient:
    async def test_returns_dict_and_sends_payload(self, monkeypatch):
        model = patch_model(monkeypatch, sufficiency, FakeStructuredModel(sufficiency.Sufficiency(useful=True)))

        assert await sufficiency.check_sufficient("能退吗", [{"id": 1}]) == {"useful": True}
        assert json.loads(model.calls[0][1][1]) == {"question": "能退吗", "evidence": [{"id": 1}]}

    async def test_parsing_error(self, monkeypatch):
        patch_model(monkeypatch, sufficiency, FakeStructuredModel(parsing_error=ValueError("x")))
        with pytest.raises(ValueError):
            await sufficiency.check_sufficient("q", [])

    async def test_missing_parse(self, monkeypatch):
        patch_model(monkeypatch, sufficiency, FakeStructuredModel(parsed=None))
        with pytest.raises(ValueError, match="有效结果"):
            await sufficiency.check_sufficient("q", [])

    async def test_timeout(self, monkeypatch):
        class Slow(FakeStructuredModel):
            async def ainvoke(self, messages):
                await asyncio.sleep(10)

        patch_model(monkeypatch, sufficiency, Slow())
        real_wait_for = asyncio.wait_for
        monkeypatch.setattr(
            sufficiency.asyncio, "wait_for",
            lambda coro, timeout: real_wait_for(coro, timeout=0.01),
        )
        with pytest.raises(TimeoutError):
            await sufficiency.check_sufficient("q", [])

    def test_schema_is_strict(self):
        with pytest.raises(ValueError):
            sufficiency.Sufficiency(useful="yes")
        with pytest.raises(ValueError):
            sufficiency.Sufficiency(useful=True, extra=1)


class TestUnderstand:
    async def test_rewrites_and_filters_expansions(self, monkeypatch):
        rewrite = query_understanding.Rewrite(
            standard=" MH-A1 退货政策 ",
            expanded=["退换货", " ", "MH-B2 退货", "mh-a1 退款", "a", "b", "c", "d"],
        )
        patch_model(monkeypatch, query_understanding, FakeStructuredModel(rewrite))

        result = await query_understanding.understand("MH-A1 能退吗")

        assert result == {
            "standard": "MH-A1 退货政策",
            "expanded": ["退换货", "mh-a1 退款", "a", "b", "c"],
        }

    async def test_blank_standard_falls_back_to_query(self, monkeypatch):
        patch_model(monkeypatch, query_understanding, FakeStructuredModel(query_understanding.Rewrite(standard="  ")))
        assert (await query_understanding.understand("原问题"))["standard"] == "原问题"

    @pytest.mark.parametrize(
        "model",
        [
            FakeStructuredModel(query_understanding.Rewrite(standard="MH-B2 退货")),  # 改了型号
            FakeStructuredModel(parsing_error=ValueError("bad")),
            FakeStructuredModel(parsed=None),
            FakeStructuredModel(error=RuntimeError("down")),
        ],
    )
    async def test_failures_fall_back_to_original(self, monkeypatch, model):
        patch_model(monkeypatch, query_understanding, model)
        assert await query_understanding.understand("MH-A1 能退吗") == {
            "standard": "MH-A1 能退吗", "expanded": [],
        }


class TestIntentClassify:
    @pytest.mark.parametrize(
        "label,route",
        [
            ("物流", "business"), ("订单", "business"), ("商品咨询", "knowledge"),
            ("退款退货", "refund"), ("售后", "refund"), ("投诉", "complaint"),
            ("人工", "human"), ("闲聊", "chat"), ("其他", "clarify"),
        ],
    )
    async def test_routes(self, label, route):
        async def predict(query):
            return {"intent": label, "confidence": 0.9}

        prediction, actual = await intent.classify("q", predict)
        assert (prediction.intent.value, actual) == (label, route)

    def test_every_intent_has_route(self):
        assert set(intent.ROUTES) == set(Intent)

    async def test_low_confidence_clarifies(self):
        async def predict(query):
            return {"intent": "物流", "confidence": 0.59}

        prediction, route = await intent.classify("q", predict)
        assert (prediction.intent, route) == (Intent.LOGISTICS, "clarify")

    async def test_threshold_inclusive(self):
        async def predict(query):
            return {"intent": "物流", "confidence": 0.6}

        assert (await intent.classify("q", predict))[1] == "business"

    @pytest.mark.parametrize(
        "raw",
        [
            {"intent": "未知", "confidence": 0.9},
            {"intent": "物流", "confidence": 1.5},
            {"intent": "物流", "confidence": "0.9"},
            {"intent": "物流", "confidence": 0.9, "extra": 1},
            RuntimeError("model down"),
        ],
    )
    async def test_bad_prediction_falls_back(self, raw):
        async def predict(query):
            if isinstance(raw, Exception):
                raise raw
            return raw

        prediction, route = await intent.classify("q", predict)
        assert (prediction.intent, prediction.confidence, route) == (Intent.OTHER, 0.0, "clarify")

    async def test_rejects_invalid_threshold(self):
        with pytest.raises(ValueError):
            await intent.classify("q", None, threshold=1.5)


class TestModelPredictor:
    async def test_messages_include_context(self):
        model = FakeStructuredModel(Prediction(intent=Intent.ORDER, confidence=0.8))
        predict = intent.model_predictor(model, " 摘要 ", [{"role": "human", "content": "上一句"}])

        result = await predict("查订单")

        assert result.intent == Intent.ORDER
        messages = model.calls[0]
        assert messages[0] == ("system", intent.INTENT_PROMPT)
        assert json.loads(messages[1][1]) == {"type": "untrusted_conversation_summary", "text": "摘要"}
        assert json.loads(messages[2][1])["type"] == "untrusted_recent_conversation"
        assert messages[-1] == ("human", "查订单")

    async def test_without_context_only_system_and_query(self):
        model = FakeStructuredModel(Prediction(intent=Intent.CHAT, confidence=0.8))
        await intent.model_predictor(model)("你好")
        assert len(model.calls[0]) == 2

    @pytest.mark.parametrize(
        "model",
        [FakeStructuredModel(parsing_error=ValueError("bad")), FakeStructuredModel(parsed=None)],
    )
    async def test_errors_propagate(self, model):
        with pytest.raises(ValueError):
            await intent.model_predictor(model)("q")


@pytest.mark.parametrize("thinking,expected", [("enabled", {"thinking": {"type": "enabled"}}), ("", None)])
def test_get_chat_model_configuration(monkeypatch, thinking, expected):
    monkeypatch.setattr(llm.settings, "chat_thinking", thinking)

    model = llm.get_chat_model(streaming=True)

    assert model.model_name == "test-chat-model"
    assert model.streaming is True
    assert model.extra_body == expected


class FakeEmbeddings:
    def __init__(self, scramble=None):
        self.requests = []
        self.scramble = scramble

    async def create(self, model, input):
        self.requests.append((model, list(input)))
        data = [
            SimpleNamespace(index=i, embedding=[float(len(text))])
            for i, text in enumerate(input)
        ]
        if self.scramble:
            data = self.scramble(data)
        return SimpleNamespace(data=data)


class TestEmbeddings:
    @pytest.fixture
    def fake(self, monkeypatch):
        def install(scramble=None):
            fake = FakeEmbeddings(scramble)
            monkeypatch.setattr(embeddings, "_client", lambda: SimpleNamespace(embeddings=fake))
            return fake
        return install

    async def test_batches_of_ten_preserve_order(self, fake):
        api = fake(scramble=lambda data: list(reversed(data)))
        texts = ["x" * i for i in range(1, 24)]

        vectors = await embeddings.embed_texts(texts)

        assert vectors == [[float(i)] for i in range(1, 24)]
        assert [len(batch) for _, batch in api.requests] == [10, 10, 3]
        assert api.requests[0][0] == "test-embed-model"

    async def test_empty_input(self, fake):
        api = fake()
        assert await embeddings.embed_texts([]) == []
        assert api.requests == []

    @pytest.mark.parametrize(
        "scramble",
        [lambda data: data[:-1], lambda data: data + data[:1]],
    )
    async def test_rejects_missing_or_duplicate_indices(self, fake, scramble):
        fake(scramble=scramble)
        with pytest.raises(ValueError):
            await embeddings.embed_texts(["a", "b"])

    async def test_embed_query(self, fake):
        fake()
        assert await embeddings.embed_query("abc") == [3.0]

    def test_client_is_lazy_singleton(self, monkeypatch):
        monkeypatch.setattr(embeddings, "_CLIENT", None)
        first = embeddings._client()
        assert embeddings._client() is first
        assert str(first.base_url).startswith("http://embed.invalid/v1")
