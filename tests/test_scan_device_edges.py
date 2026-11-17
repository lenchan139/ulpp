# -*- coding: utf-8 -*-
"""scan_board / scan_photo / scan_calib 的分支与几何小工具。"""

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from pypdf import PdfReader

from ulpp import scan_board, scan_photo

try:
    import cv2
    import numpy as np

    from ulpp import scan_calib
    from ulpp.scan_photo import _order_quad

    _HAS_CV = True
except Exception:  # pragma: no cover - 可选依赖
    cv2 = None
    np = None
    scan_calib = None
    _HAS_CV = False

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(ROOT, f"ulpp_board_edge_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_dot_positions_grid(self):
        dots = scan_board.dot_positions()
        self.assertEqual(len(dots), scan_board.COLS * scan_board.ROWS)
        self.assertEqual(dots[0], (scan_board.FIRST_X_MM, scan_board.FIRST_Y_MM))
        self.assertEqual(dots[1][0], scan_board.FIRST_X_MM + scan_board.SPACING_MM)

    def test_make_board_pdf(self):
        path = os.path.join(self.dir, "board.pdf")
        self.assertEqual(scan_board.make_board_pdf(path), path)
        reader = PdfReader(path)
        self.assertEqual(len(reader.pages), 1)
        page = reader.pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 595.28, delta=1)
        self.assertIn("标定板", str(reader.metadata.title))


class FakeCv:
    """让 find_paper_quad 走到"轮廓太小/不是四边形"的分支。"""

    COLOR_BGR2GRAY = 0
    THRESH_BINARY = 0
    THRESH_OTSU = 0
    MORPH_CLOSE = 0
    RETR_EXTERNAL = 0
    CHAIN_APPROX_SIMPLE = 0

    def __init__(self, contours, areas):
        self._contours = contours
        self._areas = areas

    def resize(self, img, *args, **kwargs):
        return img

    def cvtColor(self, img, *args, **kwargs):
        return img

    def GaussianBlur(self, img, *args, **kwargs):
        return img

    def threshold(self, img, *args, **kwargs):
        return 0, img

    def morphologyEx(self, img, *args, **kwargs):
        return img

    def Canny(self, img, *args, **kwargs):
        return img

    def dilate(self, img, *args, **kwargs):
        return img

    def findContours(self, mask, *args, **kwargs):
        return list(self._contours), None

    def contourArea(self, contour):
        return self._areas[id(contour)]

    def arcLength(self, contour, closed):
        return 4.0

    def approxPolyDP(self, contour, eps, closed):
        if self._areas[id(contour)] > 100:
            return np.zeros((5, 1, 2), dtype="int32")
        return np.zeros((4, 1, 2), dtype="int32")


