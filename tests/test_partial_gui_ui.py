# -*- coding: utf-8 -*-
"""v1「接着打」窗口与两个对话框（``ulpp.partial_gui``）。"""
from __future__ import annotations

import queue
import types
from pathlib import Path
from unittest import mock

from ulpp import partial_gui as pg
from ulpp.builder import Sticker, collect_text_stickers
from ulpp.config import GridSpec
from ulpp.partial_gui import NewSheetDialog, PartialWindow, TextDialog
from ulpp.presets import PRESETS, by_key
from ulpp.sheets import SheetStore, SheetStoreError
from ulpp.textlabel import parse_text_block

from .ui_harness import UiCase

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.pdf"


def _text_entry(text="标签", copies=1):
    return collect_text_stickers(parse_text_block("%s|%d" % (text, copies)))[0]


def _pdf_entry(name="卡片", qty=2):
    return Sticker(pdf_path="/tmp/a.pdf", page_index=0, page_no=1,
                   card=types.SimpleNamespace(name=name, qty=qty), copy_no=1)


class PartialCase(UiCase):
    def setUp(self):
        super().setUp()
        self.err = mock.patch.object(pg.messagebox, "showerror").start()
        self.warn = mock.patch.object(pg.messagebox, "showwarning").start()
        self.info = mock.patch.object(pg.messagebox, "showinfo").start()
        self.ask = mock.patch.object(pg.messagebox, "askyesno",
                                     return_value=True).start()
        self.addCleanup(mock.patch.stopall)

    def _store(self, make_sheet=True, used=(0,)):
        store = SheetStore(path=self.tmpdir / "sheets.json")
        if make_sheet:
            store.add_sheet("半张", by_key("45").to_grid(), used=list(used))
            store.save()
        return store

    def _window(self, store=None, build=True):
        win = PartialWindow(self.root, store=store or self._store())
        self.pump()
        self.close_later(win)
        return win


class ModuleHelperTests(UiCase):
    def test_short_and_safe_name(self):
        self.assertEqual(pg._short("abc"), "abc")
        self.assertEqual(pg._short("a\nb"), "a b")
        self.assertTrue(pg._short("x" * 40).endswith("…"))
        self.assertEqual(pg._safe_name(" /a:b*c "), "_a_b_c")
        self.assertEqual(pg._safe_name(""), "partial")

    def test_default_out_dir(self):
        self.assertTrue(pg._default_out_dir().endswith(pg.tr("out.default_dir")))


class LoadStoreTests(PartialCase):
    def test_loads_existing_store(self):
        win = self._window()
        self.assertEqual(len(win.store.sheets), 1)

    def test_corrupt_store_is_backed_up(self):
        path = self.tmpdir / "config" / "ulpp" / "sheets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken", encoding="utf-8")
        with mock.patch.object(pg.SheetStore, "load",
                               side_effect=SheetStoreError("坏文件")), \
                mock.patch.object(pg, "default_sheets_path", return_value=path):
            win = PartialWindow(self.root)
            self.pump()
            self.close_later(win)
        self.assertTrue(path.with_name(path.name + ".broken").exists())
        self.assertEqual(win.store.sheets, [])
        self.err.assert_called_once()

    def test_corrupt_store_backup_failure_is_ignored(self):
        path = self.tmpdir / "sheets.json"
        path.write_text("x", encoding="utf-8")
        with mock.patch.object(pg.SheetStore, "load",
                               side_effect=SheetStoreError("坏文件")), \
                mock.patch.object(pg, "default_sheets_path", return_value=path), \
                mock.patch.object(pg.os, "replace", side_effect=OSError("no")):
            win = PartialWindow(self.root)
            self.pump()
            self.close_later(win)
        self.assertEqual(win.store.sheets, [])


