# -*- coding: utf-8 -*-
"""parser 的边界分支：告警路径、格线判定、字段拼接与多文件解析。"""

import os
import unittest
from unittest.mock import patch

from ulpp.parser import (
    Card,
    PageCards,
    PdfCards,
    _bbox_union,
    _card_lines,
    _grid_positions,
    _is_rule,
    _split_merged_anchors,
    parse_card_text,
    parse_many,
    parse_page,
    parse_pdf,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), "examples", "sample.pdf")


def word(text, x0=50.0, top=50.0, width=None, bottom=None):
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + (len(text) * 8.0 if width is None else width),
        "top": top,
        "bottom": top + 10.0 if bottom is None else bottom,
    }


class FakePage:
    def __init__(self, words, width=400.0, height=400.0,
                 rects=(), lines=(), curves=()):
        self._words = list(words)
        self.width = width
        self.height = height
        self.rects = list(rects)
        self.lines = list(lines)
        self.curves = list(curves)

    def extract_words(self, **kwargs):
        return [dict(w) for w in self._words]


class TestDataclasses(unittest.TestCase):
    def test_card_label_falls_back(self):
        self.assertEqual(Card(name="").label, "?")
        self.assertEqual(Card(name="A").label, "A")

    def test_page_len_and_stickers(self):
        cards = [Card(qty=2), Card(qty=3)]
        page = PageCards(page_no=1, cards=cards)
        self.assertEqual(len(page), 2)
        self.assertEqual(PdfCards("x", 1, [page]).stickers, 5)


class TestHelpers(unittest.TestCase):
    def test_bbox_union_empty_and_union(self):
        self.assertIsNone(_bbox_union([]))
        self.assertEqual(_bbox_union([(1, 2, 3, 4), (0, 5, 2, 9)]),
                         (0, 2, 3, 9))

    def test_grid_positions_finds_lines(self):
        v, h = _grid_positions([(10, 0, 11, 400), (0, 20, 400, 21),
                                (5, 5, 50, 50)], 400, 400)
        self.assertEqual(v, [10.5])
        self.assertEqual(h, [20.5])

    def test_is_rule_all_variants(self):
        cell = (0, 0, 100, 100)
        self.assertTrue(_is_rule((0, 0, 100, 1), cell))
        self.assertTrue(_is_rule((0, 0, 1, 100), cell))
        self.assertTrue(_is_rule((0, 10, 60, 11.5), cell, hgrid=[10.5]))
        self.assertTrue(_is_rule((10, 0, 11.5, 60), cell, vgrid=[10.5]))
        self.assertFalse(_is_rule((10, 10, 20, 20), cell))
        self.assertFalse(_is_rule((10, 0, 11.5, 60), cell))

    def test_card_lines_missing_anchor(self):
        lines = [{"top": 0, "bottom": 10, "x0": 0, "x1": 10, "text": "x",
                  "words": [word("x")]}]
        self.assertEqual(_card_lines(lines, word("nope")), [])

    def test_card_lines_color_continuation_and_next_card_break(self):
        w_anchor = word("文件名称: A", top=0)
        w_color = word("颜色: 红", top=12)
        w_more = word("色很长", top=24)
        w_next = word("文件名称: B", top=40)
        lines = [
            {"top": 0, "bottom": 10, "x0": 50, "x1": 150,
             "text": "文件名称: A", "words": [w_anchor]},
            {"top": 12, "bottom": 22, "x0": 50, "x1": 130,
             "text": "颜色: 红", "words": [w_color]},
            {"top": 24, "bottom": 34, "x0": 50, "x1": 120,
             "text": "色很长", "words": [w_more]},
            {"top": 40, "bottom": 50, "x0": 50, "x1": 150,
             "text": "文件名称: B", "words": [w_next]},
        ]
        picked = _card_lines(lines, w_anchor)
        self.assertEqual([t for t, _ in picked],
                         ["文件名称: A", "颜色: 红", "色很长"])

    def test_split_merged_anchors(self):
        merged = word("文件名称:A文件名称:B")
        kept, anchors = _split_merged_anchors([merged])
        self.assertEqual(len(anchors), 2)
        self.assertEqual(len(kept), 2)
        self.assertTrue(anchors[0]["text"].startswith("文件名称"))

    def test_parse_card_text_all_fields(self):
        fields = parse_card_text("文件名称: 甲\n尺寸: 10×20\n序号: 7\n"
                                 "数量: 3\n颜色: 蓝\n图号: DWG-9")
        self.assertEqual(fields["name"], "甲")
        self.assertEqual(fields["size"], "10×20")
        self.assertEqual(fields["seq"], 7)
        self.assertEqual(fields["qty"], 3)
        self.assertEqual(fields["color"], "蓝")
        self.assertEqual(fields["dwg_no"], "DWG-9")


