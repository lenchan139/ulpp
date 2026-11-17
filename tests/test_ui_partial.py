# -*- coding: utf-8 -*-
"""v2「接着打」窗口（``ulpp.ui.partial``）：格阵、切换、生成。"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest import mock

from ulpp.builder import collect_entries
from ulpp.textlabel import parse_text_block
from ulpp.ui import partial as partial_mod
from ulpp.ui.flow import Flow
from ulpp.ui.partial import PartialWindow

from .ui_harness import UiCase

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.pdf"


class PartialWindowTests(UiCase):
    def _shell(self):
        shell = self.make_shell(flow=Flow(index=2))
        return shell

    def _window(self, shell=None):
        shell = shell or self._shell()
        win = PartialWindow(shell)
        self.pump()
        self.close_later(win)
        return shell, win

    def test_creates_initial_sheet_and_draws_grid(self):
        shell, win = self._window()
        self.assertIsNotNone(win.sheet)
        self.assertIsNotNone(win.store)
        self.assertGreater(len(win._canvas.find_all()), 0)
        self.assertEqual(win.sheet_var.get(), win.sheet.name)

    def test_store_unavailable_shows_error(self):
        shell = self._shell()
        shell.store = None
        with mock.patch.object(partial_mod.SheetStore, "load",
                               side_effect=OSError("no config")):
            win = PartialWindow(shell)
        self.pump()
        self.close_later(win)
        self.assertIsNone(win.store)
        self.assertIsNone(win.sheet)
        self.assertEqual(win.error, shell.T("partial.none"))
        # 这些动作在没 store 时应安静返回
        win._new_sheet()
        win._save_store()
        win._toggle(0)
        win._toggle_row(0)
        win._toggle_column(0)
        win._on_pick()

    def test_new_sheet_failure_records_error(self):
        shell, win = self._window()
        win.store = mock.Mock()
        win.store.sheets = []
        win.store.add_sheet.side_effect = RuntimeError("磁盘满")
        win._new_sheet()
        self.assertEqual(win.error, "磁盘满")

    def test_save_store_swallows_errors(self):
        shell, win = self._window()
        win.store = mock.Mock()
        win.store.save.side_effect = OSError("只读")
        win._save_store()      # 不抛

    def test_refresh_without_sheet_and_with_feedback(self):
        shell, win = self._window()
        win.sheet = None
        win.refresh()
        self.assertEqual(win.error, shell.T("partial.none"))
        win.output_path = "/tmp/production.pdf"
        win.leftover = 3
        win.refresh()
        texts = [w.cget("text") for w in win.right.winfo_children()
                 if w.winfo_class() == "Label"]
        joined = "\n".join(texts)
        self.assertIn("3", joined)
        self.assertIn("production.pdf", joined)

    def test_toggle_single_cell(self):
        shell, win = self._window()
        slot = win.sheet.free_cells[0]
        win._toggle(slot)
        self.assertFalse(win.sheet.is_free(slot))
        win._toggle(slot)
        self.assertTrue(win.sheet.is_free(slot))

    def test_toggle_row_and_column(self):
        shell, win = self._window()
        win._toggle_row(0)
        cols = win.sheet.grid_spec.cols
        for c in range(cols):
            self.assertFalse(win.sheet.is_free(c))
        win._toggle_row(0)
        for c in range(cols):
            self.assertTrue(win.sheet.is_free(c))

        rows = win.sheet.grid_spec.rows
        win._toggle_column(0)
        for r in range(rows):
            self.assertFalse(win.sheet.is_free(r * cols))
        win._toggle_column(0)
        for r in range(rows):
            self.assertTrue(win.sheet.is_free(r * cols))

    def test_toggle_line_guards(self):
        shell, win = self._window()
        win.sheet = None
        win._toggle_line([0, 1])
        win._toggle_row(0)
        win._toggle_column(0)
        win.sheet = win.store.sheets[0]
        win._toggle_line([])

    def test_pick_another_sheet(self):
        shell, win = self._window()
        extra = win.store.add_sheet("第二张", win.sheet.grid_spec)
        win.sheet_var.set(extra.name)
        win._on_pick()
        self.assertIs(win.sheet, extra)
        self.assertIsNone(win.output_path)
        self.assertIsNone(win.error)

    def test_on_new_creates_sheet(self):
        shell, win = self._window()
        before = len(win.store.sheets)
        win._on_new()
        self.assertEqual(len(win.store.sheets), before + 1)
        self.assertEqual(win.sheet_var.get(), win.sheet.name)

    def test_generate_without_content_reports_none(self):
        shell, win = self._window()
        shell.content_text = ""
        shell.files = []
        shell.images = []
        win.generate()
        self.assertEqual(win.error, shell.T("partial.none"))

    def test_generate_text_success_marks_cells(self):
        shell, win = self._window()
        shell.content_text = "标签一\n标签二"
        shell.files = []
        shell.images = []
        with mock.patch.object(partial_mod, "build_partial_all",
                               return_value={"production": "/tmp/out.pdf"}) as build:
            win.generate()
        self.assertIsNone(win.error)
        self.assertEqual(win.output_path, "/tmp/out.pdf")
        placements = build.call_args.args[0]
        self.assertEqual(len(placements), 2)
        for slot in placements:
            self.assertFalse(win.sheet.is_free(slot))

    def test_generate_with_pdf_parses_and_collects(self):
        shell, win = self._window()
        shell.content_text = ""
        shell.files = [str(SAMPLE)]
        shell.images = ["/tmp/a.png"]
        entries = collect_entries([], parse_text_block("图片标签"), [])
        info = mock.Mock()
        with mock.patch.object(partial_mod, "parse_many", return_value=[info]) as parse, \
                mock.patch.object(partial_mod, "collect_entries",
                                  return_value=entries) as collect, \
                mock.patch.object(partial_mod, "build_partial_all",
                                  return_value={"production": "/tmp/out.pdf"}):
            win.generate()
        parse.assert_called_once()
        collect.assert_called_once()
        self.assertIsNone(win.error)
        self.assertEqual(win.output_path, "/tmp/out.pdf")

    def test_generate_empty_entries_raises_localised_error(self):
        shell, win = self._window()
        shell.content_text = "x"
        shell.files = []
        shell.images = []
        with mock.patch.object(partial_mod, "collect_entries", return_value=[]):
            win.generate()
        self.assertEqual(win.error, shell.T("partial.none"))

    def test_generate_build_failure_is_reported(self):
        shell, win = self._window()
        shell.content_text = "标签"
        shell.files = []
        shell.images = []
        with mock.patch.object(partial_mod, "build_partial_all",
                               side_effect=RuntimeError("写不了 PDF")):
            win.generate()
        self.assertEqual(win.error, "写不了 PDF")
        self.assertIsNone(win.output_path)

    def test_open_only_with_output(self):
        shell, win = self._window()
        shell._open_path = mock.Mock()
        win._open()
        shell._open_path.assert_not_called()
        win.output_path = "/tmp/x.pdf"
        win._open()
        shell._open_path.assert_called_once_with("/tmp/x.pdf")

    def test_centre_sets_geometry(self):
        shell, win = self._window()
        win._centre()
        self.assertIn("+", win.geometry())
