# -*- coding: utf-8 -*-
"""textlabel / templates / config / presets / calibration 的边角分支。"""

import json
import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from ulpp import templates
from ulpp.calibration import _font
from ulpp.config import GridSpec
from ulpp.presets import PRESETS, _matches_title, match_grid
from ulpp.templates import Template, TemplateStore, adjusted
from ulpp.textlabel import (
    TextItem,
    _fit,
    _wrap,
    find_cjk_font,
    parse_text_block,
    render_items,
    render_text_label,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class TempDirMixin(object):
    def setUp(self):
        self.dir = os.path.join(ROOT, f"ulpp_misc_edge_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)


class FakeDraw:
    def textlength(self, text, font=None):
        return len(text) * 10.0


class TestTextLabelEdges(unittest.TestCase):
    def test_text_item_label(self):
        self.assertEqual(TextItem("a\nb").label, "a b")

    def test_suffix_only_line_is_skipped(self):
        self.assertEqual(parse_text_block("|2"), [])

    def test_find_font_explicit_missing(self):
        result = find_cjk_font("/definitely/not/a/font.ttf")
        self.assertTrue(result is None or os.path.exists(result))

    def test_find_font_none_available(self):
        with patch("ulpp.textlabel.CJK_FONT_CANDIDATES", []):
            self.assertIsNone(find_cjk_font())

    def test_tokenizer_cjk_after_ascii(self):
        # _tokenize 通过 _wrap 间接覆盖：英文后紧跟中文时先收尾再单字成 token
        lines = _wrap("ab中文", None, 10000, FakeDraw())
        self.assertEqual(len(lines), 1)

    def test_wrap_blank_paragraph(self):
        lines = _wrap("a\n\nb", None, 10000, FakeDraw())
        self.assertEqual(lines, ["a", "", "b"])

    def test_wrap_moves_orphan_character(self):
        lines = _wrap("abcd\ne", None, 10000, FakeDraw())
        self.assertEqual(lines, ["abc", "de"])

    def test_fit_bad_font_falls_back_to_default(self):
        font, lines, px, line_h, total_h = _fit(
            "AB", "/definitely/not/a/font.ttf", 400, 400, 20)
        self.assertTrue(lines)
        self.assertGreater(px, 0)

    def test_fit_never_fits_uses_minimum(self):
        font, lines, px, line_h, total_h = _fit(
            "long text", None, 4, 4, max_pt=10, min_pt=100)
        self.assertGreaterEqual(px, 6)
        self.assertTrue(lines)

    def test_render_alignment_and_items(self):
        left = render_text_label("AB", 200, 80, align="left")
        right = render_text_label("AB", 200, 80, align="right")
        self.assertEqual(left.size, (200, 80))
        self.assertNotEqual(list(left.getdata()), list(right.getdata()))
        images = render_items([TextItem("A"), TextItem("B")], 120, 60, align="center")
        self.assertEqual(len(images), 2)

    def test_render_fixed_size(self):
        img = render_text_label("固定字号", 240, 120, fixed_pt=20)
        self.assertEqual(img.size, (240, 120))


class TestConfigPresets(TempDirMixin, unittest.TestCase):
    def test_grid_load_save_roundtrip(self):
        path = os.path.join(self.dir, "grid.json")
        grid = GridSpec(cols=3, rows=4, margin_left=2.5)
        grid.save(path)
        loaded = GridSpec.load(path)
        self.assertEqual(loaded, grid)

    def test_from_dict_ignores_unknown_keys(self):
        grid = GridSpec.from_dict({"cols": 2, "unknown": 1})
        self.assertEqual(grid.cols, 2)

    def test_matches_title_empty(self):
        self.assertFalse(_matches_title(PRESETS[0], "   "))

    def test_match_grid_none(self):
        self.assertIsNone(match_grid(GridSpec(cols=7, rows=7, cell_w=1, cell_h=1)))


class TestTemplates(TempDirMixin, unittest.TestCase):
    def base(self):
        return Template(
            id="t1", name="纸", cols=2, rows=2,
            cell_w_mm=40, cell_h_mm=30, pitch_x_mm=42, pitch_y_mm=32,
        )

    def test_count_and_label(self):
        t = self.base()
        self.assertEqual(t.count, 4)
        self.assertIn("2×2", t.label())

    def test_state_dir_override(self):
        with patch.dict(os.environ, {"ULPP_STATE_DIR": self.dir}, clear=True):
            self.assertEqual(templates._state_dir(), Path(self.dir))
        with patch.dict(os.environ, {"APPDATA": self.dir}, clear=True):
            self.assertEqual(templates._state_dir(), Path(self.dir) / "ulpp")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(templates._state_dir(), Path.home() / ".ulpp")

    def test_adjusted_invalid_value(self):
        with self.assertRaises(ValueError):
            adjusted(self.base(), cols="bad")

    def test_adjusted_valid(self):
        t = adjusted(self.base(), cols=3, dx_mm=1.0, dy_mm=-1.0, name="新纸")
        self.assertEqual((t.cols, t.name), (3, "新纸"))
        self.assertAlmostEqual(t.origin_x_mm, 1.0)
        self.assertAlmostEqual(t.origin_y_mm, -1.0)

    def test_store_path_variants(self):
        by_path = TemplateStore(path=Path(self.dir) / "a.json")
        self.assertEqual(by_path.path, Path(self.dir) / "a.json")
        by_dir = TemplateStore(directory=Path(self.dir))
        self.assertEqual(by_dir.path, Path(self.dir) / templates.STATE_FILE)
        with patch.dict(os.environ, {"ULPP_STATE_DIR": self.dir}, clear=True):
            by_env = TemplateStore()
        self.assertEqual(by_env.path, Path(self.dir) / templates.STATE_FILE)

    def test_get_missing(self):
        store = TemplateStore(path=Path(self.dir) / "t.json")
        self.assertIsNone(store.get("missing"))

    def test_load_bad_json_and_non_list(self):
        path = Path(self.dir) / "bad.json"
        path.write_text("{oops", encoding="utf-8")
        self.assertEqual(TemplateStore(path=path).items, [])
        path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        self.assertEqual(TemplateStore(path=path).items, [])

    def test_save_cleans_tmp_on_replace_failure(self):
        store = TemplateStore(path=Path(self.dir) / "t.json")
        store.items = [self.base()]
        with patch.object(templates.os, "replace", side_effect=OSError("boom")):
            self.assertIsNone(store.save())
        self.assertTrue(store.last_error)
        leftovers = [p for p in Path(self.dir).glob(".templates.*")]
        self.assertEqual(leftovers, [])

    def test_save_and_upsert_remove(self):
        store = TemplateStore(path=Path(self.dir) / "t.json")
        one = self.base()
        store.upsert(one)
        self.assertEqual(len(store), 1)
        updated = adjusted(one, name="改名")
        store.upsert(updated)
        self.assertEqual(len(store), 1)
        self.assertEqual(store.get("t1").name, "改名")
        self.assertTrue(TemplateStore(path=store.path) .items)
        self.assertTrue(store.remove("t1"))
        self.assertFalse(store.remove("t1"))


class TestCalibrationFont(unittest.TestCase):
    def test_font_without_cjk_uses_default(self):
        with patch("ulpp.calibration.find_cjk_font", return_value=None):
            font = _font(12)
        self.assertIsNotNone(font)


if __name__ == "__main__":
    unittest.main()
