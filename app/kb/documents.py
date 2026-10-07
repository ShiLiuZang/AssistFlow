"""把 Markdown 文档转换成结构化知识块。"""

from dataclasses import dataclass
from app.kb import chunking

KEY_TERMS = (
    "退款",
    "退货",
    "时效",
    "运费",
    "邮费",
    "费用",
    "保修",
    "赔偿",
    "期限",
    "包邮",
)
@dataclass
class Chunk:
    category: str
    questions: str
    answer: str
    section_path: str
    content_type: str
    is_key_clause: int = 0


def is_key(title: str, body: str) -> int:
    text = title + body[:40]
    matched = any(term in text for term in KEY_TERMS)
    return int(matched)

def build_chunks(
    md: str,
    content_type: str,
    chunk_size: int = 400,
    overlap: int = 60,
    table_max_rows: int = 10,
) -> list[Chunk]:
    result = []
    for section in chunking.split_sections(md):
        path=[
            section.metadata[key]
            for key in ("h1", "h2", "h3", "h4")
            if section.metadata.get(key)
        ]
        section_path = " / ".join(path)
        title = path[-1] if path else content_type
        if len(path) > 1:
            category = " / ".join(path[:-1])
        elif path:
            category = path[0]
        else:
            category = content_type

        body = section.page_content.strip()

        if not body:
            continue
        pieces = chunking.split_body(body, chunk_size, overlap, table_max_rows)
        for piece in pieces:
            result.append(
                Chunk(
                    category=category,
                    questions=title,
                    answer=piece,
                    section_path=section_path,
                    content_type=content_type,
                    is_key_clause=is_key(title, piece),
                )
            )
    return result
