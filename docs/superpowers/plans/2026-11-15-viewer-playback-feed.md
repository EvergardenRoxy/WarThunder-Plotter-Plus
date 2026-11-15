# 查看器改版（轨迹淡化 / 倍速 / 空战图 / 兵种图标 / 战斗播报）Implementation Plan

> **执行方式：** 在当前会话中按 Task 顺序直接实施（Native），每个 Task 测试通过后提交，最后由用户手动复核（不派审查子代理）。**不使用** `scripts/run_unattended.ps1`。步骤用 `- [ ]` 勾选。

**Goal：** 比赛页一屏放下；轨迹按"行动轨迹显示时间"淡化；倍速滑块播放；空战局可切换空战图；当前位置标记按兵种画形状；采集并显示击杀播报。

**Architecture：**
- 前端在现有 `viewer.js` 上修改，新增通用模块 `static/settings.js`（localStorage 读写）。
- 后端新增 `events` 表、`/hudmsg` 客户端方法、播报接口，以及 `map.png?kind=air`。
- 布局改为全视口网格，各控件按新布局归位。

**Tech Stack：** Flask、Jinja、原生 JS（Canvas 2D）、SQLite、pytest、`node:test`。

**Spec：** `docs/superpowers/specs/2026-11-15-viewer-playback-feed-design.md`（下文写作"设计 §x"）。

## Global Constraints

- 遵守 `AGENTS.MD`：简单注释；通用工具独立于业务；不过度防御（不到处判空、加默认值、try-catch）；不过度设计。
- 界面文字都走 i18n，`wt_plotter/i18n/locales/en.json` 与 `zh.json` 同步新增；模板里不写字面文字，JS 里不用 innerHTML（由 `tests/web/test_static_keys.py` 约束）。
- 全量测试：`.venv/Scripts/python -m pytest -q`。基线 161 passed、2 skipped，每个 Task 结束时要全绿。
- 每个 Task 一个提交。提交信息结尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- 数值常量放在 `VIEW_STYLE`（viewer.js 顶部的冻结对象），不散落在代码里。

## Review Focus

1. 播报接口不可用（游戏未开或格式不符，返回 None）时，轨迹采集照常进行，不抛异常 → Task 5 的 `test_damage_unavailable_keeps_tracking`。
2. 旧的空战局（只有 `x`、没有 `x_ground`、有空战图）默认打开空战图并画出轨迹 → Task 3 的 `default_map_follows_first_sortie` 和 JS 用例 `air map uses raw coordinates`。
3. localStorage 里是旧版本或缺字段的设置 → 浅合并补默认值，Task 1 的 `settings merge defaults`。
4. 时间轴在末尾时点播放从 0 开始，在中间时点播放从当前位置开始 → Task 2 的 JS 用例。
5. 删除比赛时连同播报一起删除，不留孤儿记录 → Task 5 的 `test_delete_match_removes_events`。

---

### Task 1：布局重做 + 设置记忆 + 标记大小 + 轨迹显示时间与淡化

**Files：**
- Create：`wt_plotter/web/static/settings.js`、`tests/js/settings.test.cjs`
- Modify：`wt_plotter/web/templates/base.html`、`match.html`、`index.html`、`static/styles.css`、`static/app.js`、`static/viewer.js`、两份 locale、`tests/js/viewer.test.cjs`

**Interfaces：**
- Produces：
  - `window.Settings.load(key: string, defaults: object) -> object`（浅合并）
  - `window.Settings.save(key: string, value: object) -> void`
  - `VIEW_STYLE.trailOptions = [10, 30, 60, 120, 0]`、`VIEW_STYLE.defaults = { trail: 30, blipSize: 0.5, lineScale: 1, speed: 10 }`、`VIEW_STYLE.fadeBands = 8`
  - 线条粗细（用户追加）：`MatchViewer.prototype.setLineScale(scale)`，限制在 0.5～2，滑块 `#line-scale` 的 step 为 0.1，默认 1。轨迹线宽、描边宽度、阵亡 × 的线宽都乘以 lineScale，并保存到设置里。测试 `line scale clamps`：`setLineScale(5)` 后为 2，`setLineScale(0.1)` 后为 0.5。
  - `MatchViewer.prototype._fadeBands(points, start, end, earliest) -> Array<{ from: number, to: number, alpha: number }>`
  - 后续 Task 使用的页面元素 id：`map-kind`（Task 3 加入）、`unit-legend`（Task 4）、`event-feed`（Task 6）、`speed-slider` / `speed-value`（Task 2）
