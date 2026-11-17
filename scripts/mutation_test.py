# -*- coding: utf-8 -*-
"""轻量变异测试（mutation testing）：把源码里能改的都改一下，看测试能不能抓到。

- 用 ``ast`` 在内存里改语法树（比较符互换、布尔翻转、整数 +1、去掉 not、
  and/or 互换、Add/Sub 互换），``ast.unparse`` 写回源文件，跑指定测试；
- 跑完**立刻恢复原文件**（finally 兜底），失败/超时都不留脏文件；
- 幸存者（mutant 还让测试通过）= 测试网有洞，会列出位置。

为什么只挑小模块：每个 mutant 都要跑一遍测试；大模块的全量变异不现实，
先用小而关键的模块打样，幸存者必须补测试到 0（见 docs/design/qa.md）。

用法：
    python3 scripts/mutation_test.py \
        --pair src/ulpp/ui/flow.py=tests.test_flow \
        --pair src/ulpp/partial.py=tests.test_partial_plan \
        --max-mutants 40 --max-survivors 0
"""
from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BINOPS = {ast.Add: ast.Sub, ast.Sub: ast.Add,
          ast.Mult: ast.Div, ast.Div: ast.Mult,
          ast.BitOr: ast.BitAnd, ast.BitAnd: ast.BitOr,
          ast.FloorDiv: ast.Mod, ast.Mod: ast.FloorDiv}
CMPOPS = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
          ast.Lt: ast.GtE, ast.GtE: ast.Lt,
          ast.Gt: ast.LtE, ast.LtE: ast.Gt,
          ast.Is: ast.IsNot, ast.IsNot: ast.Is,
          ast.In: ast.NotIn, ast.NotIn: ast.In}


def _kind(node: ast.AST):
    if isinstance(node, ast.BinOp) and type(node.op) in BINOPS:
        return "binop"
    if isinstance(node, ast.Compare) and node.ops and type(node.ops[0]) in CMPOPS:
        return "compare"
    if isinstance(node, ast.BoolOp):
        return "boolop"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return "notop"
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "boolconst"
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            return "intconst"
    return None


def _walk(node: ast.AST, out: list, base_line: int = 0) -> None:
    kind = _kind(node)
    if kind:
        out.append((kind, node.lineno - base_line))
    for child in ast.iter_child_nodes(node):
        _walk(child, out, base_line)


class _OneShot(ast.NodeTransformer):
    """按枚举顺序只改第 target 个候选节点。"""

    def __init__(self, target: int) -> None:
        self.target = target
        self.seen = 0
        self.kind = None
        self.line = 0

    def _hit(self, node: ast.AST, kind: str):
        if self.seen == self.target:
            self.kind = kind
            self.line = node.lineno
        self.seen += 1
        return self.seen - 1 == self.target

    def visit_BinOp(self, node):
        if self._hit(node, "binop"):
            node.op = BINOPS[type(node.op)]()
        self.generic_visit(node)
        return node

    def visit_Compare(self, node):
        if self._hit(node, "compare"):
            node.ops = [CMPOPS[type(node.ops[0])]()]
        self.generic_visit(node)
        return node

    def visit_BoolOp(self, node):
        if self._hit(node, "boolop"):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        self.generic_visit(node)
        return node

    def visit_UnaryOp(self, node):
        if self._hit(node, "notop"):
            return node.operand          # not x → x
        self.generic_visit(node)
        return node

    def visit_Constant(self, node):
        kind = _kind(node)
        if kind and self._hit(node, kind):
            if kind == "boolconst":
                node.value = not node.value
            else:
                node.value = node.value + 1
        return node


@dataclass
class Mutant:
    index: int
    kind: str
    line: int
    source: str


def enumerate_mutants(source: str, limit: int, stride: int = 1) -> list:
    tree = ast.parse(source)
    candidates = []
    _walk(tree, candidates)
    chosen = list(range(0, len(candidates), stride))[:limit]
    mutants = []
    for index in chosen:
        tree = ast.parse(source)
        shot = _OneShot(index)
        mutated = shot.visit(tree)
        mutants.append(Mutant(index=index, kind=candidates[index][0],
                              line=candidates[index][1],
                              source=ast.unparse(mutated)))
    return mutants


@dataclass
class Result:
    module: str
    total_candidates: int
    run: int
    killed: int = 0
    survived: list = None
    errors: list = None
    seconds: float = 0.0

    def __post_init__(self):
        self.survived = self.survived or []
        self.errors = self.errors or []

    @property
    def score(self) -> float:
        checked = self.killed + len(self.survived) + len(self.errors)
        return (self.killed / checked) if checked else 1.0