class SheetTests(PartialCase):
    def test_current_sheet_prefers_combo(self):
        win = self._window()
        self.assertIs(win._current_sheet(), win.store.sheets[0])

    def test_current_sheet_falls_back_to_selected_id(self):
        win = self._window()
        win.store.add_sheet("第二张", by_key("24").to_grid())
        win.sheet_cb.current = mock.Mock(return_value=-1)
        win.selected_sheet_id = win.store.sheets[1].id
        self.assertIs(win._current_sheet(), win.store.sheets[1])

    def test_current_sheet_empty(self):
        win = self._window(store=self._store(make_sheet=False))
        self.assertIsNone(win._current_sheet())

    def test_refresh_sheet_list_no_sheets(self):
        win = self._window(store=self._store(make_sheet=False))
        self.assertEqual(win.sheet_var.get(), "")
        self.assertIsNone(win.selected_sheet_id)
        self.assertEqual(win.count_var.get(), pg.tr("partial.no_sheets"))

    def test_refresh_sheet_list_selects_requested_id(self):
        win = self._window()
        extra = win.store.add_sheet("第二张", by_key("24").to_grid())
        win._refresh_sheet_list(select_id=extra.id)
        self.assertEqual(win.selected_sheet_id, extra.id)

    def test_new_sheet_dialog_cancel(self):
        win = self._window()
        fake = mock.Mock(result=None)
        win.wait_window = mock.Mock()
        with mock.patch.object(pg, "NewSheetDialog", return_value=fake):
            win._new_sheet()
        self.assertEqual(len(win.store.sheets), 1)

    def test_new_sheet_created(self):
        win = self._window()
        grid = by_key("24").to_grid()
        fake = mock.Mock(result=("新纸", grid))
        win.wait_window = mock.Mock()
        with mock.patch.object(pg, "NewSheetDialog", return_value=fake):
            win._new_sheet()
        self.assertEqual(len(win.store.sheets), 2)
        self.assertTrue(win.sheet_var.get().startswith(win.store.sheets[-1].name))

    def test_delete_sheet_without_sheet(self):
        win = self._window(store=self._store(make_sheet=False))
        win._delete_sheet()
        self.info.assert_called_once()

    def test_delete_sheet_declined(self):
        win = self._window()
        self.ask.return_value = False
        win._delete_sheet()
        self.assertEqual(len(win.store.sheets), 1)

    def test_delete_sheet_confirmed(self):
        win = self._window()
        win._delete_sheet()
        self.assertEqual(win.store.sheets, [])
        self.assertIsNone(win.selected_sheet_id)

    def test_sheet_changed_clears_placements_and_pending(self):
        win = self._window()
        entry = _text_entry()
        win.queue = [entry]
        win.placements = {1: entry}
        win.pending_job = {"x": 1}
        win.store.add_sheet("另一张", by_key("24").to_grid())
        win._refresh_sheet_list()
        win.selected_sheet_id = win.store.sheets[0].id
        win.sheet_cb.current(1)
        win._on_sheet_changed()
        self.assertEqual(win.placements, {})
        self.assertIsNone(win.pending_job)

    def test_sheet_changed_without_sheet(self):
        win = self._window(store=self._store(make_sheet=False))
        win.sheet_cb.current = mock.Mock(return_value=-1)
        win.selected_sheet_id = None
        win._on_sheet_changed()
        self.assertIsNone(win.selected_sheet_id)

    def test_invalidate_pending_logs(self):
        win = self._window()
        win.pending_job = {"x": 1}
        win._invalidate_pending()
        self.assertIsNone(win.pending_job)
        self.assertIn(pg.tr("partial.msg.job_invalidated"),
                      win.log_text.get("1.0", "end"))

    def test_legend_builds(self):
        import tkinter as tk
        from tkinter import ttk

        parent = ttk.Frame(self.root)
        win = self._window()
        win._legend(parent, "#fff", "text")
        self.assertGreaterEqual(len(parent.winfo_children()), 2)