- `base.html` 新增 `{% block header_center %}{% endblock %}`，放在 h1 与 nav 之间。

- [ ] **Step 1：写失败测试**
  - `settings.test.cjs`：
    - `settings merge defaults`：在 context 里放一个假的 `localStorage`（`getItem` 返回 `'{"trail":60}'`），`Settings.load('k', { trail: 30, blipSize: 0.5 })` 的结果深等于 `{ trail: 60, blipSize: 0.5 }`。
    - `settings load empty`：`getItem` 返回 null 时，结果等于 defaults。
    - `settings save`：调用 `save` 后，`setItem` 收到的参数为 `('k', '{"a":1}')`。
  - `viewer.test.cjs`：
    - `fade bands`：点的 t 从 0 到 30000 每 1000 一个，trail 为 30，cutoff 为 30000，earliest 为 0。`_fadeBands` 返回 8 段，首段 alpha < 0.1，末段 alpha > 0.9，各段首尾相接（`band[i].to === band[i+1].from`），覆盖 start..end。
    - `no fade when trail is all`：trail 为 0 时，返回 1 段，alpha 为 1。
- [ ] **Step 2：** 运行 `node --test tests/js/settings.test.cjs tests/js/viewer.test.cjs`，预期失败（Settings 未定义或 `_fadeBands` 未定义）。
- [ ] **Step 3：实现**
  - `settings.js`：`load` = `{ ...defaults, ...JSON.parse(localStorage.getItem(key) ?? '{}') }`。
  - `tests/js/load.cjs` 的 context 增加可注入的 `localStorage`：`load(...files)` 保持不变，测试里直接给 `context.localStorage` 赋值；`load.cjs` 默认提供一个内存版本。
  - `_drawTrack` 改为对 `_fadeBands` 的每一段分别描边，alpha 乘以 `lineAlpha[category]`。
  - 构造函数从 `Settings.load('wtp.viewer', {...VIEW_STYLE.defaults, filters})` 读取 `trail`、`blipSize`、`filters`。`setTrail`、`setBlipSize`、`setFilter` 调用后 `save`。`setBlipSize` 的范围限制改为 0.25～1.5。
  - `match.html`：
    - 标记大小滑块改为 `min=0.25 max=1.5 step=0.05`，初值由 app.js 按设置回填。
    - 轨迹下拉的标签键改为 `viewer.trail`，译文改为"行动轨迹显示时间" / "Trail duration"。
    - 页面结构按设计 §5 重排：标题和元信息放入 `header_center`，`<details>` 收起详细字段；删除"返回"按钮；左栏是画布加播放条，右栏是控件加 `<div id="event-feed">` 占位（Task 6 填充）。
  - `styles.css`：
    - 比赛页使用 `body.match-page`（在 match.html 的 block 中给 body 加 class；base.html 增加 `{% block body_class %}`）。
    - `main` 高度为 `calc(100vh - 48px)`，网格 `1fr 320px`，`overflow: hidden`；窗口小于 900px 时改为单列并允许滚动。
    - 顶栏 `align-items: center`，链接、下拉框、按钮高度统一 32px，`line-height` 一致。
  - `app.js`：用设置回填控件的值（trail 选中项、滑块值与显示、筛选勾选状态）。
  - `index.html`：沿用新顶栏，修正列表行的垂直居中。
