# -*- coding: utf-8 -*-
"""补齐边角分支：平台分支、补丁点、罕见的失败路径。

这些用例尽量只碰一个分支，避免和主流程测试互相干扰。
"""
from __future__ import annotations

import os
import tkinter as tk
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import tkinter as tk

from ulpp import cli, gui as gui_mod, i18n, scan, templates, textlabel
from ulpp import partial_gui as pg
from ulpp import wizard as wizard_mod
from ulpp import scan_photo
from ulpp.config import GridSpec
from ulpp.sheets import SheetStore
from ulpp.templates import Template, TemplateStore
from ulpp.ui import flow as flow_mod
from ulpp.ui import screens
from ulpp.ui import shell as shell_mod
from ulpp.ui.calibrate import CalibrateWizard
from ulpp.ui.flow import Flow
from ulpp.ui.partial import PartialWindow

from .ui_harness import UiCase, requires_tk

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:  # pragma: no cover
    np = None
    HAS_NUMPY = False

try:
    import cv2

    from ulpp import scan_calib
    HAS_CV = True
except Exception:  # pragma: no cover
    cv2 = None
    scan_calib = None
    HAS_CV = False


class _FakeCvBase:
    COLOR_BGR2GRAY = 0
    THRESH_BINARY = 0
    THRESH_BINARY_INV = 0
    THRESH_OTSU = 0
    MORPH_CLOSE = 0
    RETR_EXTERNAL = 0
    RETR_LIST = 0
    CHAIN_APPROX_SIMPLE = 0
    INTER_AREA = 0

    def __init__(self, contours):
        self._contours = contours

    def resize(self, img, *a, **k):
        return img

    def cvtColor(self, img, *a, **k):
        return img

    def GaussianBlur(self, img, *a, **k):
        return img

    def threshold(self, img, *a, **k):
        return 0, img

    def morphologyEx(self, img, *a, **k):
        return img

    def findContours(self, mask, *a, **k):
        return list(self._contours), None

    def rectangle(self, *a, **k):
        return None


class _FindQuadsCv(_FakeCvBase):
    def __init__(self):
        super().__init__([object()])

    def contourArea(self, contour):
        return 1.0                     # 小于 10% 面积 → 跳过

    def arcLength(self, contour, closed):
        return 4.0

    def approxPolyDP(self, contour, eps, closed):
        return np.zeros((4, 1, 2), dtype="float32")


class _FindMarksCv(_FakeCvBase):
    def __init__(self):
        self.c = [object() for _ in range(5)]
        super().__init__(self.c)
        self._area = {id(c): 1.0 for c in self.c}
        self._peri = {id(self.c[0]): 0.0, id(self.c[1]): 4.0,
                      id(self.c[2]): 4.0, id(self.c[3]): 4.0,
                      id(self.c[4]): 4.0}
        self._approx = {id(self.c[1]): np.zeros((3, 1, 2)),
                        id(self.c[0]): np.zeros((4, 1, 2)),
                        id(self.c[2]): np.zeros((4, 1, 2)),
                        id(self.c[3]): np.zeros((4, 1, 2)),
                        id(self.c[4]): np.zeros((4, 1, 2))}
        self._rect = {id(self.c[2]): (0, (1.0, 10.0), 0),
                      id(self.c[3]): (0, (10.0, 10.0), 0),
                      id(self.c[4]): (0, (10.0, 10.0), 0)}
        self._moments = {id(self.c[3]): {"m00": 0.0, "m10": 0.0, "m01": 0.0},
                         id(self.c[4]): {"m00": 2.0, "m10": 6.0, "m01": 8.0}}

    def contourArea(self, contour):
        return self._area[id(contour)]

    def arcLength(self, contour, closed):
        return self._peri[id(contour)]

    def approxPolyDP(self, contour, eps, closed):
        return self._approx[id(contour)]

    def minAreaRect(self, contour):
        return self._rect[id(contour)]

    def moments(self, contour):
        return self._moments[id(contour)]


