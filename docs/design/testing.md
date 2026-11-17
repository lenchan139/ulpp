# 测试与覆盖率

这份文档回答三个问题：**怎么跑**、**现在盖到什么程度**、**哪些没盖到以及为什么**。
测试只用标准库 `unittest`；`coverage` 只在开发机/CI 用，不进运行时依赖。

## 1. 跑全部测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -t .
```

带覆盖率：

```bash
python3 scripts/run_coverage.py          # 表格
python3 scripts/run_coverage.py --html   # 额外生成 htmlcov/
```

或手动：

```bash
PYTHONPATH=src python3 -m coverage run --rcfile=.coveragerc \
  -m unittest discover -s tests -t .
python3 -m coverage report -m
```

有 Tk 的机器上 UI 用例会真的建窗口（`withdraw`，不弹出来）；没有 Tk 的环境
（纯容器）会用 `skipUnless` 跳过整组 UI 用例，而不是报错。Linux CI 用
`xvfb-run` 提供虚拟显示。

## 2. 测试分层

| 层 | 文件示例 | 做法 |
|---|---|---|
| 纯逻辑 | `test_flow.py`、`test_partial_plan.py`、`test_parser*.py` | 不碰 Tk / 文件系统，直接断言 |
| 属性/生成 | `test_properties.py` | 固定种子随机输入，钉不变量 |
| 业务场景（BDD） | `features/*.feature` + `test_bdd.py` | Gherkin 场景跑真实代码 |
| 硬约束 | `test_constraints.py` | 离线 / tkinter-only / 命名 / 版本一致 |
| 文件与配置 | `test_sheets*.py`、`test_templates.py`、`test_cli_edges.py` | 每个用例一个临时状态目录，退出时删 |
| 扫描/拍照 | `test_scan*.py`、`test_scan_device_edges.py` | 合成图 + OpenCV；没装 OpenCV 时 `skipUnless` |
| Tk 界面 | `test_ui_*.py`、`test_gui_ui.py`、`test_partial_gui_ui.py` | 真 `tk.Tk()`，`withdraw`；对话框用 `mock.patch` 拦掉 |
| 公共底座 | `ui_harness.py` | 临时 `ULPP_STATE_DIR` / `XDG_CONFIG_HOME`、root 生命周期、`close_later` |

质量门（覆盖率 + 指标 + 变异）与放行流程见 [qa.md](qa.md)。

UI 用例的约定：

- 不碰真实的 `~/.config/ulpp`：`ULPP_STATE_DIR` 指到 `tempfile.gettempdir()` 下；
- 不用 `TemporaryDirectory`（Windows 沙箱删不掉），统一 `makedirs` + `rmtree(..., True)`；
- 所有 Toplevel 用 `close_later()` 登记，避免模态窗口的 `grab` 串到下一个用例；
- 会真的执行外部程序的地方（`open` / `xdg-open` / `os.startfile`）一律 mock。

## 3. 当前结果

本机（macOS，Python 3.9，Tk 8.5.9，numpy/OpenCV 已装）：

```text
Ran 750 tests in ~50s
TOTAL  5994 statements  13 missed  99%
```

CI（Ubuntu + macOS，Python 3.11）实际报告：

```text
TOTAL  5996 statements   8 missed  99%
```

大部分模块 100%，包括：builder / parser / sheets / templates / config / presets /
calibration / partial / imagex / scan / scan_board / cli / i18n / __main__，以及全部
v2 界面（`ui/shell.py`、`ui/calibrate.py`、`ui/partial.py`、`ui/advanced.py`、
`ui/screens.py`）和老界面 `partial_gui.py`、`wizard.py`。

CI 上剩余 8 行不是“没写用例”，而是三类环境相关分支：

| 位置 | 原因 |
|---|---|
| `gui.py:31`、`ui/shell.py:34` | `tkinterdnd2` 可选依赖导入成功分支；CI 没装，装了才有 |
| `ui/shell.py:102`、`ui/shell.py:424` | `except Exception:` 行在异常跳转时通常不产生 line 事件 |
| `scan_calib.py:99`、`scan_dewarp.py:90` | 部分 `continue` 语句在 CPython 里不产生 line 事件（与版本/结构有关） |
| `scan.py:163`、`scan_photo.py:49` | 防御性分支：输入退化时提前返回/交换点序；正常路径构造不出来 |

本机 Python 3.9 还会少记几个 `continue` 行（见上表），所以本机是 13 行。

## 4. GitHub Actions

`.github/workflows/tests.yml` 在 PR、push 到 `main/master`、手动触发时运行，
矩阵覆盖 **Ubuntu** 和 **macOS**：

1. 两个平台都用 Python 3.11；Linux 额外装 `python3-tk` + `xvfb`（Tk 用例在
   `xvfb-run` 下跑），macOS 直接使用 runner 自带的 Aqua/Tk；
2. `pip install -e ".[photo]" coverage`（PDF/图像/OpenCV 依赖一次装齐）；
3. 跑全部 unittest；
4. 各平台生成 `coverage.txt` / `coverage.xml` / `htmlcov/` 并上传为
   `coverage-report-<os>` artifact；
5. 覆盖率低于 **95%** 直接判失败；
6. 把表格写进各自的 Job Summary；PR 上由 Ubuntu 任务发一条带标记的评论，
   后续推送**更新同一条**而不是刷屏。

仓库里原有的 `build-windows.yml` 继续覆盖 Windows（不含 numpy/OpenCV 的最小依赖），
因此 Linux / macOS / Windows 三条线都会跑同一套 unittest。`tests.yml` 还有一个
quality job：在 Linux 上跑 `scripts/quality_gate.py`（compileall + 覆盖率 +
指标棘轮 + 变异抽查），产物上传为 `quality-gate-report` artifact。

Fork PR 的评论权限可能被 GitHub 限制，所以评论步骤设了 `continue-on-error`；
测试和覆盖率门槛仍然会正常判定。

## 5. 加用例时的检查清单

- 新代码路径优先补**纯逻辑**用例；Tk 只在“信号接线/状态刷新”处补；
- 涉及图像/OpenCV 的用例用 `skipUnless`，不要假设机器装了；
- 不把客户图纸放进仓库；需要 PDF 样本时用 `examples/sample.pdf` 或代码合成；
- 跑完确认没有留下临时目录、窗口或后台线程。
