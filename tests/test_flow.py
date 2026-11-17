# -*- coding: utf-8 -*-
"""v2 向导状态机（``ulpp.ui.flow``）：纯逻辑，不碰窗口，也不碰真实 %APPDATA%。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from ulpp.ui import flow as F


class StepTests(unittest.TestCase):
    def test_starts_at_first_step(self):
        f = F.Flow()
        self.assertEqual(f.current, "sheet")
        self.assertEqual(f.number, 1)
        self.assertEqual(f.total, len(F.STEP_IDS))
        self.assertTrue(f.is_first)
        self.assertFalse(f.is_last)

    def test_next_and_prev_clamp(self):
        f = F.Flow()
        self.assertFalse(f.prev())
        self.assertEqual(f.current, "sheet")
        for _ in range(len(F.STEP_IDS) - 1):
            self.assertTrue(f.next())
        self.assertTrue(f.is_last)
        self.assertFalse(f.next())
        self.assertEqual(f.current, "output")
        self.assertTrue(f.prev())
        self.assertEqual(f.current, "orient")

    def test_goto_accepts_id_and_index(self):
        f = F.Flow()
        self.assertTrue(f.goto("orient"))
        self.assertEqual(f.number, 2)
        self.assertTrue(f.goto(0))
        self.assertEqual(f.current, "sheet")
        self.assertFalse(f.goto("nope"))
        self.assertFalse(f.goto(99))
        self.assertFalse(f.goto(-1))
        self.assertEqual(f.current, "sheet")


class SkipTests(unittest.TestCase):
    def test_skip_records_and_advances(self):
        f = F.Flow()
        f.skip()
        self.assertEqual(f.current, "orient")
        self.assertTrue(f.is_skipped("sheet"))
        self.assertNotIn("sheet", f.skipped[1:])

    def test_skip_is_idempotent(self):
        f = F.Flow()
        f.skip()
        f.prev()
        f.skip()
        self.assertEqual(f.skipped.count("sheet"), 1)

    def test_skip_on_last_step_finishes(self):
        f = F.Flow(index=len(F.STEP_IDS) - 1)
        self.assertFalse(f.skip())
        self.assertTrue(f.finished)
        self.assertEqual(f.current, "output")

    def test_finish_and_reset(self):
        f = F.Flow(index=2)
        f.answer("paper", "45")
        f.finish()
        self.assertTrue(f.finished)
        f.reset()
        self.assertFalse(f.finished)
        self.assertEqual(f.number, 1)
        self.assertEqual(f.answers, {})


class AnswerTests(unittest.TestCase):
    def test_get_set_and_default(self):
        f = F.Flow()
        self.assertIsNone(f.answer("paper"))
        self.assertEqual(f.answer("paper", default="45"), "45")
        f.answer("paper", "24")
        self.assertEqual(f.answer("paper"), "24")
        f.answer("no_scanner", True)
        self.assertIs(f.answer("no_scanner"), True)


class StoreTests(unittest.TestCase):
    def setUp(self):
        # 两个环境坑：① 沙箱允许建目录、不许删目录（ACL 拒绝），所以不用 TemporaryDirectory；
        # ② 沙箱里 tempfile.mkdtemp 建出来的目录**不可写**（0o700 + ACL），要用 makedirs。
        self.dir = Path(tempfile.gettempdir()) / ("ulpp_flow_%s" % uuid.uuid4().hex[:8])
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "v2_flow.json"

    def tearDown(self):
        for item in list(self.dir.glob("*")):
            try:
                item.unlink()
            except OSError:
                pass

    def test_save_load_roundtrip(self):
        f = F.Flow()
        f.answer("paper", "45")
        f.next()
        f.skip()
        f.finish()
        self.assertEqual(f.save(path=self.path), self.path)
        self.assertTrue(self.path.is_file())

        back = F.Flow.load(path=self.path)
        self.assertEqual(back.number, f.number)
        self.assertEqual(back.skipped, f.skipped)
        self.assertEqual(back.answer("paper"), "45")
        self.assertTrue(back.finished)

    def test_missing_file_starts_fresh(self):
        back = F.Flow.load(path=self.path)
        self.assertEqual(back.current, "sheet")
        self.assertEqual(back.answers, {})

    def test_corrupt_file_starts_fresh(self):
        self.path.write_text("{not json", encoding="utf-8")
        back = F.Flow.load(path=self.path)
        self.assertEqual(back.current, "sheet")
        self.assertIsNone(back.last_error)

    def test_index_is_clamped(self):
        f = F.Flow.from_dict({"index": 999})
        self.assertEqual(f.current, "output")
        f = F.Flow.from_dict({"index": -5})
        self.assertEqual(f.current, "sheet")

    def test_old_six_step_state_migrates(self):
        """旧版 6 站存档（devices/paper/model/orient/test/done）读进来要能用，答案不丢。"""
        old = {"version": 1, "steps": ["devices", "paper", "model", "orient", "test", "done"],
               "index": 3, "skipped": ["devices", "model"], "answers": {"paper": "45"},
               "finished": False}
        f = F.Flow.from_dict(old)
        self.assertEqual(f.steps, F.STEP_IDS)
        self.assertEqual(f.answers["paper"], "45")
        self.assertEqual(f.index, 0)          # 布局换了就从头来，但不炸
        f = F.Flow.from_dict({"answers": [1, 2], "index": "x"})
        self.assertEqual(f.steps, F.STEP_IDS)
        self.assertEqual(f.answers, {})

    def test_garbage_shape_is_tolerated(self):
        for bad in (None, [], "x", 3):
            f = F.Flow.from_dict(bad)
            self.assertEqual(f.current, "sheet")

    def test_save_failure_is_soft(self):
        f = F.Flow()
        unwritable = self.dir / "file.txt"
        unwritable.write_text("x", encoding="utf-8")
        target = unwritable / "v2_flow.json"      # 父路径是文件 → 必然失败
        self.assertIsNone(f.save(path=target))
        self.assertIsNotNone(f.last_error)
        self.assertIn("Error", f.last_error or "")

    def test_env_override_changes_state_dir(self):
        with mock.patch.dict(os.environ, {F.ENV_STATE_DIR: str(self.dir)}):
            self.assertEqual(F.default_state_dir(), self.dir)
            self.assertEqual(F.state_path(), self.dir / F.STATE_FILE)
            f = F.Flow()
            f.answer("paper", "12")
            written = f.save()
            self.assertEqual(written, self.dir / F.STATE_FILE)
            self.assertEqual(F.Flow.load().answer("paper"), "12")

    def test_state_path_explicit(self):
        self.assertEqual(F.state_path(self.path), self.path)
        self.assertEqual(F.state_path(directory=self.dir.name),
                         Path(self.dir.name) / F.STATE_FILE)


    def test_default_state_dir_prefers_override_then_appdata(self):
        env = dict(os.environ)
        env.pop("APPDATA", None)
        env.pop(F.ENV_STATE_DIR, None)
        with mock.patch.dict(os.environ, dict(env, APPDATA="/tmp/appdata"),
                             clear=True):
            self.assertEqual(F.default_state_dir(), Path("/tmp/appdata") / "ulpp")

    def test_default_state_dir_falls_back_to_home(self):
        env = dict(os.environ)
        env.pop("APPDATA", None)
        env.pop(F.ENV_STATE_DIR, None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(F.default_state_dir(), Path.home() / ".ulpp")


class RatchetTests(unittest.TestCase):
    """变异测试补出来的用例：把“看似无关”的行为也钉死。"""

    def setUp(self):
        self.dir = Path(tempfile.gettempdir()) / ("ulpp_flow_%s" % uuid.uuid4().hex[:8])
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "v2_flow.json"

    def tearDown(self):
        for item in list(self.dir.glob("*")):
            try:
                item.unlink()
            except OSError:
                pass

    def test_state_version_is_three(self):
        self.assertEqual(F.STATE_VERSION, 3)
        self.assertEqual(F.Flow().to_dict()["version"], F.STATE_VERSION)

    def test_fresh_flow_is_not_finished(self):
        self.assertFalse(F.Flow().finished)
        self.assertFalse(F.Flow().is_skipped("sheet"))

    def test_empty_steps_fall_back_to_default(self):
        f = F.Flow(steps=())
        self.assertEqual(f.current, "sheet")
        self.assertEqual(f.steps, F.STEP_IDS)

    def test_missing_index_defaults_to_first(self):
        f = F.Flow.from_dict({"answers": {"paper": "45"}})
        self.assertEqual(f.current, "sheet")
        self.assertEqual(f.number, 1)

    def test_save_creates_missing_parent_dirs(self):
        nested = self.dir / "deep" / "nested"
        target = nested / F.STATE_FILE
        f = F.Flow()
        f.answer("paper", "45")
        self.assertEqual(f.save(path=target), target)
        self.assertTrue(target.is_file())

    def test_saved_file_is_exact_json_layout(self):
        f = F.Flow()
        f.answer("paper", "标签")
        f.next()
        target = f.save(path=self.path)
        expected = json.dumps(f.to_dict(), ensure_ascii=False, indent=2)
        self.assertEqual(target.read_text(encoding="utf-8"), expected)
        # 非中文答案不被 \u 转义
        self.assertIn("标签", target.read_text(encoding="utf-8"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
