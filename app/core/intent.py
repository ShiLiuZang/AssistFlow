from enum import StrEnum


class Intent(StrEnum):
    LOGISTICS = "物流"
    ORDER = "订单"
    PRODUCT = "商品咨询"
    REFUND = "退款退货"
    AFTERSALES = "售后"
    COMPLAINT = "投诉"
    HUMAN = "人工"
    CHAT = "闲聊"
    OTHER = "其他"

ROUTES = {
    Intent.LOGISTICS: "business",
    Intent.ORDER: "business",
    Intent.PRODUCT: "knowledge",
    Intent.REFUND: "refund",
    Intent.AFTERSALES: "refund",
    Intent.COMPLAINT: "complaint",
    Intent.HUMAN: "human",
    Intent.CHAT: "chat",
    Intent.OTHER: "clarify",
}