class QueueTests(PartialCase):
    def test_entry_labels_and_kinds(self):
        win = self._window()
        text = _text_entry("很长的文字" * 10, copies=3)
        pdf = _pdf_entry("卡片名称", qty=2)
        self.assertIn("…", win._entry_label(text))
        self.assertIn("#1/3", win._entry_label(text))
        self.assertIn("#1/2", win._entry_label(pdf))
        self.assertEqual(win._entry_kind(text), pg.tr("partial.item.text"))
        self.assertEqual(win._entry_kind(pdf), pg.tr("partial.item.pdf"))
        self.assertFalse(win._is_placed(text))
        win.placements = {0: text}
        self.assertTrue(win._is_placed(text))

    def test_refresh_queue_keeps_selection(self):
        win = self._window()
        win.queue = [_text_entry("a"), _text_entry("b")]
        win.selected_queue_index = 1
        win._refresh_queue()
        self.assertEqual(win.tree.selection(), ("1",))
        win.selected_queue_index = 99
        win._refresh_queue()
        self.assertIsNone(win.selected_queue_index)

    def test_tree_select(self):
        win = self._window()
        win.queue = [_text_entry("a"), _text_entry("b")]
        win._refresh_queue()
        win.tree.selection_set("1")
        win._on_tree_select()
        self.assertEqual(win.selected_queue_index, 1)

    def test_add_pdf_cancelled(self):
        win = self._window()
        with mock.patch("tkinter.filedialog.askopenfilenames", return_value=()):
            win._add_pdf()
        self.assertEqual(win.queue, [])

    def test_add_pdf_success(self):
        win = self._window()
        with mock.patch("tkinter.filedialog.askopenfilenames",
                        return_value=(str(SAMPLE),)), \
                mock.patch.object(pg, "expand_inputs", return_value=[str(SAMPLE)]), \
                mock.patch.object(pg, "parse_many", return_value=[mock.Mock()]), \
                mock.patch.object(pg, "collect_stickers",
                                  return_value=[_pdf_entry()]):
            win._add_pdf()
        self.assertEqual(len(win.queue), 1)

    def test_add_pdf_no_files_or_no_stickers_warns(self):
        win = self._window()
        with mock.patch("tkinter.filedialog.askopenfilenames",
                        return_value=("/tmp/a.pdf",)), \
                mock.patch.object(pg, "expand_inputs", return_value=[]):
            win._add_pdf()
        self.warn.assert_called_once()

        self.warn.reset_mock()
        with mock.patch("tkinter.filedialog.askopenfilenames",
                        return_value=("/tmp/a.pdf",)), \
                mock.patch.object(pg, "expand_inputs", return_value=["/tmp/a.pdf"]), \
                mock.patch.object(pg, "parse_many", return_value=[]), \
                mock.patch.object(pg, "collect_stickers", return_value=[]):
            win._add_pdf()
        self.warn.assert_called_once()

    def test_add_pdf_failure_shows_error(self):
        win = self._window()
        with mock.patch("tkinter.filedialog.askopenfilenames",
                        return_value=("/tmp/a.pdf",)), \
                mock.patch.object(pg, "expand_inputs",
                                  side_effect=RuntimeError("坏 zip")):
            win._add_pdf()
        self.err.assert_called_once()

    def test_add_text_cancelled_and_empty(self):
        win = self._window()
        win.wait_window = mock.Mock()
        with mock.patch.object(pg, "TextDialog", return_value=mock.Mock(result=None)):
            win._add_text()
        self.assertEqual(win.queue, [])
        with mock.patch.object(pg, "TextDialog", return_value=mock.Mock(result="   ")):
            win._add_text()
        self.warn.assert_called_once()

    def test_add_text_success(self):
        win = self._window()
        win.wait_window = mock.Mock()
        with mock.patch.object(pg, "TextDialog", return_value=mock.Mock(result="标签|2")):
            win._add_text()
        self.assertEqual(len(win.queue), 2)

    def test_remove_item_guards_and_removes_placement(self):
        win = self._window()
        win.selected_queue_index = None
        win._remove_item()
        win.selected_queue_index = 99
        win._remove_item()
        entry = _text_entry("a")
        win.queue = [entry, _text_entry("b")]
        win.placements = {3: entry}
        win.selected_queue_index = 0
        win._remove_item()
        self.assertEqual(len(win.queue), 1)
        self.assertEqual(win.placements, {})
        self.assertEqual(win.selected_queue_index, 0)

    def test_clear_queue_guards_and_confirm(self):
        win = self._window()
        win._clear_queue()                     # 空队列直接返回
        entry = _text_entry()
        win.queue = [entry]
        win.placements = {0: entry}
        self.ask.return_value = False
        win._clear_queue()
        self.assertEqual(len(win.queue), 1)
        self.ask.return_value = True
        win._clear_queue()
        self.assertEqual(win.queue, [])
        self.assertEqual(win.placements, {})

    def test_auto_fill_guards(self):
        win = self._window(store=self._store(make_sheet=False))
        win._auto_fill()
        self.info.assert_called_once()

        win = self._window()
        win.store.sheets[0].mark_used(range(win.store.sheets[0].per_sheet))
        win._auto_fill()
        self.assertEqual(self.info.call_count, 2)

    def test_auto_fill_places_items(self):
        win = self._window()
        win.queue = [_text_entry("a"), _text_entry("b")]
        win._auto_fill()
        self.assertEqual(len(win.placements), 2)
        self.assertIn(pg.tr("partial.status.auto_filled", n=2), win.status_var.get())

    def test_auto_fill_zero_when_nothing_pending(self):
        win = self._window()
        win.queue = []
        win._auto_fill()
        self.assertIn(pg.tr("partial.status.auto_filled", n=0), win.status_var.get())