class TestParsePageWarnings(unittest.TestCase):
    def test_no_anchor_warning(self):
        res = parse_page(FakePage([word("无关文字")]), 2, 400.0)
        self.assertEqual(res.cards, [])
        self.assertTrue(res.warnings)
        self.assertEqual((res.cols, res.rows), (0, 0))

    def test_no_fields_warning(self):
        # 行首有邻格溢出的字，字段标签不在行首 → 收不到字段
        res = parse_page(FakePage([word("溢文件名称")]), 1, 400.0)
        self.assertEqual(res.cards, [])
        self.assertTrue(any("字段" in w or "field" in w.lower() for w in res.warnings))

    def test_no_name_warning(self):
        res = parse_page(FakePage([word("文件名称:")]), 1, 400.0)
        self.assertEqual(res.cards, [])
        self.assertTrue(res.warnings)

    def test_no_content_warning(self):
        with patch("ulpp.parser._bbox_union", return_value=None):
            res = parse_page(FakePage([word("文件名称: A")]), 1, 400.0)
        self.assertEqual(res.cards, [])
        self.assertTrue(res.warnings)

    def test_bad_box_warning(self):
        with patch("ulpp.parser._bbox_union", return_value=(50, 50, 52, 52)):
            res = parse_page(FakePage([word("文件名称: A")]), 1, 400.0)
        self.assertEqual(res.cards, [])
        self.assertTrue(res.warnings)

    def test_y1_clamped_to_cell(self):
        # 文字的 bottom 超出格底 → 裁剪框要贴回格线内侧
        words = [word("文件名称: A", top=50, bottom=60),
                 word("备注很长", top=380, bottom=399)]
        res = parse_page(FakePage(words), 1, 400.0)
        self.assertEqual(len(res.cards), 1)
        x0, y0, x1, y1 = res.cards[0].clip_pdf
        self.assertGreater(x1, x0)
        self.assertLessEqual(y1, 400.0 - 50 + 1e-6)

    def test_frame_drawing_is_ignored(self):
        frame = {"x0": 50, "top": 50, "x1": 400, "bottom": 400}
        res = parse_page(FakePage([word("文件名称: A")], rects=[frame]), 1, 400.0)
        self.assertEqual(len(res.cards), 1)

    def test_vertical_and_horizontal_grid_lines(self):
        drawings = [
            {"x0": 50, "top": 0, "x1": 51, "bottom": 400},
            {"x0": 0, "top": 50, "x1": 400, "bottom": 51},
        ]
        res = parse_page(FakePage([word("文件名称: A")], lines=drawings), 1, 400.0)
        self.assertEqual(len(res.cards), 1)


@unittest.skipUnless(os.path.exists(SAMPLE), "缺少 examples/sample.pdf")
class TestParsePdfProgress(unittest.TestCase):
    def test_progress_callback(self):
        calls = []
        parsed = parse_pdf(SAMPLE, progress=lambda done, total: calls.append((done, total)))
        self.assertTrue(parsed.pages)
        self.assertEqual(calls[-1], (len(parsed.pages), len(parsed.pages)))

    def test_parse_many_and_first_page(self):
        calls = []
        out = parse_many([SAMPLE, SAMPLE], first_page_only=True,
                         progress=lambda done, total: calls.append((done, total)))
        self.assertEqual(len(out), 2)
        self.assertTrue(all(len(p.pages) <= 1 for p in out))
        self.assertTrue(calls)


if __name__ == "__main__":
    unittest.main()
