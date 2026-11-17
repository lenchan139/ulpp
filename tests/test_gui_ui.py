# -*- coding: utf-8 -*-
"""v1 老界面（``ulpp.gui``）：语言、预设、文件、生成、队列。"""
from __future__ import annotations

import os
import queue
import types
from pathlib import Path
from unittest import mock

from ulpp import gui as gui_mod
from ulpp.gui import App
from ulpp.i18n import current_language
from ulpp.presets import PRESETS, by_key

from .ui_harness import UiCase

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.pdf"


class InlineThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon

    def start(self):
        self.target(*self.args, **self.kwargs)


class AppCase(UiCase):
    def _app(self, lang=None):
        app = App(self.root, lang=lang)
        self.pump()
        return app

    def setUp(self):
        super().setUp()
        self.msg = {
            "warn": mock.patch.object(gui_mod.messagebox, "showwarning").start(),
            "err": mock.patch.object(gui_mod.messagebox, "showerror").start(),
            "info": mock.patch.object(gui_mod.messagebox, "showinfo").start(),
            "yes": mock.patch.object(gui_mod.messagebox, "askyesno").start(),
        }
        self.addCleanup(mock.patch.stopall)


class ConstructorTests(AppCase):
    def test_defaults(self):
        app = self._app()
        self.assertEqual(app.preset_key.get(), "45")
        self.assertEqual(app.grid_vars["cols"].get(), "5")
        self.assertEqual(app.grid_vars["rows"].get(), "9")
        self.assertEqual(app.text_align.get(), "center")
        self.assertFalse(app.text_uniform.get())
        self.assertTrue(app.make_proof.get())
        self.assertTrue(app.make_csv.get())
        self.assertEqual(app.files, [])
        self.assertTrue(self.root.title().startswith(gui_mod.tr("app.name")))

    def test_language_argument(self):
        app = self._app(lang="en_US")
        self.assertEqual(current_language(), "en_US")
        self.assertTrue(app.status.get())

    def test_setup_dnd_without_library_is_noop(self):
        app = self._app()
        app._setup_dnd()

    def test_setup_dnd_errors_are_swallowed(self):
        app = self._app()
        with mock.patch.object(gui_mod, "_HAS_DND", True), \
                mock.patch.object(gui_mod, "DND_FILES", "Files"):
            app._setup_dnd()          # Listbox 没有 dnd 方法 → 捕获

    def test_on_drop(self):
        app = self._app()
        app._add_paths = mock.Mock()
        app._on_drop(types.SimpleNamespace(data="{%s}" % SAMPLE))
        app._add_paths.assert_called_once_with([str(SAMPLE)])


class LanguageTests(AppCase):
    def test_switch_to_english_preserves_state(self):
        app = self._app()
        app.files = ["/tmp/a.pdf"]
        app.listbox.insert("end", "a.pdf")
        app.text_box.insert("1.0", "粘贴的文字")
        app.open_btn.configure(state="normal")
        app.progress.configure(value=20)
        app.out_dir.set(str(self.tmpdir / "标签输出"))
        app._switch_language("en_US")
        self.assertEqual(current_language(), "en_US")
        self.assertIn("粘贴的文字", app.text_box.get("1.0", "end"))
        self.assertEqual(app.listbox.get(0), "a.pdf")
        self.assertEqual(str(app.open_btn.cget("state")), "normal")
        self.assertIn("label-output", app.out_dir.get())
        self.assertEqual(app.lang_display.get(), "English")
        app._switch_language("zh_CN")

    def test_switch_language_replaces_default_base_name(self):
        app = self._app()
        self.assertEqual(app.base_name.get(), gui_mod.tr("out.default_base"))
        app._switch_language("en_US")
        self.assertEqual(app.base_name.get(), gui_mod.tr("out.default_base"))
        app._switch_language("zh_CN")

    def test_on_lang_selected_same_language_resets(self):
        app = self._app()
        before = app.lang_display.get()
        app.lang_display.set("不存在的语言")
        app._on_lang_selected()
        self.assertEqual(app.lang_display.get(), before)

    def test_on_lang_selected_switches(self):
        app = self._app()
        app.lang_display.set("English")
        app._on_lang_selected()
        self.assertEqual(current_language(), "en_US")
        app.lang_display.set("中文")
        app._on_lang_selected()
        self.assertEqual(current_language(), "zh_CN")