class _BoardFrameCv(_FakeCvBase):
    def __init__(self):
        self.small = object()
        self.bad = object()
        self.good = object()
        super().__init__([self.small, self.bad, self.good])
        self._area = {id(self.small): 1.0, id(self.bad): 900.0,
                      id(self.good): 900.0}
        self._approx = {id(self.bad): np.zeros((5, 1, 2)),
                        id(self.good): np.array([[[0, 0]], [[10, 0]],
                                                 [[10, 10]], [[0, 10]]],
                                                dtype="float32")}

    def contourArea(self, contour):
        return self._area[id(contour)]

    def arcLength(self, contour, closed):
        return 4.0

    def approxPolyDP(self, contour, eps, closed):
        return self._approx[id(contour)]

    def pointPolygonTest(self, *a):
        return 1.0


class _SheetRegionCv(_FakeCvBase):
    def __init__(self):
        self.small, self.tiny, self.short, self.thin = (object() for _ in range(4))
        super().__init__([self.small, self.tiny, self.short, self.thin])
        self._area = {id(self.small): 1.0, id(self.tiny): 500000.0,
                      id(self.short): 500000.0, id(self.thin): 500000.0}
        self._rect = {id(self.tiny): (0, (4.0, 100.0), 0),
                      id(self.short): (0, (100.0, 200.0), 0),
                      id(self.thin): (0, (100.0, 1300.0), 0)}

    def contourArea(self, contour):
        return self._area[id(contour)]

    def minAreaRect(self, contour):
        return self._rect[id(contour)]


class CliZipAndGlobTests(UiCase):
    def test_expand_inputs_glob_pattern(self):
        pdf = self.tmpdir / "a.pdf"
        pdf.write_bytes(b"%PDF")
        found = cli.expand_inputs([str(self.tmpdir / "a.pd?")])
        self.assertEqual(found, [str(pdf)])

    def _fake_zip(self, filename):
        import io

        class Info:
            flag_bits = 0

            def is_dir(self):
                return False

        info = Info()
        info.filename = filename

        class FakeZip:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def infolist(self):
                return [info]

            def open(self, _info):
                return io.BytesIO(b"%PDF")

        return FakeZip()

    def test_zip_name_without_utf8_flag_falls_back(self):
        # cp437 的 0x80 既不是合法 GBK 也不是合法 UTF-8 → 走最后的 pass
        dest = self.tmpdir / "out"
        dest.mkdir()
        with mock.patch.object(cli.zipfile, "ZipFile",
                               return_value=self._fake_zip("\x80")):
            self.assertEqual(cli._safe_extract_zip("x.zip", str(dest)), [])

    def test_zip_gbk_name_is_recovered(self):
        # cp437 的原始字节其实是 GBK 中文名 → 应该解回 .pdf
        dest = self.tmpdir / "out"
        dest.mkdir()
        mojibake = "报告.pdf".encode("gbk").decode("cp437")
        with mock.patch.object(cli.zipfile, "ZipFile",
                               return_value=self._fake_zip(mojibake)):
            found = cli._safe_extract_zip("x.zip", str(dest))
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].endswith("报告.pdf"))


class NormalizeTests(unittest.TestCase):
    def test_english_words(self):
        self.assertEqual(i18n.normalize_language("system english"), "en_US")
        self.assertEqual(i18n.normalize_language("Chinese"), "zh_CN")


class GuiDndTests(UiCase):
    def test_setup_dnd_registers_when_available(self):
        app = gui_mod.App(self.root)
        app.listbox = mock.Mock()
        with mock.patch.object(gui_mod, "_HAS_DND", True), \
                mock.patch.object(gui_mod, "DND_FILES", "Files"):
            app._setup_dnd()
        app.listbox.drop_target_register.assert_called_once_with("Files")
        app.listbox.dnd_bind.assert_called_once()


class PartialGuiGuardsTests(UiCase):
    def _window_without_sheet(self):
        store = SheetStore(path=self.tmpdir / "sheets.json")
        with mock.patch.object(pg.messagebox, "showerror"), \
                mock.patch.object(pg.messagebox, "showinfo"), \
                mock.patch.object(pg.messagebox, "showwarning"):
            win = pg.PartialWindow(self.root, store=store)
        self.pump()
        self.close_later(win)
        win._cell_rects = {0: (0.0, 0.0, 20.0, 20.0)}
        return win

    def test_left_click_slot_but_no_sheet(self):
        win = self._window_without_sheet()
        with mock.patch.object(pg.messagebox, "showinfo"):
            win._on_left_click(types.SimpleNamespace(x=10, y=10))

    def test_right_click_slot_but_no_sheet(self):
        win = self._window_without_sheet()
        win._on_right_click(types.SimpleNamespace(x=10, y=10))


