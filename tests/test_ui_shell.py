# -*- coding: utf-8 -*-
"""v2 外壳（``ulpp.ui.shell``）：骨架、导航、扫描/选文件、生成线程、外部打开。"""
from __future__ import annotations

import os
import queue
import types
from pathlib import Path
from unittest import mock

import tkinter as tk

from ulpp.templates import Template
from ulpp.ui import shell as ShellMod
from ulpp.ui.flow import Flow

from .ui_harness import FakeMeasurement, UiCase

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.pdf"


class InlineThread:
    """把后台线程变成同步执行，测试才能断言生成结果。"""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon

    def start(self):
        if self.target:
            self.target(*self.args, **self.kwargs)

    def is_alive(self):
        return False


class ShellBasics(UiCase):
    def test_language_selection_and_fallback(self):
        shell = self.make_shell(lang="en_US")
        self.assertEqual(shell.lang, "en_US")
        self.assertTrue(shell.T("next").startswith("Next"))
        shell2 = self.make_shell(lang="xx_YY")
        self.assertEqual(shell2.lang, "zh_CN")

    def test_theme_and_alpha_from_environment(self):
        with mock.patch.dict(os.environ, {"ULPP_THEME": "mono", "ULPP_ALPHA": "0.8"}):
            shell = self.make_shell()
        self.assertEqual(shell.P["name"], "mono")

    def test_store_failure_is_soft(self):
        with mock.patch.object(ShellMod.SheetStore, "load",
                               side_effect=OSError("no config")):
            shell = self.make_shell()
        self.assertIsNone(shell.store)
        self.assertEqual(shell.feed, "")
        self.assertEqual(shell._read_feed(), "")

    def test_feed_from_store_and_failure(self):
        shell = self.make_shell()
        shell.store = mock.Mock()
        shell.store.get_printer.return_value = mock.Mock(feed="face_down_short")
        self.assertEqual(shell._read_feed(), "face_down_short")
        shell.store.get_printer.side_effect = RuntimeError("bad")
        self.assertEqual(shell._read_feed(), "")

    def test_T_tolerates_bad_format_placeholders(self):
        shell = self.make_shell()
        shell.tx = dict(shell.tx)
        shell.tx["bad"] = "{missing}"
        self.assertEqual(shell.T("bad", x=1), "{missing}")
        self.assertEqual(shell.T("does.not.exist"), "does.not.exist")

    def test_status_text_has_state_and_path(self):
        shell = self.make_shell()
        text = shell._status_text()
        self.assertIn(str(shell.state_file), text)
        self.assertIn(shell.T("state_saved"), text)
        shell.flow.last_error = "OSError: disk full"
        self.assertIn(shell.T("state_unsaved"), shell._status_text())

    def test_save_can_be_disabled(self):
        shell = self.make_shell(autosave=False)
        shell.flow.save = mock.Mock()
        shell.save()
        shell.flow.save.assert_not_called()
        self.assertTrue(shell.flow.last_error is None)


