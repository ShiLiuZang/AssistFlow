"""渠道文本：纯文本化、拆分、文字确认与选择。"""
from app.channels import text


class TestPlainText:
    def test_strips_markdown_and_citations(self):
        raw = "## 退货说明\n**七天无理由**退货[1]，详见[规则](https://x.example/a)。\n- 保持包装完好[2]\n\n\n\n联系客服"
        assert text.plain_text(raw) == "退货说明\n七天无理由退货，详见规则。\n· 保持包装完好\n\n联系客服"


class TestSplit:
    def test_short_message_unchanged(self):
        assert text.split_message("你好", 10) == ["你好"]

    def test_splits_on_sentences(self):
        parts = text.split_message("第一句话。第二句话。第三句话。", 10)
        assert parts == ["第一句话。第二句话。", "第三句话。"]
        assert all(len(p) <= 10 for p in parts)

    def test_hard_cut_long_sentence(self):
        parts = text.split_message("啊" * 25, 10)
        assert [len(p) for p in parts] == [10, 10, 5]

    def test_truncates_after_max_parts(self):
        parts = text.split_message("这是一句话。" * 40, 60, max_parts=2)
        assert len(parts) == 2 and parts[-1].endswith(text.TRUNCATED_TAIL)
        assert all(len(p) <= 60 for p in parts)

    def test_empty(self):
        assert text.split_message("  ", 10) == []


class TestConfirmation:
    def test_yes_and_no(self):
        for reply in ("确认", "好的", "可以！", "嗯嗯", "OK", "1"):
            assert text.parse_confirmation(reply) is True, reply
        for reply in ("取消", "不用了", "算了", "不要"):
            assert text.parse_confirmation(reply) is False, reply

    def test_other_text_is_unknown(self):
        assert text.parse_confirmation("我想问一下运费") is None
        assert text.parse_confirmation("确认一下我的地址对不对") is None

    def test_ticket_prompt(self):
        prompt = text.ticket_prompt({"ticket_type": "退款", "description": "杯子破了"})
        assert "「退款」" in prompt and "杯子破了" in prompt and "「确认」" in prompt


class TestOrderChoice:
    ORDERS = [{"order_id": "231003-111111111111111", "product_name": "保温杯"},
              {"order_id": "231004-222222222222222", "product_name": "键盘"}]

    def test_by_index_or_number(self):
        assert text.parse_order_choice("2", self.ORDERS) == "231004-222222222222222"
        assert text.parse_order_choice("第1个", self.ORDERS) == "231003-111111111111111"
        assert text.parse_order_choice("是 231004-222222222222222 这单", self.ORDERS) == "231004-222222222222222"

    def test_cancel_and_unknown(self):
        assert text.parse_order_choice("取消", self.ORDERS) is False
        assert text.parse_order_choice("3", self.ORDERS) is None
        assert text.parse_order_choice("随便", self.ORDERS) is None

    def test_prompt_lists_orders(self):
        prompt = text.order_prompt(self.ORDERS)
        assert "1. 保温杯 231003-111111111111111" in prompt and "2. 键盘" in prompt
