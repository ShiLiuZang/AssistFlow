"""Ch03：定义允许进入知识库的材料及其内容类型。"""

from pathlib import Path


KB_DIR = Path(__file__).resolve().parents[2] / "data" / "kb"

SOURCE_TYPES: dict[str, str] = {
    "product-faq.md": "faq",
    "returns-policy.md": "policy",
    "after-sales-manual.md": "manual",
    "product-specs.md": "spec",
    "member-benefits.md": "policy",
    "billing-shipping.md": "policy",
}

CONTENT_TYPES: tuple[str, ...] = ("faq", "policy", "manual", "spec")