- [ ] **Step 4：** 全量 pytest 通过，再在浏览器中检查：用 `dist/data/matches.db` 的副本开服务，在 1920×1080 和 1366×768 下打开 match/4，确认页面不出现纵向滚动条，播放条可见，顶栏元素垂直居中。
- [ ] **Step 5：** 提交 `feat: one-screen match layout, trail fade and remembered viewer settings`

### Task 2：倍速滑块

**Files：** Modify `match.html`、`app.js`、`viewer.js`、locale、`tests/js/viewer.test.cjs`

**Interfaces：**
- Consumes：Task 1 的 `Settings`、`VIEW_STYLE.defaults.speed`
- Produces：`MatchViewer.prototype.setSpeed(speed: number) -> void`（范围限制在 5～40 并保存）、`this.speed`；删除 `VIEW_STYLE.playbackSpeed`

- [ ] **Step 1：写失败测试**
  - `playback uses speed`：maxTimestamp 为 100000，speed 为 20，`_advancePlayback(1000)` 之后 timelinePosition 等于 0.2。
  - `play restarts only at end`：timelinePosition 为 0.5 时调用 `play()`，位置仍为 0.5；为 1 时调用 `play()`，位置变为 0。测试中把 `requestAnimationFrame` 替换为空函数。
  - `speed clamps`：`setSpeed(100)` 后 speed 为 40，`setSpeed(1)` 后为 5。
- [ ] **Step 2：** 运行 `node --test tests/js/viewer.test.cjs`，预期失败。
- [ ] **Step 3：实现**
  - `match.html` 播放条：`<input type="range" id="speed-slider" min="5" max="40" step="1">`，旁边 `<span id="speed-value">`，显示为 `t('viewer.speed_value', {n})`，即"10×"；标签键为 `viewer.speed`。
  - `app.js` 绑定 input 事件，调用 `setSpeed` 并更新显示。
  - `_advancePlayback` 用 `this.speed`。
- [ ] **Step 4：** 全量 pytest 通过。
- [ ] **Step 5：** 提交 `feat: playback speed slider 5x-40x`

### Task 3：空战图切换

**Files：** Modify `wt_plotter/storage/db.py`、`wt_plotter/web/app.py`、`match.html`、`app.js`、`viewer.js`、locale；测试 `tests/storage/test_db.py`、`tests/web/test_routes.py`、`tests/js/viewer.test.cjs`

**Interfaces：**
- Produces：
  - `CaptureDefaults.placeholder_vehicles: Tuple[str, ...] = ("", "dummy_plane")`
  - `db.first_sortie_army(conn, match_id: int, placeholders: tuple[str, ...]) -> str | None`：返回按 `timestamp_ms, id` 排序后，第一个载具名不在 placeholders 中的 tick 的 army_type
  - `GET /api/match/<id>/map.png?kind=air|ground`（默认 ground）
  - 画布属性 `data-has-air-map="true|false"`、`data-default-map="air|ground"`
  - `MatchViewer` 构造参数 `mapKind`，以及 `setMapKind(kind: 'ground'|'air') -> void`

- [ ] **Step 1：写失败测试**
  - `test_db.py::test_first_sortie_army`：tick 依次为 `air/dummy_plane`、`tank/""`、`air/f-4s`、`tank/germ_hummel`，结果为 `"air"`；只有占位 tick 时结果为 None。
  - `test_routes.py`：
    - `test_map_png_air_kind`：设置 air_map_hash 并放入对应图片，`?kind=air` 返回 200 且内容是空战图。
    - `test_map_png_air_kind_missing`：没有空战图时 `?kind=air` 返回 404。
    - `test_default_map_follows_first_sortie`：有空战图且第一次出击是 `air/f-4s` 时，页面 HTML 含 `data-default-map="air"`；第一次出击是 `tank/germ_hummel` 时含 `"ground"`；没有空战图时一律为 `"ground"`。比赛页和实时页都要断言。
  - `viewer.test.cjs`：
    - `air map uses raw coordinates`：mapKind 为 air，一个 `is_player_air_view=1`、没有 x_ground 的点和一个地面视角点，`_buildTracks` 后只有 1 条轨迹，坐标等于原始 x、y。
    - `ground map prefers ground coordinates`：mapKind 为 ground，有 x_ground 的点用 x_ground；空中视角且没有 x_ground 的点被丢弃。
