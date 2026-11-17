# -*- coding: utf-8 -*-
"""约束测试：把 AGENTS.md 的硬约束钉成用例，谁违反谁挂。

1. 离线：源码里不得 import 任何联网 / 数据库模块；
2. 只用 tkinter：不得 import Qt / PySide / customtkinter / WebView 系；
3. 名字只能是 ulpp：包名、入口、配置目录不许再出现 label_sheet / ULP；
4. 版本号两处一致：pyproject.toml 与 src/ulpp/__init__.py。
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "ulpp"

FORBIDDEN_MODULES = (
    # 联网
    "requests", "urllib", "urllib2", "http", "httpx", "aiohttp", "socket",
    "ssl", "telnetlib", "ftplib", "smtplib", "poplib", "imaplib",
    "xmlrpc", "websocket", "asyncio", "selenium",
    # 数据库（配置是纯 JSON）
    "sqlite3", "psycopg2", "pymongo", "mysql", "redis",
)
FORBIDDEN_GUI = (
    "PySide", "PyQt4", "PyQt5", "PyQt6", "qtpy", "Qt", "customtkinter",
    "webview", "wx", "PySimpleGUI", "flet",
)


def _py_files() -> list:
    return sorted(SRC.rglob("*.py"))


def _imports(tree: ast.AST) -> list:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module.split(".")[0])
    return names


class OfflineConstraintTests(unittest.TestCase):
    def test_no_network_or_database_imports(self):
        offenders = []
        for path in _py_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name in _imports(tree):
                if name in FORBIDDEN_MODULES:
                    offenders.append("%s: import %s" % (path.name, name))
        self.assertEqual(offenders, [])

    def test_no_cloud_hints_in_source(self):
        """注释/字符串里也不该出现“调云端”这类实现暗示（提示未来的人）。"""
        forbidden = ("api.openai.com", "chatgpt", "openai", "boto3", "firebase")
        offenders = []
        for path in _py_files():
            text = path.read_text(encoding="utf-8")
            for word in forbidden:
                if word in text:
                    offenders.append("%s: %s" % (path.name, word))
        self.assertEqual(offenders, [])


class TkOnlyConstraintTests(unittest.TestCase):
    def test_no_forbidden_gui_toolkits(self):
        offenders = []
        for path in _py_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name in _imports(tree):
                if name in FORBIDDEN_GUI:
                    offenders.append("%s: import %s" % (path.name, name))
        self.assertEqual(offenders, [])

    def test_tkinter_is_imported_somewhere(self):
        """界面层确实用的是 tkinter（防手滑删掉整个 UI）。"""
        found = any(
            "tkinter" in _imports(ast.parse(p.read_text(encoding="utf-8")))
            for p in _py_files()
        )
        self.assertTrue(found)


def _pyproject() -> dict:
    """不用 tomllib（本机是 3.9）：只需要 version / name / scripts 三个字段。"""
    text = (SRC.parent.parent / "pyproject.toml").read_text(encoding="utf-8")

    def field(name: str) -> str:
        match = re.search(r'^%s *= *"([^"]+)"' % name, text, re.M)
        assert match, "pyproject.toml 缺 %s" % name
        return match.group(1)

    scripts = dict(re.findall(
        r"^([A-Za-z0-9_]+) *= *\"(ulpp\.cli:main)\"", text, re.M))
    return {"version": field("version"), "name": field("name"),
            "scripts": scripts}


class NamingConstraintTests(unittest.TestCase):
    def test_package_is_ulpp(self):
        self.assertEqual(SRC.name, "ulpp")

    def test_no_legacy_names_in_paths(self):
        offenders = [
            str(p.relative_to(SRC))
            for p in _py_files()
            if re.search(r"label_?sheet|\bULP\b", p.stem)
        ]
        self.assertEqual(offenders, [])

    def test_entry_points_named_ulpp(self):
        self.assertIn("ulpp", _pyproject()["scripts"])


class VersionConsistencyTests(unittest.TestCase):
    def test_version_matches_pyproject(self):
        import ulpp

        self.assertEqual(_pyproject()["version"], ulpp.__version__)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
