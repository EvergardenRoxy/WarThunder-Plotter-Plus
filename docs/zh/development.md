[← 返回 README](../../README.zh-CN.md) · [English](../en/development.md)

# 开发

在已装 Python 3.11 和 Windows Python Launcher 的 Windows 上，从仓库根目录执行：

```powershell
.\scripts\setup.bat
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m wt_plotter --help
.\scripts\build_windows.bat
```

构建产物位于 `dist/WarThunderPlotterPlus-portable.exe`。冒烟测试时可先设置 `$env:WT_PLOTTER_SKIP_UPDATE = '1'`，再用 `serve --port 5057` 启动 EXE。检查 `GET /api/status`，发送 `POST /shutdown` 并确认进程退出。

`reference/upstream/` 用作只读参考。已有上游源码时，执行 `.venv\Scripts\python scripts/port_map_table.py` 可重新生成地图表和英文名测试数据。若地图 ID 或名称变化，同时更新两份语言文件。

## 补充地图

游戏更新地图后小地图哈希会变，战局显示为“未知地图”（见[采集与地图识别](capture.md#认不出的地图)）。补一张图：

1. 从 `data/missing_map_hashes.log` 或 `data/maps/` 里以哈希命名的图片取得哈希。
2. 确认它是哪张地图。对照同一局的录像最可靠：`Replays` 目录下保存时间与战局结束时间相差几秒的 `.wrpl`，文件开头有 `levels/avg_poland.bin` 这样的关卡名。
3. 在 `scripts/port_map_table.py` 的 `LOCAL_MAPS` 加一行（哈希、地图 ID、战斗类型、地点），重新运行脚本生成 `wt_plotter/maps/table.py`。
4. 地图 ID 是新的时，在两份语言文件里加上 `map.<地图 ID>`。

已记录的战局不用改：地图名是查看时按哈希现查的。已保存的图片是按哈希命名的，把它复制一份并改名为 `<地图 ID>.png`，旧战局才能显示底图。

## 测试

单元测试使用手写遥测与临时 SQLite 数据库。真实回放测试读取 `reference/upstream/data/raw/match_*.json` 与配套的 `reference/upstream/data/matches.db`，比较 tick 数、位置数和坐标换算参数。命令行集成测试需要访问本机环回 HTTP。

JavaScript 测试需要 Node.js 18 或更高版本，由 `tests/web/test_js.py` 调用。
