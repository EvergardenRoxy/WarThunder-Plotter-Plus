# 地图可读性与空中视角修复 Implementation Plan

> **For agentic workers:** 按 `docs/superpowers/plans/executor-prompt.md` 的规则逐个 Task 执行。每次会话只做一个 Task。步骤用 `- [ ]` 勾选跟踪。

**Goal:** 修复“坐飞机即判为空中视角”造成的坐标错算；把比赛地图从“整场散点”改成可辨认的轨迹图。

**Architecture:** 采集端只改 `tracker.py` 的空中视角判定。前端新增通用工具 `static/tracks.js`（轨迹串联、聚类、二分查找，与业务无关），`viewer.js` 用它重写绘制。前端逻辑用 Node 自带的 `node:test` 测试，由一个 pytest 用例调起，全量测试命令不变。

**Tech Stack:** 沿用现有栈。新增开发工具：Node.js ≥ 18（仅跑测试，不进运行依赖）。

**Spec:** 本文件“设计”一节即依据，没有单独的设计文档。

## 背景（2026-11-15 测试数据检查结论）

数据来自 `dist/data/matches.db`，共 4 场比赛。

1. `tracker.py` 的 `air_view = is_air or air_defence_seen or ...` 把“玩家坐飞机”直接当成空中视角。按占领点坐标核对，标为空中视角的帧里，实际仍是地面坐标的分别是：第 1 场 77/629、第 2 场 939/971、第 3 场 22/22、第 4 场 23 帧中的 19 帧。这些帧的坐标被放大了 16～32 倍，第 2 场有 8651 个点落在地图外。凡是真正处于空中坐标的帧，都出现了 `Airdefence` 图标。
2. 出生点坐标有抖动。第 4 场按 0.01 精度看只有 32 处，按 0.001 精度看有 136 处，查看器按 0.001 去重，于是叠成一团。
3. 占领点在被占领的过程中颜色是渐变的，颜色枚举表因此有 784 种颜色。查看器直接用最后一帧的颜色，可能刚好是粉白色。
4. 查看器把每条位置记录画成一个点，点的大小随缩放变大。所有友军同一种蓝色，整场历史叠在一起。`#1839A7`、`#043FFF` 这两种蓝色被归入“其他”。

## 设计

### D1 空中视角判定（tracker）

每个有效 tick 按下列顺序决定 `air_view`：

1. 有效对象中出现 `CAPTURE_FILTERS.air_defence_icons` 中的图标 → `True`。
2. 否则，若本帧有占领点，且其签名与上一个有占领点的帧不同（`poi_changed`）→ `not state.previous_air_view`。
3. 否则沿用 `state.previous_air_view`。

`is_air`（`army == "air"`）不再参与判定，只照旧写入 `ticks.is_player_air`，并继续触发 `_maybe_capture_air_map`。本帧没有占领点时，不更新 `state.capture_signature`，也不算 `poi_changed`。坐标换算的拟合时机不变：只在由地面进入空中视角、且尚无换算参数时拟合。

已有数据库不迁移。查看器载入数据时，丢弃显示坐标不在 [0, 1] 内的点（见 D3）。

### D2 通用工具 `wt_plotter/web/static/tracks.js`

挂在 `window.Tracks` 上，完整代码见 Task 2 Step 3：

- `linkTracks(frames, { maxStep, maxGap })`：`frames` 为按 `t` 升序的 `[{ t, points: [{x, y, ...}] }]`。相邻帧之间按距离从小到大贪心配对，配上的点接到已有轨迹上，配不上的点新开一条轨迹。距离超过 `maxStep`，或轨迹中断超过 `maxGap`，都不再接续。返回轨迹数组，每条是带 `t` 的点数组。
- `clusterPoints(points, radius, pick)`：按距离合并相近的点，每组交给 `pick(group)` 选出一个。
- `lastIndexAtMost(items, value, key)`：在有序数组里二分查找最后一个满足 `key(item) <= value` 的下标，找不到返回 -1。