class NavigationTests(UiCase):
    def test_next_prev_goto(self):
        shell = self.make_shell()
        shell.next_step()
        self.assertEqual(shell.flow.current, "orient")
        shell.prev_step()
        self.assertEqual(shell.flow.current, "sheet")
        shell.goto("output")
        self.assertEqual(shell.flow.current, "output")
        shell.goto(0)
        self.assertEqual(shell.flow.current, "sheet")

    def test_skip_middle_and_last(self):
        shell = self.make_shell(flow=Flow(index=1))
        shell.skip_step()
        self.assertEqual(shell.flow.current, "output")
        self.assertTrue(shell.flow.is_skipped("orient"))

        shell = self.make_shell(flow=Flow(index=2))
        shell.skip_step()
        self.assertTrue(shell.flow.finished)
        self.assertFalse(self._exists())

    def _exists(self):
        try:
            return bool(self.root.winfo_exists())
        except tk.TclError:
            return False

    def test_finish_and_close_save(self):
        shell = self.make_shell(flow=Flow(index=2))
        shell.finish_step()
        self.assertTrue(shell.flow.finished)
        self.assertTrue((self.state_dir / "v2_flow.json").is_file())
        self.assertFalse(self._exists())

    def test_render_marks_skipped_and_done_dots(self):
        shell = self.make_shell(flow=Flow(index=1))
        shell.flow.skipped = ["sheet"]
        shell.render()
        self.assertGreaterEqual(len(shell._dots.winfo_children()), 3)

    def test_on_change_updates_status(self):
        shell = self.make_shell()
        shell.on_change()
        self.assertTrue((self.state_dir / "v2_flow.json").is_file())

    def test_reset_flow(self):
        shell = self.make_shell(flow=Flow(index=2, answers={"paper": "45"}))
        shell.reset_flow()
        self.assertEqual(shell.flow.index, 0)
        self.assertEqual(shell.flow.answers, {})


class ScanTests(UiCase):
    def test_ask_scan_cancelled(self):
        shell = self.make_shell()
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=""):
            shell.ask_scan()
        self.assertIsNone(shell.measurement)

    def test_ask_scan_success(self):
        shell = self.make_shell()
        with mock.patch("tkinter.filedialog.askopenfilename",
                        return_value="/tmp/scan.png"), \
                mock.patch.object(ShellMod, "measure_file",
                                  return_value=FakeMeasurement()) as measure:
            shell.ask_scan()
        measure.assert_called_once()
        self.assertIsNotNone(shell.measurement)
        self.assertEqual(shell.scan_source, "/tmp/scan.png")

    def test_ask_scan_failure_sets_error(self):
        shell = self.make_shell()
        with mock.patch("tkinter.filedialog.askopenfilename",
                        return_value="/tmp/scan.png"), \
                mock.patch.object(ShellMod, "measure_file",
                                  side_effect=ValueError("太淡")):
            shell.ask_scan()
        self.assertEqual(shell.scan_error, "太淡")
        self.assertIsNone(shell.measurement)

    def test_ask_photo_calibrated_cancel_success_and_failure(self):
        shell = self.make_shell()
        with mock.patch.object(shell, "_pick_photo", return_value=""):
            shell.ask_photo_calibrated()
        self.assertIsNone(shell.measurement)

        import ulpp.scan_calib as scan_calib

        fake = mock.Mock(return_value=FakeMeasurement())
        with mock.patch.object(shell, "_pick_photo", return_value="/tmp/p.jpg"), \
                mock.patch.object(scan_calib, "measure_photo_calibrated", fake):
            shell.ask_photo_calibrated()
        self.assertIsNotNone(shell.measurement)
        self.assertFalse(shell.photo_fallback)

        with mock.patch.object(shell, "_pick_photo", return_value="/tmp/p.jpg"), \
                mock.patch.object(scan_calib, "measure_photo_calibrated",
                                  side_effect=RuntimeError("看不清")):
            shell.ask_photo_calibrated()
        self.assertEqual(shell.scan_error, "看不清")

    def test_ask_photo_plain_cancel_success_and_failure(self):
        shell = self.make_shell()
        with mock.patch.object(shell, "_pick_photo", return_value=""):
            shell.ask_photo_plain()
        self.assertIsNone(shell.measurement)

        import ulpp.scan_photo as scan_photo

        with mock.patch.object(shell, "_pick_photo", return_value="/tmp/p.jpg"), \
                mock.patch.object(scan_photo, "measure_photo",
                                  return_value=FakeMeasurement()):
            shell.ask_photo_plain()
        self.assertIsNotNone(shell.measurement)
        self.assertTrue(shell.photo_fallback)

        with mock.patch.object(shell, "_pick_photo", return_value="/tmp/p.jpg"), \
                mock.patch.object(scan_photo, "measure_photo",
                                  side_effect=RuntimeError("没纸边")):
            shell.ask_photo_plain()
        self.assertEqual(shell.scan_error, "没纸边")

    def test_pick_photo_dialog(self):
        shell = self.make_shell()
        with mock.patch("tkinter.filedialog.askopenfilename",
                        return_value="/tmp/a.png"):
            self.assertEqual(shell._pick_photo(), "/tmp/a.png")

    def test_save_board_cancel_success_failure(self):
        shell = self.make_shell()
        with mock.patch("tkinter.filedialog.asksaveasfilename", return_value=""):
            shell.save_board()
        self.assertIsNone(shell.scan_error)

        import ulpp.scan_board as scan_board

        shell._open_path = mock.Mock()
        with mock.patch("tkinter.filedialog.asksaveasfilename",
                        return_value="/tmp/board.pdf"), \
                mock.patch.object(scan_board, "make_board_pdf") as make:
            shell.save_board()
        make.assert_called_once_with("/tmp/board.pdf")
        shell._open_path.assert_called_once_with("/tmp/board.pdf")

        with mock.patch("tkinter.filedialog.asksaveasfilename",
                        return_value="/tmp/board.pdf"), \
                mock.patch.object(scan_board, "make_board_pdf",
                                  side_effect=OSError("只读")):
            shell.save_board()
        self.assertEqual(shell.scan_error, "只读")

    def test_save_measurement_without_result_is_noop(self):
        shell = self.make_shell()
        shell.save_measurement()
        self.assertEqual(shell.templates.items, [])

    def test_save_measurement_creates_template_and_selects_it(self):
        shell = self.make_shell()
        shell.measurement = FakeMeasurement()
        shell.scan_source = "/tmp/scan.png"
        shell.save_measurement()
        self.assertIsNone(shell.measurement)
        self.assertEqual(len(shell.templates.items), 1)
        tpl = shell.templates.items[0]
        self.assertTrue(tpl.id.startswith("scan"))
        self.assertEqual(shell.flow.answer("paper"), "tpl:" + tpl.id)


