# 开发

[English](../en/development.md)

在已装 Python 3.11 和 Windows Python Launcher 的 Windows 上，从仓库根目录执行：

```powershell
.\scripts\setup.bat
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m wt_plotter --help
.\scripts\build_windows.bat
```

构建产物位于 `dist/WarThunderPlotterPlus-portable.exe`。冒烟测试时可先设置 `$env:WT_PLOTTER_SKIP_UPDATE = '1'`，再用 `serve --port 5057` 启动 EXE。检查 `GET /api/status`，发送 `POST /shutdown` 并确认进程退出。

`reference/upstream/` 用作只读参考。已有上游源码时，执行 `.venv\Scripts\python scripts/port_map_table.py` 可重新生成地图表和英文名测试数据。若地图 ID 或名称变化，同时更新两份语言文件。

单元测试使用手写遥测与临时 SQLite 数据库。真实回放测试读取 `reference/upstream/data/raw/match_*.json` 与配套的 `reference/upstream/data/matches.db`，比较 tick 数、位置数和坐标换算参数。命令行集成测试需要访问本机环回 HTTP。