### D3 查看器 `viewer.js`

常量集中写在文件顶部的 `VIEW_STYLE` 冻结对象里，下文的数值都放在这里：

| 名称 | 值 | 用途 |
|---|---|---|
| `teamColors` | player `#faC81E`，squad `#67D756`，ally `#174DFF`，enemy `#fa0C00` | 阵营参考色，也是绘制色 |
| `ownerColors` | ally `#174DFF`，enemy `#fa0C00`，neutral `#ffffff` | 占领点、出生点的归属色 |
| `maxColorDistance` | `160` | 与最近参考色的 RGB 欧氏距离超过它，就归为 other |
| `link` | 地面图 `{ maxStep: 0.03, maxGap: 3000 }`，空战图 `{ maxStep: 0.06, maxGap: 3000 }` | 轨迹串联参数（坐标为 0～1 的比例，时间单位毫秒） |
| `aliveWindow` | `2000` | 轨迹最后一点距当前时间不超过它，就视为单位仍在场 |
| `deathMinPoints` | `20` | 点数不少于它的轨迹，在中途结束时才画 × |
| `poiClusterRadius` | `0.02` | 出生点、占领点的聚类半径 |
| `mapDim` | `0.25` | 底图上覆盖黑色遮罩的不透明度 |
| `lineWidth` | player 3，squad 2.5，enemy 2，ally 1.5，other 1.5（屏幕像素） | 轨迹线宽 |
| `lineAlpha` | ally 0.6，other 0.6，其余 1 | 轨迹不透明度 |
| `haloWidth` / `haloColor` | 线宽 + 2 / `rgba(0,0,0,0.55)` | 线条和标记的深色描边 |
| `trailOptions` | `[0, 60, 30, 10]`（秒，0 表示全部） | 轨迹长度选项 |
| `playbackSpeed` | `10` | 回放倍速 |

行为：