class CanvasTests(PartialCase):
    def test_refresh_canvas_no_sheet_and_with_sheet(self):
        win = self._window(store=self._store(make_sheet=False))
        win._refresh_canvas()
        self.assertGreater(len(win.canvas.find_all()), 0)

        win = self._window()
        win.placements = {1: _text_entry()}
        win._refresh_canvas()
        self.assertGreater(len(win.canvas.find_all()), 0)

    def test_refresh_canvas_after_destroy(self):
        win = PartialWindow(self.root, store=self._store())
        win.destroy()
        win._refresh_canvas()                  # 直接返回

    def test_slot_at_and_left_click_flow(self):
        win = self._window()
        win.queue = [_text_entry("a")]
        win._refresh_canvas()
        slot = 1
        x0, y0, x1, y1 = win._cell_rects[slot]
        event = types.SimpleNamespace(x=(x0 + x1) / 2, y=(y0 + y1) / 2)
        self.assertEqual(win._slot_at(event), slot)
        self.assertIsNone(win._slot_at(types.SimpleNamespace(x=-99, y=-99)))

        win.selected_queue_index = 0
        win._on_left_click(event)
        self.assertIn(slot, win.placements)
        win._on_left_click(event)              # 再点一次取消
        self.assertNotIn(slot, win.placements)

    def test_left_click_used_cell_warns(self):
        win = self._window()                   # slot 0 已用掉
        win._refresh_canvas()
        x0, y0, x1, y1 = win._cell_rects[0]
        win._on_left_click(types.SimpleNamespace(x=(x0 + x1) / 2, y=(y0 + y1) / 2))
        self.info.assert_called_once()

    def test_left_click_without_selection_warns(self):
        win = self._window()
        win._refresh_canvas()
        win.selected_queue_index = None
        slot = 1
        x0, y0, x1, y1 = win._cell_rects[slot]
        win._on_left_click(types.SimpleNamespace(x=(x0 + x1) / 2, y=(y0 + y1) / 2))
        self.info.assert_called_once()

    def test_left_click_moves_entry_from_old_slot(self):
        win = self._window()
        entry = _text_entry("a")
        win.queue = [entry]
        win.selected_queue_index = 0
        win.placements = {1: entry}
        win._refresh_canvas()
        x0, y0, x1, y1 = win._cell_rects[2]
        win._on_left_click(types.SimpleNamespace(x=(x0 + x1) / 2, y=(y0 + y1) / 2))
        self.assertNotIn(1, win.placements)
        self.assertIn(2, win.placements)

    def test_left_and_right_click_guards(self):
        win = self._window(store=self._store(make_sheet=False))
        win._refresh_canvas()
        win._on_left_click(types.SimpleNamespace(x=1, y=1))
        win._on_right_click(types.SimpleNamespace(x=1, y=1))

    def test_right_click_toggles_used(self):
        win = self._window()
        win._refresh_canvas()
        x0, y0, x1, y1 = win._cell_rects[1]
        event = types.SimpleNamespace(x=(x0 + x1) / 2, y=(y0 + y1) / 2)
        win._on_right_click(event)
        self.assertIn(1, win.store.sheets[0].used_cells)
        win._on_right_click(event)
        self.assertNotIn(1, win.store.sheets[0].used_cells)

    def test_right_click_used_cell_frees_it(self):
        win = self._window()
        win._refresh_canvas()
        x0, y0, x1, y1 = win._cell_rects[0]
        win._on_right_click(types.SimpleNamespace(x=(x0 + x1) / 2, y=(y0 + y1) / 2))
        self.assertNotIn(0, win.store.sheets[0].used_cells)


