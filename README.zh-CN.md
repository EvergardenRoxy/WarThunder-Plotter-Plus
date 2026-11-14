# WT Plotter Plus

[English](README.md)

WT Plotter Plus 在 Windows 上从本机《战争雷霆》客户端记录比赛轨迹。网页可以查看实时比赛、浏览历史记录，并使用时间轴、筛选、缩放和平移回放位置。

## 安装

- **便携版**：将 `WarThunderPlotterPlus-portable.exe` 放入可写目录，直接运行。也可以完成源码安装后用 `scripts\build_windows.bat` 自行构建。
- **源码版**：安装 Python 3.11 和 Windows Python Launcher，在仓库根目录运行 `scripts\setup.bat`，创建 `.venv` 并安装开发与构建依赖。

## 使用

```powershell
.\.venv\Scripts\python -m wt_plotter watch
.\.venv\Scripts\python -m wt_plotter serve --port 5057
.\.venv\Scripts\python -m wt_plotter capture
```

默认执行 `watch`，采集并打开实时页面。`serve` 仅运行网页服务，打开比赛记录。`capture` 仅运行采集，按 Ctrl+C 结束。便携版可向 EXE 传入相同子命令。两个网页模式默认监听 `127.0.0.1:5000`，可用 `--host` 和 `--port` 调整。

首次启动时使用 Windows 界面语言。可通过导航栏的下拉框切换中文和英文，两种界面的地图名均显示英文。通过网页或托盘中的「退出」关停服务，也可以在终端按 Ctrl+C。

## 数据与更新

源码版使用仓库根目录的 `data/`，便携版使用 EXE 旁的 `data/`。目录包括 `matches.db`、`maps/`、`settings.json`、`wt_plotter.log` 和存在未知哈希时生成的 `missing_map_hashes.log`。结束两个程序后，可以将上游 v0.2.0 数据库及地图图片复制到该目录。替换数据库前请备份 `data/`。

便携版启动时检查本项目的 GitHub Releases，存在更新的便携版时可自动替换 EXE。启动进程时设置环境变量 `WT_PLOTTER_SKIP_UPDATE=1` 可跳过检查。

## 开发

在仓库根目录执行 `.venv\Scripts\python -m pytest -q`。服务启停测试需要 Windows 本机环回网络。另见[架构](docs/zh/architecture.md)、[开发](docs/zh/development.md)、[数据库](docs/zh/database.md)、[翻译](docs/zh/translation.md)和[变更日志](CHANGELOG.zh-CN.md)。

## 致谢与许可

感谢 ElBartt/WarThunder-Plotter 提供原始记录器与地图数据，感谢 Sgambe33 对轨迹绘制和地图哈希的贡献，以及 ValerieOSD 提供的 WarThunderRPC。[上游项目](https://github.com/ElBartt/WarThunder-Plotter) · [WT-Plotter](https://github.com/Sgambe33/WT-Plotter) · [WarThunderRPC](https://github.com/ValerieOSD/WarThunderRPC)

项目采用 [MIT 许可证](LICENSE)。
