"""app.kb.chunking / documents / dedup / sources：切块、建块、查重与材料清单。"""
import pytest

from app.kb import chunking, dedup, documents
from app.kb.sources import CONTENT_TYPES, KB_DIR, SOURCE_TYPES


def test_every_source_file_exists_and_has_known_type():
    for name, content_type in SOURCE_TYPES.items():
        assert (KB_DIR / name).is_file(), name
        assert content_type in CONTENT_TYPES


def test_split_sections_keeps_header_metadata():
    sections = chunking.split_sections("# 售后\n## 退货\n七天无理由。\n## 换货\n十五天。")
    assert [(s.metadata, s.page_content) for s in sections] == [
        ({"h1": "售后", "h2": "退货"}, "七天无理由。"),
        ({"h1": "售后", "h2": "换货"}, "十五天。"),
    ]


def test_recursive_split_prefers_cjk_sentence_ends():
    parts = chunking.recursive_split("第一句话。第二句话。第三句话。", chunk_size=6)
    assert parts == ["第一句话。", "第二句话。", "第三句话。"]
    assert all(len(p) <= 6 for p in parts)


class TestSentenceOverlap:
    def test_prepends_trailing_sentences_of_previous_chunk(self):
        assert chunking.apply_sentence_overlap(["甲。乙。", "丙。"], overlap=2) == ["甲。乙。", "乙。丙。"]

    def test_zero_overlap(self):
        assert chunking.apply_sentence_overlap(["甲。", "乙。"], 0) == ["甲。", "乙。"]

    def test_at_least_one_sentence_even_if_longer(self):
        assert chunking.apply_sentence_overlap(["很长的一句话。", "下一句。"], 2) == ["很长的一句话。", "很长的一句话。下一句。"]

    def test_empty(self):
        assert chunking.apply_sentence_overlap([], 5) == []


TABLE = "| 型号 | 保修 |\n| --- | --- |\n| A | 1年 |\n| B | 2年 |\n| C | 3年 |"


class TestTables:
    def test_detects_table(self):
        assert chunking.is_table_block(TABLE)
        assert chunking.is_table_block("说明：\n" + TABLE)
        assert not chunking.is_table_block("| 不是表格 |\n普通文字")
        assert not chunking.is_table_block("纯文本")

    def test_split_rows_repeats_header(self):
        pieces = chunking.split_table_rows("说明\n" + TABLE, max_rows=2)
        assert pieces == [
            "说明\n| 型号 | 保修 |\n| --- | --- |\n| A | 1年 |\n| B | 2年 |",
            "| 型号 | 保修 |\n| --- | --- |\n| C | 3年 |",
        ]

    def test_non_table_returned_whole(self):
        assert chunking.split_table_rows("  文本  ", 2) == ["文本"]


class TestSplitBody:
    def test_mixes_prose_and_table(self):
        body = "前言一句。\n" + TABLE + "\n结尾一句。"
        pieces = chunking.split_body(body, chunk_size=100, overlap=0, table_max_rows=2)
        assert pieces[0] == "前言一句。"
        assert pieces[1].startswith("| 型号 | 保修 |") and "| B | 2年 |" in pieces[1]
        assert pieces[2].startswith("| 型号 | 保修 |") and "| C | 3年 |" in pieces[2]
        assert pieces[3] == "结尾一句。"

    @pytest.mark.parametrize("args", [(0, 0, 1), (10, -1, 1), (10, 0, 0)])
    def test_rejects_invalid_sizes(self, args):
        with pytest.raises(ValueError):
            chunking.split_body("x", *args)


class TestBuildChunks:
    def test_paths_categories_and_key_clauses(self):
        md = "# 售后政策\n## 退货\n### 运费\n退货运费由买家承担。\n## 会员\n积分可抵现。\n"
        chunks = documents.build_chunks(md, content_type="policy")

        assert [(c.section_path, c.category, c.questions, c.is_key_clause) for c in chunks] == [
            ("售后政策 / 退货 / 运费", "售后政策 / 退货", "运费", 1),
            ("售后政策 / 会员", "售后政策", "会员", 0),
        ]
        assert all(c.content_type == "policy" for c in chunks)

    def test_single_level_and_no_header(self):
        top = documents.build_chunks("# FAQ\n内容", "faq")[0]
        assert (top.category, top.questions) == ("FAQ", "FAQ")
        bare = documents.build_chunks("没有标题的正文", "faq")[0]
        assert (bare.section_path, bare.category, bare.questions) == ("", "faq", "faq")

    def test_empty_sections_skipped(self):
        assert documents.build_chunks("# 空\n\n# 也空\n", "faq") == []

    def test_long_section_split_with_overlap(self):
        body = "。".join(f"第{i}条说明文字" for i in range(40)) + "。"
        chunks = documents.build_chunks(f"# 长\n{body}", "manual", chunk_size=50, overlap=10)
        assert len(chunks) > 1
        assert all(c.section_path == "长" for c in chunks)

    @pytest.mark.parametrize("name", sorted(SOURCE_TYPES))
    def test_real_sources_produce_chunks(self, name):
        chunks = documents.build_chunks((KB_DIR / name).read_text(encoding="utf-8"), SOURCE_TYPES[name])
        assert chunks
        assert all(c.answer.strip() for c in chunks)

    def test_is_key_only_checks_title_and_body_prefix(self):
        assert documents.is_key("退货", "") == 1
        assert documents.is_key("说明", "包邮") == 1
        assert documents.is_key("说明", "x" * 40 + "包邮") == 0


class TestDedup:
    @pytest.mark.parametrize(
        "raw,expected",
        [(" 能退货吗？ ", "能退货吗"), ("Can I Return_It?", "canireturnit"), ("！！", "")],
    )
    def test_normalize(self, raw, expected):
        assert dedup.normalize_question(raw) == expected

    def test_dedupe_against_existing_and_batch(self):
        class Item:
            def __init__(self, q):
                self.question = q

        items = [Item("能退吗"), Item("能 退 吗？"), Item("怎么换货"), Item("？"), Item("已有问题")]
        kept, discarded = dedup.dedupe(items, ["已有问题"])
        assert [i.question for i in kept] == ["能退吗", "怎么换货"]
        assert [i.question for i in discarded] == ["能 退 吗？", "？", "已有问题"]
