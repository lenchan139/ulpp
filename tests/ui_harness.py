# -*- coding: utf-8 -*-
"""Tk 测试的共同底座。

- 每个用例一个临时状态目录（``ULPP_STATE_DIR`` + ``XDG_CONFIG_HOME``），
  不让测试碰到真实的 ``~/.config/ulpp``；
- 每个用例一个 ``tk.Tk()``（withdraw，不弹窗），用完销毁；
- 机器上没有 Tk（纯 CI 容器）时整组用例 skip，而不是报错。

注意仓库约定：Windows 沙箱里 ``tempfile.mkdtemp()`` 出来的目录不可写，
所以统一手写 ``makedirs``；目录删不掉也不影响用例结果。
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Optional

from ulpp.ui.flow import Flow


def _tk_available() -> bool:
    try:
        import tkinter as tk
    except Exception:            # pragma: no cover - 无 Tk 的环境
        return False
    try:
        root = tk.Tk()
    except Exception:            # pragma: no cover - 无显示/无 Tk 服务
        return False
    try:
        root.withdraw()
        root.update_idletasks()
    finally:
        root.destroy()
    return True


HAS_TK = _tk_available()
requires_tk = unittest.skipUnless(HAS_TK, "Tk 不可用（headless）")


class FakeMeasurement:
    """扫描/拍照量出来的结果（真的那个是 ``scan.Measurement``，这里只要字段）。"""

    def __init__(self, ok=True, confidence=0.9, **kw):
        self.ok = ok
        self.confidence = confidence
        self.cols = kw.get("cols", 5)
        self.rows = kw.get("rows", 9)
        self.cell_w_mm = kw.get("cell_w_mm", 40.0)
        self.cell_h_mm = kw.get("cell_h_mm", 30.0)
        self.pitch_x_mm = kw.get("pitch_x_mm", 41.5)
        self.pitch_y_mm = kw.get("pitch_y_mm", 32.0)
        self.first_x_mm = kw.get("first_x_mm", 4.0)
        self.first_y_mm = kw.get("first_y_mm", 6.0)
        self.page_w_mm = kw.get("page_w_mm", 210.0)
        self.page_h_mm = kw.get("page_h_mm", 297.0)
        self.rotation_deg = kw.get("rotation_deg", 0.0)
        self.warnings = kw.get("warnings", ["low_contrast: 太淡", "no_marks: 没刻度"])


class UiCase(unittest.TestCase):
    """带真实 Tk root 与隔离状态目录的 TestCase。"""

    def setUp(self) -> None:
        if not HAS_TK:          # pragma: no cover - 由 requires_tk 拦住
            self.skipTest("Tk 不可用（headless）")
        import tkinter as tk

        from ulpp.i18n import set_language

        set_language("zh_CN")
        self.tmpdir = Path(tempfile.gettempdir()) / (
            "ulpp_ui_%s" % uuid.uuid4().hex[:8])
        self.state_dir = self.tmpdir / "state"
        self.config_dir = self.tmpdir / "config"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._old_env = {
            key: os.environ.get(key)
            for key in ("ULPP_STATE_DIR", "XDG_CONFIG_HOME", "ULPP_THEME",
                        "ULPP_ALPHA", "ULPP_GRAD", "ULPP_SHAPE", "APPDATA")
        }
        os.environ["ULPP_STATE_DIR"] = str(self.state_dir)
        os.environ["XDG_CONFIG_HOME"] = str(self.config_dir)
        os.environ.pop("ULPP_THEME", None)
        os.environ.pop("ULPP_ALPHA", None)
        os.environ.pop("ULPP_GRAD", None)
        os.environ.pop("ULPP_SHAPE", None)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._teardown)

    def _teardown(self) -> None:
        try:
            if self.root.winfo_exists():
                self.root.destroy()
        except Exception:
            pass
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from ulpp.i18n import set_language

        set_language("zh_CN")
        shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    # ------------------------------------------------------------ 构造器
    def make_flow(self, **kw) -> Flow:
        return Flow(**kw)

    def make_shell(self, flow: Optional[Flow] = None, **kw):
        from ulpp.ui.shell import Shell

        shell = Shell(self.root, flow=flow or self.make_flow(), **kw)
        self.root.update_idletasks()
        return shell

    def pump(self) -> None:
        self.root.update_idletasks()

    def close_later(self, widget) -> None:
        """登记一个 Toplevel/控件，用例结束时无论如何都关掉。"""

        def _close():
            try:
                if widget.winfo_exists():
                    widget.destroy()
            except Exception:
                pass

        self.addCleanup(_close)

    def destroy_toplevels(self) -> None:
        """把当前 root 下的 Toplevel 全关掉（模态窗会抢 grab）。"""
        try:
            children = list(self.root.winfo_children())
        except Exception:
            return
        for child in children:
            try:
                if child.winfo_class() == "Toplevel":
                    child.grab_release()
            except Exception:
                pass
            try:
                child.destroy()
            except Exception:
                pass
        self.pump()