class ScanFallbackTests(unittest.TestCase):
    def test_period_autocorr_invalid_range_with_signal(self):
        profile = [1.0, 0.0] * 20
        self.assertIsNone(scan._period_autocorr(profile, pmin=100, pmax=1))

    def test_lattice_fit_with_too_few_samples_per_period(self):
        self.assertIsNone(scan._fold_fit([1.0] * 40, pmin=100, pmax=1))

    @unittest.skipUnless(HAS_NUMPY, "需要 numpy")
    def test_order_quad_reverses_clockwise(self):
        pts = np.array([[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0]])
        ordered = scan_photo._order_quad(pts.copy())
        self.assertEqual({tuple(p) for p in ordered}, {tuple(p) for p in pts})

    @unittest.skipUnless(HAS_NUMPY, "需要 numpy")
    def test_fold_fit_fine_search_improves_period(self):
        xs = np.arange(400)
        period = 18.5
        profile = np.exp(-((xs % period - 5) ** 2) / 2.0).tolist()
        fit = scan._fold_fit(profile, 18.0, 22.0)
        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit["period"], period, delta=0.02)


@unittest.skipUnless(HAS_NUMPY, "需要 numpy")
class DewarpGuardTests(UiCase):
    def test_sample_lines_skips_lines_touching_edges(self):
        from ulpp import scan_dewarp as dw
        from PIL import Image

        dark = dw._darkness(Image.new("L", (80, 80), 255))
        self.assertEqual(dw._sample_lines_at(dark, [0, 79], 0, 4.0).shape, (0, 3))

    def test_refine_grid_stops_when_fit_returns_nothing(self):
        from ulpp import scan_dewarp as dw
        from PIL import Image, ImageDraw

        img = Image.new("L", (400, 400), 255)
        draw = ImageDraw.Draw(img)
        for pos in range(10, 400, 20):
            draw.line([(pos, 0), (pos, 399)], fill=0)
            draw.line([(0, pos), (399, pos)], fill=0)
        expected = list(range(10, 400, 20))
        with mock.patch.object(dw, "_fit_field", return_value=None):
            out, stats = dw.refine_grid(img, expected, expected, iterations=1)
        self.assertEqual(out.size, img.size)
        self.assertEqual(stats["after"], [])


class TemplateAndTextTests(UiCase):
    def test_template_save_survives_cleanup_failure(self):
        store = TemplateStore(directory=self.tmpdir)
        store.items.append(Template(id="x", name="纸", cols=1, rows=1,
                                    cell_w_mm=10, cell_h_mm=10,
                                    pitch_x_mm=10, pitch_y_mm=10))
        with mock.patch.object(templates.os.path, "exists", return_value=True), \
                mock.patch.object(templates.os, "remove", side_effect=OSError("no")):
            self.assertEqual(store.save(), store.path)

    def test_find_cjk_font_explicit_path(self):
        font = self.tmpdir / "font.ttf"
        font.write_bytes(b"x")
        self.assertEqual(textlabel.find_cjk_font(str(font)), str(font))