class PrintTests(PartialCase):
    def test_offset_valid_and_invalid(self):
        win = self._window()
        self.assertEqual(win._offset(), (0.0, 0.0))
        win.offset_x_var.set("x")
        with self.assertRaises(ValueError):
            win._offset()

    def test_choose_out_dir(self):
        win = self._window()
        with mock.patch("tkinter.filedialog.askdirectory", return_value="/tmp/out"):
            win._choose_out_dir()
        self.assertEqual(win.out_dir_var.get(), "/tmp/out")
        with mock.patch("tkinter.filedialog.askdirectory", return_value=""):
            win._choose_out_dir()
        self.assertEqual(win.out_dir_var.get(), "/tmp/out")

    def test_generate_guards(self):
        win = self._window(store=self._store(make_sheet=False))
        win._generate_pdf()
        self.info.assert_called_once()

        win = self._window()
        win._generate_pdf()
        self.assertEqual(self.info.call_count, 2)

        win.placements = {1: _text_entry()}
        win.offset_x_var.set("bad")
        win._generate_pdf()
        self.err.assert_called_once()

    def test_generate_success(self):
        win = self._window()
        entry = _text_entry()
        win.placements = {1: entry}
        win._open_path = mock.Mock()
        with mock.patch.object(pg, "build_partial_all",
                               return_value={"production": "/tmp/p.pdf"}) as build:
            win._generate_pdf()
        build.assert_called_once()
        self.assertIsNotNone(win.pending_job)
        self.assertEqual(win.pending_job["slots"], [1])
        win._open_path.assert_called_once_with("/tmp/p.pdf")
        self.info.assert_called_once()

    def test_generate_failure(self):
        win = self._window()
        win.placements = {1: _text_entry()}
        with mock.patch.object(pg, "build_partial_all",
                               side_effect=RuntimeError("写不了")):
            win._generate_pdf()
        self.err.assert_called_once()

    def test_mark_printed_without_job(self):
        win = self._window()
        win._mark_printed()
        self.info.assert_called_once()

    def test_mark_printed_missing_sheet(self):
        win = self._window()
        win.pending_job = {"sheet_id": "gone", "slots": [1], "entries": []}
        win._mark_printed()                    # 找不到纸就返回

    def test_mark_printed_declined(self):
        win = self._window()
        entry = _text_entry()
        win.queue = [entry]
        win.placements = {1: entry}
        win.pending_job = {"sheet_id": win.store.sheets[0].id,
                           "slots": [1], "entries": [entry]}
        self.ask.return_value = False
        win._mark_printed()
        self.assertIsNotNone(win.pending_job)

    def test_mark_printed_success_and_undo(self):
        win = self._window()
        entry = _text_entry()
        win.queue = [entry]
        win.placements = {1: entry}
        win.pending_job = {"sheet_id": win.store.sheets[0].id,
                           "slots": [1], "entries": [entry]}
        win._mark_printed()
        self.assertIsNone(win.pending_job)
        self.assertIn(1, win.store.sheets[0].used_cells)
        self.assertEqual(win.queue, [])

        win._undo()
        self.assertIsNone(win.last_job)
        self.assertNotIn(1, win.store.sheets[0].used_cells)
        self.assertIn(entry, win.queue)

    def test_undo_without_job_and_missing_sheet(self):
        win = self._window()
        win._undo()
        self.info.assert_called_once()
        win.last_job = {"sheet_id": "gone", "slots": [1], "entries": []}
        win._undo()                            # 不炸

    def test_undo_does_not_duplicate_queue_entries(self):
        win = self._window()
        entry = _text_entry()
        win.queue = [entry]
        win.last_job = {"sheet_id": win.store.sheets[0].id,
                        "slots": [1], "entries": [entry]}
        win._undo()
        self.assertEqual(win.queue.count(entry), 1)


