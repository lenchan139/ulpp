# -*- coding: utf-8 -*-
"""i18n 的回退、告警去重与语言解析分支。"""

import json
import os
import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ulpp import i18n

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class I18nEdgeBase(unittest.TestCase):
    def setUp(self):
        self._packs = dict(i18n._PACKS)
        self._warned = set(i18n._WARNED)
        self._current = i18n._CURRENT
        self._initialized = i18n._INITIALIZED
        self.dir = os.path.join(ROOT, f"ulpp_i18n_edge_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def tearDown(self):
        i18n._PACKS.clear()
        i18n._PACKS.update(self._packs)
        i18n._WARNED.clear()
        i18n._WARNED.update(self._warned)
        i18n._CURRENT = self._current
        i18n._INITIALIZED = self._initialized


class TestWarn(I18nEdgeBase):
    def test_warn_without_stderr(self):
        with patch.object(i18n, "sys", SimpleNamespace(stderr=None)):
            self.assertIsNone(i18n._warn("ignored"))

    def test_warn_once_deduplicates(self):
        with patch.object(i18n, "_warn") as warn:
            i18n._warn_once("same-key", "first")
            i18n._warn_once("same-key", "second")
        self.assertEqual(warn.call_count, 1)
        self.assertIn("same-key", i18n._WARNED)


class TestNormalize(I18nEdgeBase):
    def test_empty_values(self):
        self.assertIsNone(i18n.normalize_language(None))
        self.assertIsNone(i18n.normalize_language("   "))

    def test_hyphen_and_words(self):
        self.assertEqual(i18n.normalize_language("zh-TW"), "zh_CN")
        self.assertEqual(i18n.normalize_language("en-GB"), "en_US")
        self.assertEqual(i18n.normalize_language("Chinese"), "zh_CN")
        self.assertEqual(i18n.normalize_language("English"), "en_US")
        self.assertIsNone(i18n.normalize_language("Klingon"))

    def test_language_name_unknown(self):
        self.assertEqual(i18n.language_name("xx_YY"), "xx_YY")


class TestLocaleDir(I18nEdgeBase):
    def test_meipass_branch_is_consulted(self):
        with patch.object(i18n, "sys", SimpleNamespace(_MEIPASS=self.dir)):
            path = i18n._locale_dir()
        self.assertTrue(path.is_dir())

    def test_falls_back_to_package_path(self):
        with patch.object(i18n, "__file__", "/nonexistent/ulpp/i18n.py"), \
                patch.object(i18n, "sys", SimpleNamespace()):
            path = i18n._locale_dir()
        self.assertEqual(path.name, "locales")
        self.assertIn("ulpp", str(path))


class TestLoad(I18nEdgeBase):
    def test_missing_pack_warns_and_returns_empty(self):
        with patch.object(i18n, "_warn") as warn:
            pack = i18n._load("xx_MISSING")
        self.assertEqual(pack, {})
        self.assertEqual(warn.call_count, 1)

    def test_non_object_pack_is_empty(self):
        name = "broken_test"
        Path(self.dir, f"{name}.json").write_text("[]", encoding="utf-8")
        with patch.object(i18n, "_locale_dir", return_value=Path(self.dir)), \
                patch.object(i18n, "_warn"):
            self.assertEqual(i18n._load(name), {})

    def test_load_pack_normalizes(self):
        pack = i18n.load_pack("en")
        self.assertIsInstance(pack, dict)
        self.assertTrue(pack)


class TestResolve(I18nEdgeBase):
    def test_env_language_used(self):
        with patch.dict(os.environ, {"LC_ALL": "zh_CN.UTF-8"}, clear=True):
            self.assertEqual(i18n._env_language(), "zh_CN")

    def test_env_language_absent(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(i18n._env_language())

    def test_system_language_reads_locale(self):
        with patch.object(i18n.locale, "getlocale",
                          return_value=("en_US", "UTF-8")):
            self.assertEqual(i18n._system_language(), "en_US")

    def test_system_language_error_is_soft(self):
        with patch.object(i18n.locale, "getlocale",
                          side_effect=OSError("no locale")):
            self.assertIsNone(i18n._system_language())

    def test_empty_pack_falls_back_to_default(self):
        with patch.object(i18n, "_load", return_value={}), \
                patch.object(i18n, "_warn") as warn:
            code = i18n.resolve_language("en")
        self.assertEqual(code, i18n.DEFAULT_LANGUAGE)
        self.assertEqual(warn.call_count, 1)

    def test_unsupported_explicit_warns_but_resolves(self):
        with patch.object(i18n, "_warn") as warn, \
                patch.dict(os.environ, {"LC_ALL": "zh_CN.UTF-8"}, clear=True):
            code = i18n.resolve_language("xx_EDGE_ONLY")
        self.assertEqual(code, "zh_CN")
        self.assertEqual(warn.call_count, 1)


if __name__ == "__main__":
    unittest.main()