class CalibrateGuardTests(UiCase):
    def _wizard(self):
        shell = self.make_shell(flow=Flow(index=2))
        wiz = CalibrateWizard(shell)
        self.pump()
        self.close_later(wiz)
        return shell, wiz

    def _photo(self):
        from PIL import Image

        path = self.tmpdir / "p.jpg"
        Image.new("RGB", (200, 100), "white").save(path)
        return str(path)

    def test_redraw_all_degenerate_crop_returns(self):
        shell, wiz = self._wizard()
        wiz.photo_path = self._photo()
        wiz.step = "corners"
        wiz.render()
        wiz._img_off = (10000.0, 10000.0)
        wiz._redraw_all()                     # 裁剪窗口退化 → 直接返回

    def test_redraw_corners_without_canvas(self):
        shell, wiz = self._wizard()
        wiz._canvas = None
        wiz._redraw_corners()

    def test_release_with_four_corners_does_not_add(self):
        shell, wiz = self._wizard()
        wiz.photo_path = self._photo()
        wiz.step = "corners"
        wiz.render()
        wiz.corners = [(10, 10), (100, 10), (100, 80), (10, 80)]
        wiz._on_canvas_press(types.SimpleNamespace(x=15, y=15))
        wiz._on_canvas_release(types.SimpleNamespace(x=15, y=15))
        self.assertEqual(len(wiz.corners), 4)


class FlowBranchesTests(unittest.TestCase):
    def test_default_state_dir_appdata_and_home(self):
        env = dict(os.environ)
        env.pop("APPDATA", None)
        env.pop(flow_mod.ENV_STATE_DIR, None)
        with mock.patch.dict(os.environ, dict(env, APPDATA="/tmp/appdata"), clear=True):
            self.assertEqual(flow_mod.default_state_dir(),
                             Path("/tmp/appdata") / "ulpp")
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(flow_mod.default_state_dir(), Path.home() / ".ulpp")

    def test_save_cleanup_removal_failure_is_soft(self):
        import tempfile
        import uuid

        directory = Path(tempfile.gettempdir()) / ("ulpp_flow_gap_%s" % uuid.uuid4().hex[:8])
        directory.mkdir(parents=True, exist_ok=True)
        try:
            f = Flow()
            with mock.patch.object(flow_mod.os.path, "exists", return_value=True), \
                    mock.patch.object(flow_mod.os, "remove", side_effect=OSError("no")):
                target = f.save(directory=directory)
            self.assertEqual(target, directory / flow_mod.STATE_FILE)
        finally:
            import shutil

            shutil.rmtree(str(directory), ignore_errors=True)

    def test_saved_at(self):
        f = Flow()
        self.assertFalse(f.saved_at(directory="/definitely/not/here"))
        import tempfile
        import uuid

        directory = Path(tempfile.gettempdir()) / ("ulpp_flow_saved_%s" % uuid.uuid4().hex[:8])
        directory.mkdir(parents=True, exist_ok=True)
        try:
            f.save(directory=directory)
            self.assertTrue(f.saved_at(directory=directory))
        finally:
            import shutil

            shutil.rmtree(str(directory), ignore_errors=True)


class PartialV2GuardTests(UiCase):
    def test_generate_without_sheet_returns(self):
        shell = self.make_shell(flow=Flow(index=2))
        win = PartialWindow(shell)
        self.pump()
        self.close_later(win)
        win.sheet = None
        win.generate()                         # 直接返回


class ScreensLastStepTests(UiCase):
    def test_orient_on_last_step_returns_after_tip(self):
        shell = self.make_shell(flow=Flow(steps=("sheet", "orient"), index=1))
        holder = tk.Frame(self.root)
        screens.build_orient(shell, holder)
        self.assertTrue(holder.winfo_children())


class ShellGuardTests(UiCase):
    def test_alpha_failure_is_swallowed(self):
        with mock.patch.dict(os.environ, {"ULPP_ALPHA": "0.8"}), \
                mock.patch.object(tk.Tk, "attributes", side_effect=RuntimeError("no")):
            shell = self.make_shell()
        self.assertIsNotNone(shell)

    def test_root_dnd_registration_failure_is_swallowed(self):
        with mock.patch.object(shell_mod, "_HAS_DND", True), \
                mock.patch.object(shell_mod, "DND_FILES", "Files"):
            shell = self.make_shell()
        self.assertIsNotNone(shell)

    def test_attach_text_box_dnd_failure_is_swallowed(self):
        shell = self.make_shell()
        box = tk.Text(self.root)
        with mock.patch.object(shell_mod, "_HAS_DND", True), \
                mock.patch.object(shell_mod, "DND_FILES", "Files"):
            shell.attach_text_box(box)
        box.destroy()

    def test_open_wizard_store_error_uses_default_profile(self):
        shell = self.make_shell()
        shell.store = mock.Mock()
        shell.store.get_printer.side_effect = RuntimeError("bad")
        captured = {}

        class FakeWizard:
            def __init__(self, master, profile=None, on_save=None, output_dir=None):
                captured["profile"] = profile

        import ulpp.wizard as wizard_mod2
        with mock.patch.object(wizard_mod2, "CalibrationWizard", FakeWizard):
            shell.open_wizard()
        self.assertEqual(captured["profile"].feed, "face_up_short")


