# -*- coding: utf-8 -*-
"""scan_dewarp：格线拉直的采样、拟合与重采样。没有 numpy 时跳过。"""

import unittest

from PIL import Image, ImageDraw

try:
    import numpy as np
    from ulpp import scan_dewarp as dw
    HAS_NUMPY = True
except ImportError:  # pragma: no cover - 可选依赖
    np = None
    dw = None
    HAS_NUMPY = False


def grid_image(size=400, pitch=20, width=2):
    img = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(img)
    for pos in range(10, size, pitch):
        draw.line([(pos, 0), (pos, size - 1)], fill=0, width=width)
        draw.line([(0, pos), (size - 1, pos)], fill=0, width=width)
    return img


@unittest.skipUnless(HAS_NUMPY, "需要 numpy")
class TestDewarp(unittest.TestCase):
    def test_darkness(self):
        arr = dw._darkness(grid_image(80, 20))
        self.assertEqual(arr.shape, (80, 80))
        self.assertGreaterEqual(float(arr.min()), 0.0)

    def test_lattice_finds_period(self):
        xs = np.arange(400)
        profile = np.exp(-((xs % 20 - 5) ** 2) / 8.0)
        period, phase = dw._lattice(profile, 15, 25)
        self.assertAlmostEqual(period, 20.0, delta=1.5)
        self.assertEqual(phase, 0.0)

    def test_fold_finds_phase(self):
        profile = np.array([1.0 if i % 20 == 5 else 0.0 for i in range(400)])
        phase, peak = dw._fold(profile, 20.0)
        self.assertGreater(peak, 0)
        self.assertGreaterEqual(phase, 0.0)
        self.assertLess(phase, 20.0)

    def test_sample_lines_axis0_and_axis1(self):
        img = grid_image(240, 20)
        dark = dw._darkness(img)
        expected = list(range(10, 230, 20))
        sx = dw._sample_lines_at(dark, expected, 0, 4.0)
        sy = dw._sample_lines_at(dark, expected, 1, 4.0)
        self.assertGreater(len(sx), 20)
        self.assertGreater(len(sy), 20)
        self.assertEqual(sx.shape[1], 3)

    def test_sample_lines_empty_and_edges(self):
        dark = dw._darkness(grid_image(80, 20))
        self.assertEqual(dw._sample_lines_at(dark, [], 0, 4.0).shape, (0, 3))
        # 贴边的线被跳过
        self.assertEqual(dw._sample_lines_at(dark, [0], 0, 4.0).shape, (0, 3))

    def test_sample_lines_tiny_and_flat(self):
        tiny = np.zeros((10, 10), dtype=np.float32)
        self.assertEqual(dw._sample_lines_at(tiny, [5], 0, 2.0).shape, (0, 3))
        flat = np.zeros((120, 120), dtype=np.float32)
        self.assertEqual(dw._sample_lines_at(flat, [60], 0, 4.0).shape, (0, 3))

    def test_fit_field_needs_enough_points(self):
        self.assertIsNone(dw._fit_field(np.zeros((3, 3)), (100, 100), 0))

    def test_fit_field_returns_coefficients(self):
        samples = np.array([[10 + i, 20 + i, 0.5] for i in range(30)], dtype=np.float32)
        coef = dw._fit_field(samples, (200, 300), 0)
        self.assertEqual(len(coef), dw.FEATURES)

    def test_apply_field_both_and_single(self):
        img = grid_image(120, 20)
        coef = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        self.assertEqual(dw._apply_field(img, None, None).size, img.size)
        self.assertEqual(dw._apply_field(img, coef, None).size, img.size)
        self.assertEqual(dw._apply_field(img, None, coef).size, img.size)
        self.assertEqual(dw._apply_field(img, coef, coef).size, img.size)

    def test_refine_grid_runs_and_improves(self):
        img = grid_image(400, 20)
        expected = list(range(10, 400, 20))
        out, stats = dw.refine_grid(img, expected, expected, iterations=2)
        self.assertEqual(out.size, img.size)
        self.assertTrue(stats["before"])

    def test_refine_grid_breaks_when_too_few_lines(self):
        img = grid_image(100, 100)
        out, stats = dw.refine_grid(img, [50], [50], iterations=2)
        self.assertEqual(out.size, img.size)
        self.assertEqual(stats["before"], [])

    def test_refine_grid_with_period_hint(self):
        img = grid_image(200, 20)
        expected = list(range(10, 200, 20))
        out, stats = dw.refine_grid(img, expected, expected, iterations=1,
                                    period_hint=20.0)
        self.assertEqual(out.size, img.size)


if __name__ == "__main__":
    unittest.main()
