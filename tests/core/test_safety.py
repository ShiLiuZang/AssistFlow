"""app.core.safety：输出拦截、个人信息脱敏与日志过滤器。"""
import logging

import pytest

from app.core import safety


class TestGuardReply:
    @pytest.mark.parametrize("text", [
        "已为您退款，请注意查收", "您的退款已完成", "退款已原路退回", "我们保证全额退款",
        "我马上为您退款", "已经帮您办理退款了", "已 为 您 退 款",
    ])
    def test_blocks_promises(self, text):
        assert safety.guard_reply(text) == (safety.SAFE_REPLY, True)

    @pytest.mark.parametrize("text", [
        "退货商品经平台核验通过后,退款原路退回，到账时效以平台售后规则为准",
        "您可以在订单页申请退款", "无法保证全额退款", "不能为您退款，可以转人工", "我们不会立即为您退款，需要先审核", "",
    ])
    def test_allows_explanations_and_refusals(self, text):
        assert safety.guard_reply(text) == (text, False)


class TestDesensitize:
    @pytest.mark.parametrize("text,expected", [
        ("收货地址：浙江省杭州市西湖区文三路 398 号 5 栋 1201 室", "收货地址：[地址]"),
        ("广东省深圳市南山区科技园路1号", "[地址]"),
        ("收件人：张三，电话13812345678", "收件人：[姓名]，电话[手机号]"),
        ("联系人 李小明", "联系人 [姓名]"),
        ("身份证 110101199003071234", "身份证 [身份证号]"),
        ("邮箱 a.b@example.com", "邮箱 [邮箱]"),
        ("单号 202610020001234", "单号 [单号]"),
        ("型号 MH-LP100 的尺寸", "型号 MH-LP100 的尺寸"),
        ("我想退货", "我想退货"),
    ])
    def test_rules(self, text, expected):
        assert safety.desensitize(text) == expected

    def test_corpus_lib_uses_same_rules(self):
        from scripts.finetune.corpus_lib import desensitize

        assert desensitize("收件人：张三") == safety.desensitize("收件人：张三")


class TestLogFilter:
    def test_masks_message_and_args(self):
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "用户 %s 地址 %s", ("13812345678", "北京市朝阳区建国路88号"), None)
        assert safety.DesensitizeFilter().filter(record)
        assert record.getMessage() == "用户 [手机号] 地址 [地址]"

    def test_leaves_clean_records_alone(self):
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "ok", None, None)
        safety.DesensitizeFilter().filter(record)
        assert (record.msg, record.args) == ("ok", None)

    def test_record_factory_redacts_every_logger(self, monkeypatch, caplog):
        monkeypatch.setattr(safety, "_factory_installed", False)
        original = logging.getLogRecordFactory()
        try:
            safety.install_log_redaction()
            safety.install_log_redaction()
            with caplog.at_level(logging.INFO, logger="any.module"):
                logging.getLogger("any.module").info("顾客手机 %s", "13812345678")
            assert caplog.records[-1].getMessage() == "顾客手机 [手机号]"
        finally:
            logging.setLogRecordFactory(original)
