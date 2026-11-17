# -*- coding: utf-8 -*-
"""Gherkin（BDD）用例：features/*.feature → tests/bdd/gherkin.py 的执行器。

- 每个场景生成一个独立的 unittest 方法，失败信息里带场景名和步骤文本；
- ``@skip`` 的场景跳过；步骤抛 ``unittest.SkipTest`` 同样生效（无 Tk 环境）；
- 这里也顺带钉住解析器本身的行为（Outline 展开、找不到步骤定义等）。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from .bdd import gherkin
from .bdd import steps as step_defs
from .bdd.gherkin import (Feature, Hooks, Scenario, Step, StepRegistry,
                          expand_scenario, parse_feature, parse_feature_text,
                          run_scenario)

FEATURES_DIR = Path(__file__).resolve().parent / "features"


def _safe(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", name).strip("_") or "x"


def _build_methods() -> None:
    for feature_path in sorted(FEATURES_DIR.glob("*.feature")):
        feature = parse_feature(feature_path)
        for scenario in feature.scenarios:
            if "skip" in scenario.tags:
                continue
            for index, one in enumerate(expand_scenario(scenario)):

                def _test(self, _feature=feature, _scenario=one, _index=index):
                    _run_scenario(_feature, _scenario)

                _test.__doc__ = "%s / %s" % (feature.title, one.name)
                method_name = "test_%s_%s" % (
                    _safe(feature_path.stem), _safe(one.name))
                if hasattr(BddFeatureTests, method_name):
                    method_name = "%s_%d" % (method_name, _index)
                setattr(BddFeatureTests, method_name, _test)


def _run_scenario(feature: Feature, scenario: Scenario) -> None:
    context = {}
    try:
        context = run_scenario(feature, scenario, step_defs.REGISTRY)
    finally:
        for hook in step_defs.HOOKS.after_scenario:
            hook(context)


class BddFeatureTests(unittest.TestCase):
    """由 ``_build_methods()`` 动态填充。"""


_build_methods()


class ParserTests(unittest.TestCase):
    def test_parses_feature_background_and_steps(self):
        feature = parse_feature_text(
            "@x\nFeature: 标题\n"
            "  Background:\n    Given 前置\n"
            "  Scenario: 一\n    When 动作\n    Then 结果\n")
        self.assertEqual(feature.title, "标题")
        self.assertEqual(feature.tags, ["x"])
        self.assertEqual([s.text for s in feature.background], ["前置"])
        self.assertEqual(len(feature.scenarios), 1)
        self.assertEqual([s.keyword for s in feature.scenarios[0].steps],
                         ["When", "Then"])
        self.assertEqual(feature.scenarios[0].steps[1].keyword, "Then")

    def test_and_but_inherit_then_role(self):
        feature = parse_feature_text(
            "Feature: t\n  Scenario: s\n    Given a\n    And b\n    But c\n")
        steps = feature.scenarios[0].steps
        self.assertEqual([s.keyword for s in steps], ["Given", "Then", "Then"])

    def test_comments_and_blank_lines_are_ignored(self):
        feature = parse_feature_text(
            "Feature: t\n  # 注释\n\n  Scenario: s\n    When 动作 # 说明\n")
        self.assertEqual(feature.scenarios[0].steps[0].text, "动作")

    def test_outline_rows_expand_with_substitution(self):
        text = (
            "Feature: t\n"
            "  Scenario Outline: 数一数\n"
            "    When 数 <n> 个\n"
            "    Examples:\n"
            "      | n | 什么 |\n"
            "      | 1 | 苹果 |\n"
            "      | 3 | 梨   |\n")
        feature = parse_feature_text(text)
        scenarios = expand_scenario(feature.scenarios[0])
        self.assertEqual(len(scenarios), 2)
        self.assertEqual(scenarios[0].steps[0].text, "数 1 个")
        self.assertEqual(scenarios[1].name, "数一数 [2]")

    def test_skip_tag_is_honoured(self):
        feature = parse_feature_text(
            "Feature: t\n  @skip\n  Scenario: s\n    When 动作\n"
            "  Scenario: 跑\n    When 动作\n")
        registry = StepRegistry()
        called = []
        registry.register(r"动作", lambda ctx: called.append(1))
        gherkin.run_feature(feature, registry)
        self.assertEqual(called, [1])

    def test_missing_step_definition_raises(self):
        feature = parse_feature_text(
            "Feature: t\n  Scenario: s\n    When 没定义的动作\n")
        with self.assertRaises(LookupError):
            run_scenario(feature, feature.scenarios[0], StepRegistry())

    def test_run_feature_cleans_up_on_failure(self):
        class Boom(Exception):
            pass

        feature = parse_feature_text(
            "Feature: t\n  Scenario: s\n    When 炸\n")
        registry = StepRegistry()
        registry.register(r"炸", lambda ctx: (_ for _ in ()).throw(Boom()))
        cleaned = []
        hooks = Hooks()
        hooks.after_scenario.append(lambda ctx: cleaned.append(True))
        with self.assertRaises(Boom):
            gherkin.run_feature(feature, registry, hooks)
        self.assertEqual(cleaned, [True])

    def test_step_dataclasses(self):
        step = Step(keyword="Given", text="x", line=3)
        self.assertEqual(step.keyword, "Given")
        self.assertTrue(Scenario(name="s").is_outline is False)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