- [ ] **Step 2：** 运行 pytest 中的对应用例和 node 测试，预期失败。
- [ ] **Step 3：实现**
  - 路由按设计 §6.4。`match_view` 计算 `default_map` 后传给模板。
  - 查看器：`_loadPositions` 不再选定显示坐标，原始点（包括 x_ground）全部保留，越界判断移到 `_buildTracks`（`positionCount` 仍然统计全部点）；`_isDrawable` 按 mapKind 判断；`isAirMap` 改为 getter，`battleType === 'air' || mapKind === 'air'`。
  - `_loadMap` 使用 `?kind=${this.mapKind}`。
  - 右栏统计面板增加分段按钮 `#map-kind`（地面图 / 空战图），只在 `has-air-map` 时渲染。
- [ ] **Step 4：** 全量 pytest 通过。在浏览器里打开 match/7：默认是空战图，能看到轨迹；切到地面图时没有轨迹，属正常，因为没有换算参数。
- [ ] **Step 5：** 提交 `fix: show air map and air tracks for air battles`

### Task 4：兵种图标、悬停与图例

**Files：** Create `wt_plotter/web/static/shapes.js`、`tests/js/shapes.test.cjs`；Modify `viewer.js`、`match.html`、locale、`tests/js/viewer.test.cjs`

**Interfaces：**
- Produces：
  - `window.Shapes.path(ctx, shape: string, x, y, size, angle = 0) -> void`：通用几何形状，只建立路径，不描边。shape 取值为 `diamond|circle|square|triangle|circle-cross|pentagon|arrow`。
  - `VIEW_STYLE.unitShapes`：icon → `{ shape, scale }`，取值见设计 §6.5 的表；`Player` 不放在表里，单独处理。
  - `VIEW_STYLE.markerBase = 14`
  - `MatchViewer.prototype._markerAt(screenX, screenY) -> { icon } | null`
  - i18n 键 `unit.LightTank`、`unit.MediumTank`、`unit.HeavyTank`、`unit.TankDestroyer`、`unit.SPAA`、`unit.SAM`、`unit.Wheeled`、`unit.Fighter`、`unit.Assault`、`unit.Bomber`、`unit.Player`

- [ ] **Step 1：写失败测试**
  - `shapes.test.cjs`：用一个记录调用的假 ctx，`path(ctx, 'square', 10, 10, 4)` 依次调用 beginPath、rect 或 moveTo/lineTo，围出的边界框为 8..12。`path(ctx, 'arrow', 0, 0, 10, Math.PI / 2)` 生成的顶点经旋转后，尖端在 +x 方向。
  - `viewer.test.cjs`：
    - `drops hidden unit icons`：icon 为 `Artillery`、`Pillbox`、`Airdefence` 和未知值的非 POI 点，载入后不进入 positions；`MediumTank`、`Player` 保留。
    - `tracks keep icon`：`_buildTracks` 之后轨迹的最后一点带 `icon`。
    - `marker hit test`：一个当前位置标记位于屏幕 (100, 100)，`_markerAt(103, 100)` 返回该标记，`_markerAt(140, 100)` 返回 null。
- [ ] **Step 2：** 运行 node 测试，预期失败。
- [ ] **Step 3：实现**
  - `_drawCurrent` 按 `unitShapes[point.icon]` 画形状：先用阵营色填充，再加 1.5px 黑边。箭头角度取轨迹最后两点的方向（`Math.atan2`）。
  - `_render` 把本帧画出的当前位置标记的屏幕坐标和半径记入 `this.markers`，供 `_markerAt` 使用。
  - 画布的 mousemove 事件：不在拖动时命中标记，就显示 `#unit-tooltip`（定位在鼠标旁，textContent 为 `t('unit.' + icon)`），否则隐藏。
  - 筛选面板底部的 `#unit-legend`：用 Jinja 循环输出内联 SVG 形状和 `t('unit.x')`；SVG 路径写在模板宏里。