1. **分类** `_categorize(pos)`：`capture_zone` → `capture_zone`；类型含 `respawn` 或 `airfield` → `respawn`；其余对象按与 `teamColors` 中最近参考色的 RGB 距离分类，超过 `maxColorDistance` 归为 `other`。删除旧的阈值判断和 `icon === 'player'` 分支（玩家阵亡后被观察的友军图标是蓝色，归为 ally 是对的）。
2. **归属色** `_ownerColor(hex)`：返回 `ownerColors` 中最近的颜色。占领点和出生点都用它绘制。
3. **载入**：在 `_loadPositions` 合并 tick 字段、选定显示坐标（有 `x_ground` 就用它）之后，丢弃 `x`、`y` 不在 [0, 1] 内的点，然后照旧分入 `positions` / `pois`。每次载入到新数据后调用 `_buildTracks()`。
4. **轨迹** `_buildTracks()`：取满足 `_isDrawable(pos)` 的非 POI 点（即原 `_shouldShow` 中与筛选、时间轴无关的部分：地面图隐藏飞机，以及没有地面坐标的空中视角点）。按分类分组，每组按 `timestamp` 组装成帧，交给 `Tracks.linkTracks`，得到 `this.tracks = [{ category, points }]`。筛选和时间轴只在绘制时生效，不触发重建。
5. **当前时间** `cutoff`：实时页面和时间轴拉到最右时等于 `maxTimestamp`，否则等于 `maxTimestamp * timelinePosition`。轨迹长度 `trail` 不为 0 时，只画 `t` 在 `[cutoff - trail*1000, cutoff]` 内的点，起止下标用 `Tracks.lastIndexAtMost` 求。
6. **绘制顺序**：底图 → `mapDim` 遮罩 → 占领点 → 出生点 → 轨迹（先画 ally 和 other，再画 enemy、squad，最后画 player）→ 当前位置标记 → 阵亡 ×。
7. **线条**：每条轨迹先用 `haloColor` 和 `haloWidth` 画一遍，再用阵营色、`lineWidth`、`lineAlpha` 画一遍，`lineJoin` 与 `lineCap` 都设为 `round`。所有线宽和尺寸都除以 `zoom`，在屏幕上保持恒定。
8. **当前位置标记**：轨迹在 `cutoff` 之前的最后一点，若满足 `cutoff - t <= aliveWindow`，在该点画实心圆，屏幕半径为 `blipSize * 3`，外加 1.5px 黑边。玩家的圆半径再乘 1.4，外加一圈 2px 白环。
9. **阵亡 ×**：轨迹点数 ≥ `deathMinPoints`，且最后一点满足 `t < cutoff - aliveWindow`，同时 `t < maxTimestamp - aliveWindow`，在最后一点画 ×，屏幕边长为 `blipSize * 2.5`，用阵营色加深色描边。
10. **占领点**：取 `t <= cutoff` 的占领点 POI，用 `Tracks.clusterPoints` 按 `poiClusterRadius` 聚类，每组保留 `timestamp` 最大的那个。画圆，屏幕半径 12px：先画深色描边，再用归属色以 0.3 不透明度填充，最后用 2px 归属色描边。
11. **出生点**：全部出生点 POI 按同一半径聚类，每组保留最新的。画边长 8px 的屏幕方块：归属色以 0.5 不透明度填充，加 1.5px 归属色边框和深色描边。
12. **统计**：标记点数量改为占领点聚类数与出生点聚类数之和，位置记录数不变。
13. **高分屏**：`_resize` 把 CSS 尺寸记为逻辑宽高。画布的 `width`、`height` 设为逻辑尺寸乘以 `devicePixelRatio`，`style.width`、`style.height` 设为逻辑尺寸。每次 `_render` 先执行 `ctx.setTransform(dpr, 0, 0, dpr, 0, 0)`，之后的绘制和平移计算都用逻辑尺寸。
14. 删除不再使用的 `_drawPosition`、`_drawPOI`、`_getCurrentPois`、`_parseColor` 中的旧分支，以及 `_hexToRgba` 中的颜色名映射（数据里只有 `#RRGGBB`）。

### D4 侧栏控件

- 新增“轨迹长度”面板，实时页面和回放页面都有：`<select id="trail-length">`，选项来自 `trailOptions`，默认值为 0（全部）。选项文字使用 `viewer.trail_all` 和 `viewer.trail_seconds`。
- 回放页面的时间轴面板新增 `<button id="timeline-play">`，文字在 `viewer.play` 和 `viewer.pause` 之间切换。播放时用 `requestAnimationFrame` 推进，每帧把 `timelinePosition` 增加 `dt * playbackSpeed / maxTimestamp`（`dt` 为毫秒），同时同步滑块。到达 1 时自动停止；用户拖动滑块时也停止。
- 新增语言键（中英文都要加）：`viewer.trail`（轨迹长度 / Trail length）、`viewer.trail_all`（全部 / All）、`viewer.trail_seconds`（最近 {n} 秒 / Last {n}s）、`viewer.play`（播放 / Play）、`viewer.pause`（暂停 / Pause）。

### 不在本期范围

- 不修改表结构，不迁移已有数据库，不清理颜色枚举表，也不改占领点每帧都存一条的做法。
- 不调整实时页面的轮询频率。

## Global Constraints

- 一切 Python 命令用 `.venv\Scripts\python`。全量测试命令为 `.venv\Scripts\python -m pytest -q`，每个 Task 结束时必须全绿。
- 不新增运行依赖。Node 只用于测试，JS 测试只用 `node:test` 和 `node:assert`，不装 npm 包，不建 `package.json`。
- `wt_plotter/` 内禁止 `except Exception`、裸 `except`、`except ...: pass`。
- 遵守 `AGENTS.MD`：注释写中文且简短，不过度防御，通用工具不放进业务模块。
- 不得出现 `innerHTML`，不得把位置数组展开成函数参数（`tests/web/test_static_keys.py` 已有检查）。
- 模板不写死任何文字，界面文字全部走语言文件。
- 标识符、日志、提交信息用英文。不 `git push`，不改动项目目录以外的文件。
- `dist/` 下的数据只读，不得修改 `dist/data/`。

