# 设计记录

这里放**为什么这么做**：试过什么、数据是多少、哪些路走不通。
使用说明看根目录 `README.md`，版本变更看 `CHANGELOG.md`。

| 文档 | 一句话 |
|---|---|
| [photo-measurement.md](photo-measurement.md) | 拍照量纸：单张照片的精度上限、三种标定路线的取舍、七个踩过的坑 |
| [method-notes.md](method-notes.md) | 方法记录：怎么拆问题、怎么用数据决策、与小马的讨论摘要、什么时候该停 |
| [wizard-flow.md](wizard-flow.md) | 全流程向导：两站式外壳、状态机、跳过与重入（v2，建设中） |
| [template-model.md](template-model.md) | 胶纸模板的数据模型：为什么模板与打印机解耦（v2，建设中） |
| [testing.md](testing.md) | 测试分层、覆盖率现状、Tk/OpenCV 的坑与 CI 报告 |

> 写新文档的约定：文件名用 ASCII 小写连字符；开头一段写清"这份解决什么问题"；
> 数据写成表格并注明是合成/实测；结论要能独立读懂（不要只写"见某次讨论"）。