- [ ] **Step 4：** 全量 pytest 通过，在浏览器里抽查 match/4 的形状和悬停提示。
- [ ] **Step 5：** 提交 `feat: draw unit class shapes with legend and hover names`

### Task 5：采集战斗播报

**Files：** Modify `wt_plotter/config.py`、`capture/client.py`、`capture/tracker.py`、`capture/capturer.py`、`storage/db.py`；测试 `tests/capture/test_client.py`、`test_tracker.py`、`test_capturer.py`、`tests/storage/test_db.py`

**Interfaces：**
- Produces：
  - `CaptureEndpoints.hudmsg_path = "hudmsg"`，以及 `hudmsg_url(last_damage: int) -> str`，返回 `f"{base_url}/hudmsg?lastEvt=0&lastDmg={last_damage}"`
  - `CaptureTimeouts.async_hudmsg = 1.0`
  - `TelemetryClient.fetch_damage(last_id: int) -> list[dict] | None`，返回 `response.json()["damage"]`
  - `db.EventRecord(timestamp: float, game_id: int, msg: str, raw: str)`（dataclass）
  - `db.add_events(conn, match_id, events: list[EventRecord]) -> None`
  - `db.get_events(conn, match_id, since_ms: int) -> list[dict]`，返回 `[{timestamp, msg}]`，按 timestamp 升序
  - `MatchTracker.damage_cursor -> int`（属性，取自当前比赛状态，没有比赛时为 0）
  - `MatchTracker.record_damage(now: float, entries: list[dict]) -> None`
- 新表 `events`：`id INTEGER PK AUTOINCREMENT, match_id INTEGER NOT NULL REFERENCES matches(id), timestamp_ms INTEGER NOT NULL, game_id INTEGER NOT NULL, msg TEXT NOT NULL, raw TEXT NOT NULL`，索引为 `idx_events_match_ts(match_id, timestamp_ms)`。

- [ ] **Step 1：写失败测试**（样本按社区资料格式：`{"events": [], "damage": [{"id": 5, "msg": "A (Tiger E) destroyed B (M4A3)", "sender": "", "enemy": false, "mode": "", "time": 95}]}`）
  - `test_client.py::test_fetch_damage`：mock session 返回上面的样本，`fetch_damage(4)` 请求的 URL 以 `hudmsg?lastEvt=0&lastDmg=4` 结尾，返回 damage 列表；连接失败时返回 None。
  - `test_tracker.py`：
    - `test_first_damage_batch_is_skipped`：比赛开始后第一次调用 `record_damage(now, [id 3, id 5])` 不入库，`damage_cursor` 变为 5。
    - `test_damage_recorded_after_prime`：第二次调用 `record_damage(started + 2.5, [id 6])` 写入 1 条，timestamp_ms 为 2500，raw 是该条的 JSON，cursor 变为 6。
    - `test_damage_without_match_ignored`：没有比赛时调用不报错，也不写入。
    - `test_new_match_resets_cursor`：结束比赛再开新比赛后，`damage_cursor` 为 0，并重新跳过第一批。
  - `test_capturer.py`：
    - fixture 的 Mock 增加 `"fetch_damage.return_value": None`。
    - `test_damage_unavailable_keeps_tracking`：map 有效、对象有效、`fetch_damage` 返回 None 时，tick 照常写入。
    - `test_damage_fetched_with_cursor`：map 有效时，`fetch_damage` 以 `tracker.damage_cursor` 为参数调用。
  - `test_db.py`：
    - `test_events_roundtrip`：`add_events` 之后 `get_events(since=0)` 按时间升序返回，`since` 能过滤。
    - `test_delete_match_removes_events`：删除比赛后 events 表里该比赛的记录数为 0。
