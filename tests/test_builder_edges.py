# -*- coding: utf-8 -*-
"""builder 的边界分支：旋转页、空内容、无效格号/偏移、进度与日志回调。"""

import os
import shutil
import unittest
import uuid

from pypdf import PdfReader, PdfWriter

from ulpp.builder import (
    ImageSticker,
    Sticker,
    TextSticker,
    _placement,
    build_all,
    build_partial_all,
    build_partial_pdf,
    build_pdf,
)
from ulpp.config import GridSpec
from ulpp.parser import Card
from ulpp.textlabel import TextItem

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLE = os.path.join(ROOT, "examples", "sample.pdf")


class BuilderEdgeBase(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(ROOT, f"ulpp_builder_edge_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def path(self, name):
        return os.path.join(self.dir, name)

    def make_pdf(self, name="src.pdf", pages=1, rotate=0):
        path = self.path(name)
        writer = PdfWriter()
        for _ in range(pages):
            page = writer.add_blank_page(width=120, height=90)
            if rotate:
                page.rotate(rotate)
        with open(path, "wb") as fh:
            writer.write(fh)
        return path

    @staticmethod
    def card(clip=(10, 10, 70, 60), qty=1):
        return Card(name="EDGE", seq=3, qty=qty, clip_pdf=clip,
                    cell_pdf=(0, 0, 100, 100))

    def sticker(self, pdf=None, card=None):
        return Sticker(pdf_path=pdf or self.make_pdf(), page_index=0, page_no=1,
                       card=card or self.card(), copy_no=1)


class TestStickerTotals(unittest.TestCase):
    def test_total_copies_properties(self):
        self.assertEqual(self.sticker_for(4).total_copies, 4)
        self.assertEqual(TextSticker(TextItem("a", copies=3)).total_copies, 3)
        self.assertEqual(ImageSticker("x.png").total_copies, 1)

    @staticmethod
    def sticker_for(qty):
        return Sticker(pdf_path="x.pdf", page_index=0, page_no=1,
                       card=Card(qty=qty), copy_no=1)


class TestPlacement(BuilderEdgeBase):
    def test_zero_size_clip_returns_none(self):
        self.assertIsNone(_placement((10, 10, 10, 60), (0, 0, 100, 100), 2))

    def test_normal_clip_returns_geometry(self):
        placed = _placement((10, 10, 70, 60), (0, 0, 100, 100), 2)
        self.assertIsNotNone(placed)
        scale, tx, ty, target = placed
        self.assertGreater(scale, 0)
        self.assertEqual(len(target), 4)


class TestBuildPdfEdges(BuilderEdgeBase):
    def test_rotated_source_page(self):
        pdf = self.make_pdf(rotate=90)
        out = self.path("rotated.pdf")
        manifest = build_pdf([self.sticker(pdf)], GridSpec(cols=2, rows=2), out)
        self.assertEqual(len(manifest), 1)
        self.assertTrue(os.path.isfile(out))

    def test_zero_clip_entry_is_skipped(self):
        out = self.path("skip.pdf")
        entry = self.sticker(card=self.card(clip=(10, 10, 10, 50)))
        manifest = build_pdf([entry], GridSpec(cols=2, rows=2), out)
        self.assertEqual(manifest, [])
        reader = PdfReader(out)
        self.assertEqual(len(reader.pages), 1)

    def test_text_uniform_and_progress(self):
        items = [TextItem("统一字号 A", copies=1, index=0),
                 TextItem("统一字号 B", copies=1, index=1)]
        entries = [TextSticker(i, copy_no=1) for i in items]
        calls = []
        out = self.path("uniform.pdf")
        manifest = build_pdf(entries, GridSpec(cols=2, rows=2), out,
                             text_uniform=True,
                             progress=lambda done, total: calls.append((done, total)))
        self.assertEqual(len(manifest), 2)
        self.assertEqual(calls, [(1, 1)])

    def test_image_sticker(self):
        from PIL import Image
        img = self.path("dot.png")
        Image.new("RGB", (30, 20), (200, 10, 10)).save(img)
        out = self.path("image.pdf")
        manifest = build_pdf([ImageSticker(img)], GridSpec(cols=2, rows=2), out)
        self.assertEqual(manifest[0]["kind"] != "", True)
        self.assertEqual(manifest[0]["name"], "dot")


class TestBuildAllEdges(BuilderEdgeBase):
    def test_empty_entries_raises(self):
        with self.assertRaises(ValueError):
            build_all([], GridSpec(cols=2, rows=2), self.dir)

    def test_progress_log_and_options(self):
        pdf = self.make_pdf()
        from ulpp.parser import PageCards, PdfCards
        cards = PdfCards(path=pdf, n_pages=1,
                         pages=[PageCards(page_no=1, cards=[self.card()])])
        logs = []
        stages = []
        outs = build_all(
            [cards], GridSpec(cols=2, rows=2), self.dir, base_name="edge",
            make_proof=True, make_csv=True,
            text_items=[TextItem("文字", copies=2)],
            progress=lambda stage, done, total: stages.append((stage, done, total)),
            log=logs.append,
        )
        self.assertEqual(set(outs), {"production", "proof", "manifest"})
        self.assertTrue(os.path.exists(outs["production"]))
        self.assertTrue(os.path.exists(outs["proof"]))
        self.assertTrue(os.path.exists(outs["manifest"]))
        self.assertIn("production", [s[0] for s in stages])
        self.assertIn("proof", [s[0] for s in stages])
        self.assertTrue(any(".csv" in line for line in logs))

    def test_without_proof_or_csv(self):
        pdf = self.make_pdf()
        from ulpp.parser import PageCards, PdfCards
        cards = PdfCards(path=pdf, n_pages=1,
                         pages=[PageCards(page_no=1, cards=[self.card()])])
        outs = build_all([cards], GridSpec(cols=2, rows=2), self.dir,
                         make_proof=False, make_csv=False)
        self.assertEqual(set(outs), {"production"})


class TestBuildPartialEdges(BuilderEdgeBase):
    def test_bad_slot_key(self):
        entry = TextSticker(TextItem("x"))
        with self.assertRaises(ValueError):
            build_partial_pdf({object(): entry}, GridSpec(), self.path("p.pdf"))

    def test_bad_offset(self):
        entry = TextSticker(TextItem("x"))
        with self.assertRaises(ValueError):
            build_partial_pdf({0: entry}, GridSpec(), self.path("p.pdf"),
                              offset_mm=("bad", "offset"))
        with self.assertRaises(ValueError):
            build_partial_pdf({0: entry}, GridSpec(), self.path("p.pdf"),
                              offset_mm=(1,))

    def test_out_of_range_slot(self):
        entry = TextSticker(TextItem("x"))
        with self.assertRaises(ValueError):
            build_partial_pdf({99: entry}, GridSpec(), self.path("p.pdf"))
        with self.assertRaises(ValueError):
            build_partial_pdf({-1: entry}, GridSpec(), self.path("p.pdf"))

    def test_zero_clip_skipped_but_pdf_written(self):
        entry = self.sticker(card=self.card(clip=(1, 1, 1, 5)))
        out = self.path("skip_partial.pdf")
        manifest = build_partial_pdf({0: entry}, GridSpec(), out)
        self.assertEqual(manifest, [])
        self.assertTrue(os.path.isfile(out))

    def test_progress_callback(self):
        calls = []
        out = self.path("partial.pdf")
        build_partial_pdf({0: TextSticker(TextItem("部分")), 3: TextSticker(TextItem("再"))},
                          GridSpec(), out,
                          progress=lambda done, total: calls.append((done, total)))
        self.assertEqual(calls, [(1, 1)])
        self.assertEqual(len(PdfReader(out).pages), 1)

    def test_offset_applied(self):
        out = self.path("offset.pdf")
        manifest = build_partial_pdf({0: TextSticker(TextItem("偏移"))}, GridSpec(),
                                     out, offset_mm=(1.0, -1.0))
        self.assertEqual(len(manifest), 1)

    def test_partial_all_empty_raises(self):
        with self.assertRaises(ValueError):
            build_partial_all({}, GridSpec(), self.dir)

    def test_partial_all_logs(self):
        logs = []
        outs = build_partial_all({0: TextSticker(TextItem("字"))}, GridSpec(),
                                 self.dir, base_name="partial", log=logs.append)
        self.assertEqual(set(outs), {"production", "manifest"})
        self.assertTrue(os.path.isfile(outs["manifest"]))
        self.assertTrue(any(".csv" in line for line in logs))

        logs2 = []
        outs2 = build_partial_all({1: TextSticker(TextItem("字"))}, GridSpec(),
                                  self.dir, base_name="partial2", make_csv=False,
                                  log=logs2.append)
        self.assertEqual(set(outs2), {"production"})
        self.assertEqual(len(logs2), 1)
        self.assertIn("1", logs2[0])


if __name__ == "__main__":
    unittest.main()
