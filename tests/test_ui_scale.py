# -*- coding: utf-8 -*-
"""v2 显示尺度（``ulpp.ui.scale``）：主题、缩放、字体、窗口尺寸、DPI 声明。"""
from __future__ import annotations

import sys
import types
import unittest
from unittest import mock

from ulpp.ui import scale

from .ui_harness import UiCase, requires_tk


class ThemeTests(UiCase):
    def test_every_theme_has_required_keys(self):
        for name, theme in scale.THEMES.items():
            self.assertEqual(theme["name"], name)
            for key in ("bg", "card", "border", "text", "muted", "accent",
                        "accent_text", "soft", "soft_text", "chip", "dot_off",
                        "dot_done", "green"):
                self.assertIn(key, theme)

    def test_unknown_theme_falls_back_to_light(self):
        m = scale.Metrics(self.root, theme="nope")
        self.assertIs(m.theme, scale.LIGHT)

    def test_known_theme_is_used(self):
        m = scale.Metrics(self.root, theme="mono")
        self.assertIs(m.theme, scale.MONO)
        self.assertEqual(m.palette("accent"), "#000000")
        self.assertEqual(m.palette("missing", "#123456"), "#123456")
        self.assertEqual(m.palette("missing"), "#000000")

    def test_scale_and_font(self):
        m = scale.Metrics(self.root, theme="aero")
        m.z = 1.5
        self.assertEqual(m.s(10), 15)
        self.assertEqual(m.s(10.2), 15)
        self.assertEqual(m.font(11), (m.family, 11))
        self.assertEqual(m.font(11, True), (m.family, 11, "bold"))
        self.assertEqual(m.font(1)[1], 8)          # 最小字号
        self.assertEqual(m.img_px, 560)            # img_px 在 __init__ 时按真实 z 定

    def test_window_size_never_exceeds_screen(self):
        m = scale.Metrics(self.root)
        m.screen = lambda: (800, 600)
        m.z = 1.0
        w, h = m.window_size()
        self.assertLessEqual(w, 760)
        self.assertLessEqual(h, 520)
        m.screen = lambda: (4000, 3000)
        w, h = m.window_size()
        self.assertEqual((w, h), (scale.DESIGN_W, scale.DESIGN_H))

    def test_font_family_falls_back_when_font_service_fails(self):
        with mock.patch.object(scale.tkfont, "families",
                               side_effect=RuntimeError("no font service")):
            m = scale.Metrics(self.root)
        self.assertEqual(m.family, "TkDefaultFont")


class DpiTests(unittest.TestCase):
    def test_non_windows_is_skipped(self):
        with mock.patch.object(scale.os, "name", "posix"):
            self.assertEqual(scale.enable_dpi_awareness(), "skipped:not-windows")

    def _fake_ctypes(self, shcore=None, user32=None):
        fake = types.ModuleType("ctypes")
        fake.windll = types.SimpleNamespace()
        if shcore is not None:
            fake.windll.shcore = types.SimpleNamespace(
                SetProcessDpiAwareness=shcore)
        if user32 is not None:
            fake.windll.user32 = types.SimpleNamespace(
                SetProcessDPIAware=user32)
        return fake

    def test_shcore_success(self):
        fake = self._fake_ctypes(shcore=lambda level: 0)
        with mock.patch.object(scale.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"ctypes": fake}):
            self.assertEqual(scale.enable_dpi_awareness(), "shcore:ok")

    def test_shcore_nonzero_result(self):
        fake = self._fake_ctypes(shcore=lambda level: 5,
                                 user32=lambda: None)
        with mock.patch.object(scale.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"ctypes": fake}):
            self.assertEqual(scale.enable_dpi_awareness(), "shcore:hr=5")

    def test_shcore_missing_falls_back_to_user32(self):
        fake = self._fake_ctypes(user32=lambda: None)
        with mock.patch.object(scale.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"ctypes": fake}):
            self.assertEqual(scale.enable_dpi_awareness(), "user32:ok")

    def test_both_fail(self):
        def boom():
            raise OSError("no")

        fake = self._fake_ctypes(user32=boom)
        with mock.patch.object(scale.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"ctypes": fake}):
            self.assertEqual(scale.enable_dpi_awareness(), "failed:OSError")


class RequireTkSmoke(UiCase):
    @requires_tk
    def test_root_is_real(self):
        self.assertTrue(self.root.winfo_exists())