## Review Focus

1. 坐飞机但小地图仍是地面坐标 → 不判为空中视角，不做换算（Task 1）。
2. 空中视角中途看不到防空图标 → 保持空中视角，不来回闪烁（Task 1）。
3. 两个单位交错而过 → 贪心配对不会让一条轨迹瞬移到地图另一侧（Task 2）。
4. 坐标在 [0, 1] 之外的旧数据 → 不画到地图外，也不进入轨迹（Task 3）。
5. 回放播到结尾，或用户拖动滑块 → 播放停止，不越界（Task 4）。

---

### Task 1: 空中视角判定

**Files:**
- Modify: `wt_plotter/capture/tracker.py`
- Modify: `tests/capture/test_tracker.py`

**Interfaces:**
- 不改任何签名。仅改变 `ticks.is_player_air_view` 的取值规则，以及随之变化的 `x_ground`、`y_ground`。

- [x] **Step 1:** 改写 `test_air_view_transform_applied`：输入改为每帧都带占领点，才能触发视角切换。tick 0 为 `{"army": "tank"}`，对象为 4 个 `capture_zone` 加 4 个 `ground_model`，取原测试的 `ground` 坐标。tick 1 为 `{"army": "air"}`，同样 8 个对象，坐标按 `0.25*x+0.1`、`0.25*y+0.2` 换算。断言保持不变：换算参数约为 `(0.25, 0.1, 0.25, 0.2)`；tick 1 的 `is_player_air_view == 1`；tick 1 每个位置的地面坐标约等于原坐标。这是本期规则有意变化导致的输入调整，断言不得放宽。
- [x] **Step 2:** 新增失败测试：
  - `test_plane_on_ground_frame_is_not_air_view`：tick 0 为 tank，对象为 4 个占领点加 1 个 `ground_model`；tick 1 为 air，对象完全相同。断言 tick 1 的 `is_player_air == 1`、`is_player_air_view == 0`，且 tick 1 所有位置的 `x_ground is None`。
  - `test_air_view_persists_without_air_defence`：tick 0 为 tank，用地面坐标的占领点；tick 1 为 air，用换算后的占领点；tick 2 为 air，占领点与 tick 1 相同，不含防空图标。断言 `is_player_air_view` 依次为 `[0, 1, 1]`。
  - `test_air_defence_forces_air_view`：tick 0 为 tank，用地面占领点；tick 1 为 tank，占领点不变，另加一个 `icon="Airdefence"` 的对象。断言 tick 1 的 `is_player_air_view == 1`。
  - `test_tick_without_zones_keeps_view`：tick 0 为 tank，用地面占领点；tick 1 为 air，用换算后的占领点；tick 2 为 air，只有 `ground_model`，没有占领点；tick 3 为 air，占领点与 tick 1 相同。断言 `is_player_air_view` 依次为 `[0, 1, 1, 1]`。
- [x] **Step 3:** 跑 `tests/capture/test_tracker.py`，确认新测试失败。
- [x] **Step 4:** 按设计 D1 修改 `_capture_positions`：`poi_changed` 只在本帧有占领点时计算，`capture_signature` 也只在此时更新；`air_view` 按 D1 的三条规则判定。其余逻辑（初始占领点、换算拟合、`previous_objects`）保持不变。
- [x] **Step 5:** 跑全量测试至全绿，包括原有的 `test_return_to_ground_is_not_air_view`。
- [x] **Step 6:** 提交：`fix: decide air view from map evidence, not vehicle type`。

