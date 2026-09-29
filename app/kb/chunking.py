"""Ch03：Markdown 标题解析、正文切分、重叠和表格切分。"""
import re
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_core.documents import Document
HEADERS = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
]


def split_sections(md: str) -> list[Document]:
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS,
        strip_headers=True,
    )

    documents = splitter.split_text(md)
    return documents


CJK_SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    "；",
    "!",
    "?",
    ";",
    "，",
    " ",
    "",
]

def recursive_split(
    text: str,
    chunk_size: int,
    chunk_overlap: int = 0,
) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=CJK_SEPARATORS,
        is_separator_regex=False,
        length_function=len,
        keep_separator="end",
    )

    result = splitter.split_text(text)
    return result

_SENT_RE = re.compile(
    r"[^。！？!?…\n]*[。！？!?…\n]|[^。！？!?…\n]+$"
)
def _split_sentences(text: str) -> list[str]:
    sentences = _SENT_RE.findall(text)
    return [sentence for sentence in sentences if sentence]

def _trailing_sentences(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    sentences = _split_sentences(text)
    selected = []
    total = 0

    for sentence in reversed(sentences):
        if selected and total + len(sentence) > max_chars:
            break

        selected.insert(0, sentence)
        total += len(sentence)

    return "".join(selected)

def apply_sentence_overlap(
    chunks: list[str],
    overlap: int,
) -> list[str]:
    if not chunks:
        return []
    result = [chunks[0]]
    for index in range(1, len(chunks)):
        previous = chunks[index - 1]
        current = chunks[index]


        previous=_trailing_sentences(chunks[index-1], overlap)
        current=chunks[index]
        result.append(previous+current)
    return result

_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
def _find_table_header(lines: list[str]) -> int:
    for index in range(len(lines) - 1):
        current = lines[index]
        next_line = lines[index + 1]


        if (
                current.lstrip().startswith("|")
                and _TABLE_SEP_RE.match(next_line)
                and "-" in next_line
        ):
            return index


    return -1
def is_table_block(text: str) -> bool:
    lines = [
        line
        for line in text.strip().splitlines()
        if line.strip()
    ]

    header_index = _find_table_header(lines)
    return header_index != -1

def split_table_rows(
    table_md: str,
    max_rows: int,
) -> list[str]:
    lines = [
        line
        for line in table_md.strip().splitlines()
        if line.strip()
    ]

    header_index = _find_table_header(lines)

    if header_index == -1:
        return [table_md.strip()]

    preamble = lines[:header_index]
    header = lines[header_index]
    separator = lines[header_index + 1]
    rows = lines[header_index + 2:]

    result = []

    for start in range(0, len(rows), max_rows):
        group = rows[start:start + max_rows]

        if start == 0:
            block = [*preamble, header, separator, *group]
        else:
            block = [header, separator, *group]

        result.append("\n".join(block))

    return result


def split_body(text: str, chunk_size: int, overlap: int, table_max_rows: int) -> list[str]:
    """混合正文先分出表格，避免把表后说明当数据行。"""
    if chunk_size < 1 or overlap < 0 or table_max_rows < 1:
        raise ValueError("分块大小/表格行数必须为正，重叠不能为负")
    lines = text.splitlines()
    pieces, prose = [], []
    def flush_prose():
        if prose:
            parts = recursive_split("\n".join(prose), chunk_size)
            pieces.extend(apply_sentence_overlap(parts, overlap))
            prose.clear()
    index = 0
    while index < len(lines):
        if index + 1 < len(lines) and _find_table_header(lines[index:index + 2]) == 0:
            flush_prose()
            end = index + 2
            while end < len(lines) and lines[end].lstrip().startswith("|"):
                end += 1
            pieces.extend(split_table_rows("\n".join(lines[index:end]), table_max_rows))
            index = end
        else:
            prose.append(lines[index])
            index += 1
    flush_prose()
    return pieces
