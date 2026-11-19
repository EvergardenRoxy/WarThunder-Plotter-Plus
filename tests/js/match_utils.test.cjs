const assert = require('node:assert/strict');
const test = require('node:test');
const { load } = require('./load.cjs');

test('classifies battle feed messages including zero-width-space Chinese War Thunder text', () => {
    const { MatchUtils } = load('match_utils.js').window;
    assert.equal(MatchUtils.classifyEvent('Pilot 已\u200b掉\u200b线。'), 'leave');
    assert.equal(MatchUtils.classifyEvent('Pilot left the match'), 'leave');
    assert.equal(MatchUtils.classifyEvent('Alice 击\u200b毁\u200b了 Bob'), 'kill');
    assert.equal(MatchUtils.classifyEvent('Alice 的\u200b攻\u200b击\u200b引\u200b燃\u200b了 Bob'), 'kill');
    assert.equal(MatchUtils.classifyEvent('Alice destroyed Bob'), 'kill');
    assert.equal(MatchUtils.classifyEvent('Alice 获\u200b得\u200b嘉\u200b奖\u200b“团\u200b队\u200b协\u200b作”'), 'award');
    assert.equal(MatchUtils.classifyEvent('Alice 先\u200b拔\u200b头\u200b筹！'), 'award');
    assert.equal(MatchUtils.classifyEvent('Alice 投\u200b放\u200b了\u200b核\u200b武\u200b器！'), 'nuke');
    assert.equal(MatchUtils.classifyEvent('Bob 击\u200b落\u200b了 Alice (☢\u200bB-29A)'), 'nuke');
    assert.equal(MatchUtils.classifyEvent('油\u200b温\u200b过\u200b高'), 'other');
});

test('filters feed kinds and ranks timeline slot priority', () => {
    const { MatchUtils } = load('match_utils.js').window;
    assert.equal(MatchUtils.matchesFeedFilter('leave', 'all'), true);
    assert.equal(MatchUtils.matchesFeedFilter('leave', 'no_leave'), false);
    assert.equal(MatchUtils.matchesFeedFilter('kill', 'no_leave'), true);
    assert.equal(MatchUtils.matchesFeedFilter('kill', 'kill'), true);
    assert.equal(MatchUtils.matchesFeedFilter('nuke', 'kill'), true);
    assert.equal(MatchUtils.matchesFeedFilter('nuke', 'award'), true);
    assert.equal(MatchUtils.matchesFeedFilter('award', 'award'), true);
    assert.equal(MatchUtils.matchesFeedFilter('award', 'kill'), false);
    assert.ok(MatchUtils.eventPriority('nuke') > MatchUtils.eventPriority('kill'));
    assert.ok(MatchUtils.eventPriority('kill') > MatchUtils.eventPriority('award'));
    assert.ok(MatchUtils.eventPriority('award') > MatchUtils.eventPriority('other'));
    assert.ok(MatchUtils.eventPriority('other') > MatchUtils.eventPriority('leave'));
});

test('extracts only actually spawned sorties (ignoring spawn-screen vehicle clicks)', () => {
    const { MatchUtils } = load('match_utils.js').window;
    const ticks = [
        { id: 1, timestamp: 0, army_type: 'air', vehicle_type: 'dummy_plane' },
        { id: 2, timestamp: 8000, army_type: 'tank', vehicle_type: 'germ_tiger' },
        { id: 3, timestamp: 20000, army_type: 'tank', vehicle_type: 'germ_tiger' },
        { id: 4, timestamp: 587000, army_type: 'tank', vehicle_type: 'germ_panzerjager_tiger' },
        { id: 5, timestamp: 588000, army_type: 'tank', vehicle_type: 'germ_le_kpz_m41' },
        { id: 6, timestamp: 591000, army_type: 'tank', vehicle_type: 'germ_le_kpz_m41' },
    ];
    // 只有 tick 3 和 6 在地图上存在 Player 标记（tick 2、4、5 只是选车界面预览）。
    const playerTickIds = new Set([3, 6]);
    assert.deepEqual(Array.from(MatchUtils.extractSorties(ticks, ['dummy_plane'], playerTickIds), item => ({ ...item })), [
        { timestamp: 20000, vehicle: 'germ tiger', army: 'tank' },
        { timestamp: 591000, vehicle: 'germ le kpz m41', army: 'tank' },
    ]);
});
