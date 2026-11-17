# -*- coding: utf-8 -*-
"""v2 三屏内容（``ulpp.ui.screens``）：选纸 / 方向 / 输出。"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest import mock

from ulpp.presets import PRESETS, by_key
from ulpp.templates import Template
from ulpp.ui import screens

from .ui_harness import FakeMeasurement, UiCase


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _find(widget, cls, text=None):
    for child in _walk(widget):
        if child.winfo_class() == cls:
            if text is None:
                return child
            try:
                if child.cget("text") == text:
                    return child
            except tk.TclError:
                pass
    return None


def _all(widget, cls):
    return [c for c in _walk(widget) if c.winfo_class() == cls]


class SheetScreenTests(UiCase):
    def test_default_sheet_screen_builds_preview_and_buttons(self):
        shell = self.make_shell()
        self.assertEqual(shell.flow.current, "sheet")
        self.assertIsNotNone(_find(shell.root, "Canvas"))
        names = [w.cget("text") for w in _all(shell.root, "Button")]
        self.assertIn(shell.T("calib.new_paper"), names)

    def test_combo_picks_preset_and_callbacks_run(self):
        shell = self.make_shell()
        combo = _find(shell.root, "TCombobox")
        self.assertIsNotNone(combo)
        idx = len(shell.templates.items) + len(PRESETS) - 1
        combo.current(idx)
        combo.event_generate("<<ComboboxSelected>>")
        self.pump()
        self.assertEqual(shell.flow.answer("paper"),
                         PRESETS[len(PRESETS) - 1].key)

    def test_combo_ignores_invalid_current(self):
        shell = self.make_shell()
        combo = _find(shell.root, "TCombobox")
        before = shell.flow.answer("paper")
        combo.set("手写的值")
        combo.event_generate("<<ComboboxSelected>>")
        self.pump()
        self.assertEqual(shell.flow.answer("paper"), before)

    def test_selecting_template_uses_template(self):
        shell = self.make_shell()
        tpl = Template(id=Template.new_id("t"), name="我的纸", cols=3, rows=4,
                       cell_w_mm=50, cell_h_mm=40, pitch_x_mm=52, pitch_y_mm=42)
        shell.templates.upsert(tpl)
        shell.flow.answer("paper", "tpl:" + tpl.id)
        shell.render()
        combo = _find(shell.root, "TCombobox")
        combo.current(0)
        combo.event_generate("<<ComboboxSelected>>")
        self.pump()
        self.assertEqual(shell.flow.answer("paper"), "tpl:" + tpl.id)

    def test_measurement_banner_ok_shape(self):
        shell = self.make_shell()
        shell.measurement = FakeMeasurement()
        shell.render()
        labels = [w.cget("text") for w in _all(shell.root, "Label")]
        self.assertTrue(any("41.5" in t for t in labels))

    def test_measurement_banner_low_confidence_and_warning_reasons(self):
        shell = self.make_shell()
        shell.measurement = FakeMeasurement(ok=False, confidence=0.2)
        shell.render()
        labels = [w.cget("text") for w in _all(shell.root, "Label")]
        joined = "\n".join(labels)
        self.assertIn("low_contrast", joined)
        self.assertIn("no_marks", joined)

    def test_scan_error_banner(self):
        shell = self.make_shell()
        shell.scan_error = "文件坏了"
        shell.render()
        labels = [w.cget("text") for w in _all(shell.root, "Label")]
        self.assertTrue(any("文件坏了" in t for t in labels))

    def test_save_and_rescan_buttons_are_wired(self):
        shell = self.make_shell()
        shell.measurement = FakeMeasurement()
        shell.save_measurement = mock.Mock()
        shell.ask_scan = mock.Mock()
        shell.render()
        buttons = {w.cget("text"): w for w in _all(shell.root, "Button")}
        buttons[shell.T("sheet.save_tpl")].invoke()
        buttons[shell.T("sheet.rescan")].invoke()
        shell.save_measurement.assert_called_once()
        shell.ask_scan.assert_called_once()

    def test_selected_falls_back_for_broken_paper_answer(self):
        shell = self.make_shell()
        shell.flow.answer("paper", "tpl:missing")
        self.assertEqual(screens._selected(shell).key, "45")
        shell.flow.answer("paper", "totally-unknown")
        self.assertEqual(screens._selected(shell).key, "45")
        shell.flow.answer("paper", "not-a-key")
        self.assertEqual(screens._selected(shell).key, "45")

    def test_display_helpers(self):
        shell = self.make_shell()
        preset = by_key("45")
        self.assertEqual(screens._name(preset), preset.title)
        self.assertEqual(screens._display(shell, preset), preset.title)
        tpl = Template(id="x", name="纸", cols=1, rows=1, cell_w_mm=10,
                       cell_h_mm=10, pitch_x_mm=10, pitch_y_mm=10)
        self.assertEqual(screens._name(tpl), "纸")
        self.assertIn("纸", screens._display(shell, tpl))


class OrientScreenTests(UiCase):
    def test_direction_label_known_and_unknown(self):
        shell = self.make_shell(flow=self.make_flow(index=1))
        for feed in ("face_up_short", "face_up_long", "face_down_short",
                     "face_down_long"):
            shell.feed = feed
            self.assertEqual(shell.direction_label(), shell.T("feed." + feed))
        shell.feed = "sideways"
        self.assertEqual(shell.direction_label(), shell.T("orient.unknown"))
        shell.feed = ""
        self.assertEqual(shell.direction_label(), shell.T("orient.unknown"))

    def test_orient_screen_buttons(self):
        shell = self.make_shell(flow=self.make_flow(index=1))
        shell.open_wizard = mock.Mock()
        shell.render()
        buttons = {w.cget("text"): w for w in _all(shell.root, "Button")}
        buttons[shell.T("orient.calibrate")].invoke()
        shell.open_wizard.assert_called_once()


class OutputScreenTests(UiCase):
    def _at_output(self, **kw):
        return self.make_shell(flow=self.make_flow(index=2), **kw)

    def test_empty_output_screen(self):
        shell = self._at_output()
        labels = [w.cget("text") for w in _all(shell.root, "Label")]
        self.assertIn(shell.T("output.empty"), labels)
        self.assertIsNotNone(_find(shell.root, "Text"))

    def test_files_and_images_listed_and_clear_button(self):
        shell = self._at_output()
        shell.files = ["/tmp/a.pdf", "/tmp/b.pdf", "/tmp/c.pdf", "/tmp/d.pdf"]
        shell.images = ["/tmp/x.png"]
        shell.clear_files = mock.Mock()
        shell.render()
        labels = [w.cget("text") for w in _all(shell.root, "Label")]
        joined = "\n".join(labels)
        self.assertIn("a.pdf", joined)
        self.assertIn("…", joined)
        self.assertIn(shell.T("output.images", n=1), joined)
        buttons = {w.cget("text"): w for w in _all(shell.root, "Button")}
        buttons[shell.T("output.clear")].invoke()
        shell.clear_files.assert_called_once()

    def test_output_done_and_error(self):
        shell = self._at_output()
        shell.output_path = "/tmp/production.pdf"
        shell.output_error = "boom"
        shell.open_output = mock.Mock()
        shell.generate = mock.Mock()
        shell.render()
        labels = [w.cget("text") for w in _all(shell.root, "Label")]
        joined = "\n".join(labels)
        self.assertIn("production.pdf", joined)
        self.assertIn("boom", joined)
        buttons = {w.cget("text"): w for w in _all(shell.root, "Button")}
        buttons[shell.T("output.open")].invoke()
        buttons[shell.T("output.again")].invoke()
        shell.open_output.assert_called_once()
        shell.generate.assert_called_once()

    def test_pick_buttons_are_wired(self):
        shell = self._at_output()
        for name in ("pick_pdfs", "pick_folder", "pick_zip", "generate",
                     "pick_out_dir"):
            setattr(shell, name, mock.Mock())
        shell.render()
        buttons = {w.cget("text"): w for w in _all(shell.root, "Button")}
        buttons[shell.T("output.pick")].invoke()
        buttons[shell.T("output.add_folder")].invoke()
        buttons[shell.T("output.add_zip")].invoke()
        buttons[shell.T("output.generate")].invoke()
        buttons[shell.T("output.browse")].invoke()
        shell.pick_pdfs.assert_called_once()
        shell.pick_folder.assert_called_once()
        shell.pick_zip.assert_called_once()
        shell.generate.assert_called_once()
        shell.pick_out_dir.assert_called_once()

    def test_option_widgets_write_answers(self):
        shell = self._at_output()
        shell.first_page_only.set(True)
        shell.text_align.set("right")
        shell.text_uniform.set(True)
        shell.make_proof.set(False)
        shell.make_csv.set(False)
        shell.make_marks.set(True)
        shell.out_dir.set("/tmp/out")
        shell.base_name.set("名字")
        shell.on_options()
        a = shell.flow.answers
        self.assertTrue(a["pages_first"])
        self.assertEqual(a["align"], "right")
        self.assertTrue(a["uniform"])
        self.assertFalse(a["proof"])
        self.assertFalse(a["csv"])
        self.assertTrue(a["marks"])
        self.assertEqual(a["out_dir"], "/tmp/out")
        self.assertEqual(a["base_name"], "名字")

    def test_unknown_builder_falls_back_to_sheet(self):
        shell = self._at_output()
        shell.flow.steps = ("mystery",)
        shell.flow.index = 0
        shell.render()
        self.assertIsNotNone(_find(shell.root, "TCombobox"))

    def test_preview_handles_template_and_preset(self):
        shell = self.make_shell()
        tpl = Template(id="t", name="纸", cols=2, rows=2, cell_w_mm=10,
                       cell_h_mm=10, pitch_x_mm=11, pitch_y_mm=11)
        for item in (tpl, by_key("45")):
            canvas = screens._preview(shell, shell.root, item)
            self.assertGreaterEqual(len(canvas.find_all()), 3)
            canvas.destroy()

    def test_button_without_command_is_disabled(self):
        shell = self.make_shell()
        btn = screens._button(shell, shell.root, "x")
        self.assertEqual(btn.cget("state"), "disabled")
        btn.destroy()

    def test_spec_text_contains_counts(self):
        shell = self.make_shell()
        text = screens._spec(shell, by_key("45"))
        self.assertIn("5", text)
        self.assertIn("9", text)