### Task 2: 轨迹工具与 JS 测试

**Files:**
- Create: `wt_plotter/web/static/tracks.js`
- Create: `tests/js/tracks.test.cjs` `tests/js/load.cjs`
- Create: `tests/web/test_js.py`
- Modify: `docs/en/development.md` `docs/zh/development.md`

**Interfaces:**
- Produces：`window.Tracks = { linkTracks, clusterPoints, lastIndexAtMost }`（语义见设计 D2）
- Produces：`tests/js/load.cjs` 导出 `load(...files)`。它在 `node:vm` 中建立上下文，至少提供 `window`、`console`、`document` 桩，按顺序执行 `wt_plotter/web/static/` 下的指定文件，返回上下文对象。写法参考 `docs/reviews/2026-11-15/reproduce.cjs`。

- [x] **Step 1:** 写 `tests/web/test_js.py`：`test_node_tests_pass` 用 `subprocess.run(["node", "--test", "tests/js/"], cwd=项目根目录)` 运行 JS 测试，断言返回码为 0，失败时把 stdout 和 stderr 作为断言信息输出。找不到 `node` 时直接报错，不要 skip。
- [x] **Step 2:** 写失败测试 `tests/js/tracks.test.cjs`：
  - 两个点同向平行移动 10 帧，间距 0.1、步长 0.005，`maxStep` 为 0.03 → 得到 2 条轨迹，每条 10 个点，且各自的 x 坐标保持不变。
  - 单个点在第 5 帧跳了 0.2 → 得到 2 条轨迹，点数分别为 5 和 5。
  - 单个点相邻两帧间隔 4000ms，`maxGap` 为 3000 → 得到 2 条轨迹。
  - 两点相向交错：A 从 (0.40, 0.5) 向右，B 从 (0.46, 0.5) 向左，步长 0.01，共 6 帧 → 得到 2 条轨迹，且每条相邻点之间的距离都不超过 0.03。
  - 返回的每个点都带上了所在帧的 `t`，并保留原点上的其他字段。
  - `clusterPoints`：点 (0.1, 0.1)、(0.105, 0.1)、(0.5, 0.5)，半径 0.02，`pick` 取每组第一个 → 得到 2 个点。
  - `lastIndexAtMost`：在 `[1, 3, 5]` 中查找 0、3、4、9，结果依次为 -1、1、1、2。
- [x] **Step 3:** 写 `tracks.js`，内容如下：

```js
// 把逐帧的无编号点串成轨迹：相邻帧之间按最近距离贪心配对。
// frames: [{ t, points: [{ x, y, ... }] }]，按 t 升序。
// maxStep：两帧之间允许的最大位移；maxGap：轨迹可中断的最长时间。
function linkTracks(frames, { maxStep, maxGap }) {
    const tracks = [];
    let open = [];
    for (const frame of frames) {
        open = open.filter(track => frame.t - track.lastT <= maxGap);
        const pairs = [];
        frame.points.forEach((point, pi) => {
            open.forEach((track, ti) => {
                const last = track.points[track.points.length - 1];
                const d = Math.hypot(point.x - last.x, point.y - last.y);
                if (d <= maxStep) pairs.push([d, ti, pi]);
            });
        });
        pairs.sort((a, b) => a[0] - b[0]);
        const usedTracks = new Set();
        const usedPoints = new Set();
        for (const [, ti, pi] of pairs) {
            if (usedTracks.has(ti) || usedPoints.has(pi)) continue;
            usedTracks.add(ti);
            usedPoints.add(pi);
            open[ti].points.push({ ...frame.points[pi], t: frame.t });
            open[ti].lastT = frame.t;
        }
        frame.points.forEach((point, pi) => {
            if (usedPoints.has(pi)) return;
            const track = { points: [{ ...point, t: frame.t }], lastT: frame.t };
            tracks.push(track);
            open.push(track);
        });
    }
    return tracks.map(track => track.points);
}

// 按距离合并相近的点，每组保留 pick 选出的那个。
function clusterPoints(points, radius, pick) {
    const groups = [];
    for (const point of points) {
        const group = groups.find(g => Math.hypot(g[0].x - point.x, g[0].y - point.y) <= radius);
        if (group) group.push(point);
        else groups.push([point]);
    }
    return groups.map(pick);
}

// 有序数组里最后一个 key(item) <= value 的下标，没有则为 -1。
function lastIndexAtMost(items, value, key) {
    let lo = 0;
    let hi = items.length - 1;
    let found = -1;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (key(items[mid]) <= value) {
            found = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    return found;
}

window.Tracks = { linkTracks, clusterPoints, lastIndexAtMost };
```

