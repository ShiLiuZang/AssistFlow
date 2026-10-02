"""app.schemas：请求体与报表模型的校验边界。"""
import pytest
from pydantic import ValidationError

from app.schemas.actions import ResumeTicketRequest, SelectOrderRequest
from app.schemas.chat import ChatRequest
from app.schemas.cost_report import CostReportRow
from app.schemas.extract import AfterSalesTicket, ExtractRequest, RequestType


class TestChatRequest:
    def test_defaults(self):
        assert ChatRequest(user_id="u", message="m").conversation_id is None

    @pytest.mark.parametrize("data", [{"user_id": "", "message": "m"}, {"user_id": "u", "message": ""}, {"user_id": "u"}])
    def test_rejects(self, data):
        with pytest.raises(ValidationError):
            ChatRequest(**data)


class TestResumeTicketRequest:
    def test_valid(self):
        request = ResumeTicketRequest(conversation_id=1, user_id="u", confirmed=False)
        assert request.tool_call_id is None

    @pytest.mark.parametrize("data", [{"confirmed": "true"}, {"confirmed": 1}, {"confirmed": True, "extra": 1}])
    def test_strict(self, data):
        with pytest.raises(ValidationError):
            ResumeTicketRequest(conversation_id=1, user_id="u", **data)


class TestSelectOrderRequest:
    BASE = {"conversation_id": 1, "user_id": "u", "request_id": "r"}

    def test_select(self):
        assert SelectOrderRequest(**self.BASE, order_id="ORD-1").kind == "select_order"

    def test_cancel(self):
        assert SelectOrderRequest(**self.BASE, cancelled=True).order_id is None

    @pytest.mark.parametrize(
        "data,message",
        [
            ({}, "请选择订单或明确取消"),
            ({"order_id": "ORD-1", "cancelled": True}, "取消不能同时选择订单"),
            ({"order_id": ""}, "at least 1"),
            ({"order_id": "ORD-1", "cancelled": "false"}, "boolean"),
            ({"order_id": "ORD-1", "kind": "confirm_ticket"}, "select_order"),
            ({"order_id": "ORD-1", "conversation_id": 0}, "greater than 0"),
            ({"order_id": "ORD-1", "request_id": ""}, "at least 1"),
            ({"order_id": "ORD-1", "extra": 1}, "Extra inputs"),
        ],
    )
    def test_rejects(self, data, message):
        with pytest.raises(ValidationError, match=message):
            SelectOrderRequest(**{**self.BASE, **data})


class TestAfterSalesTicket:
    @pytest.mark.parametrize("placeholder", ["", " null ", "None", "N/A", "无", None])
    def test_missing_order_id_placeholders(self, placeholder):
        ticket = AfterSalesTicket(order_id=placeholder, request_type="退款", expected_solution="退钱")
        assert ticket.order_id is None

    def test_keeps_real_order_id(self):
        ticket = AfterSalesTicket(order_id="ORD-1", request_type=RequestType.REPAIR, expected_solution="修好")
        assert (ticket.order_id, ticket.request_type) == ("ORD-1", RequestType.REPAIR)

    @pytest.mark.parametrize("data", [{"request_type": "退货"}, {"expected_solution": ""}])
    def test_rejects(self, data):
        with pytest.raises(ValidationError):
            AfterSalesTicket(**{"request_type": "退款", "expected_solution": "x", **data})

    def test_extract_request_requires_text(self):
        with pytest.raises(ValidationError):
            ExtractRequest(text="")


class TestCostReportRow:
    ROW = {
        "intent": "i", "requests": 1, "generations": 1, "input_tokens": 1, "output_tokens": 1, "unknown_usage": 0,
        "unpriced": 0, "priced_subtotals": {}, "price_versions": [], "estimate_complete": True,
        "duration_samples": 0, "p95_generation_ms": None,
    }

    def test_valid(self):
        assert CostReportRow(**self.ROW).p95_generation_ms is None

    @pytest.mark.parametrize(
        "patch",
        [{"requests": 1.0}, {"requests": True}, {"p95_generation_ms": float("inf")}, {"p95_generation_ms": -1.0},
         {"intent": ""}, {"estimate_complete": 1}],
    )
    def test_strict(self, patch):
        with pytest.raises(ValidationError):
            CostReportRow(**{**self.ROW, **patch})
