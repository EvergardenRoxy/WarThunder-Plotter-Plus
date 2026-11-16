<a id="ai-制作声明"></a>

[![AI Assisted](https://img.shields.io/badge/AI-Claude%20Fable%205.2%20%2B%20Claude%20Opus%205.5-D97757?style=for-the-badge&logo=anthropic&logoColor=white)](#ai-制作声明)

本项目在 ElBartt/WarThunder-Plotter 的基础上整体重建：Fable 5.2 负责设计、数据核对与复核，Opus 5.5 完成了大部分实现。

# WT Plotter Plus

[English](README.md)

在 Windows 上记录《战争雷霆》每一局的战场态势：谁在哪里、往哪走、谁击毁了谁。打完之后可以在浏览器里拖动时间轴回放整局，也可以在对局中实时查看。

数据全部来自游戏客户端自带的本机接口（`localhost:8111`，就是游戏内置的网页地图），不读内存、不改游戏文件，记录只保存在本机。

## 功能

- **[自动采集](docs/zh/capture.md)**：进入战局后自动开始记录，离开后自动结束，不需要手动操作。按小地图识别地图名，分辨陆战、空战和海战。
- **[战局回放](docs/zh/viewer.md)**：在地图上按阵营画出每个单位的行动轨迹，轨迹越旧越淡。可以播放（5×～40×）、拖动时间轴、缩放和平移，按阵营筛选。
- **[实时战局](docs/zh/viewer.md#实时战局)**：对局进行时同步显示，适合放在第二块屏幕上。
- **[兵种与阵亡标记](docs/zh/viewer.md#读图)**：轻坦、中坦、重坦、坦歼、防空车、飞机各用不同形状；自己、小队和友军阵亡的位置画 ×。
- **[空战图切换](docs/zh/viewer.md#地面图与空战图)**：陆战里开飞机时会另外记录空战图，回放时可以在两张底图之间切换。
- **[战斗播报](docs/zh/viewer.md#战斗播报)**：记录游戏里的击毁、击落、起火等播报，回放时跟着时间轴滚动。
- **中英文界面**：在导航栏切换，首次启动跟随 Windows 界面语言。

## 示例

| 陆战回放 | 空战回放 |
| --- | --- |
| ![陆战回放](docs/images/match_ground.png) | ![空战回放](docs/images/match_air.png) |

示例中的战斗播报使用虚构昵称。更多示例：[历史战局列表](docs/images/match_list.png)。

## 安装

- **便携版**：从 [Releases](https://github.com/EvergardenRoxy/WarThunder-Plotter-Plus/releases) 下载 `WarThunderPlotterPlus-portable.exe`，放进一个可写的文件夹，双击运行。
- **源码版**：安装 Python 3.11 和 Windows Python Launcher，在仓库根目录运行 `scripts\setup.bat`。

## 使用

先启动程序，再进游戏打一局。程序会打开浏览器，停在“实时战局”页；进入战局后页面自动开始显示。打完的战局在“历史战局”里。

```text
WarThunderPlotterPlus-portable.exe            采集并打开实时页面（默认，等同 watch）
WarThunderPlotterPlus-portable.exe serve      只看历史战局，不采集
WarThunderPlotterPlus-portable.exe capture    只采集，不开网页
```

源码版把 EXE 换成 `.\.venv\Scripts\python -m wt_plotter`。网页默认在 `http://127.0.0.1:5000`，可用 `--host` 和 `--port` 修改。在网页右上角或系统托盘点“退出”关闭程序。

## 文档

- [采集与地图识别](docs/zh/capture.md)
- [战局查看器](docs/zh/viewer.md)
- [数据、设置与更新](docs/zh/data.md)
- [架构](docs/zh/architecture.md)
- [数据库](docs/zh/database.md)
- [开发指南](docs/zh/development.md)
- [翻译](docs/zh/translation.md)
- [变更日志](CHANGELOG.zh-CN.md)

## 来源与致谢

本项目重建自 [ElBartt/WarThunder-Plotter](https://github.com/ElBartt/WarThunder-Plotter)，沿用它的数据库结构和地图哈希表，特别感谢。也感谢 Sgambe33 的 [WT-Plotter](https://github.com/Sgambe33/WT-Plotter)（轨迹绘制和地图哈希）以及 ValerieOSD 的 [WarThunderRPC](https://github.com/ValerieOSD/WarThunderRPC)。

本项目与 Gaijin Entertainment 没有关联。

## 开源许可

本项目采用 [MIT 许可证](LICENSE)。
