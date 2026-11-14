# WT Plotter Plus 重建设计

日期：2026-11-15　状态：待确认（标 ★ 的是设计者的默认决定，可改）

## 1. 目的

上游 `ElBartt/WarThunder-Plotter`（v0.2.0）已停止维护。本仓库以它为**参考**重建，目标：

1. 程序界面与文档支持中文、英文。
2. 代码与文档结构清晰，符合 `AGENTS.MD`，便于后续开发。

上游代码放在 `reference/upstream/`（只读，不进入 git）。

## 2. 目标 / 非目标 / 反目标

**目标**
- 功能与上游等价：采集、比赛列表、回放、实时视图、托盘、单实例、自动更新、单文件 EXE。
- 所有界面文字来自语言文件，中英可切换。
- 采集逻辑可脱离游戏测试。
- 旧版 `data/matches.db` 可直接读取（表结构不变）。

**非目标**
- 不加新功能（热力图、多局对比等）。
- 不换语言、不引入前端构建链。
- 不支持中英以外的语言（但加语言只需加一个 JSON 文件）。
- 本期不翻译地图名（中文界面下地图名显示英文）。
- 不推送到远端，不发布 Release。

**反目标（出现即失败）**
- 用显示文字做逻辑判断。
- `except Exception` / 裸 `except` / `except: pass`。
- 任何请求指向 `ElBartt` 仓库。
- 为通过测试而跳过、删除或放宽测试。

## 3. 约束

- Python 3.11，Windows。虚拟环境 `.venv`（`py -3.11 -m venv .venv`）。
- 运行依赖仅：`flask>=3.0`、`requests>=2.31`、`click>=8.1`、`Pillow>=10.0`、`pystray>=0.19.5`。不用 `numpy`、`aiohttp`。
- 开发依赖：`pytest`、`pyinstaller`。
- 遵守 `AGENTS.MD`：简单注释；通用工具不塞进业务模块；不过度防御；不过度设计。
- ★ 注释用中文，标识符、日志、命令行帮助、提交信息用英文。
- 上游为 MIT 许可：`LICENSE` 保留 `ElBartt` 的版权行，另加本项目版权行；README 致谢上游及其致谢对象。

## 4. 方案取舍

| 方案 | 结论 |
|---|---|
| 一、Python 重建，形态不变 | **采用**。解决全部已知问题，不引入新工具链 |
| 二、前后端分离（Vue/React） | 不采用。仅 3 个页面，Node 构建链换不回收益 |
| 三、换语言做原生程序 | 不采用。dHash 需在另一图像库重新对齐，无对应收益 |
| 原地渐进重构 | 不采用。无测试兜底，且用户要求按新规则重建 |

## 5. 必须原样移植的资产

这些是上游实测得来的知识，逻辑不得改动，只改组织方式：

| 资产 | 上游位置 | 说明 |
|---|---|---|
| 地图哈希表 | `map_hashes.py` 各 `*_MAPS` 字典 | 用脚本转换，不手抄 |
| dHash 算法 | `capture.py::_compute_dhash` | 灰度 → `resize((16,15), LANCZOS)` → 横向比较 → 每 4 位一个十六进制字符 |
| 哈希模糊匹配 | `map_hashes.py::lookup_map_info`、`_hamming_distance` | 容差 42 |
| 空中坐标换算 | `capture.py::_compute_air_transform` | 阈值：最少 3 点、缩放上限 0.5、误差上限 0.01 |
| 比赛状态机 | `capture.py::_tick` 及其调用链 | 20 秒宽限期、核弹切图、No Map 结束 |
| 数据库表结构 | `db.py::_create_tables` | 逐字相同 |
| 颜色分类规则 | `viewer.js::_categorize` | RGB 阈值不变 |
| 采集过滤配置 | `config.py` 全部数值 | 数值不变 |

## 6. 目录结构

```
pyproject.toml  requirements.txt  requirements-dev.txt  LICENSE
README.md  README.zh-CN.md  CHANGELOG.md  CHANGELOG.zh-CN.md
wt_plotter/
  __init__.py          __version__ = "0.3.0"
  __main__.py          python -m wt_plotter 入口
  cli.py               命令行、单实例、服务器启停
  config.py            全部常量（冻结 dataclass）
  i18n/__init__.py     语言加载、翻译、语言设置
  i18n/locales/en.json zh.json
  maps/table.py        哈希 → MapInfo（脚本生成）
  maps/lookup.py       精确与模糊查找
  maps/dhash.py        dHash
  capture/client.py    读游戏本地接口
  capture/air_transform.py  空中坐标换算
  capture/tracker.py   比赛状态机（不碰网络）
  capture/capturer.py  后台线程，串起 client + tracker
  storage/db.py        SQLite
  web/app.py           Flask 路由
  web/templates/       base.html index.html match.html waiting.html
  web/static/          styles.css i18n.js app.js viewer.js
  desktop/tray.py      托盘
  desktop/updater.py   自动更新
data/maps/*.png        随仓库分发的地图图片（从上游复制）
scripts/               setup.bat run.bat build_windows.bat port_map_table.py run_unattended.ps1
tests/
docs/en/  docs/zh/     成对文档
docs/superpowers/      设计与计划
reference/upstream/    上游代码（git 忽略）
```

