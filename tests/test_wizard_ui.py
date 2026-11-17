# -*- coding: utf-8 -*-
"""9 步位置校准向导（``ulpp.wizard``）的界面流程。"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest import mock

from PIL import Image

from ulpp.sheets import PrinterProfile
from ulpp import wizard as wizard_mod
from ulpp.wizard import CalibrationWizard

from .ui_harness import UiCase


def _fake_img(self, name):
    key = ("fake", name)
    if key not in self.images:
        self.images[key] = tk.PhotoImage(width=12, height=12, master=self)
    return self.images[key]


class WizardCase(UiCase):
    def _wizard(self, profile=None, on_save=None, patch_img=True):
        profile = profile or PrinterProfile()
        patcher = None
        if patch_img:
            patcher = mock.patch.object(CalibrationWizard, "img", _fake_img)
            patcher.start()
            self.addCleanup(patcher.stop)
            wiz = CalibrationWizard(self.root, profile, on_save=on_save,
                                    output_dir=str(self.tmpdir))
        else:
            with mock.patch.object(CalibrationWizard, "img", _fake_img):
                wiz = CalibrationWizard(self.root, profile, on_save=on_save,
                                        output_dir=str(self.tmpdir))
        self.pump()
        self.close_later(wiz)
        return wiz


class BasicsTests(WizardCase):
    def test_initial_step_and_texts(self):
        wiz = self._wizard()
        self.assertEqual(wiz.step, 1)
        self.assertEqual(wiz.lang, "zh_CN")
        self.assertEqual(wiz.T("cancel"), "取消")
        self.assertIn("第 1 步", wiz.T("step_of", title="位置校准", n=1, total=9))
        self.assertEqual(wiz.S(10), 10)
        self.assertIn(wiz.fam, wiz.f(10)[0])
        self.assertEqual(len(wiz.fp(20)), 2)
        self.assertIs(wiz.TH, wizard_mod.LIGHT)

    def test_theme_toggle_rebuilds_in_mono_and_back(self):
        wiz = self._wizard()
        wiz.toggle_theme()
        self.assertEqual(wiz.theme_key, "mono")
        self.assertIs(wiz.TH, wizard_mod.MONO)
        wiz.toggle_theme()
        self.assertEqual(wiz.theme_key, "light")

    def test_go_clamps_steps(self):
        wiz = self._wizard()
        wiz.go(0)
        self.assertEqual(wiz.step, 1)
        wiz.go(99)
        self.assertEqual(wiz.step, 9)
        wiz.go(3)
        self.assertEqual(wiz.step, 3)

    def test_next_respects_unanswered_questions(self):
        wiz = self._wizard()
        wiz.go(6)
        wiz.next()
        self.assertEqual(wiz.step, 6)
        wiz.pick_face("up")
        wiz.next()
        self.assertEqual(wiz.step, 7)
        wiz.next()
        self.assertEqual(wiz.step, 7)
        wiz.pick_edge("top")
        wiz.next()
        self.assertEqual(wiz.step, 8)
        wiz.next()
        self.assertEqual(wiz.step, 9)

    def test_next_labels(self):
        wiz = self._wizard()
        for step, key in ((5, "next_print"), (8, "next_fine"), (9, "save")):
            wiz.step = step
            self.assertEqual(wiz._next_label(), wiz.T(key))

    def test_clear_cancels_animation_job(self):
        wiz = self._wizard()
        wiz.go(4)
        self.assertIsNotNone(wiz.anim_job)
        job = wiz.anim_job
        wiz.clear()
        self.assertIsNone(wiz.anim_job)
        self.assertNotIn(job, [])

    def test_img_loads_and_caches_from_resources(self):
        wiz = self._wizard(patch_img=False)
        base = self.tmpdir / "assets" / "light" / "560"
        base.mkdir(parents=True)
        path = base / "tray_plain.png"
        Image.new("RGB", (8, 8), "white").save(path, format="GIF")
        wiz.images = {}
        with mock.patch.object(wizard_mod, "_resources", return_value=self.tmpdir):
            first = wiz.img("tray_plain.png")
            second = wiz.img("tray_plain.png")
        self.assertIs(first, second)
        self.assertGreater(first.width(), 0)

    def test_resources_prefers_meipass(self):
        with mock.patch.dict("os.environ", {"_MEIPASS": str(self.tmpdir)}):
            self.assertEqual(wizard_mod._resources(), Path(self.tmpdir))
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(wizard_mod._resources(),
                             Path(wizard_mod.__file__).resolve().parent)


class BuildStepTests(WizardCase):
    def test_all_nine_steps_build(self):
        wiz = self._wizard()
        for step in range(1, 10):
            wiz.go(step)
            self.assertEqual(wiz.step, step)
            self.assertTrue(wiz.left.winfo_exists())
            self.assertTrue(wiz.right.winfo_exists())

    def test_step1_profile_prefilled(self):
        wiz = self._wizard(PrinterProfile(name="My Printer", tray="Tray 1"))
        self.assertEqual(wiz.printer_var.get(), "My Printer")
        self.assertEqual(wiz.tray_var.get(), "Tray 1")

    def test_step1_defaults_when_profile_empty(self):
        wiz = self._wizard(PrinterProfile(name="", tray=""))
        self.assertEqual(wiz.printer_var.get(), "Xerox C8055")
        self.assertTrue(wiz.tray_var.get())

    def test_step4_animation_ticks(self):
        wiz = self._wizard()
        wiz.go(4)
        self.assertEqual(len(wiz.anim), 12)
        start = wiz.anim_i
        wiz._tick_anim()
        self.assertEqual(wiz.anim_i, (start + 1) % 12)
        wiz.anim = []
        wiz._tick_anim()

    def test_textcol_tipbox_checklist(self):
        wiz = self._wizard()
        wiz.textcol("标题", "正文", "提示")
        wiz.checklist(["第一", "第二"])
        labels = [w.cget("text") for w in wiz.right.winfo_children()
                  if w.winfo_class() == "Label"]
        self.assertIn("标题", labels)
        self.assertIn("正文", labels)

    def test_draw_sheet_modes_and_arrows(self):
        wiz = self._wizard()
        canvas = tk.Canvas(self.root, width=400, height=300)
        for mode in ("plain", "test_back", "faceup", "edge_top", "edge_bottom",
                     "edge_left", "edge_right"):
            canvas.delete("all")
            wiz.draw_sheet(canvas, 10, 10, 100, 140, mode, label="说明")
            self.assertGreater(len(canvas.find_all()), 2)
        canvas.destroy()

    def test_page_canvas_and_iso_view(self):
        wiz = self._wizard()
        canvas = wiz.page_canvas(100, 140, "plain", "说明")
        self.assertIsNotNone(canvas)
        label = wiz.iso_view("tray_plain.png")
        self.assertIsNotNone(label)

    def test_bind_all_binds_children(self):
        wiz = self._wizard()
        frame = tk.Frame(self.root)
        child = tk.Label(frame, text="x")
        child.pack()
        called = []
        wiz.bind_all(frame, lambda _e: called.append(1))
        self.assertTrue(frame.bind("<Button-1>"))
        self.assertTrue(child.bind("<Button-1>"))
        frame.destroy()


class InteractionTests(WizardCase):
    def test_pick_face_highlights_selection(self):
        wiz = self._wizard()
        wiz.go(6)
        wiz.pick_face("down")
        self.assertEqual(wiz.face, "down")
        self.assertEqual(int(wiz.cards6["down"].cget("highlightthickness")), 3)
        self.assertEqual(int(wiz.cards6["up"].cget("highlightthickness")), 2)

    def test_pick_edge_maps_to_short_and_long(self):
        wiz = self._wizard()
        wiz.go(7)
        for key, short in (("top", "short"), ("bottom", "short"),
                           ("left", "long"), ("right", "long")):
            wiz.pick_edge(key)
            self.assertEqual(wiz.edge_pos, key)
            self.assertEqual(wiz.edge, short)
            self.assertEqual(int(wiz.cards7[key].cget("highlightthickness")), 3)

    def test_feed_text_and_key_use_answers(self):
        wiz = self._wizard(PrinterProfile(feed="face_up_short"))
        wiz.face, wiz.edge = "down", "long"
        self.assertEqual(wiz.feed_key(), "face_down_long")
        self.assertIn("正面朝下", wiz.feed_text())
        wiz.face = None
        self.assertEqual(wiz.feed_key(), "face_up_short")

    def test_make_test_pdf_success_and_failure(self):
        wiz = self._wizard()
        wiz.go(5)
        with mock.patch.object(wizard_mod, "make_orientation_pdf") as make:
            wiz.make_test_pdf()
        make.assert_called_once()
        self.assertIn("已生成", wiz.print_lbl.cget("text"))
        self.assertEqual(wiz.print_btn.cget("text"), wiz.T("s5.again"))

        with mock.patch.object(wizard_mod, "make_orientation_pdf",
                               side_effect=OSError("写不了")):
            wiz.make_test_pdf()
        self.assertIn("写不了", wiz.print_lbl.cget("text"))

    def test_finish_saves_profile_and_offsets(self):
        saves = []
        wiz = self._wizard(on_save=lambda *args: saves.append(args))
        wiz.go(6)
        wiz.pick_face("down")
        wiz.go(7)
        wiz.pick_edge("left")
        wiz.go(9)
        wiz.printer_var.set("新机器")
        wiz.off_x_var.set(1.5)
        wiz.off_y_var.set(-2.5)
        wiz.finish()
        self.assertEqual(wiz.profile.name, "新机器")
        self.assertEqual(saves, [("face_down_long", 1.5, -2.5)])
        try:
            exists = wiz.winfo_exists()
        except Exception:
            exists = 0
        self.assertFalse(exists)

    def test_finish_blank_printer_keeps_old_name(self):
        wiz = self._wizard(PrinterProfile(name="旧名字"))
        wiz.go(6)
        wiz.pick_face("up")
        wiz.go(7)
        wiz.pick_edge("top")
        wiz.go(9)
        wiz.printer_var.set("   ")
        wiz.finish()
        self.assertEqual(wiz.profile.name, "旧名字")

    def test_finish_bad_offsets_and_callback_errors_are_soft(self):
        calls = []

        def on_save(*args):
            calls.append(args)
            raise RuntimeError("callback boom")

        wiz = self._wizard(on_save=on_save)
        wiz.go(9)
        wiz.off_x_var = mock.Mock()
        wiz.off_x_var.get.side_effect = tk.TclError("not a number")
        wiz.off_y_var = mock.Mock()
        wiz.off_y_var.get.return_value = 0.0
        wiz.finish()
        self.assertEqual(calls, [("face_up_short", wiz.off_x, 0.0)])

    def test_step8_note_for_face_down_and_up(self):
        wiz = self._wizard()
        wiz.face, wiz.edge = "down", "short"
        wiz.go(8)
        texts = [w.cget("text") for w in wiz.right.winfo_children()
                 if w.winfo_class() == "Label"]
        self.assertTrue(any(wiz.T("s8.note_down") == t for t in texts))
        wiz.face = "up"
        wiz.go(8)
        texts = [w.cget("text") for w in wiz.right.winfo_children()
                 if w.winfo_class() == "Label"]
        self.assertTrue(any(wiz.T("s8.note_up") == t for t in texts))