- [x] **Step 4:** 跑全量测试至全绿。若交错用例失败，先确认失败的根因是贪心配对本身，再调整算法，不要改用例。
- [x] **Step 5:** 在中英文开发文档的测试一节各补一句：JS 测试需要 Node.js 18 或更高版本，由 `tests/web/test_js.py` 调用。
- [x] **Step 6:** 提交：`test: add track utilities with node tests`。

### Task 3: 查看器绘制重写

**Files:**
- Modify: `wt_plotter/web/static/viewer.js` `wt_plotter/web/static/styles.css`
- Modify: `wt_plotter/web/templates/match.html`（在 `viewer.js` 之前引入 `tracks.js`）
- Create: `tests/js/viewer.test.cjs`

**Interfaces:**
- Consumes：`window.Tracks`
- 保持不变：`MatchViewer` 构造参数，以及 `app.js` 调用的公开方法（`zoomIn` `zoomOut` `resetView` `setFilter` `setBlipSize` `setTimeline` `getTimelineMax` `formatTime` `destroy`）、属性 `timelinePosition`
- Produces（供测试和 Task 4 使用）：`_categorize(pos)`、`_ownerColor(hex)`、`_buildTracks()`、`this.tracks`、`_cutoff()`

- [ ] **Step 1:** 写失败测试 `tests/js/viewer.test.cjs`。用 `load('tracks.js', 'viewer.js')` 载入，参照 `reproduce.cjs`，以 `Object.create(MatchViewer.prototype)` 构造对象，避免执行构造函数。
  - `_categorize`：`#faC81E` → player，`#67D756` → squad，`#174DFF`、`#1839A7`、`#043FFF` → ally，`#fa0C00`、`#f00C00` → enemy，`#888888` → other，`type: 'capture_zone'` → capture_zone，`type: 'respawn_base_tank'` → respawn。
  - `_ownerColor`：`#feD0C9` → `#ffffff`，`#3564FE` → `#174DFF`，`#fb554B` → `#fa0C00`。
  - 载入过滤：用桩 `fetch` 返回一个 bundle，含 3 个非 POI 点，显示坐标分别为 (0.5, 0.5)、(1.4, 0.5)、`x_ground: -0.2`。调用 `_loadPositions()` 后 `positions.length === 1`。
  - `_buildTracks`：两帧，各有一个友军点 (0.5, 0.5)、(0.505, 0.5)，以及一个玩家点 → `tracks` 里有 1 条 ally 轨迹（2 个点）和 1 条 player 轨迹。
  - `_cutoff`：`isLive` 为假、`maxTimestamp = 10000`、`timelinePosition = 0.5` → 5000；`isLive` 为真 → 10000。