class PresetTests(AppCase):
    def test_apply_known_and_unknown(self):
        app = self._app()
        app._apply_preset(PRESETS[-1].key)
        self.assertEqual(app.preset_key.get(), PRESETS[-1].key)
        self.assertEqual(app.grid_vars["cols"].get(), str(PRESETS[-1].cols))
        app._apply_preset("does-not-exist")
        self.assertEqual(app.preset_key.get(), PRESETS[-1].key)

    def test_apply_without_log(self):
        app = self._app()
        app._apply_preset("24", log=False)
        self.assertEqual(app.preset_key.get(), "24")

    def test_on_preset_selected(self):
        app = self._app()
        app.preset_cb.current(len(PRESETS) - 1)
        app._on_preset_selected()
        self.assertEqual(app.preset_key.get(), PRESETS[-1].key)


class FileTests(AppCase):
    def test_add_paths_success_and_dedupe(self):
        app = self._app()
        with mock.patch("ulpp.gui.expand_inputs", return_value=[str(SAMPLE)]):
            app._add_paths([str(SAMPLE)])
        self.assertEqual(app.files, [str(SAMPLE)])
        self.assertEqual(app.listbox.size(), 1)
        self.assertTrue(app.out_dir.get())
        with mock.patch("ulpp.gui.expand_inputs", return_value=[str(SAMPLE)]):
            app._add_paths([str(SAMPLE)])
        self.assertEqual(app.listbox.size(), 1)

    def test_add_paths_no_result_warns(self):
        app = self._app()
        with mock.patch("ulpp.gui.expand_inputs", return_value=[]):
            app._add_paths(["/tmp/none"])
        self.msg["warn"].assert_called_once()
        self.assertEqual(app.files, [])

    def test_add_pdfs_folder_zip(self):
        app = self._app()
        app._add_paths = mock.Mock()
        with mock.patch("tkinter.filedialog.askopenfilenames",
                        return_value=(str(SAMPLE),)):
            app.add_pdfs()
        app._add_paths.assert_called_with([str(SAMPLE)])

        with mock.patch("tkinter.filedialog.askdirectory", return_value="/tmp/dir"):
            app.add_folder()
        app._add_paths.assert_called_with(["/tmp/dir"])

        with mock.patch("tkinter.filedialog.askopenfilename",
                        return_value="/tmp/a.zip"):
            app.add_zip()
        app._add_paths.assert_called_with(["/tmp/a.zip"])

    def test_add_dialogs_cancelled(self):
        app = self._app()
        app._add_paths = mock.Mock()
        with mock.patch("tkinter.filedialog.askopenfilenames", return_value=()):
            app.add_pdfs()
        with mock.patch("tkinter.filedialog.askdirectory", return_value=""):
            app.add_folder()
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=""):
            app.add_zip()
        app._add_paths.assert_not_called()

    def test_remove_selected_and_clear(self):
        app = self._app()
        app.files = ["/tmp/a.pdf", "/tmp/b.pdf"]
        app.listbox.insert("end", "a.pdf")
        app.listbox.insert("end", "b.pdf")
        app.listbox.selection_set(0)
        app.remove_selected()
        self.assertEqual(app.files, ["/tmp/b.pdf"])
        self.assertEqual(app.listbox.size(), 1)
        app.clear_files()
        self.assertEqual(app.files, [])
        self.assertEqual(app.listbox.size(), 0)

    def test_choose_out_dir(self):
        app = self._app()
        with mock.patch("tkinter.filedialog.askdirectory", return_value="/tmp/out"):
            app.choose_out_dir()
        self.assertEqual(app.out_dir.get(), "/tmp/out")
        with mock.patch("tkinter.filedialog.askdirectory", return_value=""):
            app.choose_out_dir()
        self.assertEqual(app.out_dir.get(), "/tmp/out")


class OpenTests(AppCase):
    def test_open_out_dir_existing(self):
        app = self._app()
        app.out_dir.set(str(self.tmpdir))
        with mock.patch("os.startfile", create=True) as start:
            app.open_out_dir()
        start.assert_called_once_with(str(self.tmpdir))

    def test_open_out_dir_falls_back_to_info(self):
        app = self._app()
        app.out_dir.set(str(self.tmpdir))
        with mock.patch("os.startfile", create=True,
                        side_effect=OSError("no explorer")):
            app.open_out_dir()
        self.msg["info"].assert_called_once()

    def test_open_out_dir_missing_path_does_nothing(self):
        app = self._app()
        app.out_dir.set("/definitely/not/here")
        app.open_out_dir()
        self.msg["info"].assert_not_called()

    def test_open_partial_reuses_existing_window(self):
        app = self._app()
        fake = mock.Mock()
        fake.winfo_exists.return_value = True
        app.partial_window = fake
        app.open_partial()
        fake.lift.assert_called_once()
        fake.focus_force.assert_called_once()

    def test_open_partial_creates_window(self):
        app = self._app()
        app.partial_window = None
        with mock.patch("ulpp.partial_gui.PartialWindow") as cls:
            app.open_partial()
        cls.assert_called_once_with(self.root)