class WizardEntryTests(UiCase):
    def test_open_wizard_passes_profile_and_saves_result(self):
        shell = self.make_shell()
        shell.feed = "face_up_short"
        captured = {}

        class FakeWizard:
            def __init__(self, master, profile=None, on_save=None, output_dir=None):
                captured.update(master=master, profile=profile,
                                on_save=on_save, output_dir=output_dir)

        import ulpp.wizard as wizard_mod

        with mock.patch.object(wizard_mod, "CalibrationWizard", FakeWizard):
            shell.open_wizard()
        self.assertIs(captured["master"], self.root)
        self.assertIsNotNone(captured["on_save"])
        captured["on_save"]("face_down_long", 1.5, -2.0)
        self.assertEqual(shell.feed, "face_down_long")
        self.assertIsNotNone(shell.store)
        printer = shell.store.get_printer()
        self.assertEqual(printer.feed, "face_down_long")
        self.assertEqual(printer.offset_x_mm, 1.5)
        self.assertEqual(printer.offset_y_mm, -2.0)

    def test_open_wizard_callback_tolerates_store_errors(self):
        shell = self.make_shell()
        captured = {}

        class FakeWizard:
            def __init__(self, master, profile=None, on_save=None, output_dir=None):
                captured["on_save"] = on_save

        import ulpp.wizard as wizard_mod

        with mock.patch.object(wizard_mod, "CalibrationWizard", FakeWizard):
            shell.open_wizard()
        shell.store = mock.Mock()
        shell.store.get_printer.side_effect = RuntimeError("bad")
        captured["on_save"]("face_up_long", 0, 0)     # 不应抛
        self.assertEqual(shell.feed, "face_up_long")

    def test_open_wizard_uses_default_profile_when_store_missing(self):
        shell = self.make_shell()
        shell.store = None
        captured = {}

        class FakeWizard:
            def __init__(self, master, profile=None, on_save=None, output_dir=None):
                captured.update(profile=profile, on_save=on_save)

        import ulpp.wizard as wizard_mod

        with mock.patch.object(wizard_mod, "CalibrationWizard", FakeWizard):
            shell.open_wizard()
        self.assertEqual(captured["profile"].feed, "face_up_short")
        captured["on_save"]("face_down_short", 0, 0)
        self.assertEqual(shell.feed, "face_down_short")