class WizardStartfileTests(UiCase):
    def test_make_test_pdf_opens_on_windows_and_swallows_failure(self):
        import ulpp.wizard as wm
        from ulpp.sheets import PrinterProfile

        def fake_img(self, name):
            key = ("fake", name)
            if key not in self.images:
                self.images[key] = tk.PhotoImage(width=8, height=8, master=self)
            return self.images[key]

        with mock.patch.object(wm.CalibrationWizard, "img", fake_img):
            wiz = wm.CalibrationWizard(self.root, PrinterProfile(),
                                       output_dir=str(self.tmpdir))
        self.pump()
        self.close_later(wiz)
        wiz.go(5)
        with mock.patch.object(wm, "make_orientation_pdf"), \
                mock.patch.object(wm.os, "name", "nt"), \
                mock.patch("os.startfile", create=True) as start:
            wiz.make_test_pdf()
        start.assert_called_once()

        with mock.patch.object(wm, "make_orientation_pdf"), \
                mock.patch.object(wm.os, "name", "nt"), \
                mock.patch("os.startfile", create=True, side_effect=OSError("no")):
            wiz.make_test_pdf()                 # 打不开也不影响结果页
        self.assertIn("已生成", wiz.print_lbl.cget("text"))


class CartoonToggleTests(UiCase):
    def test_toggle_off_after_schedule_cancels_job(self):
        from ulpp.ui.calibrate import CartoonHelp

        shell = self.make_shell()
        help_win = CartoonHelp(shell)
        self.pump()
        self.close_later(help_win)
        help_win._schedule()
        self.assertIsNotNone(help_win._after)
        help_win.toggle()
        self.assertFalse(help_win.playing)
        self.assertIsNone(help_win._after)