@unittest.skipUnless(_HAS_CV, "没装 OpenCV")
class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(ROOT, f"ulpp_photo_edge_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_order_quad_handles_clockwise_input(self):
        points = [[0, 0], [0, 10], [10, 10], [10, 0]]
        quad = _order_quad(points)
        self.assertEqual(quad.shape, (4, 2))
        self.assertEqual(tuple(quad[0]), (0.0, 0.0))

    def test_find_paper_quad_skips_small_contours(self):
        small, big = object(), object()
        fake = FakeCv([small, big], {id(small): 1.0, id(big): 5000.0})
        blank = np.zeros((100, 100, 3), dtype=np.uint8)
        with patch.object(scan_photo, "_cv2", return_value=fake):
            with self.assertRaises(ValueError):
                scan_photo.find_paper_quad(blank)

    def test_measure_photo_unreadable_file(self):
        path = os.path.join(self.dir, "junk.jpg")
        with open(path, "wb") as fh:
            fh.write(b"not an image")
        with self.assertRaises(ValueError):
            scan_photo.measure_photo(path)

    def test_rectify_to_a4(self):
        bgr = np.full((100, 100, 3), 200, dtype=np.uint8)
        quad = np.array([[0, 0], [99, 0], [99, 99], [0, 99]], dtype="float32")
        page = scan_photo.rectify_to_a4(bgr, quad, dpi=30)
        self.assertEqual(page.mode, "L")
        self.assertGreater(page.width, 0)


@unittest.skipUnless(_HAS_CV, "没装 OpenCV")
class CalibUnitTests(unittest.TestCase):
    def test_assign_marks_filters_outside_and_offset(self):
        quad = np.array([[0, 0], [210, 0], [210, 297], [0, 297]], dtype="float32")
        marks = [(25, 30), (45, 50), (500, 500), (34, 30)]
        img_pts, mm_pts = scan_calib.assign_marks(marks, quad)
        self.assertEqual(img_pts.shape, (2, 2))
        self.assertEqual(mm_pts.shape, (2, 2))

    def test_undistort_points_identity(self):
        pts = np.array([[1.0, 2.0], [3.0, 4.0]], dtype="float32")
        out = scan_calib._undistort_points(pts, 0.0, 0.0, (5.0, 5.0), 10.0)
        np.testing.assert_allclose(out, pts, atol=1e-4)

    def test_estimate_distortion(self):
        mm = np.array([[25, 30], [45, 30], [25, 50], [45, 50]], dtype="float32")
        k1, k2, err = scan_calib.estimate_distortion(mm.copy(), mm.copy(), (100, 100, 3))
        self.assertAlmostEqual(k1, 0.0, delta=0.01)
        self.assertEqual(k2, 0.0)
        self.assertGreaterEqual(err, 0.0)

    def test_estimate_distortion_degenerate(self):
        pts = np.zeros((4, 2), dtype="float32")
        k1, k2, err = scan_calib.estimate_distortion(pts, pts, (100, 100, 3))
        self.assertEqual((k1, k2), (0.0, 0.0))
        self.assertEqual(err, float("inf"))

    def test_undo_distortion_noop_and_warp(self):
        bgr = np.full((40, 50, 3), 100, dtype=np.uint8)
        self.assertIs(scan_calib.undo_distortion(bgr, 0.0, 0.0), bgr)
        out = scan_calib.undo_distortion(bgr, 0.1, 0.0)
        self.assertEqual(out.shape, bgr.shape)

    def test_pick_sheet(self):
        quads = [
            np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype="float32"),
            np.array([[200, 0], [300, 0], [300, 100], [200, 100]], dtype="float32"),
            np.array([[400, 0], [600, 0], [600, 200], [400, 200]], dtype="float32"),
        ]
        marks = [(2, 2), (3, 3), (4, 4), (1, 4)]
        best = scan_calib._pick_sheet(quads, marks, board_area=10000.0)
        self.assertIsNotNone(best)
        self.assertEqual(best[1][0], 300)

    def test_cluster_1d(self):
        groups = scan_calib._cluster_1d(np.array([1.0, 1.2, 5.0, 9.0, 9.1]), 0.5)
        self.assertEqual(len(groups), 3)
        self.assertEqual(len(groups[0][1]), 2)

    def test_filter_grid_marks_small_and_extra_corners(self):
        few = scan_calib._filter_grid_marks([(1, 2), (3, 4)])
        self.assertEqual(len(few), 2)
        pts = [(25 + 20 * c, 30 + 20 * r) for r in range(13) for c in range(9)]
        pts += [(15, 30), (195, 30)]
        filtered = scan_calib._filter_grid_marks(pts)
        self.assertLess(len(filtered), len(pts))

    def test_homography_from_marks(self):
        pts = [(25 + 20 * c, 30 + 20 * r) for r in range(13) for c in range(9)]
        matrix, (img_pts, mm_pts) = scan_calib._homography_from_marks(pts)
        self.assertEqual(matrix.shape, (3, 3))
        self.assertGreaterEqual(len(img_pts), 8)
        self.assertEqual(img_pts.shape, mm_pts.shape)

    def test_homography_needs_enough_marks(self):
        with self.assertRaises(ValueError):
            scan_calib._homography_from_marks([(1, 1), (2, 2)])

    def test_homography_marks_off_grid(self):
        pts = [(1000 + i * 37, 2000 + i * 53) for i in range(12)]
        with self.assertRaises(ValueError):
            scan_calib._homography_from_marks(pts)

    def test_warp_to_mm(self):
        bgr = np.full((60, 40, 3), 200, dtype=np.uint8)
        matrix = np.eye(3, dtype="float64")
        warped, origin, px_per_mm = scan_calib._warp_to_mm(bgr, matrix, px_per_mm=2.0)
        self.assertEqual(warped.shape[2], 3)
        self.assertEqual(px_per_mm, 2.0)
        self.assertEqual(len(origin), 2)

    def test_find_sheet_region_and_warp(self):
        px = 4.0
        canvas = np.full((int(400 * px), int(600 * px), 3), 40, dtype=np.uint8)
        # 胶纸放在标定板右边：x=300..510mm, y=0..297mm
        cv2.rectangle(canvas, (int(300 * px), 0), (int(510 * px), int(297 * px)),
                      (240, 240, 240), -1)
        rect = scan_calib._find_sheet_region(canvas, (0.0, 0.0), px)
        self.assertIsNotNone(rect)
        page = scan_calib._warp_sheet(canvas, rect, dpi=30)
        self.assertEqual(page.mode, "L")
        self.assertGreater(page.width, 0)

    def test_find_sheet_region_missing(self):
        canvas = np.full((400, 400, 3), 20, dtype=np.uint8)
        with self.assertRaises(ValueError):
            scan_calib._find_sheet_region(canvas, (0.0, 0.0), 4.0)

    def test_warp_by_points(self):
        bgr = np.full((100, 100, 3), 200, dtype=np.uint8)
        corners = [[0, 0], [99, 0], [99, 99], [0, 99]]
        page = scan_calib._warp_by_points(bgr, corners, dpi=30)
        self.assertEqual(page.mode, "L")

    def test_measure_photo_corners_uses_marks(self):
        bgr = np.full((100, 100, 3), 200, dtype=np.uint8)
        page = Image.new("L", (50, 50), 255)
        fake = type("M", (), {"ok": True})()
        with patch.object(scan_calib.np, "fromfile", return_value=b""), \
                patch.object(cv2, "imdecode", return_value=bgr), \
                patch.object(scan_calib, "find_marks", side_effect=RuntimeError("none")), \
                patch.object(scan_calib, "_warp_by_points", return_value=page), \
                patch.object(scan_calib, "measure_image", return_value=fake):
            out = scan_calib.measure_photo_corners(
                "x.jpg", [[0, 0], [99, 0], [99, 99], [0, 99]])
        self.assertIs(out, fake)

    def test_measure_photo_corners_unreadable(self):
        with patch.object(scan_calib.np, "fromfile", return_value=b""), \
                patch.object(cv2, "imdecode", return_value=None):
            with self.assertRaises(ValueError):
                scan_calib.measure_photo_corners("x.jpg", [[0, 0]] * 4)


if __name__ == "__main__":
    unittest.main()