class InputTests(UiCase):
    def test_attach_text_box_restores_and_tracks_content(self):
        shell = self.make_shell()
        shell.content_text = "以前粘的字"
        box = tk.Text(self.root)
        shell.attach_text_box(box)
        self.assertEqual(box.get("1.0", "end-1c"), "以前粘的字")
        self.assertTrue(box.bind("<KeyRelease>"))
        box.insert("end", "，新的")
        self.assertIn("新的", box.get("1.0", "end-1c"))
        box.destroy()

    def test_pick_pdfs_folder_zip(self):
        shell = self.make_shell()
        shell._add_inputs = mock.Mock()
        with mock.patch("tkinter.filedialog.askopenfilenames",
                        return_value=("/tmp/a.pdf",)):
            shell.pick_pdfs()
        shell._add_inputs.assert_called_with(["/tmp/a.pdf"])

        with mock.patch("tkinter.filedialog.askdirectory",
                        return_value="/tmp/dir"):
            shell.pick_folder()
        shell._add_inputs.assert_called_with(["/tmp/dir"])

        with mock.patch("tkinter.filedialog.askopenfilename",
                        return_value="/tmp/a.zip"):
            shell.pick_zip()
        shell._add_inputs.assert_called_with(["/tmp/a.zip"])

    def test_pick_cancelled_does_nothing(self):
        shell = self.make_shell()
        shell._add_inputs = mock.Mock()
        with mock.patch("tkinter.filedialog.askopenfilenames", return_value=()):
            shell.pick_pdfs()
        with mock.patch("tkinter.filedialog.askdirectory", return_value=""):
            shell.pick_folder()
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=""):
            shell.pick_zip()
        shell._add_inputs.assert_called_once_with([])

    def test_add_inputs_collects_images_and_pdfs(self):
        shell = self.make_shell()
        img = self.tmpdir / "a.png"
        img.write_bytes(b"x")
        sub = self.tmpdir / "sub"
        sub.mkdir()
        (sub / "b.JPG").write_bytes(b"x")
        with mock.patch("ulpp.cli.expand_inputs", return_value=["/tmp/a.pdf"]):
            shell._add_inputs([str(img), str(sub)])
        self.assertEqual(shell.files, ["/tmp/a.pdf"])
        self.assertEqual(set(shell.images), {str(img), str(sub / "b.JPG")})
        self.assertIsNone(shell.output_error)

        with mock.patch("ulpp.cli.expand_inputs", return_value=["/tmp/a.pdf"]):
            shell._add_inputs(["/tmp/a.pdf"])
        self.assertEqual(shell.files, ["/tmp/a.pdf"])     # 去重

    def test_add_inputs_expand_failure_sets_error(self):
        shell = self.make_shell()
        with mock.patch("ulpp.cli.expand_inputs", side_effect=ValueError("坏 zip")):
            shell._add_inputs(["/tmp/a.zip"])
        self.assertEqual(shell.output_error, "坏 zip")
        self.assertEqual(shell.files, [])

    def test_pick_out_dir(self):
        shell = self.make_shell()
        with mock.patch("tkinter.filedialog.askdirectory", return_value="/tmp/out"):
            shell.pick_out_dir()
        self.assertEqual(shell.out_dir.get(), "/tmp/out")
        self.assertEqual(shell.flow.answers["out_dir"], "/tmp/out")

    def test_clear_files(self):
        shell = self.make_shell()
        shell.files = [SAMPLE.as_posix()]
        shell.images = ["a.png"]
        shell.output_path = "x"
        shell.clear_files()
        self.assertEqual(shell.files, [])
        self.assertEqual(shell.images, [])
        self.assertIsNone(shell.output_path)

    def test_clear_content_clears_text_box(self):
        shell = self.make_shell()
        box = tk.Text(self.root)
        box.insert("1.0", "abc")
        shell.attach_text_box(box)
        shell.files = ["a"]
        shell.images = ["b"]
        shell.output_error = "e"
        shell.clear_content()
        self.assertEqual(shell.content_text, "")
        self.assertEqual(box.get("1.0", "end-1c"), "")
        self.assertEqual(shell.files, [])
        self.assertEqual(shell.images, [])
        self.assertIsNone(shell.output_error)
        box.destroy()

    def test_out_dir_priority(self):
        shell = self.make_shell()
        self.assertTrue(shell._out_dir().endswith("ulpp输出"))
        shell.files = [str(self.tmpdir / "input" / "a.pdf")]
        self.assertEqual(shell._out_dir(),
                         str(self.tmpdir / "input" / "ulpp输出"))
        shell.out_dir.set("/tmp/custom")
        self.assertEqual(shell._out_dir(), "/tmp/custom")

    def test_drop_path(self):
        shell = self.make_shell()
        event = types.SimpleNamespace(data="{%s}" % (self.tmpdir / "a b.pdf"))
        self.assertEqual(shell.drop_path(event), str(self.tmpdir / "a b.pdf"))
        self.assertIsNone(shell.drop_path(types.SimpleNamespace(data="{")))

    def test_on_drop_adds_inputs(self):
        shell = self.make_shell()
        shell._add_inputs = mock.Mock()
        event = types.SimpleNamespace(data="{%s}" % SAMPLE)
        shell._on_drop(event)
        shell._add_inputs.assert_called_once_with([str(SAMPLE)])

    def test_bind_drop_noop_without_dnd(self):
        shell = self.make_shell()
        widget = mock.Mock()
        shell.bind_drop(widget, lambda p: None)
        widget.drop_target_register.assert_not_called()

    def test_bind_drop_registers_and_handles_errors(self):
        shell = self.make_shell()
        widget = mock.Mock()
        with mock.patch.object(ShellMod, "_HAS_DND", True), \
                mock.patch.object(ShellMod, "DND_FILES", "Files"):
            shell.bind_drop(widget, lambda p: None)
        widget.drop_target_register.assert_called_once()

        widget = mock.Mock()
        widget.drop_target_register.side_effect = RuntimeError("no dnd")
        with mock.patch.object(ShellMod, "_HAS_DND", True), \
                mock.patch.object(ShellMod, "DND_FILES", "Files"):
            shell.bind_drop(widget, lambda p: None)     # 不抛


