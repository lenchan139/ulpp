# -*- coding: utf-8 -*-
"""scan 的取样、拟合、告警与命令行分支。"""

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ulpp import scan
from ulpp.scan import (
    Measurement,
    _band_width_mm,
    _fold_fit,
    _lattice_fit,
    _load,
    _period_autocorr,
    describe,
    measure_file,
    measure_image,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def measurement(**overrides):
    data = dict(
        page_w_mm=210.0, page_h_mm=297.0, mm_per_px=1.0,
        pitch_x_mm=20.0, pitch_y_mm=20.0, first_x_mm=10.0, first_y_mm=10.0,
        cols=5, rows=5, cell_w_mm=18.0, cell_h_mm=18.0,
        rotation_deg=0.0, confidence=0.9, dpi=300.0,
    )
    data.update(overrides)
    return Measurement(**data)


class ScanEdgeBase(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(ROOT, f"ulpp_scan_edge_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def path(self, name):
        return os.path.join(self.dir, name)


class TestMeasurement(unittest.TestCase):
    def test_to_dict_and_ok(self):
        m = measurement()
        self.assertIn("pitch_x_mm", m.to_dict())
        self.assertTrue(m.ok)
        self.assertFalse(measurement(confidence=0.1).ok)
        self.assertFalse(measurement(warnings=("fail: bad",)).ok)

    def test_describe(self):
        text = describe(measurement(warnings=("note",)))
        self.assertIn("格阵", text)
        self.assertIn("note", text)


class TestLoad(ScanEdgeBase):
    def test_png_without_dpi(self):
        path = self.path("plain.png")
        Image.new("L", (60, 80), 200).save(path)
        img, w, h, dpi, warnings = _load(path)
        self.assertEqual(img.size, (60, 80))
        self.assertEqual(dpi, scan.DEFAULT_DPI)
        self.assertTrue(any("no-dpi" in w for w in warnings))

    def test_png_with_dpi(self):
        path = self.path("dpi.png")
        Image.new("L", (60, 80), 200).save(path, dpi=(150, 150))
        img, w, h, dpi, warnings = _load(path)
        self.assertAlmostEqual(dpi, 150.0, places=1)
        self.assertEqual(warnings, [])

    def test_pdf_with_image(self):
        path = self.path("scan.pdf")
        Image.new("L", (100, 140), 250).save(path, "PDF")
        img, w, h, dpi, warnings = _load(path)
        self.assertEqual(img.mode, "L")
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)
        self.assertGreater(dpi, 0)

    def test_pdf_without_image(self):
        from pypdf import PdfWriter
        path = self.path("vector.pdf")
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with open(path, "wb") as fh:
            writer.write(fh)
        with self.assertRaises(ValueError):
            _load(path)


class TestSignals(unittest.TestCase):
    def test_period_autocorr_range_empty(self):
        self.assertIsNone(_period_autocorr([0.0] * 40, pmin=100, pmax=1))

    def test_period_autocorr_flat_profile(self):
        self.assertIsNone(_period_autocorr([0.0] * 200, pmin=10, pmax=30))

    def test_period_autocorr_finds_period(self):
        prof = [1.0 if i % 20 == 0 else 0.0 for i in range(400)]
        self.assertAlmostEqual(_period_autocorr(prof, 15, 25), 20.0, delta=1.0)

    def test_lattice_fit_short_or_small(self):
        self.assertIsNone(_lattice_fit([0.0] * 10, coarse_period=100))
        self.assertIsNone(_lattice_fit([0.0] * 100, coarse_period=2))

    def test_lattice_fit_zero_profile(self):
        result = _lattice_fit([0.0] * 200, coarse_period=20)
        self.assertEqual(result["count"], 0)

    def test_lattice_fit_finds_centres(self):
        prof = [1.0 if i % 20 == 5 else 0.0 for i in range(400)]
        result = _lattice_fit(prof, coarse_period=20)
        self.assertGreaterEqual(result["count"], 2)
        self.assertAlmostEqual(result["period"], 20.0, delta=1.0)

    def test_fold_fit_none_for_short_profile(self):
        self.assertIsNone(_fold_fit([0.0] * 20, 5, 10))

    def test_fold_fit_returns_lattice(self):
        prof = [1.0 if i % 20 == 5 else 0.0 for i in range(240)]
        result = _fold_fit(prof, 15, 25)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["period"], 20.0, delta=1.0)
        self.assertGreaterEqual(result["count"], 3)
        self.assertEqual(len(result["centres"]), result["count"])

    def test_band_width_edges(self):
        self.assertIsNone(_band_width_mm([1.0], [], 1.0, 0.3, 5.0))
        self.assertIsNone(_band_width_mm([0.0] * 10, [5], 1.0, 0.3, 5.0))
        self.assertIsNone(_band_width_mm([1.0] * 10, [-5], 1.0, 0.3, 5.0))
        width = _band_width_mm([0.0, 0.0, 4.0, 4.0, 0.0, 0.0], [2.5], 1.0, 0.3, 5.0)
        self.assertGreaterEqual(width, 0.3)


class TestMeasureImage(ScanEdgeBase):
    def lattice(self, centres=(10, 30, 50, 70), period=20.0):
        return {"period": period, "phase": 0.0,
                "centres": list(centres), "residuals": [0.0] * len(centres),
                "count": len(centres)}

    def run_measure(self, col=None, row=None, page=(210.0, 297.0), size=(200, 200),
                    expect_cols=None, expect_rows=None, band="__default__"):
        img = Image.new("L", size, 255)
        col = col if col is not None else self.lattice()
        row = row if row is not None else self.lattice()
        with patch.object(scan, "_estimate_skew", return_value=0.0), \
                patch.object(scan, "_period_autocorr", return_value=20.0), \
                patch.object(scan, "_lattice_fit", side_effect=[col, row]):
            if band == "__default__":
                return measure_image(img, page[0], page[1], 300.0,
                                     expect_cols=expect_cols, expect_rows=expect_rows)
            with patch.object(scan, "_band_width_mm", return_value=band):
                return measure_image(img, page[0], page[1], 300.0,
                                     expect_cols=expect_cols, expect_rows=expect_rows)

    def test_basic(self):
        m = self.run_measure()
        self.assertGreater(m.pitch_x_mm, 0)
        self.assertEqual(m.dpi, 300.0)
        self.assertTrue(m.ok)

    def test_lattice_failure_raises(self):
        with patch.object(scan, "_estimate_skew", return_value=0.0), \
                patch.object(scan, "_period_autocorr", return_value=20.0), \
                patch.object(scan, "_lattice_fit", return_value=None):
            with self.assertRaises(ValueError):
                measure_image(Image.new("L", (200, 200), 255), 210.0, 297.0, 300.0)

    def test_no_period_raises(self):
        with patch.object(scan, "_estimate_skew", return_value=0.0), \
                patch.object(scan, "_period_autocorr", return_value=None):
            with self.assertRaises(ValueError):
                measure_image(Image.new("L", (200, 200), 255), 210.0, 297.0, 300.0)

    def test_count_warning_with_expect_cols(self):
        m = self.run_measure(expect_cols=8, expect_rows=5)
        self.assertTrue(any(w.startswith("count-x") for w in m.warnings))

    def test_few_lines_warnings(self):
        one = self.lattice(centres=(10,))
        m = self.run_measure(col=one, row=one, expect_cols=5, expect_rows=5)
        self.assertTrue(any(w.startswith("few-cols") for w in m.warnings))
        self.assertTrue(any(w.startswith("few-rows") for w in m.warnings))

    def test_fail_warning_when_too_few_lines(self):
        one = self.lattice(centres=(10,))
        m = self.run_measure(col=one, row=one, expect_cols=20, expect_rows=20)
        self.assertTrue(any(w.startswith("fail:") for w in m.warnings))

    def test_residual_and_size_warnings(self):
        bad = self.lattice()
        bad["residuals"] = [10.0, 10.0, 10.0, 10.0]
        m = self.run_measure(col=bad, row=bad, page=(300.0, 400.0))
        self.assertTrue(any(w.startswith("resid:") for w in m.warnings))
        self.assertTrue(any(w.startswith("size:") for w in m.warnings))

    def test_seam_fallback_warning(self):
        m = self.run_measure(band=None)
        self.assertTrue(any(w.startswith("seam:") for w in m.warnings))
        self.assertEqual(m.cell_w_mm, round(m.pitch_x_mm - 2.0, 2))

    def test_small_image_skips_crop(self):
        m = self.run_measure(size=(30, 30), page=(20.0, 20.0))
        self.assertGreater(m.mm_per_px, 0)


class TestMain(unittest.TestCase):
    def test_no_args_returns_usage(self):
        self.assertEqual(scan.main([]), 2)

    def test_main_success_and_failure(self):
        good = measurement()
        bad = measurement(confidence=0.1, warnings=("fail: x",))
        calls = []

        def fake(path):
            calls.append(path)
            if path == "bad":
                raise RuntimeError("nope")
            return bad if path == "weak" else good

        with patch.object(scan, "measure_file", side_effect=fake):
            rc = scan.main(["good", "weak", "bad"])
        self.assertEqual(rc, 1)
        self.assertEqual(calls, ["good", "weak", "bad"])

    def test_measure_file_delegates(self):
        img = Image.new("L", (200, 200), 255)
        fake = measurement()
        with patch.object(scan, "_load",
                          return_value=(img, 210.0, 297.0, 300.0, [])), \
                patch.object(scan, "measure_image", return_value=fake) as m:
            self.assertIs(measure_file("x.png"), fake)
        self.assertTrue(m.called)


if __name__ == "__main__":
    unittest.main()
