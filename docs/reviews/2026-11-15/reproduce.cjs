// 审查复现：直接加载生产 viewer.js；DOM、网络用测试桩代替。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const failures = [];
const context = {
    window: {},
    console: { error: (...args) => failures.push(args), debug() {}, warn() {} },
    document: { getElementById: () => ({ hidden: true }) },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../../../wt_plotter/web/static/viewer.js'), 'utf8'), context);
const Viewer = context.window.MatchViewer;
function viewer() {
    return Object.assign(Object.create(Viewer.prototype), {
        matchId: 1, positions: [], pois: [], lastTimestamp: 0, maxTimestamp: 0,
        filters: {}, isLive: false, timelinePosition: 1,
        renders: 0, _render() { this.renders++; }, _updateStats() {}, _showMatchEnded() {},
    });
}
function bundle(count) {
    return {
        ticks: [{ id: 1, timestamp: 1000, army_type: 'tank', vehicle_type: 'test', is_player_air: 0, is_player_air_view: 0 }],
        positions: Array.from({ length: count }, (_, id) => ({ id, tick_id: 1, x: .3, y: .4, type: 'ground_model', icon: 'Tank', color: '#fa0C00', is_poi: 0, x_ground: null, y_ground: null })),
    };
}
(async () => {
    const large = viewer();
    context.fetch = async () => ({ json: async () => bundle(200000) });
    await large._loadPositions();
    assert.equal(large.positions.length, 200000);
    assert.equal(large.lastTimestamp, 0);
    assert.equal(large.renders, 0);
    assert.equal(failures.at(-1)[1].name, 'RangeError');
    console.log('large_history: 200000 points -> RangeError; cursor=0; render calls=0');

    const overlap = viewer();
    const pending = [];
    context.fetch = url => new Promise(resolve => pending.push({ url, resolve }));
    const a = overlap._loadPositions();
    const b = overlap._loadPositions();
    assert.equal(pending[0].url, pending[1].url);
    pending.forEach(p => p.resolve({ json: async () => bundle(1) }));
    await Promise.all([a, b]);
    assert.equal(overlap.positions.length, 2);
    assert.equal(new Set(overlap.positions.map(p => p.id)).size, 1);
    console.log('overlapping_requests: 1 database position appended twice');

    const pureAir = viewer();
    const air = { type: 'aircraft', icon: 'player', color: '#faC81E', is_player_air: 1, is_player_air_view: 1, x_ground: null, y_ground: null };
    assert.equal(pureAir._shouldShow(air), false);
    assert.equal(pureAir._shouldShow({ ...air, type: 'capture_zone' }), false);
    console.log('pure_air: both player aircraft and untransformed air POIs hidden');

    const ending = viewer();
    ending.isLive = true;
    let positionRequests = 0;
    let currentRows = 1;
    let ended = false;
    let poll;
    context.setInterval = callback => { poll = callback; return 1; };
    context.fetch = async url => {
        if (url.includes('/positions')) {
            positionRequests++;
            const snapshot = bundle(currentRows);
            // 位置查询取得旧快照后，最后一条位置入库并结束比赛。
            currentRows = 2;
            ended = true;
            return { json: async () => snapshot };
        }
        return { json: async () => url === '/api/active' ? null : url === '/api/status' ? { capturing: true } : { ended_at: ended ? '2026-11-15T12:00:00' : null } };
    };
    ending._startPolling();
    await new Promise(resolve => setImmediate(resolve));
    poll();
    await new Promise(resolve => setImmediate(resolve));
    poll();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(ending.isLive, false);
    assert.equal(positionRequests, 1);
    assert.equal(ending.positions.length, 1);
    assert.equal(currentRows, 2);
    console.log('match_end: server has 2 positions; viewer keeps 1 after subsequent poll');
})().catch(error => { console.error(error); process.exitCode = 1; });