class GenerateTests(UiCase):
    def _shell(self):
        shell = self.make_shell(flow=Flow(index=2))
        return shell

    def test_generate_without_content_sets_error(self):
        shell = self._shell()
        shell.generate()
        self.assertEqual(shell.output_error, shell.T("output.need_content"))
        self.assertIsNone(shell.output_path)

    def test_generate_while_worker_alive_returns(self):
        shell = self._shell()
        shell._worker = mock.Mock()
        shell._worker.is_alive.return_value = True
        shell.content_text = "abc"
        shell.generate()
        self.assertIsNone(shell.output_error)

    def test_generate_success_inline(self):
        shell = self._shell()
        shell.content_text = "标签"
        shell._text_box = None
        info = mock.Mock()
        info.pages = [mock.Mock(warnings=["w1"])]
        info.stickers = 1
        outs = {"production": "/tmp/production.pdf"}
        with mock.patch.object(ShellMod, "parse_many", return_value=[info]), \
                mock.patch.object(ShellMod, "build_all", return_value=outs) as build, \
                mock.patch.object(ShellMod.threading, "Thread", InlineThread):
            shell.generate()
        self.assertEqual(shell.output_path, "/tmp/production.pdf")
        self.assertIsNone(shell.output_error)
        kwargs = build.call_args.kwargs
        self.assertEqual(kwargs["base_name"], "标签")
        self.assertTrue(kwargs["make_proof"])
        self.assertTrue(kwargs["make_csv"])
        self.assertEqual(kwargs["text_align"], "center")

    def test_generate_error_inline(self):
        shell = self._shell()
        shell.content_text = "标签"
        shell._text_box = None
        with mock.patch.object(ShellMod, "parse_many", return_value=[]), \
                mock.patch.object(ShellMod, "build_all",
                                  side_effect=RuntimeError("no space")), \
                mock.patch.object(ShellMod.threading, "Thread", InlineThread):
            shell.generate()
        self.assertEqual(shell.output_error, "no space")
        self.assertIsNone(shell.output_path)

    def test_generate_uses_files_first_page_and_custom_options(self):
        shell = self._shell()
        shell.files = ["/tmp/a.pdf"]
        shell.first_page_only.set(True)
        shell.make_proof.set(False)
        shell.make_csv.set(False)
        shell.make_marks.set(True)
        shell.text_align.set("left")
        shell.text_uniform.set(True)
        shell.base_name.set("   ")
        info = mock.Mock(pages=[], stickers=0)
        with mock.patch.object(ShellMod, "parse_many", return_value=[info]) as parse, \
                mock.patch.object(ShellMod, "build_all",
                                  return_value={"production": "x"}) as build, \
                mock.patch.object(ShellMod.threading, "Thread", InlineThread):
            shell.generate()
        parse.assert_called_once_with(["/tmp/a.pdf"], first_page_only=True)
        kwargs = build.call_args.kwargs
        self.assertEqual(kwargs["base_name"], "标签")
        self.assertFalse(kwargs["make_proof"])
        self.assertFalse(kwargs["make_csv"])
        self.assertEqual(kwargs["text_align"], "left")
        self.assertTrue(kwargs["text_uniform"])

    def test_poll_generate_handles_progress_then_done(self):
        shell = self._shell()
        shell._queue = queue.Queue()
        shell._queue.put(("progress", 2, 4))
        shell._queue.put(("done", {"production": "/tmp/x.pdf"}))
        shell._poll_generate()
        self.assertEqual(shell.output_path, "/tmp/x.pdf")
        self.assertIsNone(shell._worker)

    def test_poll_generate_handles_error(self):
        shell = self._shell()
        shell._queue = queue.Queue()
        shell._queue.put(("error", "炸了"))
        shell._poll_generate()
        self.assertEqual(shell.output_error, "炸了")

    def test_poll_generate_empty_schedules_again(self):
        shell = self._shell()
        shell._queue = queue.Queue()
        with mock.patch.object(self.root, "after") as after:
            shell._poll_generate()
        after.assert_called_once_with(120, shell._poll_generate)