class PrinterTests(PartialCase):
    def test_feed_values_and_load_printer(self):
        win = self._window()
        self.assertGreaterEqual(len(win._feed_display_to_key), 4)
        win.store.get_printer().feed = "face_down_long"
        win._load_printer()
        self.assertEqual(win.feed_var.get(),
                         pg.tr("calibration.feed.face_down_long"))

    def test_save_printer_bad_offset(self):
        win = self._window()
        win.offset_x_var.set("bad")
        win._save_printer()
        self.err.assert_called_once()

    def test_save_printer_success(self):
        win = self._window()
        win.offset_x_var.set("1.5")
        win.offset_y_var.set("-2")
        win.feed_var.set(pg.tr("calibration.feed.face_down_short"))
        win._save_printer()
        profile = win.store.get_printer()
        self.assertEqual((profile.offset_x_mm, profile.offset_y_mm), (1.5, -2.0))
        self.assertEqual(profile.feed, "face_down_short")

    def test_calibration_page_with_and_without_sheet(self):
        win = self._window()
        win._open_path = mock.Mock()
        with mock.patch.object(pg, "make_calibration_pdf") as make:
            win._calibration_page()
        make.assert_called_once()
        win._open_path.assert_called_once()

        win.store.sheets.clear()
        win.selected_sheet_id = None
        win._open_path = mock.Mock()
        with mock.patch.object(pg, "make_calibration_pdf") as make:
            win._calibration_page()
        make.assert_called_once()
        self.assertIsInstance(make.call_args.args[0], GridSpec)

    def test_calibration_page_failure(self):
        win = self._window()
        with mock.patch.object(pg, "make_calibration_pdf",
                               side_effect=OSError("只读")):
            win._calibration_page()
        self.err.assert_called_once()

    def test_open_wizard_copies_profile_and_saves(self):
        win = self._window()
        win.store.get_printer().name = "旧机器"
        win.store.get_printer().tray = "Tray 5"
        captured = {}

        class FakeWizard:
            def __init__(self, master, profile=None, on_save=None, output_dir=None):
                captured.update(on_save=on_save, profile=profile,
                                output_dir=output_dir)

        import ulpp.wizard as wizard_mod
        with mock.patch.object(wizard_mod, "CalibrationWizard", FakeWizard):
            win._open_wizard()
        captured["on_save"]("face_down_short", 2.0, -1.0)
        profile = win.store.get_printer()
        self.assertEqual(profile.feed, "face_down_short")
        self.assertEqual(profile.name, "旧机器")
        self.assertEqual(profile.tray, "Tray 5")
        self.assertEqual(profile.offset_x_mm, 2.0)

    def test_open_wizard_without_optional_profile_fields(self):
        win = self._window()
        win.store.get_printer().name = ""
        win.store.get_printer().tray = ""
        captured = {}

        class FakeWizard:
            def __init__(self, master, profile=None, on_save=None, output_dir=None):
                captured["on_save"] = on_save

        import ulpp.wizard as wizard_mod
        with mock.patch.object(wizard_mod, "CalibrationWizard", FakeWizard):
            win._open_wizard()
        captured["on_save"]("face_up_long", 0, 0)
        self.assertEqual(win.store.get_printer().feed, "face_up_long")