def _run_tests(tests: str, timeout: float) -> tuple:
    tmp = tempfile.mkdtemp(prefix="ulpp_mut_env_")
    env = {
        "PYTHONPATH": str(ROOT / "src"),
        "PATH": "/usr/bin:/bin",
        # 让 default_state_dir 的 APPDATA / 家目录分支在子进程里也走到
        "APPDATA": tmp,
        # HOME 保持真实家目录：user site-packages 依赖它，改了会找不到 PIL
        "HOME": str(Path.home()),
        # 不写 .pyc：变异后的源文件必须重新编译，不能用缓存
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    cmd = [sys.executable, "-m", "unittest"] + tests.split(",") + ["-v", "-b"]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.returncode, proc.stdout.decode("utf-8", "replace")[-4000:]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def mutate_module(module: str, tests: str, limit: int, stride: int,
                  timeout: float, verbose: bool = False) -> Result:
    path = Path(module)
    if not path.is_absolute():
        path = ROOT / path
    original = path.read_text(encoding="utf-8")
    tree = ast.parse(original)
    candidates = []
    _walk(tree, candidates)
    result = Result(module=str(path.relative_to(ROOT)),
                    total_candidates=len(candidates), run=0)
    started = time.time()
    backup = None
    tmpdir = Path(tempfile.mkdtemp(prefix="ulpp_mut_"))
    try:
        backup = tmpdir / path.name
        shutil.copy2(path, backup)
        baseline_rc, _ = _run_tests(tests, timeout)
        if baseline_rc != 0:
            raise RuntimeError("基准测试没有全绿：%s" % tests)
        for mutant in enumerate_mutants(original, limit=limit, stride=stride):
            # 清掉字节码缓存：同尺寸的 mutant 可能命中旧缓存（mtime/size 校验）
            cache = path.parent / "__pycache__"
            if cache.is_dir():
                shutil.rmtree(str(cache), ignore_errors=True)
            path.write_text(mutant.source, encoding="utf-8")
            result.run += 1
            try:
                rc, output = _run_tests(tests, timeout)
            except subprocess.TimeoutExpired:
                result.errors.append(mutant)
                continue
            if rc == 0:
                result.survived.append(mutant)
                if verbose:
                    print("  SURVIVED %s:%d (%s)"
                          % (path.name, mutant.line, mutant.kind))
            else:
                result.killed += 1
    finally:
        shutil.copy2(backup, path)
        shutil.rmtree(str(tmpdir), ignore_errors=True)
    result.seconds = time.time() - started
    return result


def format_report(results: list) -> str:
    lines = ["== 变异测试 =="]
    for result in results:
        lines.append(
            "%s：候选 %d，抽测 %d，杀掉 %d，幸存 %d，出错 %d（%.1fs，得分 %.0f%%）"
            % (result.module, result.total_candidates, result.run,
               result.killed, len(result.survived), len(result.errors),
               result.seconds, result.score * 100))
        for mutant in result.survived:
            lines.append("  幸存 #%-3d %s 第 %d 行" % (mutant.index, mutant.kind,
                                                      mutant.line))
        for mutant in result.errors:
            lines.append("  超时 #%-3d %s 第 %d 行" % (mutant.index, mutant.kind,
                                                      mutant.line))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", action="append", default=[],
                        help="模块=测试（可重复），如 src/ulpp/partial.py=tests.test_partial_plan")
    parser.add_argument("--max-mutants", type=int, default=30)
    parser.add_argument("--stride", type=int, default=1,
                        help="每 stride 个候选抽 1 个（控制运行时间）")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="单次测试超时（秒）")
    parser.add_argument("--max-survivors", type=int, default=None,
                        help="幸存者超过该数则 exit 1")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if not args.pair:
        parser.error("至少给一个 --pair")

    results = []
    try:
        for pair in args.pair:
            module, _, tests = pair.partition("=")
            if not tests:
                parser.error("--pair 需要 模块=测试 的形式：%s" % pair)
            result = mutate_module(module, tests, limit=args.max_mutants,
                                   stride=args.stride, timeout=args.timeout,
                                   verbose=args.verbose)
            results.append(result)
            print("done", result.module, "survived", len(result.survived),
                  flush=True)
    finally:
        print(format_report(results))

    if args.max_survivors is not None:
        total = sum(len(r.survived) for r in results) + sum(len(r.errors)
                                                            for r in results)
        if total > args.max_survivors:
            print("!! 幸存/超时 %d > 允许 %d" % (total, args.max_survivors),
                  file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