class OpenPathTests(UiCase):
    def test_open_path_darwin(self):
        shell = self.make_shell()
        with mock.patch("sys.platform", "darwin"), \
                mock.patch("subprocess.Popen") as popen:
            shell._open_path("/tmp/x.pdf")
        popen.assert_called_once_with(["open", "/tmp/x.pdf"])

    def test_open_path_other_unix(self):
        shell = self.make_shell()
        with mock.patch.object(ShellMod.os, "name", "posix"), \
                mock.patch("sys.platform", "linux"), \
                mock.patch("subprocess.Popen") as popen:
            shell._open_path("/tmp/x.pdf")
        popen.assert_called_once_with(["xdg-open", "/tmp/x.pdf"])

    def test_open_path_windows(self):
        shell = self.make_shell()
        with mock.patch.object(ShellMod.os, "name", "nt"), \
                mock.patch("os.startfile", create=True) as start:
            shell._open_path("C:/x.pdf")
        start.assert_called_once_with("C:/x.pdf")

    def test_open_path_swallows_errors(self):
        shell = self.make_shell()
        with mock.patch("subprocess.Popen", side_effect=OSError("no opener")):
            shell._open_path("/tmp/x.pdf")

    def test_open_output_only_when_path(self):
        shell = self.make_shell()
        shell._open_path = mock.Mock()
        shell.open_output()
        shell._open_path.assert_not_called()
        shell.output_path = "/tmp/out.pdf"
        shell.open_output()
        shell._open_path.assert_called_once_with("/tmp/out.pdf")