class ToolTests(PartialCase):
    def test_save_store_failure_shows_error(self):
        win = self._window()
        win.store = mock.Mock()
        win.store.save.side_effect = OSError("只读")
        win._save_store()
        self.err.assert_called_once()

    def test_log(self):
        win = self._window()
        win._log("a")
        win._log("b")
        self.assertIn("a\nb", win.log_text.get("1.0", "end"))

    def test_open_path_all_platforms(self):
        win = self._window()
        with mock.patch("sys.platform", "darwin"), \
                mock.patch("subprocess.Popen") as popen:
            win._open_path("/tmp/x.pdf")
        popen.assert_called_once_with(["open", "/tmp/x.pdf"])

        with mock.patch.object(pg.os, "name", "nt"), \
                mock.patch("os.startfile", create=True) as start:
            win._open_path("C:/x.pdf")
        start.assert_called_once_with("C:/x.pdf")

        with mock.patch.object(pg.os, "name", "posix"), \
                mock.patch.object(pg.sys, "platform", "linux"), \
                mock.patch("subprocess.Popen") as popen:
            win._open_path("/tmp/x.pdf")
        popen.assert_called_once_with(["xdg-open", "/tmp/x.pdf"])

    def test_open_path_failure_shows_info(self):
        win = self._window()
        with mock.patch("subprocess.Popen", side_effect=OSError("no opener")):
            win._open_path("/tmp/x.pdf")
        self.info.assert_called_once()

    def test_close_cancels_and_saves(self):
        win = PartialWindow(self.root, store=self._store())
        win._cancel_after = mock.Mock()
        win.store.save = mock.Mock()
        win._on_close()
        win._cancel_after.assert_called()
        win.store.save.assert_called_once()

    def test_close_swallows_save_error(self):
        win = PartialWindow(self.root, store=self._store())
        win.store.save = mock.Mock(side_effect=OSError("no"))
        win._on_close()

    def test_cancel_after_handles_errors_and_missing_id(self):
        win = self._window()
        win._after_id = None
        win._cancel_after()
        win._after_id = "123456"
        with mock.patch.object(win, "after_cancel", side_effect=Exception("bad")):
            win._cancel_after()
        self.assertIsNone(win._after_id)

    def test_on_destroy_only_reacts_to_self(self):
        win = self._window()
        win._cancel_after = mock.Mock()
        win._on_destroy(types.SimpleNamespace(widget=object()))
        win._cancel_after.assert_not_called()
        win._on_destroy(types.SimpleNamespace(widget=win))
        win._cancel_after.assert_called_once()


class NewSheetDialogTests(PartialCase):
    def _dialog(self):
        dialog = NewSheetDialog(self.root)
        self.pump()
        self.close_later(dialog)
        return dialog

    def test_preset_prefilled(self):
        dialog = self._dialog()
        self.assertEqual(dialog.name_var.get(), PRESETS[0].title)
        self.assertEqual(dialog.vars["cols"].get(), str(PRESETS[0].cols))

    def test_on_preset_custom_keeps_typed_name(self):
        dialog = self._dialog()
        dialog.name_var.set("我自己写的")
        dialog.preset_cb.current(len(PRESETS))
        dialog._on_preset()
        self.assertEqual(dialog.name_var.get(), "我自己写的")

    def test_on_preset_custom_sets_default_name(self):
        dialog = self._dialog()
        dialog.name_var.set("")
        dialog.preset_cb.current(len(PRESETS))
        dialog._on_preset()
        self.assertEqual(dialog.name_var.get(), pg.tr("partial.new.title"))

    def test_fill(self):
        dialog = self._dialog()
        dialog._fill(by_key("24").to_grid())
        self.assertEqual(dialog.vars["cols"].get(), str(by_key("24").cols))

    def test_create_success(self):
        dialog = self._dialog()
        dialog.name_var.set("新纸")
        dialog._create()
        self.assertIsNotNone(dialog.result)
        name, grid = dialog.result
        self.assertEqual(name, "新纸")
        self.assertIsInstance(grid, GridSpec)

    def test_create_defaults_name(self):
        dialog = self._dialog()
        dialog.name_var.set("")
        dialog._create()
        self.assertEqual(dialog.result[0], pg.tr("partial.new.title"))

    def test_create_bad_numbers(self):
        dialog = self._dialog()
        dialog.vars["cols"].set("x")
        dialog._create()
        self.err.assert_called_once()

    def test_create_non_positive(self):
        dialog = self._dialog()
        dialog.vars["cols"].set("0")
        dialog._create()
        self.err.assert_called_once()

    def test_create_invalid_mm(self):
        dialog = self._dialog()
        dialog.vars["cell_w"].set("-1")
        dialog._create()
        self.err.assert_called_once()

    def test_create_too_big(self):
        dialog = self._dialog()
        dialog.vars["cols"].set("100")
        dialog.vars["pitch_x"].set("50")
        dialog._create()
        self.err.assert_called_once()

    def test_cancel_button_destroys(self):
        dialog = self._dialog()
        dialog.destroy()
        try:
            exists = dialog.winfo_exists()
        except Exception:
            exists = 0
        self.assertFalse(exists)


class TextDialogTests(PartialCase):
    def test_ok_returns_text(self):
        dialog = TextDialog(self.root)
        self.pump()
        self.close_later(dialog)
        dialog.text.insert("1.0", "两行\n文字")
        dialog._ok()
        self.assertEqual(dialog.result, "两行\n文字")
