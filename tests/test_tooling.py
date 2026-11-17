# -*- coding: utf-8 -*-
"""开发工具自身的测试：质量指标与变异工具不能成为盲区。"""
from __future__ import annotations

import ast
import json
import tempfile
import unittest
import uuid
from collections import Counter
from pathlib import Path

from scripts import mutation_test as mt
from scripts import quality_metrics as qm

ROOT = Path(__file__).resolve().parent.parent


class MetricsTests(unittest.TestCase):
    def test_collect_returns_sane_numbers(self):
        metrics = qm.collect()
        self.assertGreater(metrics["module_count"], 10)
        self.assertGreater(metrics["total_lines"], 1000)
        self.assertGreater(metrics["max_cyclomatic"], 1)
        self.assertLessEqual(metrics["max_module_lines"], 100000)
        self.assertTrue(0.0 <= metrics["docstring_ratio"] <= 1.0)
        self.assertIsNone(metrics["coverage"])

    def test_current_tree_passes_thresholds(self):
        metrics = qm.collect()
        self.assertEqual(qm.violations(metrics), [])

    def test_violations_fire_when_broken(self):
        metrics = qm.collect()
        metrics["coverage"] = 1.0
        metrics["max_cyclomatic"] = 999
        metrics["max_function_lines"] = 9999
        metrics["max_module_lines"] = 99999
        metrics["docstring_ratio"] = 0.0
        metrics["todos"] = 999
        problems = qm.violations(metrics)
        self.assertEqual(len(problems), 6)
        self.assertIn("coverage", problems[0])

    def test_coverage_reader(self):
        path = Path(tempfile.gettempdir()) / ("cov_%s.json" % uuid.uuid4().hex[:8])
        path.write_text(json.dumps({"totals": {"percent_covered": 99.1}}),
                        encoding="utf-8")
        try:
            self.assertAlmostEqual(qm.load_coverage(path), 99.1)
        finally:
            path.unlink(missing_ok=True)

    def test_report_mentions_coverage_when_missing(self):
        report = qm.format_report(qm.collect())
        self.assertIn("未提供", report)


class MutationToolTests(unittest.TestCase):
    SOURCE = (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def maybe(flag):\n"
        "    if flag and not flag:\n"
        "        return 1\n"
        "    return 2\n"
    )

    def test_candidates_are_enumerated_deterministically(self):
        first = mt.enumerate_mutants(self.SOURCE, limit=100)
        second = mt.enumerate_mutants(self.SOURCE, limit=100)
        self.assertEqual([m.index for m in first], [m.index for m in second])
        kinds = {m.kind for m in first}
        self.assertIn("binop", kinds)
        self.assertIn("boolop", kinds)
        self.assertIn("notop", kinds)
        self.assertIn("intconst", kinds)

    def test_binop_swap(self):
        mutants = mt.enumerate_mutants(self.SOURCE, limit=100)
        swapped = [m for m in mutants if m.kind == "binop" and m.line == 2]
        self.assertTrue(swapped)
        tree = ast.parse(swapped[0].source)
        node = ast.walk(tree) and next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.BinOp))
        self.assertIsInstance(node.op, ast.Sub)

    def test_bool_flip_and_not_removal(self):
        mutants = mt.enumerate_mutants(self.SOURCE, limit=100)
        sources = [m.source for m in mutants]
        # Add → Sub
        self.assertTrue(any(
            isinstance(next(n for n in ast.walk(ast.parse(s))
                            if isinstance(n, ast.BinOp)).op, ast.Sub)
            for s in sources))
        # and → or（保留 not）
        self.assertTrue(any("flag or not flag" in s for s in sources))
        # not x → x（去掉 not）
        self.assertTrue(any("flag and flag" in s for s in sources))

    def test_stride_limits_count(self):
        all_mutants = mt.enumerate_mutants(self.SOURCE, limit=100)
        sampled = mt.enumerate_mutants(self.SOURCE, limit=100, stride=2)
        self.assertGreater(len(all_mutants), 0)
        self.assertEqual(len(sampled), (len(all_mutants) + 1) // 2)

    def test_one_shot_only_changes_one_node(self):
        """除目标节点外，其余“可变异节点”在变异前后必须一致。"""
        def dumps(source: str) -> list:
            out = []
            _walk_dump(ast.parse(source), out)
            return out

        def _walk_dump(node: ast.AST, out: list) -> None:
            if mt._kind(node):
                out.append(ast.dump(node, include_attributes=False))
            for child in ast.iter_child_nodes(node):
                _walk_dump(child, out)

        original = dumps(self.SOURCE)
        for mutant in mt.enumerate_mutants(self.SOURCE, limit=100):
            mutated = dumps(mutant.source)
            added = list((Counter(mutated) - Counter(original)).elements())
            removed = list((Counter(original) - Counter(mutated)).elements())
            if len(mutated) == len(original):
                self.assertEqual(len(added), 1, mutant.index)
                self.assertEqual(len(removed), 1, mutant.index)
            else:
                # 去掉 not：候选少一个（UnaryOp 没了），且包含它的 BoolOp 也变了
                self.assertEqual(len(mutated), len(original) - 1, mutant.index)
                self.assertEqual(len(added), 1, mutant.index)
                self.assertEqual(len(removed), 2, mutant.index)
                self.assertTrue(any("UnaryOp" in x for x in removed))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