运行期数据目录：打包后为 EXE 所在目录下的 `data/`，源码运行为仓库根目录下的 `data/`。

## 7. 各部分设计

### 7.1 地图（maps）

- `MapInfo(map_id: str, battle_type: BattleType, location: str)`，冻结 dataclass。**没有显示名字段。**
- `location` = 上游显示名去掉开头非字母数字字符后转小写（即上游 `_normalize_map_name` 的结果）。同一地点的地面图与空中图 `location` 相同。
- 显示名放在语言文件，键为 `map.<map_id>`。英文名 = 上游显示名去掉开头的 emoji 前缀。
- 界面按 `battle_type` 在地图名前显示图标，图标沿用上游显示名的前缀。
- 未知地图：`UNKNOWN_MAP = MapInfo("unknown", BattleType.UNKNOWN, "")`。
- 结束判定用 `map_id == "no_map"`。
- 核弹切图判定：前一张图 `battle_type` 为 GROUND 或 NAVAL，当前为 AIR，且两者 `location` 相同且非空。
- 未匹配的哈希追加写入 `data/missing_map_hashes.log`（JSON 行，字段同上游）。

### 7.2 多语言（i18n）

- 语言文件为扁平 JSON：`{"nav.matches": "比赛", ...}`，占位符用 `{name}`。
- `LANGUAGES = ("en", "zh")`。
- `translate(lang, key, **params) -> str`：缺键直接抛 `KeyError`。
- 语言设置是**应用级**的（本地单用户程序），存 `data/settings.json`：`{"language": "zh"}`。
- 文件不存在时（首次运行）按系统界面语言判断：Windows `GetUserDefaultUILanguage()` 主语言为中文 → `zh`，否则 `en`。
- 切换：导航栏下拉框 → `POST /api/language` → 写入设置 → 页面刷新。
- 模板：Jinja 全局函数 `t(key, **params)` 与变量 `lang`。
- 前端：服务端把当前语言的整份字典注入 `window.I18N`，`i18n.js` 提供 `t(key, params)`，缺键抛错。
- 托盘菜单文字用可调用对象，每次展开时读取当前语言。
- 翻译范围：页面、JS 生成的文字、确认框、托盘菜单、接口错误、地图名、战斗类型名。
- 不翻译：日志、命令行帮助、数据库内容。
- 接口错误只返回代码：`{"error": "match_not_found"}`，前端用 `error.<code>` 翻译。
- 键名前缀：`nav.` `index.` `match.` `waiting.` `viewer.` `filter.` `confirm.` `tray.` `error.` `map.` `battle_type.`。
- 地图名本期不翻译：`zh.json` 中 `map.<map_id>` 的值与 `en.json` 相同（英文）。键保留在两个文件里，以后翻译只需改 `zh.json` 的值。

### 7.3 存储（storage）

- 表结构、PRAGMA、坐标量化（5 位）、毫秒时间戳、枚举表缓存，全部同上游。
- 每个线程用自己的连接：采集线程一个；Web 每个请求一个（存 `flask.g`，请求结束关闭）。不再跨线程共享连接。
- `Match` dataclass 只含表字段，不含地图查找逻辑。
- 删除比赛后执行 `PRAGMA incremental_vacuum`（替代上游每次 `VACUUM`）。
- 启动时关闭上次遗留的未结束比赛（保留：断电、强杀属于真实情况）。

### 7.4 采集（capture）

**client.py**
- `requests.Session`，基址 `http://127.0.0.1:8111`。
- 游戏未运行是常态：只捕获 `requests.ConnectionError` 与 `requests.Timeout`，返回 `None`。其它异常不捕获。
- 每个 tick 先取 `map_info.json`；`valid` 为真才取 `indicators` 与 `map_obj.json`。

**tracker.py**（状态机，不碰网络）
- 构造时注入：数据库连接、`fetch_map_image: Callable[[], bytes | None]`、地图图片目录。
- `tick(now, map_valid, indicators, objects)` 完成上游一个 `_tick` 的全部行为。
- 比赛状态用一个 dataclass，开始和结束时整体换新实例（上游是逐字段重置两遍）。
- 取不到地图图片：比赛照常开始，`map_hash` 为空串，记为未知地图。
- dHash 失败不再回退 MD5，异常直接抛出。

