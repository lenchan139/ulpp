# -*- coding: utf-8 -*-
"""高级参数对话框（``ulpp.ui.advanced``）：读字段、校验、存成模板。"""
from __future__ import annotations

import tkinter as tk
from unittest import mock

from ulpp.templates import Template
from ulpp.ui.advanced import AdvancedDialog, _fmt

from .ui_harness import UiCase


class FormatTests(UiCase):
    def test_fmt_keeps_integers_and_trims_decimals(self):
        self.assertEqual(_fmt(5), "5")
        self.assertEqual(_fmt(5.0), "5")
        self.assertEqual(_fmt(5.25), "5.25")
        self.assertEqual(_fmt(5.2), "5.2")


class AdvancedDialogTests(UiCase):
    def _dialog(self, shell=None):
        shell = shell or self.make_shell()
        dialog = AdvancedDialog(shell)
        self.pump()
        self.close_later(dialog)
        return shell, dialog

    def test_fields_prefilled_from_selected_preset(self):
        shell, dialog = self._dialog()
        self.assertEqual(dialog.vars["cols"].get(), "5")
        self.assertEqual(dialog.vars["rows"].get(), "9")
        self.assertEqual(dialog.dx.get(), "0")
        self.assertEqual(dialog.dy.get(), "0")
        self.assertTrue(dialog.base_name)

    def test_numbers_accepts_comma_decimal(self):
        _, dialog = self._dialog()
        dialog.vars["cell_w_mm"].set("40,5")
        numbers = dialog._numbers()
        self.assertEqual(numbers["cell_w_mm"], 40.5)
        self.assertIsInstance(numbers["cols"], int)

    def test_numbers_rejects_garbage_with_localised_message(self):
        shell, dialog = self._dialog()
        dialog.vars["pitch_x_mm"].set("abc")
        with self.assertRaises(ValueError) as ctx:
            dialog._numbers()
        self.assertIn(shell.T("adv.pitch_x_mm"), str(ctx.exception))

    def test_save_from_preset_wraps_into_template(self):
        shell, dialog = self._dialog()
        shell.apply_advanced = mock.Mock()
        dialog.vars["cols"].set("3")
        dialog.vars["rows"].set("4")
        dialog.vars["pitch_x_mm"].set("50")
        dialog.vars["pitch_y_mm"].set("40")
        dialog.vars["cell_w_mm"].set("48")
        dialog.vars["cell_h_mm"].set("38")
        dialog.dx.set("1.5")
        dialog.dy.set("-2")
        dialog._save()
        shell.apply_advanced.assert_called_once()
        tpl = shell.apply_advanced.call_args.args[0]
        self.assertEqual(tpl.cols, 3)
        self.assertEqual(tpl.rows, 4)
        self.assertAlmostEqual(tpl.origin_x_mm, 3.5)
        self.assertAlmostEqual(tpl.origin_y_mm, 4.0)
        self.assertIn("改", tpl.name)
        self.assertTrue(tpl.source.startswith("preset:"))

    def test_save_existing_template_keeps_name(self):
        shell = self.make_shell()
        tpl = Template(id="mine", name="我的纸", cols=2, rows=2, cell_w_mm=20,
                       cell_h_mm=20, pitch_x_mm=21, pitch_y_mm=21)
        shell.templates.upsert(tpl)
        shell.flow.answer("paper", "tpl:mine")
        shell.apply_advanced = mock.Mock()
        dialog = AdvancedDialog(shell)
        self.pump()
        self.close_later(dialog)
        dialog._save()
        out = shell.apply_advanced.call_args.args[0]
        self.assertEqual(out.name, "我的纸")
        self.assertEqual(out.id, "mine")

    def test_save_bad_dx_reports_error_and_keeps_dialog(self):
        shell, dialog = self._dialog()
        shell.apply_advanced = mock.Mock()
        dialog.dx.set("nope")
        dialog._save()
        self.assertIn("nope", dialog.error.cget("text").lower())
        shell.apply_advanced.assert_not_called()
        self.assertTrue(dialog.winfo_exists())

    def test_save_invalid_geometry_reports_error(self):
        shell, dialog = self._dialog()
        shell.apply_advanced = mock.Mock()
        dialog.vars["cell_w_mm"].set("100")
        dialog.vars["pitch_x_mm"].set("10")
        dialog._save()
        self.assertTrue(dialog.error.cget("text"))
        shell.apply_advanced.assert_not_called()

    def test_escape_binding_exists(self):
        _, dialog = self._dialog()
        self.assertTrue(dialog.bind("<Escape>"))
