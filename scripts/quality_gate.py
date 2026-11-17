# -*- coding: utf-8 -*-
"""质量门（quality gate）：把"跑完全部关卡"变成一条命令。

    python3 scripts/quality_gate.py            # 全关卡
    python3 scripts/quality_gate.py --skip-mutation
    python3 scripts/quality_gate.py --html     # 额外生成 htmlcov/

关卡顺序（任何一关挂了就停，exit 1）：
1. ``compileall`` 语法/导入级检查；
2. 全量 unittest（含 BDD/属性/约束测试）；
3. 语句覆盖率（``.coveragerc``），并把 coverage.json 喂给质量指标；
4. 质量指标棘轮（复杂度/长度/docstring/TODO/覆盖率底线）；
5. 变异测试抽查（flow / partial / i18n，幸存者必须为 0）。

CI 里 ``tests`` 工作流的 quality job 跑的就是本脚本。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = dict(os.environ, PYTHONPATH=str(ROOT / "src"))

MUTATION_PAIRS = [
    "src/ulpp/ui/flow.py=tests.test_flow",
    "src/ulpp/partial.py=tests.test_partial_plan,tests.test_partial",
    "src/ulpp/i18n.py=tests.test_i18n,tests.test_i18n_edges",
]


def _run(title: str, cmd: list, **kw) -> None:
    print("\n$ %s" % " ".join(cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT), env=ENV, **kw)
    if rc != 0:
        print("\n!! %s 失败（exit %d）" % (title, rc), file=sys.stderr)
        raise SystemExit(rc)
    print("[ok] %s" % title, flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-mutation", action="store_true",
                        help="跳过关卡 5（本地快速迭代用）")
    parser.add_argument("--skip-unittest", action="store_true",
                        help="跳过关卡 2（CI 上矩阵已跑过）")
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args(argv)

    coverage_json = ROOT / "coverage.json"

    _run("语法检查", [sys.executable, "-m", "compileall", "-q", "src", "tests"])
    if not args.skip_unittest:
        _run("全量测试", [sys.executable, "-m", "unittest", "discover",
                          "-s", "tests", "-t", "."])
    _run("覆盖率采集", [sys.executable, "-m", "coverage", "run",
                        "--rcfile=.coveragerc", "-m", "unittest", "discover",
                        "-s", "tests", "-t", "."])
    extra = [sys.executable, "-m", "coverage", "report", "-m"]
    subprocess.call(extra, cwd=str(ROOT), env=ENV)
    _run("覆盖率 JSON", [sys.executable, "-m", "coverage", "json",
                         "-o", str(coverage_json)])
    if args.html:
        _run("覆盖率 HTML", [sys.executable, "-m", "coverage", "html"])
    _run("质量指标", [sys.executable, "scripts/quality_metrics.py",
                      "--coverage", str(coverage_json), "--fail"])
    if not args.skip_mutation:
        cmd = [sys.executable, "scripts/mutation_test.py"]
        for pair in MUTATION_PAIRS:
            cmd += ["--pair", pair]
        cmd += ["--max-mutants", "60", "--max-survivors", "0"]
        _run("变异抽查", cmd)
    print("\n全部关卡通过 ✓")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
