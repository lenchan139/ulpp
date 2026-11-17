# -*- coding: utf-8 -*-
"""把 Gherkin 场景接到真实代码上；一个正则一个动作，不写额外业务逻辑。"""
from __future__ import annotations

import os
import shutil
import tempfile
import tkinter as tk
import uuid
import zipfile
from pathlib import Path

from ulpp.partial import plan_placements
from ulpp.presets import by_key
from ulpp.textlabel import parse_text_block as parse_label_block
from ulpp.ui import flow as flow_mod
from ulpp.ui.flow import Flow
from ulpp.wizard import feed_from_answers

from .gherkin import Hooks, StepRegistry

REGISTRY = StepRegistry()
HOOKS = Hooks()


def _hook(hook) -> None:
    HOOKS.after_scenario.append(hook)


def register(pattern):
    def wrap(func):
        REGISTRY.register(pattern, func)
        return func
    return wrap


# ---------------------------------------------------------------- 公共
def _tmpdir(prefix: str) -> Path:
    path = Path(tempfile.gettempdir()) / ("%s_%s" % (prefix, uuid.uuid4().hex[:8]))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup(context: dict) -> None:
    root = context.get("root")
    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass
    state = context.get("state_dir_backup")
    if state is not None:
        old, value = state
        if value is None:
            os.environ.pop(old, None)
        else:
            os.environ[old] = value
    tmp = context.get("tmpdir")
    if tmp is not None:
        shutil.rmtree(str(tmp), ignore_errors=True)


_hook(_cleanup)


def _require_tk() -> tk.Tk:
    try:
        root = tk.Tk()
    except Exception as exc:                     # 无 Tk 的环境跳过整个场景
        import unittest

        raise unittest.SkipTest("Tk 不可用（headless）") from exc
    root.withdraw()
    return root


# ---------------------------------------------------------------- 向导状态机
@register(r"全新的向导")
def _fresh_flow(context):
    context["tmpdir"] = _tmpdir("ulpp_bdd_flow")
    context["flow"] = Flow()


@register(r"连续前进 (\d+) 步")
def _advance(context, count):
    for _ in range(int(count)):
        context["flow"].next()


@register(r"回退一步")
def _back(context):
    context["flow"].prev()


@register(r"再回退一步")
def _back_again(context):
    context["flow"].prev()


@register(r"跳到 (.+)")
def _goto(context, target):
    value = int(target) if target.isdigit() else target
    context["flow"].goto(value)


@register(r"当前站是 \"?(\w+)\"?")
def _assert_step(context, step_id):
    assert context["flow"].current == step_id, (
        "期望第 %s 站，实际 %s" % (step_id, context["flow"].current))


@register(r"在最后一站跳过")
def _skip_last(context):
    context["flow"].skip()


@register(r"向导已完成")
def _assert_done(context):
    assert context["flow"].finished


@register(r'回答 "(\S+)" 为 "(\S+)"')
def _answer(context, key, value):
    context["flow"].answer(key, value)


@register(r"保存进度")
def _save(context):
    assert context["flow"].save(directory=context["tmpdir"])


@register(r"重新读取进度")
def _reload(context):
    context["flow"] = Flow.load(directory=context["tmpdir"])


@register(r'答案 "(\S+)" 是 "(\S+)"')
def _assert_answer(context, key, value):
    assert context["flow"].answer(key) == value


@register(r'写入坏存档 "(.+)"')
def _write_bad(context, payload):
    (context["tmpdir"] / flow_mod.STATE_FILE).write_text(payload, encoding="utf-8")


@register(r"没有记录错误")
def _assert_no_error(context):
    assert context["flow"].last_error is None


# ---------------------------------------------------------------- 文字标签
@register(r'解析文字块 "(.*)"')
def _parse_block(context, block):
    text = block.replace("\\n", "\n")
    context["labels"] = parse_label_block(text)


@register(r"文字项数量是 (\d+)")
def _assert_label_count(context, count):
    assert len(context["labels"]) == int(count)


@register(r"第一项份数是 (\d+)")
def _assert_copies(context, count):
    assert context["labels"][0].copies == int(count)