class DialogsAndEntryTests(UiCase):
    def test_open_calibrate(self):
        shell = self.make_shell()
        import ulpp.ui.calibrate as cal

        with mock.patch.object(cal, "CalibrateWizard") as cls:
            shell.open_calibrate()
        cls.assert_called_once_with(shell)

    def test_open_partial(self):
        shell = self.make_shell()
        import ulpp.ui.partial as part

        with mock.patch.object(part, "PartialWindow") as cls:
            shell.open_partial()
        cls.assert_called_once_with(shell)

    def test_open_advanced(self):
        shell = self.make_shell()
        import ulpp.ui.advanced as adv

        with mock.patch.object(adv, "AdvancedDialog") as cls:
            shell.open_advanced()
        cls.assert_called_once_with(shell)

    def test_apply_advanced_selects_template(self):
        shell = self.make_shell()
        tpl = Template(id="adv1", name="改过的纸", cols=2, rows=3,
                       cell_w_mm=40, cell_h_mm=30, pitch_x_mm=41, pitch_y_mm=31)
        shell.apply_advanced(tpl)
        self.assertEqual(shell.flow.answer("paper"), "tpl:adv1")
        self.assertIs(shell.templates.get("adv1"), tpl)

    def test_wizard_button(self):
        shell = self.make_shell()
        btn = shell._wizard_button(self.root, "校准", lambda: None)
        self.assertEqual(btn.cget("text"), "校准")
        btn.destroy()

    def test_selected_grid(self):
        shell = self.make_shell()
        grid = shell._selected_grid()
        self.assertEqual((grid.cols, grid.rows), (5, 9))


class MainTests(UiCase):
    def test_autoplay_walks_to_last_step(self):
        shell = mock.Mock()
        shell.flow.is_last = False
        shell.root.after = mock.Mock()
        ShellMod._autoplay(shell)
        shell.next_step.assert_called_once()
        shell.root.after.assert_called_once()
        shell.reset_mock()
        shell.flow.is_last = True
        ShellMod._autoplay(shell)
        shell.next_step.assert_not_called()

    def test_main_builds_shell_and_enters_mainloop(self):
        fake_root = mock.Mock()
        fake_shell = mock.Mock()
        with mock.patch.object(ShellMod, "enable_dpi_awareness") as aware, \
                mock.patch.object(ShellMod.tk, "Tk", return_value=fake_root), \
                mock.patch.object(ShellMod, "Shell", return_value=fake_shell) as cls:
            result = ShellMod.main(lang="en_US")
        self.assertEqual(result, 0)
        aware.assert_called_once()
        class_kwargs = cls.call_args.kwargs
        self.assertEqual(class_kwargs["lang"], "en_US")
        fake_root.mainloop.assert_called_once()

    def test_main_autoplay_schedules(self):
        fake_root = mock.Mock()
        with mock.patch.object(ShellMod, "enable_dpi_awareness"), \
                mock.patch.object(ShellMod.tk, "Tk", return_value=fake_root), \
                mock.patch.object(ShellMod, "Shell", return_value=mock.Mock()):
            ShellMod.main(autoplay=True)
        fake_root.after.assert_called_once()
        args = fake_root.after.call_args.args
        self.assertEqual(args[0], 600)