**air_transform.py**
- `fit_air_transform(prev_objects, curr_objects) -> tuple[float, float, float, float] | None`
- `to_ground(x, y, transform) -> tuple[float, float]`
- 用纯 Python 一元线性回归（斜率 = 协方差 / 方差）替代 `numpy.linalg.lstsq`。
- 任一轴方差为 0 时返回 `None`。

**capturer.py**
- 后台线程，每 0.2 秒一个 tick。循环内**不捕获异常**；线程因异常退出时，traceback 写入日志。
- `stop()`：停循环、等线程结束、结束当前比赛（写 `ended_at`）。
- 属性：`is_running`（线程存活）、`army_type`、`vehicle_type`。
- 上游的 `save_raw_data` 调试功能不移植。

### 7.5 网页（web）

- `create_app(db_path, capturer | None) -> Flask`。
- 路由路径与返回结构同上游（`viewer.js` 依赖 `/api/match/<id>/positions` 的结构），变化只有：
  - 错误改为代码：`match_not_found`、`cannot_delete_active`、`unknown_language`。
  - 含 `map_name` 的返回值按当前语言翻译，并同时带 `map_id`、`battle_type`。
  - 新增 `POST /api/language`，请求体 `{"language": "zh"}`，成功 204，未知语言 400。
  - `/api/status` 的 `capturing` = `capturer.is_running`；无 capturer（serve 模式）为 `false`。
- `base.html` 承载导航、语言下拉框、`window.I18N`、公共脚本；其余模板继承它。
- `app.js`：退出、删除比赛、语言切换（上游在 3 个模板里各抄一遍）。
- `viewer.js`：从上游移植。文字全部走 `t()`；不使用 `innerHTML`（上游把载具名拼进 HTML）；时间轴刷新改为构造参数里的回调（上游在模板里改写 `_render`）。
- `/api/status` 显示采集未运行时，实时页显示“采集已停止”提示。

### 7.6 桌面（cli / tray / updater）

- 命令：`watch`（默认）、`serve`、`capture`，选项 `--host` `--port`，同上游。
- 服务器用 `werkzeug.serving.make_server(..., threaded=True)`。`POST /shutdown` 在新线程里调用 `server.shutdown()`。`serve_forever()` 返回后依次：`capturer.stop()`、停托盘。不使用 `os._exit`。
- 单实例：启动时请求 `http://<host>:<port>/api/status`，能通则只打开浏览器并退出（同上游）。检查用实际传入的 host/port。
- 托盘：打开、退出两项。启动失败不吞异常。
- 更新器：仓库常量 `UPDATE_REPO = "EvergardenRoxy/WarThunder-Plotter-Plus"`。仅打包运行时检查；环境变量 `WT_PLOTTER_SKIP_UPDATE` 可跳过；断网（`requests.RequestException`）视为无更新。换文件脚本逻辑同上游。
- 日志同时输出到控制台与 `data/wt_plotter.log`。
- 产品名 `WT Plotter Plus`，EXE 名 `WarThunderPlotterPlus-portable.exe`。

### 7.7 文档

- `README.md`（英文）与 `README.zh-CN.md`，顶部互相链接。
- `docs/en/` 与 `docs/zh/` 文件名一一对应：`architecture.md`、`development.md`、`database.md`（移植上游 `DB_optimization.md`）、`translation.md`（如何加语言、加文字）。
- `CHANGELOG.md` 与 `CHANGELOG.zh-CN.md`：0.3.0 条目说明与上游的差异。
- 上游 README 中的法语段落、过时的项目结构不保留。
- `.bat` 脚本输出用英文（避免控制台编码问题）。

## 8. 测试策略

- `pytest`。数据库测试用 `tmp_path` 里的真实 SQLite，不用假对象。
- 状态机：用手写的 tick 序列覆盖 §5 列出的每条行为。
- **真实录像回放**：若 `reference/upstream/data/raw/match_*.json` 存在（用户用上游程序录制），逐个回放到新状态机，并与 `reference/upstream/data/matches.db` 中同一 `match_id` 的 tick 数、position 数比较，必须相等。没有录像时该测试参数为空，不算失败。
- dHash：`data/maps/` 下每张图算出的哈希应查到与文件名相同的 `map_id`。
- 语言文件：`en.json` 与 `zh.json` 键集相同；地图表里每个 `map_id` 都有 `map.<map_id>`；模板与 JS 中出现的每个 `t('...')` 键都存在。
- 文档：`docs/en` 与 `docs/zh` 文件名集合相同。
- 网页：Flask 测试客户端覆盖每条路由，两种语言各渲染一次。

## 9. 留给实施者决定的

- 语言文件里界面文字的具体键名与措辞（遵守 §7.2 的前缀）。
- 模板与样式的细节（外观与上游保持一致即可）。
- 函数内部实现、私有辅助函数的拆分。