@register(r'第一项文本是 "(.+)"')
def _assert_text(context, text):
    assert context["labels"][0].text == text


# ---------------------------------------------------------------- 接着打
@register(r'空闲格子 "(.*)"$')
def _free_cells(context, cells):
    context["free"] = [int(c) for c in cells.split(",") if c.strip()]


@register(r"内容 (\d+) 条")
def _entries(context, count):
    context["entries"] = [object() for _ in range(int(count))]


@register(r"计算放格")
def _plan(context):
    context["placements"], context["left"] = plan_placements(
        context["free"], context["entries"])


@register(r"放进 (\d+) 格")
def _assert_placed(context, count):
    assert len(context["placements"]) == int(count)


@register(r"剩余 (\d+) 条")
def _assert_left(context, count):
    assert context["left"] == int(count)


# ---------------------------------------------------------------- 预设
@register(r'选择预设 "(.+)"')
def _pick_preset(context, key):
    try:
        context["preset"] = by_key(key)
    except KeyError as exc:
        context["preset_error"] = exc


@register(r"列数是 (\d+)")
def _assert_cols(context, count):
    assert context["preset"].cols == int(count)


@register(r"行数是 (\d+)")
def _assert_rows(context, count):
    assert context["preset"].rows == int(count)


@register(r"份数是 (\d+)")
def _assert_total(context, count):
    assert context["preset"].count == int(count)


@register(r"报 KeyError")
def _assert_key_error(context):
    assert isinstance(context.get("preset_error"), KeyError)


# ---------------------------------------------------------------- 输入展开
@register(r"临时输入目录")
def _make_input_dir(context):
    context["tmpdir"] = _tmpdir("ulpp_bdd_inputs")


@register(r'临时目录里有一个 PDF "(.+)"')
def _make_pdf(context, name):
    (context["tmpdir"] / name).write_bytes(b"%PDF-1.4 stub")


@register(r'打包 "(.+)" 里有 "(.+)"')
def _make_zip(context, zip_name, member):
    with zipfile.ZipFile(context["tmpdir"] / zip_name, "w") as zf:
        zf.writestr(member, b"%PDF-1.4 stub")


@register(r'展开 "?([^\s"]+)"?')
def _expand(context, target):
    from ulpp.cli import expand_inputs

    if target == "[dir]":
        target = str(context["tmpdir"])
    else:
        target = str(context["tmpdir"] / target)
    context["found"] = expand_inputs([target])


@register(r"找到 (\d+) 个 PDF")
def _assert_found(context, count):
    assert len(context["found"]) == int(count)


# ---------------------------------------------------------------- 校准结论
@register(r'答案是 face "(\w+)" edge "(\w+)"')
def _feed_answers(context, face, edge):
    context["face"] = None if face == "none" else face
    context["edge"] = None if edge == "none" else edge


@register(r'feed 是 "(\w+)"')
def _assert_feed(context, feed):
    got = feed_from_answers(context["face"], context["edge"], "fallback")
    assert got == feed, "期望 %s，实际 %s" % (feed, got)


# ---------------------------------------------------------------- v2 外壳
@register(r"一个 v2 外壳(?: 语言 (\S+))?")
def _make_shell(context, lang=None):
    context["tmpdir"] = _tmpdir("ulpp_bdd_shell")
    context["state_dir_backup"] = ("ULPP_STATE_DIR", os.environ.get("ULPP_STATE_DIR"))
    os.environ["ULPP_STATE_DIR"] = str(context["tmpdir"])
    root = _require_tk()
    context["root"] = root

    from ulpp.ui.shell import Shell

    context["shell"] = Shell(root, flow=Flow(), lang=lang)
    root.update_idletasks()


@register(r"点下一步")
def _shell_next(context):
    context["shell"].next_step()
    context["root"].update_idletasks()


@register(r'外壳当前站是 "(\S+)"')
def _assert_shell_step(context, step_id):
    assert context["shell"].flow.current == step_id


@register(r"进度已落盘")
def _assert_saved(context):
    assert (Path(context["tmpdir"]) / flow_mod.STATE_FILE).is_file()


@register(r'外壳语言是 "(\S+)"')
def _assert_shell_lang(context, code):
    assert context["shell"].lang == code
