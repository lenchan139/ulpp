# QA 流程与质量门

这份文档是"约束清单 + 关卡清单 + 放行标准"。目标只有一个：**让每一行进仓库的代码
都跑完全部关卡**——单元、属性、BDD、约束、覆盖率、质量指标、变异测试——
漏掉任何一关都不允许合入。

测试怎么写、怎么跑见 [testing.md](testing.md)；这里讲**流程与门槛**。

## 1. 关卡总览

| # | 关卡 | 工具 | 底线 | 在哪跑 |
|---|---|---|---|---|
| 1 | 语法/导入 | `compileall` | 0 错误 | 本地 + CI |
| 2 | 单元测试 | stdlib unittest（750 个用例） | 全绿 | 本地 + CI（Linux/macOS/Windows） |
| 3 | BDD 场景 | `tests/bdd/gherkin.py` + `features/*.feature` | 全绿 | 并入关卡 2 |
| 4 | 属性测试 | 固定种子随机生成 | 全绿 | 并入关卡 2 |
| 5 | 约束测试 | `tests/test_constraints.py` | 全绿 | 并入关卡 2 |
| 6 | 语句覆盖率 | `coverage`（`.coveragerc`） | ≥ 98% | 本地 + CI |
| 7 | 质量指标 | `scripts/quality_metrics.py` | 见 §4 棘轮 | 本地 + CI |
| 8 | 变异测试 | `scripts/mutation_test.py` | 幸存者 = 0 | 本地 + CI（抽查） |

一条命令跑完 1/2/6/7/8：

```bash
python3 scripts/quality_gate.py            # 全关卡
python3 scripts/quality_gate.py --skip-mutation   # 快速迭代
python3 scripts/quality_gate.py --html     # 额外生成 htmlcov/
```

## 2. 硬约束（违者直接挂）

`tests/test_constraints.py` 把 AGENTS.md 的硬约束钉成用例：

- **离线**：`src/ulpp` 不得 import `requests / urllib / socket / sqlite3` 等
  联网或数据库模块；源码里不得出现 openai/boto3/firebase 等云端实现暗示；
- **只用 tkinter**：不得 import Qt / PySide / PyQt / customtkinter / webview / wx；
- **名字**：包目录必须叫 `ulpp`，入口必须叫 `ulpp`，不许再出现 `label_sheet`；
- **版本一致**：`pyproject.toml` 的 `version` 必须等于 `ulpp.__version__`
  （发版流程的最后防线）。

新增硬约束时：先在 `test_constraints.py` 加用例（红），再改代码（绿）。

## 3. BDD（Gherkin）

业务规则用场景文件写，人能直接读懂：

- `tests/features/*.feature` —— 向导状态机、文字标签、接着打排格、预设、
  输入展开、校准结论、v2 外壳导航；
- `tests/bdd/gherkin.py` —— 极简解析器/运行器（只用标准库）；
- `tests/bdd/steps.py` —— 步骤定义，一个正则一个动作；
- `tests/test_bdd.py` —— 把每个场景变成独立 unittest 方法，同时钉住解析器行为。

约定：

- 场景描述**用户可见的行为**，不描述实现；一个场景一个可观察结果；
- 步骤定义禁止藏业务逻辑，只许调真实代码 + 断言；
- 新功能先写 `.feature`（红），再实现（绿）。

## 4. 质量指标（棘轮，只紧不松）

`scripts/quality_metrics.py` 用 ast 数静态指标、读 `coverage.json` 拿覆盖率。
底线写在脚本里（改底线必须说明原因）：

| 指标 | 底线 | 2026-11 基线 |
|---|---|---|
| 语句覆盖率 | ≥ 98% | 99%（CI） |
| 最大圈复杂度 | ≤ 30 | 30 |
| 最长函数 | ≤ 238 行 | 238 |
| 最大模块 | ≤ 930 行 | 930 |
| docstring 覆盖率 | ≥ 26% | 27% |
| TODO/FIXME | 0 个 | 0 |

规则：**新增代码不得超过当前最大值**；想把某个指标降下来，先改代码，
棘轮会自动收紧。临时放宽阈值必须在 PR 里写原因和到期时间。

## 5. 变异测试

`scripts/mutation_test.py` 用 ast 生成 mutants（比较符互换、布尔翻转、
整数 ±1、去掉 not、and/or 互换、算术互换），逐个跑测试：

- **幸存者（survivor）= 测试网有洞**，必须补测试把它杀掉；
- 当前抽查目标（全部 100% 杀灭）：`ui/flow.py`（53 mutants）、`partial.py`、
  `i18n.py`（31 mutants）；
- 选模块的原则：**纯逻辑、跑得快、对输出正确性关键**。数据表/常量表
  （如 `presets.py` 的纸样规格）不选——变异它们只会产生无意义失败；
- CI 上每次跑完整抽查；想扩大目标就在 `scripts/quality_gate.py` 的
  `MUTATION_PAIRS` 里加一行，同时保证新目标 0 幸存。

写代码时的心法：**每个 if/比较/常量都要有测试盯着**，否则变异测试会揪出来。

## 6. QA 流程

### 6.1 提 PR 前（开发者自查）

1. `python3 scripts/quality_gate.py` 本地全绿；
2. 新代码有对应用例：纯逻辑 → unittest；业务规则 → 先写 `.feature`；
   关键常量/比较 → 变异测试不产生幸存者；
3. 新增了硬约束？先补 `test_constraints.py`；
4. 指标变差了？改代码，不要改棘轮。

### 6.2 PR 门（CI 自动）

| 检查 | 工作流 |
|---|---|
| Linux + macOS 全量测试 + 覆盖率 ≥95% + PR 覆盖率评论 | `tests.yml` |
| Windows 最小依赖全量测试 + exe 构建 | `build-windows.yml` |
| 质量门（compileall + 覆盖率 + 指标 + 变异） | `tests.yml` 的 quality job |

任何一项红 → 不允许合入。fork PR 的评论可能受限，但门槛判定不受影响。

### 6.3 合入标准

- 全部关卡绿；
- 覆盖率不低于棘轮底线；
- 变异幸存者 0；
- 测试新增/修改与本 change 同一个 PR（不许"先合代码后补测试"）。

### 6.4 发版门

1. 版本号只改 `pyproject.toml` + `src/ulpp/__init__.py` 两处（约束测试兜底）；
2. 打 tag 前：`CHANGELOG.md` 更新 + `quality_gate.py` 全绿 + 打包冒烟
   （`packaging/ulpp_v2.spec` 出 exe 能打开主界面）；
3. `publish.yml` 校验 tag == pyproject 版本，不一致直接失败。

### 6.5 缺陷处理

- **必修**：挂任何关卡、打印错误、数据损坏 → 当天修，补回归用例；
- **应修**：界面小瑕疵 → 下个版本；必须带复现步骤；
- **记录**：所有缺陷修复都要能指向一个失败用例（变异测试的精神：没有用例的修复等于没修）。

## 7. 证据

- 覆盖率：CI artifact `coverage-report-<os>`（txt/xml/html）+ PR 评论；
- 质量门：CI artifact `quality-gate-report`（coverage.json + htmlcov）；
- 变异：gate 日志里的得分表（当前 3/3 模块 100%）；
- BDD：`tests/features/*.feature` 即可读的业务规格。
