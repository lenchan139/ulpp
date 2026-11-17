# -*- coding: utf-8 -*-
"""开发用：跑全部 unittest 并输出覆盖率（不参与打包，不是运行时依赖）。

    python3 scripts/run_coverage.py            # 表格
    python3 scripts/run_coverage.py --html     # 额外生成 htmlcov/

需要先安装 coverage：``python3 -m pip install --user coverage``。
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "src") + os.pathsep + env.get("PYTHONPATH", "")
    run = [sys.executable, "-m", "coverage", "run", "--rcfile=.coveragerc",
           "-m", "unittest", "discover", "-s", "tests", "-t", "."]
    print("$", " ".join(run))
    rc = subprocess.call(run, cwd=ROOT, env=env)
    if rc:
        return rc
    report = [sys.executable, "-m", "coverage", "report", "-m"]
    subprocess.call(report, cwd=ROOT, env=env)
    if "--html" in argv:
        subprocess.call([sys.executable, "-m", "coverage", "html"],
                        cwd=ROOT, env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