- [ ] **Step 2:** 跑测试，确认失败。
- [ ] **Step 3:** 按设计 D3 的第 1～14 条实现，常量集中写在 `VIEW_STYLE` 里。
- [ ] **Step 4:** `styles.css`：去掉 `.canvas-wrapper` 的 `min-height: 800px`，改为 `min-height: 60vh`；去掉 `#mapCanvas` 的 `height: auto`，画布尺寸由脚本设定。
- [ ] **Step 5:** 跑全量测试至全绿。
- [ ] **Step 6:** 冒烟检查：把 `dist/data/matches.db*` 复制到系统临时目录下的新文件夹（例如 `$env:TEMP\wt_viewer_check\`），在该数据上启动服务。启动方式查 `wt_plotter/cli.py` 与 `config.py`，看服务如何指定数据目录；若不支持指定，就用 Flask 测试客户端加 `create_app` 指向这份副本。确认 `/match/1` 到 `/match/4`、`/static/tracks.js`、`/api/match/4/positions?since=0` 都返回 200。在 `PROGRESS.md` 的“待人工复核”记一条：用户需在浏览器里逐场查看 4 场比赛的效果。
- [ ] **Step 7:** 提交：`feat: draw linked tracks with live markers and clustered pois`。

### Task 4: 轨迹长度与回放播放

**Files:**
- Modify: `wt_plotter/web/templates/match.html` `wt_plotter/web/static/app.js` `wt_plotter/web/static/viewer.js` `wt_plotter/web/static/styles.css`
- Modify: `wt_plotter/i18n/locales/en.json` `wt_plotter/i18n/locales/zh.json`
- Modify: `tests/js/viewer.test.cjs`

**Interfaces:**
- Produces：`viewer.setTrail(seconds)`；`viewer.play()`、`viewer.pause()`、`viewer.isPlaying`。另提供构造参数 `onPlayStateChange(isPlaying)`，供 `app.js` 切换按钮文字。

- [ ] **Step 1:** 写失败测试，追加到 `viewer.test.cjs`：
  - 轨迹长度窗口：一条轨迹的点 `t` 为 0、1000、…、10000，`cutoff` 为 10000，`setTrail(3)` → 绘制范围的下标为 7～10。为此把计算起止下标的逻辑提取成 `_visibleRange(points, cutoff)`，返回 `[start, end]`，测试直接调用它。
  - `_advancePlayback(dt)`：`maxTimestamp = 10000`、`timelinePosition = 0.5`、`dt = 100` → `timelinePosition === 0.6`；从 0.95 开始、`dt = 100` → 结果为 1，且 `isPlaying === false`。
- [ ] **Step 2:** 跑测试，确认失败。
- [ ] **Step 3:** 按设计 D4 实现：`viewer.js` 中的 `setTrail`、`_visibleRange`、`play`、`pause`、`_advancePlayback`；`match.html` 中的轨迹长度面板（实时和回放都有）和播放按钮（只有回放有）；`app.js` 的事件绑定，拖动滑块时调用 `pause()`；两个语言文件各加 5 个键。
- [ ] **Step 4:** 跑全量测试至全绿。`test_static_keys.py` 会检查新键是否存在，以及模板中是否没有写死文字。
- [ ] **Step 5:** 提交：`feat: add trail length and timeline playback`。

### Task 5: 发布

**Files:**
- Modify: `wt_plotter/__init__.py` `CHANGELOG.md` `CHANGELOG.zh-CN.md`

- [ ] **Step 1:** 版本号改为 `0.3.2`。如有测试断言旧版本号，同步修改。
- [ ] **Step 2:** 中英文变更日志各新增 `0.3.2` 一节，分别写明：坐飞机时不再误判为空中视角，地面坐标不再被错算；地图改为轨迹线，并显示当前位置和阵亡位置；出生点和占领点不再重叠成团，占领点显示归属；新增轨迹长度选项和回放播放；高分屏下画面清晰。
- [ ] **Step 3:** 跑全量测试至全绿。
- [ ] **Step 4:** 运行 `scripts\build_windows.bat` 构建 EXE。构建失败时把现象记入 `PROGRESS.md` 的“待人工复核”，不算阻塞。
- [ ] **Step 5:** 提交：`chore: release 0.3.2`。