- [ ] **Step 2：** 运行对应 pytest，预期失败。
- [ ] **Step 3：实现**
  - `_MatchState` 增加 `damage_cursor: int = 0`、`damage_primed: bool = False`。
  - `record_damage`：没有比赛时直接返回；把 cursor 设为 `max(e["id"])`；未 primed 时置为 primed 并返回；否则写入 `EventRecord(now - started_at, e["id"], e["msg"], json.dumps(e, ensure_ascii=False))`。
  - `Capturer._capture_tick`：map 有效时调用 `fetch_damage`，结果不为 None 就交给 `record_damage`；放在 `tracker.tick` 之后，保证新比赛的状态已经建立。
  - `delete_match` 先删除 events。
- [ ] **Step 4：** 全量 pytest 通过。
- [ ] **Step 5：** 提交 `feat: record hudmsg damage feed per match`

### Task 6：显示战斗播报

**Files：** Modify `wt_plotter/web/app.py`、`viewer.js`、`app.js`、`match.html`、`styles.css`、locale；测试 `tests/web/test_routes.py`、`tests/js/viewer.test.cjs`

**Interfaces：**
- Consumes：Task 5 的 `db.get_events`
- Produces：
  - `GET /api/match/<id>/events?since=<ms>`
  - `MatchViewer.prototype._loadEvents() -> Promise<void>`（增量载入，游标 `this.lastEventTimestamp`）
  - `MatchViewer.prototype._visibleEvents(cutoff) -> Array<{timestamp, msg}>`（最新的在前）
  - 回调 `onEvents(events)`，由 app.js 渲染到 `#event-feed`

- [ ] **Step 1：写失败测试**
  - `test_routes.py::test_events_since`：写入 timestamp 为 1000 和 3000 的两条播报，`?since=2000` 只返回第二条，字段为 `timestamp`、`msg`。
  - `viewer.test.cjs`：
    - `visible events newest first`：三条播报的时间为 1000、2000、5000，cutoff 为 3000，结果为 [2000, 1000]。
    - `load events advances cursor`：假 fetch 返回 [{timestamp: 1500}]，调用后 `lastEventTimestamp` 为 1501，再次调用时请求的 URL 含 `since=1501`。
- [ ] **Step 2：** 运行测试，预期失败。
- [ ] **Step 3：实现**
  - 查看器载入位置时同时调用 `_loadEvents`，实时页在 `_poll` 中也调用。`_render` 结束后，用 `_visibleEvents(cutoff)` 调用 `onEvents`；列表内容没变时不重绘 DOM（比较长度和首条时间）。
  - app.js 渲染列表：每条是一个 `<li>`，包含 `<time>`（`formatTime`）和文字，用 textContent 写入。空列表时显示 `t('viewer.feed_empty')`。
  - 面板标题键为 `viewer.feed`，即"战斗播报" / "Battle feed"。
- [ ] **Step 4：** 全量 pytest 通过。在浏览器里打开任意旧比赛，确认播报区显示"暂无播报"，页面无报错。
- [ ] **Step 5：** 提交 `feat: show battle feed synced with timeline`

### Task 7：收尾

**Files：** `wt_plotter/__init__.py`、`CHANGELOG.md`、`CHANGELOG.zh-CN.md`、`docs/en|zh/architecture.md`、`docs/en|zh/database.md`、`docs/superpowers/plans/PROGRESS.md`

- [ ] **Step 1：** 版本号改为 `0.4.0`。双语变更日志写明 8 项改动，并注明"播报格式尚未用真实游戏数据核对"。数据库文档补充 events 表，架构文档补充 settings.js、shapes.js 和播报流程。
- [ ] **Step 2：** 全量 pytest 通过（`tests/test_docs.py` 会检查文档）。
- [ ] **Step 3：** 提交 `chore: release 0.4.0`，在 PROGRESS.md 记录各 Task 的提交哈希。
- [ ] **Step 4：** 交给用户手动复核，不派审查子代理。
- [ ] **Step 5（等用户确认后才做）：** 构建便携 EXE（`scripts/build_windows.bat`）。