class GridTests(AppCase):
    def test_grid_defaults(self):
        app = self._app()
        grid = app._grid()
        self.assertEqual((grid.cols, grid.rows), (5, 9))

    def test_grid_bad_number(self):
        app = self._app()
        app.grid_vars["cols"].set("abc")
        with self.assertRaises(ValueError):
            app._grid()

    def test_grid_non_positive(self):
        app = self._app()
        app.grid_vars["rows"].set("0")
        with self.assertRaises(ValueError):
            app._grid()


class StartTests(AppCase):
    def test_start_without_content_warns(self):
        app = self._app()
        app.start()
        self.msg["warn"].assert_called_once()

    def test_start_bad_grid_shows_error(self):
        app = self._app()
        app.text_box.insert("1.0", "标签")
        app.grid_vars["cols"].set("x")
        app.start()
        self.msg["err"].assert_called_once()

    def test_start_success_inline(self):
        app = self._app()
        app.text_box.insert("1.0", "标签")
        info = mock.Mock(pages=[mock.Mock(warnings=["w"]), mock.Mock(warnings=[])], stickers=2)
        outs = {"production": "/tmp/production.pdf"}
        with mock.patch.object(gui_mod, "parse_many", return_value=[info]), \
                mock.patch.object(gui_mod, "build_all", return_value=outs) as build, \
                mock.patch.object(gui_mod.threading, "Thread", InlineThread):
            app.files = [str(SAMPLE)]
            app.start()
        app._poll_queue()
        self.assertEqual(str(app.status.get()), gui_mod.tr("gui.status.done"))
        self.assertEqual(str(app.start_btn.cget("state")), "normal")
        self.assertEqual(str(app.lang_cb.cget("state")), "readonly")
        self.assertEqual(str(app.open_btn.cget("state")), "normal")
        self.msg["info"].assert_called_once()
        self.assertTrue(build.called)

    def test_start_failure_inline(self):
        app = self._app()
        app.text_box.insert("1.0", "标签")
        with mock.patch.object(gui_mod, "build_all",
                               side_effect=RuntimeError("no space")), \
                mock.patch.object(gui_mod.threading, "Thread", InlineThread):
            app.start()
        app._poll_queue()
        self.assertEqual(str(app.status.get()), gui_mod.tr("gui.status.error"))
        self.msg["err"].assert_called_once()
        self.assertIn("no space", app.log_text.get("1.0", "end"))


class QueueTests(AppCase):
    def _app_with_queue(self):
        app = self._app()
        app.q = queue.Queue()
        return app

    def test_log_and_progress(self):
        app = self._app_with_queue()
        app.q.put(("log", "hello"))
        app.q.put(("progress", 3, 5))
        app._poll_queue()
        self.assertIn("hello", app.log_text.get("1.0", "end"))
        self.assertEqual(float(app.progress.cget("value")), 3.0)

    def test_done_and_unknown(self):
        app = self._app_with_queue()
        app.q.put(("done", {"production": "/tmp/a.pdf", "checklist": "/tmp/c.csv"}))
        app.q.put(("what", None))
        app._poll_queue()
        log = app.log_text.get("1.0", "end")
        self.assertIn("production", log)
        self.assertIn("checklist", log)

    def test_error(self):
        app = self._app_with_queue()
        app.q.put(("error", "bad\nTraceback"))
        app._poll_queue()
        self.assertEqual(str(app.status.get()), gui_mod.tr("gui.status.error"))

    def test_log_writes_and_keeps_disabled(self):
        app = self._app()
        app._log("a")
        app._log("b")
        self.assertEqual(str(app.log_text.cget("state")), "disabled")
        self.assertIn("a\nb", app.log_text.get("1.0", "end"))


class MainTests(UiCase):
    def test_main_builds_app_and_loops(self):
        fake_root = mock.Mock()
        with mock.patch.object(gui_mod.tk, "Tk", return_value=fake_root), \
                mock.patch.object(gui_mod, "App") as cls:
            gui_mod.main(lang="en_US")
        self.assertEqual(current_language(), "en_US")
        cls.assert_called_once_with(fake_root)
        fake_root.mainloop.assert_called_once()
        from ulpp.i18n import set_language
        set_language("zh_CN")
