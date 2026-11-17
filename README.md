# 通用标签打印平台 · ulpp

[English](README.en.md)

![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-2E7D6B)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-4B5563)
![Offline](https://img.shields.io/badge/offline-yes-0E8A90)

把 PDF 页面里的**小块**或一段**文字**，按份数排进 A4 预切不干胶的格子，输出可直接打印的 PDF。
不联网、不依赖 AI、不装驱动；Windows 下双击即用。

> 最初是为了摆脱手工排版的“案牍之劳形”——现在它还能自己量纸、自己记住没打完的半张。

<p align="center">
  <img src="https://raw.githubusercontent.com/Imensama/ulpp/main/docs/v2-home.png" width="620" alt="选纸与生成"><br>
  <sub>选一张纸 → 放内容 → 生成（界面为 v2 预览）</sub>
</p>

---

## 目录

- [三分钟上手](#三分钟上手)
- [它能做什么](#它能做什么)
- [界面](#界面)
- [支持的标签纸](#支持的标签纸)
- [接着打（半张纸）](#接着打半张纸)
- [位置校准向导](#位置校准向导)
- [输出文件](#输出文件)
- [v2 预览（新外壳）](#v2-预览新外壳)
- [常见问题](#常见问题)
- [开发与打包](#开发与打包)
- [平台支持](#平台支持)
- [许可](#许可)

---

## 三分钟上手

| 方式 | 适合谁 | 怎么做 |
|---|---|---|
| **① 下载 exe** | 不想装环境 | [Releases](../../releases) 下载 `ulpp.exe`，双击运行 |
| **② 源码运行** | 想改代码 / mac / Linux | `pip install -r requirements.txt` → `pip install -e .` → `python -m ulpp` |
| **③ 命令行** | 批量 / 定时 | `python -m ulpp 表单.zip -o 输出目录` |

> 未签名的 exe 可能被 Defender / SmartScreen 拦一下：点「更多信息 → 仍要运行」。
> 介意就用源码方式，功能完全一样。

```bash
git clone https://github.com/Imensama/ulpp.git
cd ulpp
pip install -r requirements.txt
pip install -e .
python -m ulpp            # 图形界面
python -m ulpp -h         # 全部命令行参数
```

---

## 它能做什么

| 能力 | 说明 |
| --- | --- |
| **按份数复制** | 读到「数量 2」就出 2 张，「数量 10」出 10 张；同一张连排，方便分发 |
| **矢量裁剪** | 整格内容按矢量缩放进格子，放大不糊；文字标签用 600 dpi 位图，PDF 只有几十 KB |
| **文字自动排版** | 自动折行、自动选字号；居中/左/右对齐；可整批「统一字号」 |
| **份数写法** | 行尾 `\|2` 或 ` ×2` 表示印 2 份（`120×80×6` 这种尺寸不会被误判） |
| **混排** | PDF 卡片在前、文字标签在后，一起填满一版 |
| **一次出三件** | 打印版、网格参考版、标签清单 CSV |
| **中英双语** | 界面即时切换，或 `--lang zh\|en`；文件名也跟着变 |
| **多种输入** | PDF / 文件夹 / ZIP（中文文件名自动纠正编码），装了 `tkinterdnd2` 还能拖拽 |

<p align="center">
  <img src="https://raw.githubusercontent.com/Imensama/ulpp/main/docs/example.png" width="620" alt="表格型 PDF 的效果"><br>
  <sub>表格型 PDF：整格内容按矢量抠出来，等比缩进标签格</sub>
</p>

---

## 界面

主界面四块：**① 添加 PDF**（可跳过）→ **② 文字标签**（可跳过）→ **③ 生成选项** → **④ 纸张规格**，点「开始生成」。

1. 装了 `tkinterdnd2` 可以直接把文件/文件夹拖进列表
2. 文字标签一行一张，行尾 `|2` 表示两份
3. 「网格参考版」建议勾上：先用普通纸打一张，和胶纸透光叠对，确认格子位置
4. 右下角可切换 **中文 / English**；「接着打…」打开半张纸窗口

> 纸张对齐别靠猜：先打「网格参考版」，量出偏移，再改「行节距 / 上边距 / 安全边」三个数。

---

## 支持的标签纸

内置 14 种常见规格，也可自定义列数、格宽、节距、边距。

| 预设 | 列×行 | 单格 | 预设 | 列×行 | 单格 |
| --- | --- | --- | --- | --- | --- |
| 45 格 | 5×9 | 40 × 30 mm（节距 41.5×32） | 40 格 | 4×10 | 48 × 25 mm |
| 24 格 | 3×8 | 70 × 37 mm | 72 格 | 6×12 | 33 × 23 mm |
| 21 格 | 3×7 | 70 × 42.3 mm | 65 格 | 5×13 | 38 × 22 mm |
| 30 格 | 3×10 | 70 × 29.7 mm | 44 格 | 4×11 | 46 × 25 mm |
| 12 格 | 2×6 | 99 × 49.5 mm | 10 格 | 2×5 | 99 × 59.4 mm |
| 8 格 | 2×4 | 99 × 74.25 mm | 6 格 | 2×3 | 99 × 99 mm |
| 4 格 | 2×2 | 105 × 148.5 mm | 2 格 | 1×2 | 210 × 148.5 mm |

> 每家纸的裁切线会差 0.5~1 mm。命令行可用稳定 id：`--preset 45`。

---

## 接着打（半张纸）

上次没用完的胶纸不用攒满一整版：主界面右下角「接着打…」。

1. **新建一张没用完的胶纸**：选预设，或自定义列/行/格宽/节距
2. **标已用格**：右键点格子变灰（点错再右键恢复）
3. **放内容**：选中一条内容，左键点空格 = 打在这儿；也可「自动填满空格」
4. **生成**：只包含选中格子，其余留白；打印选 **100% 实际大小**
5. **打完后标记已用**；点错可「撤销上一单」

记录存在 `%APPDATA%\ulpp\sheets.json`（macOS/Linux 为 `~/.config/ulpp/sheets.json`），旧版 `inventory.json` 会自动迁移。

**限制**：只能打还贴着标签的格子；消费级打印机重复放纸有 ±1~2 mm 误差；激光优先（喷墨在旧胶纸上易蹭墨）。

---

## 位置校准向导

「正着放还是反着放、哪条边先伸进去」每台机器都不一样，说明书还常写反。
向导把它变成两个不用懂打印机就能答的问题。

入口：**接着打** → 位置校准与放纸 → **不知道怎么放？用校准向导…**

![位置校准向导](https://raw.githubusercontent.com/Imensama/ulpp/main/docs/wizard.png)
![向导结论](https://raw.githubusercontent.com/Imensama/ulpp/main/docs/wizard-done.png)

九步：选机器 → 写个大 A → 确认 A 面朝上 → 放上手送盘（带动画）→
打一张方向测试页 → 问「字在哪一面」→ 问「TOP 箭头在哪条边」→ 结论 → 微调。
测试页是 **A4 300 dpi 普通纸**，打印时必须 **100% 实际大小**。

---

## 输出文件

| 文件 | 用途 |
| --- | --- |
| `*_打印版.pdf` | 直接上胶纸打印（无网格线） |
| `*_网格参考版.pdf` | 普通纸试打，透光叠对，检查对位 |
| `*_标签清单.csv` | 每张标签的版号/格号/来源/名称/数量 |
| `*_接着打.pdf` | 只打半张纸上的空格 |
| `*_接着打清单.csv` | 接着打的格子清单 |

> 英文界面下文件名是 `*_print.pdf`、`*_grid-reference.pdf`、`*_label-list.csv`、`*_continue.pdf`、`*_continue-list.csv`。

---

## v2 预览（新外壳）

```powershell
python -m ulpp --v2
```

老界面不受影响（`python -m ulpp`）。v2 的新东西：

- **初次校准**：两屏二选一（有扫描仪 / 没有 → 有 A4 可打印 / 没有），一路下一步
- **拍照量纸**：打印标定板 + 手机拍一张，或手动点胶纸四角（支持滚轮缩放、拖动微调）
- **设计记录**：[`docs/design/`](https://raw.githubusercontent.com/Imensama/ulpp/main/docs/design/) —— 单张照片为什么只能到 0.3~0.5 mm、试错过程、方法记录

<p align="center">
  <img src="https://raw.githubusercontent.com/Imensama/ulpp/main/docs/v2-calibrate.png" width="420" alt="初次校准：二选一">
  <img src="https://raw.githubusercontent.com/Imensama/ulpp/main/docs/v2-corners.png" width="300" alt="手动点四角">
</p>
<p align="center"><sub>初次校准（左）与手动点四角（右）</sub></p>

---

## 常见问题

<details>
<summary><b>识别不到卡片？</b></summary>

这个模式针对“每格一条记录”的表格型 PDF。扫描件（整页图片）或没有这些字段名的 PDF 取不到——
可以改用文字模式，或修改 `parser.py` 顶部的字段名。
</details>

<details>
<summary><b>文字标签字号忽大忽小？</b></summary>

默认每张尽量填满；勾「统一字号」后整批用同一档（自动取放得下的最小值）。
</details>

<details>
<summary><b>某个格子的标签空白 / 只有一小条？</b></summary>

多半是那一格的表格线被判成了内容。把 PDF 发个 issue，或先用 `--inset 1` 试试。
</details>

<details>
<summary><b>格子位置对不上？</b></summary>

先打网格参考版，量出偏移，改「上边距」和「行节距」，或换更接近的预设。
接着打时，先在普通纸上打校准页，把左右/上下微调填好再打胶纸。
</details>

<details>
<summary><b>能加条码 / 二维码吗？</b></summary>

目前不生成；源 PDF 里已有的会原样抠过来。需要生成可基于 `textlabel.py` 扩展。
</details>

---

## 开发与打包

```bash
pip install -r requirements.txt
pip install -e .
python -m unittest discover -s tests -t .      # 751 个用例
python3 scripts/quality_gate.py                # 全质量门（测试+覆盖率+指标+变异）
```

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# 产物：dist\ulpp.exe（单文件）；v2 带 OpenCV 的用 packaging\ulpp_v2.spec
```

打 tag（如 `v1.3.3`）后 GitHub Actions 自动构建并上传 Release；`publish.yml` 负责发 PyPI。

目录结构与技术要点见 [`docs/design/`](https://raw.githubusercontent.com/Imensama/ulpp/main/docs/design/) 与源码注释。

---

## 平台支持

| 平台 | 状态 | 额外依赖 |
| --- | --- | --- |
| Windows 10/11 | 主要支持，有 exe | 无 |
| macOS | 源码可跑 | Python 3.9+（官网安装包自带 tkinter） |
| Linux | 源码可跑 | `python3-tk`；中文字体 `fonts-wqy-microhei` |

exe 仅 Windows；mac/Linux 用 `python -m ulpp`。

---

## 许可

[MIT](LICENSE)。第三方组件均为宽松协议（MIT / BSD / PSF / MIT-CMU），可随 exe 分发。
详见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