@unittest.skipUnless(HAS_CV and HAS_NUMPY, "需要 OpenCV")
class CalibBranchTests(unittest.TestCase):
    def test_find_quads_skips_small_contour(self):
        fake = _FindQuadsCv()
        bgr = np.zeros((100, 100, 3), dtype=np.uint8)
        with mock.patch.object(scan_calib, "_cv2", return_value=fake):
            self.assertEqual(scan_calib.find_quads(bgr), [])

    def test_find_marks_filter_branches(self):
        fake = _FindMarksCv()
        bgr = np.zeros((100, 100, 3), dtype=np.uint8)
        with mock.patch.object(scan_calib, "_cv2", return_value=fake):
            pts = scan_calib.find_marks(bgr)
        self.assertEqual(pts, [(3.0, 4.0)])

    def test_find_board_frame_skips_bad_and_keeps_quad(self):
        fake = _BoardFrameCv()
        bgr = np.zeros((100, 100, 3), dtype=np.uint8)
        with mock.patch.object(scan_calib, "_cv2", return_value=fake):
            best = scan_calib.find_board_frame(bgr)
        self.assertEqual(best.shape, (4, 2))

    def test_filter_grid_marks_skips_axis_with_few_clusters(self):
        pts = [(1.0, float(i)) for i in range(40)]
        out = scan_calib._filter_grid_marks(pts)
        self.assertEqual(len(out), 40)

    def test_homography_honours_none_from_find_homography(self):
        class Wrap:
            def __getattr__(self, name):
                return getattr(cv2, name)

            def findHomography(self, *a, **k):
                return None, None

        pts = [(25 + 20 * c, 30 + 20 * r) for r in range(13) for c in range(9)]
        with mock.patch.object(scan_calib, "_cv2", return_value=Wrap()):
            matrix, chosen = scan_calib._homography_from_marks(pts)
        self.assertIsNone(matrix)
        self.assertIsNotNone(chosen)

    def test_find_sheet_region_skips_bad_rectangles(self):
        fake = _SheetRegionCv()
        canvas = np.full((1600, 2000, 3), 40, dtype=np.uint8)
        with mock.patch.object(scan_calib, "_cv2", return_value=fake):
            with self.assertRaises(ValueError):
                scan_calib._find_sheet_region(canvas, (0.0, 0.0), 4.0)

    def test_warp_sheet_rotates_point_order(self):
        canvas = np.full((1600, 2000, 3), 40, dtype=np.uint8)
        rect = ((900.0, 800.0), (300.0, 500.0), 90.0)
        page = scan_calib._warp_sheet(canvas, rect, dpi=30)
        self.assertEqual(page.mode, "L")

    def test_measure_photo_calibrated_unreadable(self):
        with mock.patch.object(scan_calib.np, "fromfile", return_value=b""), \
                mock.patch.object(cv2, "imdecode", return_value=None):
            with self.assertRaises(ValueError):
                scan_calib.measure_photo_calibrated("x.jpg")

    def _calibrated_patches(self, marks, quads):
        return [
            mock.patch.object(scan_calib.np, "fromfile", return_value=b""),
            mock.patch.object(cv2, "imdecode",
                              return_value=np.zeros((100, 100, 3), dtype=np.uint8)),
            mock.patch.object(scan_calib, "find_marks", side_effect=marks),
            mock.patch.object(scan_calib, "_homography_from_marks",
                              return_value=(np.eye(3),
                                            (np.zeros((8, 2)), np.zeros((8, 2))))),
            mock.patch.object(scan_calib, "estimate_distortion",
                              return_value=(0.0, 0.0, 0.0)),
            mock.patch.object(scan_calib, "undo_distortion",
                              side_effect=lambda bgr, *a: bgr),
            mock.patch.object(scan_calib, "find_quads", return_value=quads),
        ]

    def _run_calibrated(self, marks, quads, **patches):
        ctx = self._calibrated_patches(marks, quads)
        for extra in patches.values():
            ctx.append(extra)
        for item in ctx:
            item.start()
            self.addCleanup(item.stop)
        with self.assertRaises(ValueError):
            scan_calib.measure_photo_calibrated("x.jpg")

    def test_measure_photo_calibrated_needs_two_quads(self):
        marks = [(1.0, 2.0)] * 30
        self._run_calibrated([marks], [])

    def test_measure_photo_calibrated_needs_board_marks(self):
        marks = [(1.0, 2.0)] * 30
        quad = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype="float32")
        with mock.patch.object(scan_calib, "_inside", return_value=0):
            self._run_calibrated([marks, []], [quad, quad.copy()])

    def test_measure_photo_calibrated_needs_sheet(self):
        marks = [(1.0, 2.0)] * 30
        quad = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype="float32")
        with mock.patch.object(scan_calib, "_inside", return_value=25), \
                mock.patch.object(scan_calib, "_pick_sheet", return_value=None):
            self._run_calibrated([marks, marks], [quad, quad.copy()])

    def test_measure_photo_corners_applies_distortion(self):
        bgr = np.zeros((100, 100, 3), dtype=np.uint8)
        page = None
        with mock.patch.object(scan_calib.np, "fromfile", return_value=b""), \
                mock.patch.object(cv2, "imdecode", return_value=bgr), \
                mock.patch.object(scan_calib, "find_marks",
                                  return_value=[(1.0, 2.0)] * 30), \
                mock.patch.object(scan_calib, "_homography_from_marks",
                                  return_value=(np.eye(3),
                                                (np.zeros((8, 2)), np.zeros((8, 2))))), \
                mock.patch.object(scan_calib, "estimate_distortion",
                                  return_value=(0.2, 0.0, 0.0)), \
                mock.patch.object(scan_calib, "_warp_by_points",
                                  return_value="page") as warp, \
                mock.patch.object(scan_calib, "measure_image",
                                  return_value=page):
            out = scan_calib.measure_photo_corners(
                "x.jpg", [[0, 0], [99, 0], [99, 99], [0, 99]])
        self.assertIsNone(out)
        self.assertTrue(warp.called)
