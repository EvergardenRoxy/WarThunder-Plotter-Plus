[← 返回 README](../../README.zh-CN.md) · [English](../en/data.md)

# 数据、设置与更新

## 数据目录

便携版的数据在 EXE 旁边的 `data/` 文件夹，源码版在仓库根目录的 `data/`。

| 文件 | 内容 |
| --- | --- |
| `matches.db` | 所有战局：位置、播报和战局信息（SQLite）。运行时旁边还有 `-wal`、`-shm` 两个文件 |
| `maps/` | 小地图图片。认得的地图按地图 ID 命名，认不出的按哈希命名 |
| `settings.json` | 界面语言 |
| `wt_plotter.log` | 运行日志 |
| `missing_map_hashes.log` | 认不出的地图哈希，见[采集与地图识别](capture.md#认不出的地图) |
| `capture.lock` | 采集进行中的标记，保证同一目录只有一个采集程序 |

便携版首次运行会把随程序打包的地图图片解到 `data/maps/`，已有的文件不覆盖。

## 备份与迁移

先退出程序，再复制整个 `data/` 文件夹。搬到另一台电脑或另一个文件夹时，把它放回 EXE 旁边即可。

数据库结构沿用上游 WarThunder-Plotter v0.2.0，那个版本的 `matches.db` 和地图图片可以直接复制进来使用。替换数据库之前先备份。

一小时的战局大约占 10～20 MB。在“历史战局”里删除不要的战局会回收空间。

## 界面语言

导航栏的下拉框切换中文和英文，选择保存在 `settings.json`。首次启动跟随 Windows 界面语言。地图名在两种语言下都显示英文。

回放页的轨迹时间、标记大小等设置保存在浏览器里，不在 `data/` 中，见[战局查看器](viewer.md#侧栏设置)。

## 网页地址

默认只在本机监听 `127.0.0.1:5000`。想从局域网里的另一台设备（比如平板）查看：

```text
WarThunderPlotterPlus-portable.exe watch --host 0.0.0.0 --port 5000
```

然后在另一台设备上打开 `http://<这台电脑的局域网地址>:5000`。页面没有登录，能访问这个地址的人都能查看和删除战局，以及退出程序，只在可信的网络里这样用。

程序已经在运行时再次启动，只会打开浏览器，不会启动第二个实例。

## 自动更新

便携版启动时检查本项目的 [GitHub Releases](https://github.com/EvergardenRoxy/WarThunder-Plotter-Plus/releases)，有新版时下载并替换 EXE，`data/` 不动。连不上 GitHub 时跳过，不影响使用。

不想检查更新，启动前设置环境变量 `WT_PLOTTER_SKIP_UPDATE=1`。源码版不检查更新。
