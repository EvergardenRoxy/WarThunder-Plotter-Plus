const assert = require('node:assert/strict');
const test = require('node:test');
const { load } = require('./load.cjs');

function makeViewer(context, properties = {}) {
    return Object.assign(Object.create(context.window.MatchViewer.prototype), {
        matchId: 1,
        isLive: false,
        isAirMap: false,
        timelinePosition: 1,
        lastTimestamp: 0,
        maxTimestamp: 0,
        positionCount: 0,
        positions: [],
        pois: [],
        _render() {},
        _updateStats() {},
    }, properties);
}

test('categorizes team colors, map objects and gray markers', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'));
    for (const [color, expected] of [
        ['#faC81E', 'player'], ['#67D756', 'squad'], ['#174DFF', 'ally'],
        ['#1839A7', 'ally'], ['#043FFF', 'ally'], ['#fa0C00', 'enemy'],
        ['#f00C00', 'enemy'], ['#888888', 'other'],
    ]) {
        assert.equal(viewer._categorize({ type: 'ground_model', icon: 'player', color }), expected, color);
    }
    assert.equal(viewer._categorize({ type: 'capture_zone' }), 'capture_zone');
    assert.equal(viewer._categorize({ type: 'respawn_base_tank' }), 'respawn');
});

test('normalizes POI colors to the nearest owner', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'));
    assert.equal(viewer._ownerColor('#feD0C9'), '#ffffff');
    assert.equal(viewer._ownerColor('#3564FE'), '#174DFF');
    assert.equal(viewer._ownerColor('#fb554B'), '#fa0C00');
});

test('discards out-of-range display coordinates while advancing the cursor', async () => {
    const context = load('tracks.js', 'viewer.js');
    const viewer = makeViewer(context);
    const position = { tick_id: 1, x: 0.5, y: 0.5, type: 'ground_model', color: '#174DFF' };
    context.fetch = async () => ({
        json: async () => ({
            ticks: [{ id: 1, timestamp: 1000 }, { id: 2, timestamp: 1500 }],
            positions: [position, { ...position, x: 1.4 }, { ...position, tick_id: 2, x_ground: -0.2, y_ground: 0.5 }],
        }),
    });
    await viewer._loadPositions();
    assert.equal(viewer.positions.length, 1);
    assert.equal(viewer.positionCount, 3);
    assert.equal(viewer.tracks.length, 1);
    assert.equal(viewer.lastTimestamp, 1501);
});

test('builds tracks by category and keeps ground data while the player flies', () => {
    const ally = { type: 'ground_model', color: '#174DFF', x: 0.5, y: 0.5, timestamp: 0 };
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        positions: [
            ally,
            { ...ally, color: '#faC81E' },
            { ...ally, x: 0.505, timestamp: 1000, is_player_air: 1, is_player_air_view: 0 },
            { ...ally, x: 0.51, timestamp: 2000, is_player_air_view: 1 },
            { ...ally, x: 0.515, timestamp: 3000, type: 'aircraft' },
        ],
    });
    viewer._buildTracks();
    assert.deepEqual(Array.from(viewer.tracks, ({ category, points }) => [category, points.length]), [
        ['ally', 2], ['player', 1],
    ]);
});

test('uses the selected replay time and the latest live time', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), { maxTimestamp: 10000, timelinePosition: 0.5 });
    assert.equal(viewer._cutoff(), 5000);
    viewer.isLive = true;
    assert.equal(viewer._cutoff(), 10000);
});
