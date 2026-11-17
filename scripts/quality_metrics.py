# -*- coding: utf-8 -*-
"""质量指标（quality metrics）：一次跑完，超出底线就挂。

指标分两类：
- **静态**：圈复杂度、函数长度、模块行数、docstring 覆盖率、TODO 数 —— 用 ast 数；
- **动态**：语句覆盖率 —— 读 ``coverage json``（没有该文件就跳过并标注 NA）。

阈值是“棘轮”（ratchet）：按当前基线卡死，代码只能变好不能变差；
要放松阈值必须改本文件并说明原因（见 docs/design/qa.md）。

用法：
    python3 scripts/quality_metrics.py                     # 打印表格
    python3 scripts/quality_metrics.py --json quality.json # 额外输出 JSON
    python3 scripts/quality_metrics.py --fail              # 超线时 exit 1
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "ulpp"

# ------------------------------------------------------------- 底线（棘轮）
THRESHOLDS = {
    # 2026-11 基线：max_cc=30, max_fn_lines=238, max_module_lines=930, docstring=27%
    "coverage_min": 98.0,          # CI（Linux/macOS）实测 99%
    "max_cyclomatic": 30,
    "max_function_lines": 238,
    "max_module_lines": 930,
    "min_docstring_ratio": 0.26,
    "max_todo": 0,                 # 现在 0 个 TODO；要留必须在这里放宽并写原因
}

_DECISION_NODES = (ast.If, ast.For, ast.While, ast.IfExp,
                   ast.ExceptHandler, ast.Assert)
_TODO_RE = re.compile(r"\b(TODO|FIXME|XXX)\b", re.I)


def cyclomatic(node: ast.AST) -> int:
    """近似圈复杂度：1 + 分支点（if/for/while/except/三元/断言/布尔/推导式）。"""
    score = 1
    for child in ast.walk(node):
        if isinstance(child, _DECISION_NODES):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(0, len(child.values) - 1)
        elif isinstance(child, ast.comprehension):
            score += 1 + len(child.ifs)
    return score


def _docstring(node: ast.AST) -> bool:
    return ast.get_docstring(node) is not None


def module_metrics(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = len(path.read_text(encoding="utf-8").splitlines())
    functions, docstrings, max_cc, max_fn_lines = 0, 0, 1, 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions += 1
            if _docstring(node):
                docstrings += 1
            cc = cyclomatic(node)
            fn_lines = (node.end_lineno or node.lineno) - node.lineno + 1
            max_cc = max(max_cc, cc)
            max_fn_lines = max(max_fn_lines, fn_lines)
    classes = sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree))
    todos = len(_TODO_RE.findall(path.read_text(encoding="utf-8")))
    return {
        "path": str(path.relative_to(ROOT)),
        "lines": lines,
        "functions": functions,
        "classes": classes,
        "docstring_ratio": (docstrings / functions) if functions else 1.0,
        "max_cyclomatic": max_cc,
        "max_function_lines": max_fn_lines,
        "todos": todos,
    }


def collect() -> dict:
    modules = [module_metrics(p) for p in sorted(SRC.rglob("*.py"))]
    total_todos = sum(m["todos"] for m in modules)
    funcs = sum(m["functions"] for m in modules)
    doc_funcs = sum(round(m["docstring_ratio"] * m["functions"]) for m in modules)
    return {
        "modules": modules,
        "module_count": len(modules),
        "total_lines": sum(m["lines"] for m in modules),
        "total_functions": funcs,
        "docstring_ratio": (doc_funcs / funcs) if funcs else 1.0,
        "max_cyclomatic": max((m["max_cyclomatic"] for m in modules), default=0),
        "max_function_lines": max((m["max_function_lines"] for m in modules),
                                  default=0),
        "max_module_lines": max((m["lines"] for m in modules), default=0),
        "todos": total_todos,
        "coverage": None,
    }


def load_coverage(path: Path) -> float:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("totals", {})
    percent = summary.get("percent_covered")
    return float(percent) if percent is not None else None


def violations(metrics: dict) -> list:
    out = []
    cov = metrics["coverage"]
    if cov is not None and cov < THRESHOLDS["coverage_min"]:
        out.append("coverage %.1f%% < %.1f%%" % (cov, THRESHOLDS["coverage_min"]))
    if metrics["max_cyclomatic"] > THRESHOLDS["max_cyclomatic"]:
        out.append("max cyclomatic %d > %d"
                   % (metrics["max_cyclomatic"], THRESHOLDS["max_cyclomatic"]))
    if metrics["max_function_lines"] > THRESHOLDS["max_function_lines"]:
        out.append("max function lines %d > %d"
                   % (metrics["max_function_lines"],
                      THRESHOLDS["max_function_lines"]))
    if metrics["max_module_lines"] > THRESHOLDS["max_module_lines"]:
        out.append("max module lines %d > %d"
                   % (metrics["max_module_lines"], THRESHOLDS["max_module_lines"]))
    if metrics["docstring_ratio"] < THRESHOLDS["min_docstring_ratio"]:
        out.append("docstring ratio %.2f < %.2f"
                   % (metrics["docstring_ratio"],
                      THRESHOLDS["min_docstring_ratio"]))
    if metrics["todos"] > THRESHOLDS["max_todo"]:
        out.append("todo count %d > %d" % (metrics["todos"],
                                           THRESHOLDS["max_todo"]))
    return out


def format_report(metrics: dict) -> str:
    lines = [
        "== 质量指标 ==",
        "模块数 %d · 总行数 %d · 函数 %d · docstring %.0f%%"
        % (metrics["module_count"], metrics["total_lines"],
           metrics["total_functions"], metrics["docstring_ratio"] * 100),
        "最大圈复杂度 %d（线 %d）· 最长函数 %d 行 · 最大模块 %d 行 · TODO %d"
        % (metrics["max_cyclomatic"], THRESHOLDS["max_cyclomatic"],
           metrics["max_function_lines"], metrics["max_module_lines"],
           metrics["todos"]),
        "覆盖率 %s" % ("%.1f%%" % metrics["coverage"]
                       if metrics["coverage"] is not None else "未提供"),
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, default=None,
                        help="coverage json 路径（coverage json -o ...）")
    parser.add_argument("--json", type=Path, default=None,
                        help="把指标写成 JSON")
    parser.add_argument("--fail", action="store_true",
                        help="违反底线时返回非 0")
    args = parser.parse_args(argv)

    metrics = collect()
    if args.coverage and args.coverage.is_file():
        metrics["coverage"] = load_coverage(args.coverage)

    report = format_report(metrics)
    print(report)
    if args.json:
        args.json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    if args.fail:
        problems = violations(metrics)
        if problems:
            for problem in problems:
                print("!! %s" % problem, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
