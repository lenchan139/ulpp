# -*- coding: utf-8 -*-
"""极简 Gherkin 解析器 + 运行器（只用标准库，离线）。

支持的子集（够写业务场景即可，不追求全量语法）：
- ``Feature:`` 标题
- ``Background:`` 每个场景都执行的前置步骤
- ``Scenario:`` / ``Scenario Outline:`` + ``Examples:`` 数据表
- ``Given/When/Then/And/But`` 步骤
- ``@tag``（``@skip`` 的场景会被跳过）
- ``#`` 行注释、空行

设计取舍：故意不做参数表（step table）——现有场景用不上，少 200 行解析代码。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

STEP_KEYWORDS = ("Given", "When", "Then", "And", "But")
_SCENARIO_HEAD = re.compile(r"^(?:Scenario(?: Outline)?)\s*:\s*(.+?)$")
_STEP_LINE = re.compile(r"^([A-Za-z]+)\s+(.+?)$")
_TABLE_ROW = re.compile(r"^\|(.+)\|$")


@dataclass
class Step:
    keyword: str
    text: str
    line: int = 0


@dataclass
class Scenario:
    name: str
    tags: List[str] = field(default_factory=list)
    steps: List[Step] = field(default_factory=list)
    rows: List[Dict[str, str]] = field(default_factory=list)  # Outline 才有

    @property
    def is_outline(self) -> bool:
        return bool(self.rows)


@dataclass
class Feature:
    path: Optional[Path] = None
    title: str = ""
    tags: List[str] = field(default_factory=list)
    background: List[Step] = field(default_factory=list)
    scenarios: List[Scenario] = field(default_factory=list)


def parse_feature(path) -> Feature:
    return parse_feature_text(Path(path).read_text(encoding="utf-8"),
                              path=Path(path))


def parse_feature_text(text: str, path: Optional[Path] = None) -> Feature:
    """把 Gherkin 文本解析成结构；不认识的行直接忽略（宽容优先）。"""
    feature = Feature(path=path)
    scenario: Optional[Scenario] = None
    in_examples = False
    last_header: List[str] = []
    pending_tags: List[str] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("@"):
            if not feature.title:
                pending_tags.extend(stripped[1:].split())
            elif scenario is not None:
                scenario.tags.extend(stripped[1:].split())
            else:
                pending_tags.extend(stripped[1:].split())
            continue
        if stripped.startswith("Feature:"):
            feature.title = stripped[len("Feature:"):].strip()
            feature.tags = list(pending_tags)
            pending_tags = []
            continue
        match = _SCENARIO_HEAD.match(stripped)
        if match:
            scenario = Scenario(name=match.group(1), tags=list(pending_tags))
            pending_tags = []
            in_examples = False
            feature.scenarios.append(scenario)
            continue
        if stripped.startswith("Background:"):
            scenario = None
            in_examples = False
            continue
        if stripped.startswith("Examples:"):
            in_examples = True
            last_header = []
            continue
        row_match = _TABLE_ROW.match(stripped)
        if row_match and in_examples and scenario is not None:
            cells = [c.strip() for c in row_match.group(1).split("|")]
            if not last_header:
                last_header = cells
            else:
                scenario.rows.append(dict(zip(last_header, cells)))
            continue
        if row_match:
            continue                        # 非数据表的杂散表格行忽略

        step = _as_step(stripped, lineno)
        if step is None:
            continue
        if scenario is not None:
            in_examples = False             # 表格之后回到普通步骤
            scenario.steps.append(step)
        else:
            feature.background.append(step)
    return feature


def _as_step(stripped: str, lineno: int) -> Optional[Step]:
    match = _STEP_LINE.match(stripped)
    if not match:
        return None
    keyword = match.group(1)
    if keyword not in STEP_KEYWORDS:
        return None
    keyword = "Then" if keyword in ("And", "But") else keyword
    return Step(keyword=keyword, text=match.group(2), line=lineno)


def expand_scenario(scenario: Scenario) -> List[Scenario]:
    """Scenario Outline → 每行 Examples 一个具名场景。"""
    if not scenario.rows:
        return [scenario]
    out = []
    for i, row in enumerate(scenario.rows, start=1):
        steps = []
        for step in scenario.steps:
            text = step.text
            for key, value in row.items():
                text = text.replace("<%s>" % key, value)
            steps.append(Step(keyword=step.keyword, text=text, line=step.line))
        out.append(Scenario(name="%s [%d]" % (scenario.name, i),
                            tags=list(scenario.tags), steps=steps))
    return out


class StepRegistry:
    """``register("当前步骤是 (.+)")`` 风格；正则捕获组会作为参数传给函数。"""

    def __init__(self) -> None:
        self._steps: List[tuple] = []

    def register(self, pattern: str, func: Callable) -> None:
        self._steps.append((re.compile(pattern), func))

    def match(self, step: Step):
        for pattern, func in self._steps:
            match = pattern.fullmatch(step.text)
            if match:
                return func, match
        raise LookupError("没有步骤定义：%s %s" % (step.keyword, step.text))


class Hooks:
    def __init__(self) -> None:
        self.after_scenario: List[Callable[[dict], None]] = []


def run_scenario(feature: Feature, scenario: Scenario, registry: StepRegistry):
    """执行一个场景；任何步骤抛出的异常原样上抛（由 unittest 包装成失败）。"""
    context: dict = {}
    for step in list(feature.background) + list(scenario.steps):
        func, match = registry.match(step)
        func(context, *match.groups(), **match.groupdict())
    return context


def run_feature(feature: Feature, registry: StepRegistry,
                hooks: Optional[Hooks] = None) -> None:
    hooks = hooks or Hooks()
    for scenario in feature.scenarios:
        if "skip" in scenario.tags:
            continue
        for one in expand_scenario(scenario):
            context = {}
            try:
                context = run_scenario(feature, one, registry)
            finally:
                for hook in hooks.after_scenario:
                    hook(context)
