# -*- coding: utf-8 -*-
"""属性/生成式测试（不引第三方库：用固定种子的 random 自己生成）。

不追求证明，只追求“用几百个随机输入暴露不变量被破坏”。
所有用例都用固定种子，可复现。
"""
from __future__ import annotations

import json
import random
import unittest

from ulpp.config import GridSpec
from ulpp.partial import plan_placements
from ulpp.sheets import SheetRecord
from ulpp.textlabel import parse_text_block
from ulpp.ui.flow import Flow, STEP_IDS


def _rand_flow(rng: random.Random) -> Flow:
    f = Flow()
    for _ in range(rng.randint(0, 12)):
        action = rng.choice(["next", "prev", "goto", "skip", "answer", "reset"])
        if action == "next":
            f.next()
        elif action == "prev":
            f.prev()
        elif action == "goto":
            f.goto(rng.choice([0, 1, 2, 99, "sheet", "orient", "output", "nope"]))
        elif action == "skip":
            f.skip()
        elif action == "answer":
            f.answer("k%d" % rng.randint(0, 3), rng.randint(0, 99))
        else:
            f.reset()
    return f


class FlowPropertyTests(unittest.TestCase):
    SEED = 20260101

    def test_random_navigation_invariants(self):
        rng = random.Random(self.SEED)
        for round_no in range(120):
            f = _rand_flow(rng)
            # 不变量 1：current 一定指向合法站
            self.assertIn(f.current, STEP_IDS)
            # 不变量 2：index 在范围内
            self.assertTrue(0 <= f.index < len(f.steps))
            # 不变量 3：skipped 里的站都是合法站且去重
            self.assertEqual(len(f.skipped), len(set(f.skipped)))
            for s in f.skipped:
                self.assertIn(s, STEP_IDS)
            # 不变量 4：finished 与 is_last+skip 的关系由 finish/skip 控制，reset 可清
            if f.finished:
                f.reset()
                self.assertFalse(f.finished)

    def test_save_load_roundtrip_random(self):
        rng = random.Random(self.SEED + 1)
        for _ in range(30):
            f = _rand_flow(rng)
            data = json.loads(json.dumps(f.to_dict()))
            back = Flow.from_dict(data)
            self.assertEqual(back.current, f.current)
            self.assertEqual(back.skipped, f.skipped)
            self.assertEqual(back.answers, f.answers)
            self.assertEqual(back.finished, f.finished)
            # 再走一次存/读（不落盘，走字典）
            back2 = Flow.from_dict(back.to_dict())
            self.assertEqual(back2.current, back.current)


class TextLabelPropertyTests(unittest.TestCase):
    SEED = 20260201

    def _rand_block(self, rng: random.Random) -> str:
        lines = []
        for _ in range(rng.randint(0, 6)):
            if rng.random() < 0.2:
                lines.append("")            # 空行
                continue
            text = "标签%d" % rng.randint(0, 9)
            if rng.random() < 0.4:
                text += "|%d" % rng.randint(1, 5)
            lines.append(text)
        return "\n".join(lines)

    def test_concat_equals_joined(self):
        """整块解析 == 逐行解析之和（空行不产生内容）。"""
        rng = random.Random(self.SEED)
        for _ in range(80):
            lines = []
            block = self._rand_block(rng)
            for line in block.splitlines():
                lines.extend(parse_text_block(line))
            joined = parse_text_block(block)
            self.assertEqual(
                [(i.text, i.copies) for i in lines],
                [(i.text, i.copies) for i in joined],
            )

    def test_copies_at_least_one_and_text_nonempty(self):
        rng = random.Random(self.SEED + 1)
        for _ in range(80):
            block = self._rand_block(rng)
            for item in parse_text_block(block):
                self.assertGreaterEqual(item.copies, 1)
                self.assertTrue(item.text)


class PartialPropertyTests(unittest.TestCase):
    SEED = 20260301

    def test_plan_placements_invariants(self):
        rng = random.Random(self.SEED)
        for _ in range(100):
            per_sheet = rng.randint(1, 48)
            free = sorted(rng.sample(range(per_sheet), rng.randint(0, per_sheet)))
            n_entries = rng.randint(0, per_sheet + 5)
            entries = [object() for _ in range(n_entries)]
            placements, leftover = plan_placements(free, entries)
            # 不变量 1：放的格子都在 free 里且不重复
            self.assertTrue(set(placements) <= set(free))
            # 不变量 2：每格一条内容
            self.assertLessEqual(len(placements), min(len(free), n_entries))
            # 不变量 3：leftover = 没塞下的条数
            self.assertEqual(leftover, max(0, n_entries - len(placements)))
            # 不变量 4：放的顺序 = free 的顺序
            self.assertEqual(list(placements), free[:len(placements)])


class SheetPropertyTests(unittest.TestCase):
    SEED = 20260401

    def test_used_free_count_invariant(self):
        rng = random.Random(self.SEED)
        for _ in range(60):
            grid = GridSpec().to_dict()
            sheet = SheetRecord(id="x", name="纸", grid=grid)
            per = sheet.per_sheet
            for _ in range(rng.randint(0, 20)):
                slot = rng.randrange(per)
                if rng.random() < 0.5:
                    sheet.mark_used([slot])
                else:
                    sheet.mark_free([slot])
            self.assertEqual(sheet.free_count, per - len(sheet.used_cells))
            self.assertEqual(sheet.free_count, len(sheet.free_cells))


class GridPropertyTests(unittest.TestCase):
    SEED = 20260501

    def test_grid_dict_roundtrip(self):
        rng = random.Random(self.SEED)
        for _ in range(60):
            spec = GridSpec(
                page_w=210.0, page_h=297.0,
                cols=rng.randint(1, 20), rows=rng.randint(1, 30),
                cell_w=rng.uniform(5, 60), cell_h=rng.uniform(5, 60),
                pitch_x=rng.uniform(6, 70), pitch_y=rng.uniform(6, 70),
                margin_top=rng.uniform(0, 20), inset=rng.uniform(0, 5),
            )
            data = spec.to_dict()
            back = GridSpec.from_dict(data)
            self.assertEqual(back.to_dict(), data)
            self.assertEqual(back.per_sheet, spec.cols * spec.rows)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
