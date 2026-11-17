# -*- coding: utf-8 -*-
"""初次校准向导（``ulpp.ui.calibrate``）：三条路线、点四角、结果、卡通帮助。"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest import mock

from PIL import Image

from ulpp.templates import Template
from ulpp.ui import calibrate as cal_mod
from ulpp.ui.calibrate import CalibrateWizard, CartoonHelp
from ulpp.ui.flow import Flow

from .ui_harness import FakeMeasurement, UiCase

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.pdf"


class WizardCase(UiCase):
    def _shell(self):
        return self.make_shell(flow=Flow(index=2))

    def _wizard(self, shell=None):
        shell = shell or self._shell()
        wiz = CalibrateWizard(shell)
        self.pump()
        self.close_later(wiz)
        return shell, wiz

    def _photo(self):
        path = self.tmpdir / "photo.jpg"
        Image.new("RGB", (200, 100), (240, 240, 240)).save(path)
        return str(path)


class RenderStepTests(WizardCase):
    def test_constructor_starts_at_ask(self):
        shell, wiz = self._wizard()
        self.assertEqual(wiz.step, "ask")
        self.assertIsNone(wiz.measurement)
        self.assertIsNone(wiz.error)

    def test_step_sizes(self):
        shell, wiz = self._wizard()
        for step, want in (("corners", (780, 700)), ("result", (620, 400)),
                           ("ask", (660, 300)), ("paper", (660, 300)),
                           ("shoot", (700, 400)), ("other", (700, 300))):
            wiz.step = step
            got = wiz._size_for()
            self.assertEqual(got, (shell.S(want[0]), shell.S(want[1])))

    def test_go_clears_error_and_renders_each_simple_step(self):
        shell, wiz = self._wizard()
        for step in ("paper", "scan", "print", "shoot", "plain", "ask"):
            wiz.error = "旧错误"
            wiz.go(step)
            self.assertIsNone(wiz.error)
            self.assertEqual(wiz.step, step)

    def test_error_lines_are_rendered_on_each_step(self):
        shell, wiz = self._wizard()
        for step in ("scan", "print", "shoot", "plain"):
            wiz.step = step
            wiz.error = "看不清"
            wiz.render()
            labels = [w.cget("text") for w in wiz.body.winfo_children()
                      if w.winfo_class() == "Label"]
            self.assertTrue(any("看不清" in t for t in labels))

    def test_paper_back_button_returns_to_ask(self):
        shell, wiz = self._wizard()
        wiz.go("paper")
        texts = []
        canvases = []

        def walk(widget):
            for child in widget.winfo_children():
                try:
                    texts.append(child.cget("text"))
                except Exception:
                    pass
                if child.winfo_class() == "Canvas":
                    canvases.append(child)
                walk(child)

        walk(wiz.body)
        self.assertTrue(canvases)
        drawn = " ".join(
            str(canvas.itemcget(item, "text"))
            for canvas in canvases
            for item in canvas.find_all()
            if canvas.type(item) == "text"
        )
        self.assertIn(shell.T("calib.yes_paper"), drawn)
        self.assertIn(shell.T("calib.no_paper"), drawn)
        wiz.go("ask")
        self.assertEqual(wiz.step, "ask")

    def test_hug_respects_min_width(self):
        shell, wiz = self._wizard()
        wiz._hug(900)
        self.assertIn("+", wiz.geometry())

    def test_button_kinds(self):
        shell, wiz = self._wizard()
        for kind in ("solid", "warn", "ghost", "soft"):
            btn = wiz._button(wiz.body, kind, lambda: None, kind=kind)
            self.assertEqual(btn.cget("text"), kind)
            btn.destroy()

    def test_round_button_plain_and_gradient(self):
        shell, wiz = self._wizard()
        plain = wiz._round_button(wiz.body, "go", lambda: None, True, 120)
        self.assertIsNotNone(plain)
        with mock.patch.dict(os.environ, {"ULPP_GRAD": "on", "ULPP_THEME": "aero"}):
            shell.P  # noqa: B018 - 主题在 Shell 构造时已定
            wiz.app.P = dict(shell.P, accent2="#00A4A9")
            grad = wiz._round_button(wiz.body, "go", lambda: None, True, 120)
        self.assertIsNotNone(grad)
        self.assertEqual(wiz._hex_rgb("#00A4A9"), (0, 164, 169))
        plain.destroy()
        grad.destroy()

    def test_choice_box_style(self):
        shell, wiz = self._wizard()
        with mock.patch.dict(os.environ, {"ULPP_SHAPE": "box"}):
            row = wiz._choice(wiz.body, "左", lambda: None, "右", lambda: None)
        self.assertIsNotNone(row)
        row.destroy()

    def test_option_card_is_clickable(self):
        shell, wiz = self._wizard()
        called = []
        card = wiz._option(wiz.body, "标题", "说明", lambda: called.append(1))
        self.assertIsNotNone(card)
        card.event_generate("<Button-1>")
        self.pump()
        card.destroy()


class ScanRouteTests(WizardCase):
    def test_pick_scan_cancel_success_failure(self):
        shell, wiz = self._wizard()
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=""):
            wiz.pick_scan()
        self.assertIsNone(wiz.measurement)

        with mock.patch("tkinter.filedialog.askopenfilename",
                        return_value="/tmp/a.png"), \
                mock.patch("ulpp.scan.measure_file",
                           return_value=FakeMeasurement()) as measure:
            wiz.pick_scan()
        measure.assert_called_once()
        self.assertEqual(wiz.step, "result")
        self.assertIsNotNone(wiz.measurement)
        self.assertEqual(wiz.source, "/tmp/a.png")

        wiz.step = "scan"
        with mock.patch("tkinter.filedialog.askopenfilename",
                        return_value="/tmp/b.png"), \
                mock.patch("ulpp.scan.measure_file",
                           side_effect=ValueError("太淡")):
            wiz.pick_scan()
        self.assertEqual(wiz.error, "太淡")
        self.assertEqual(wiz.step, "scan")

    def test_drop_scan(self):
        shell, wiz = self._wizard()
        wiz._drop_scan("")
        self.assertIsNone(wiz.measurement)
        with mock.patch.object(wiz, "_measure_scan") as measure:
            wiz._drop_scan("/tmp/a.png")
        measure.assert_called_once_with("/tmp/a.png")


class PrintShootRouteTests(WizardCase):
    def test_save_board_cancel_success_failure(self):
        shell, wiz = self._wizard()
        with mock.patch("tkinter.filedialog.asksaveasfilename", return_value=""):
            wiz.save_board()
        self.assertIsNone(wiz.error)

        shell._open_path = mock.Mock()
        with mock.patch("tkinter.filedialog.asksaveasfilename",
                        return_value="/tmp/board.pdf"), \
                mock.patch("ulpp.scan_board.make_board_pdf") as make:
            wiz.save_board()
        make.assert_called_once_with("/tmp/board.pdf")
        shell._open_path.assert_called_once_with("/tmp/board.pdf")
        self.assertEqual(wiz.step, "shoot")

        wiz.step = "print"
        with mock.patch("tkinter.filedialog.asksaveasfilename",
                        return_value="/tmp/board.pdf"), \
                mock.patch("ulpp.scan_board.make_board_pdf",
                           side_effect=OSError("只读")):
            wiz.save_board()
        self.assertEqual(wiz.error, "只读")

    def test_pick_photo_success(self):
        shell, wiz = self._wizard()
        fake_mod = types.ModuleType("ulpp.scan_calib")
        fake_mod.measure_photo_calibrated = mock.Mock(return_value=FakeMeasurement())
        with mock.patch("tkinter.filedialog.askopenfilename",
                        return_value="/tmp/p.jpg"), \
                mock.patch.dict(sys.modules, {"ulpp.scan_calib": fake_mod}):
            wiz.pick_photo()
        self.assertEqual(wiz.step, "result")
        self.assertFalse(wiz.measurement_plain)

    def test_pick_photo_failure_goes_to_corners(self):
        shell, wiz = self._wizard()
        photo = self._photo()
        fake_mod = types.ModuleType("ulpp.scan_calib")
        fake_mod.measure_photo_calibrated = mock.Mock(
            side_effect=RuntimeError("认不出纸边"))
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=photo), \
                mock.patch.dict(sys.modules, {"ulpp.scan_calib": fake_mod}):
            wiz.pick_photo()
        self.assertEqual(wiz.step, "corners")
        self.assertEqual(wiz.photo_path, photo)
        self.assertEqual(wiz.corners, [])
        self.assertEqual(wiz.error, "认不出纸边")

    def test_drop_photo(self):
        shell, wiz = self._wizard()
        wiz._drop_photo("")
        with mock.patch.object(wiz, "_try_photo") as try_photo:
            wiz._drop_photo("/tmp/p.jpg")
        try_photo.assert_called_once_with("/tmp/p.jpg")

    def test_pick_photo_plain_success_and_failure(self):
        shell, wiz = self._wizard()
        photo = self._photo()
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=photo), \
                mock.patch("ulpp.scan_photo.measure_photo",
                           return_value=FakeMeasurement()):
            wiz.pick_photo_plain()
        self.assertTrue(wiz.measurement_plain)
        self.assertEqual(wiz.step, "result")

        with mock.patch("tkinter.filedialog.askopenfilename", return_value=photo), \
                mock.patch("ulpp.scan_photo.measure_photo",
                           side_effect=RuntimeError("没纸边")):
            wiz.pick_photo_plain()
        self.assertEqual(wiz.step, "corners")
        self.assertEqual(wiz.error, "没纸边")

    def test_pick_photo_plain_cancel(self):
        shell, wiz = self._wizard()
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=""):
            wiz.pick_photo_plain()
        self.assertIsNone(wiz.measurement)

    def test_drop_plain(self):
        shell, wiz = self._wizard()
        wiz._drop_plain("")
        with mock.patch.object(wiz, "_measure_plain") as measure:
            wiz._drop_plain("/tmp/p.jpg")
        measure.assert_called_once_with("/tmp/p.jpg")


class CornerTests(WizardCase):
    def _corners_wizard(self):
        shell, wiz = self._wizard()
        wiz.photo_path = self._photo()
        wiz.step = "corners"
        wiz.render()
        self.pump()
        return shell, wiz

    def test_canvas_and_redraw(self):
        shell, wiz = self._corners_wizard()
        self.assertIsNotNone(wiz._canvas)
        self.assertGreater(wiz._base_scale, 0)
        wiz.corners = [(10, 10), (100, 10)]
        wiz._redraw_corners()
        wiz.corners.append((100, 80))
        wiz.corners.append((10, 80))
        wiz._redraw_corners()
        self.assertGreater(len(wiz._canvas.find_withtag("quad")), 0)

    def test_coordinates_roundtrip(self):
        shell, wiz = self._corners_wizard()
        cx, cy = wiz._canvas_xy(40, 30)
        ix, iy = wiz._image_xy(cx, cy)
        self.assertAlmostEqual(ix, 40)
        self.assertAlmostEqual(iy, 30)

    def test_zoom_and_fit(self):
        shell, wiz = self._corners_wizard()
        wiz._zoom = 1.0
        wiz._zoom_at(100, 100, 1.5)
        self.assertGreater(wiz._zoom, 1.0)
        wiz._zoom_at(100, 100, 100.0)
        self.assertLessEqual(wiz._zoom, 6.0)
        wiz._on_wheel(types.SimpleNamespace(x=100, y=100, delta=1))
        wiz._on_wheel(types.SimpleNamespace(x=100, y=100, delta=-1))
        wiz._zoom_fit()
        self.assertEqual(wiz._zoom, 1.0)

    def test_zoom_without_photo_is_noop(self):
        shell, wiz = self._wizard()
        wiz._zoom_at(10, 10, 2)
        wiz._zoom_fit()
        wiz._clamp_offset()
        wiz._redraw_all()

    def test_pan(self):
        shell, wiz = self._corners_wizard()
        wiz._zoom = 2.0
        wiz._pan_start(types.SimpleNamespace(x=10, y=10))
        before = wiz._img_off
        wiz._pan_move(types.SimpleNamespace(x=100, y=100))
        self.assertNotEqual(wiz._img_off, before)
        wiz._pan_move(types.SimpleNamespace(x=5000, y=5000))
        self.assertLessEqual(wiz._img_off[0], 0)

    def test_pan_move_without_start(self):
        shell, wiz = self._corners_wizard()
        wiz._pan_move(types.SimpleNamespace(x=10, y=10))

    def test_click_adds_corner_and_limits_to_four(self):
        shell, wiz = self._corners_wizard()
        cx, cy = wiz._canvas_xy(100, 50)
        for _ in range(5):
            wiz._on_canvas_press(types.SimpleNamespace(x=cx, y=cy))
            wiz._on_canvas_release(types.SimpleNamespace(x=cx, y=cy))
        self.assertLessEqual(len(wiz.corners), 4)
        self.assertGreaterEqual(len(wiz.corners), 1)

    def test_click_outside_image_does_not_add(self):
        shell, wiz = self._corners_wizard()
        wiz._on_canvas_press(types.SimpleNamespace(x=-1000, y=-1000))
        wiz._on_canvas_release(types.SimpleNamespace(x=-1000, y=-1000))
        self.assertEqual(wiz.corners, [])

    def test_motion_under_threshold_does_nothing(self):
        shell, wiz = self._corners_wizard()
        wiz._on_canvas_press(types.SimpleNamespace(x=50, y=50))
        wiz._on_canvas_motion(types.SimpleNamespace(x=51, y=51))
        self.assertFalse(wiz._moved)

    def test_motion_drags_existing_corner(self):
        shell, wiz = self._corners_wizard()
        cx, cy = wiz._canvas_xy(40, 30)
        wiz.corners = [(40, 30)]
        wiz._on_canvas_press(types.SimpleNamespace(x=cx, y=cy))
        self.assertEqual(wiz._press_dot, 0)
        wiz._on_canvas_motion(types.SimpleNamespace(x=cx + 20, y=cy + 10))
        self.assertNotEqual(wiz.corners[0], (40, 30))
        wiz._on_canvas_release(types.SimpleNamespace(x=cx + 20, y=cy + 10))
        self.assertEqual(len(wiz.corners), 1)

    def test_motion_pans_when_not_on_corner(self):
        shell, wiz = self._corners_wizard()
        wiz._zoom = 2.0
        wiz._on_canvas_press(types.SimpleNamespace(x=10, y=10))
        wiz._on_canvas_motion(types.SimpleNamespace(x=80, y=80))
        self.assertTrue(wiz._moved)

    def test_motion_without_press(self):
        shell, wiz = self._corners_wizard()
        wiz._on_canvas_motion(types.SimpleNamespace(x=10, y=10))

    def test_reset_and_go_button(self):
        shell, wiz = self._corners_wizard()
        wiz.corners = [(1, 1), (2, 2), (3, 3), (4, 4)]
        wiz._sync_go_btn()
        self.assertEqual(str(wiz._go_btn.cget("state")), "normal")
        wiz._reset_corners()
        self.assertEqual(wiz.corners, [])
        self.assertEqual(str(wiz._go_btn.cget("state")), "disabled")
        wiz._go_btn = None
        wiz._sync_go_btn()

    def test_measure_corners_requires_four(self):
        shell, wiz = self._corners_wizard()
        wiz.corners = [(1, 1)]
        wiz.measure_corners()
        self.assertEqual(wiz.step, "corners")

    def test_measure_corners_success(self):
        shell, wiz = self._corners_wizard()
        wiz.corners = [(1, 1), (100, 1), (100, 80), (1, 80)]
        fake_mod = types.ModuleType("ulpp.scan_calib")
        fake_mod.measure_photo_corners = mock.Mock(return_value=FakeMeasurement())
        with mock.patch.dict(sys.modules, {"ulpp.scan_calib": fake_mod}):
            wiz.measure_corners()
        fake_mod.measure_photo_corners.assert_called_once()
        self.assertEqual(wiz.step, "result")
        self.assertFalse(wiz.measurement_plain)
        self.assertEqual(wiz.source, wiz.photo_path)

    def test_measure_corners_failure_stays_on_corners(self):
        shell, wiz = self._corners_wizard()
        wiz.corners = [(1, 1), (100, 1), (100, 80), (1, 80)]
        fake_mod = types.ModuleType("ulpp.scan_calib")
        fake_mod.measure_photo_corners = mock.Mock(
            side_effect=RuntimeError("四边形不合法"))
        with mock.patch.dict(sys.modules, {"ulpp.scan_calib": fake_mod}):
            wiz.measure_corners()
        self.assertEqual(wiz.step, "corners")
        self.assertEqual(wiz.error, "四边形不合法")

    def test_hit_corner(self):
        shell, wiz = self._corners_wizard()
        wiz.corners = [(40, 30)]
        cx, cy = wiz._canvas_xy(40, 30)
        self.assertEqual(wiz._hit_corner(cx, cy), 0)
        self.assertIsNone(wiz._hit_corner(cx + 100, cy + 100))


class ResultTests(WizardCase):
    def test_result_without_measurement_returns_after_title(self):
        shell, wiz = self._wizard()
        wiz.measurement = None
        wiz.step = "result"
        wiz.render()
        self.assertIsNone(wiz.measurement)

    def test_result_renders_spec_confidence_and_warnings(self):
        shell, wiz = self._wizard()
        wiz.measurement = FakeMeasurement(confidence=0.77,
                                          warnings=["mark_too_few: 刻度太少"])
        wiz.step = "result"
        wiz.render()
        labels = [w.cget("text") for w in wiz.body.winfo_children()
                  if w.winfo_class() == "Label"]
        joined = "\n".join(labels)
        self.assertIn("5", joined)
        self.assertIn("0.77", joined)
        self.assertIn("刻度太少", joined)

    def test_back_to_pick_prefers_corners_after_photo(self):
        shell, wiz = self._wizard()
        wiz.measurement = FakeMeasurement()
        wiz.go("result")
        wiz.photo_path = self._photo()
        wiz.back_to_pick()
        self.assertEqual(wiz.step, "corners")
        self.assertIsNone(wiz.measurement)

    def test_back_to_pick_without_photo_goes_scan(self):
        shell, wiz = self._wizard()
        wiz.measurement = FakeMeasurement()
        wiz.back_to_pick()
        self.assertEqual(wiz.step, "scan")

    def test_save_template_requires_measurement(self):
        shell, wiz = self._wizard()
        wiz.measurement = None
        wiz.save_template()
        self.assertEqual(shell.templates.items, [])

    def test_save_template_creates_and_selects(self):
        shell, wiz = self._wizard()
        wiz.measurement = FakeMeasurement()
        wiz.source = "/tmp/scan.png"
        wiz.save_template()
        self.assertEqual(len(shell.templates.items), 1)
        tpl = shell.templates.items[0]
        self.assertTrue(tpl.id.startswith("calib"))
        self.assertEqual(shell.flow.answer("paper"), "tpl:" + tpl.id)
        try:
            exists = wiz.winfo_exists()
        except Exception:
            exists = 0
        self.assertFalse(exists)

    def test_pick_file_passes_parent_and_filters(self):
        shell, wiz = self._wizard()
        with mock.patch("tkinter.filedialog.askopenfilename",
                        return_value="/tmp/x") as ask:
            self.assertEqual(wiz._pick_file("t", [("x", "*")]), "/tmp/x")
        self.assertIs(ask.call_args.kwargs["parent"], wiz)


class HelpTests(WizardCase):
    def test_help_plays_and_toggles(self):
        shell = self._shell()
        help_win = CartoonHelp(shell)
        self.pump()
        self.close_later(help_win)
        self.assertTrue(help_win.playing)
        help_win.toggle()
        self.assertFalse(help_win.playing)
        help_win.toggle()
        self.assertTrue(help_win.playing)
        help_win._schedule()
        help_win._next()
        help_win.playing = False
        help_win._next()

    def test_help_draws_three_frames(self):
        shell = self._shell()
        help_win = CartoonHelp(shell)
        self.pump()
        self.close_later(help_win)
        for index in (0, 1, 2):
            help_win.show(index)
            self.assertEqual(help_win.index, index)
            self.assertGreater(len(help_win.canvas.find_all()), 0)
            self.assertTrue(help_win.caption.cget("text"))

    def test_help_geom_falls_back_for_tiny_canvas(self):
        shell = self._shell()
        help_win = CartoonHelp(shell)
        self.pump()
        self.close_later(help_win)
        with mock.patch.object(help_win.canvas, "winfo_width", return_value=1), \
                mock.patch.object(help_win.canvas, "winfo_height", return_value=1), \
                mock.patch.object(help_win.canvas, "winfo_reqwidth",
                                  return_value=100), \
                mock.patch.object(help_win.canvas, "winfo_reqheight",
                                  return_value=80):
            w, h = help_win._geom()
        self.assertEqual((w, h), (100.0, 80.0))
