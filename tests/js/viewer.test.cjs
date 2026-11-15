const assert = require('node:assert/strict');
const test = require('node:test');
const { load } = require('./load.cjs');

function makeViewer(context, properties = {}) {
    return Object.assign(Object.create(context.window.MatchViewer.prototype), {
        matchId: 1,
        isLive: false,
        battleType: 'ground',
        mapKind: 'ground',
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
    const position = { tick_id: 1, x: 0.5, y: 0.5, type: 'ground_model', icon: 'MediumTank', color: '#174DFF' };
    context.fetch = async () => ({
        json: async () => ({
            ticks: [{ id: 1, timestamp: 1000 }, { id: 2, timestamp: 1500 }],
            positions: [position, { ...position, x: 1.4 }, { ...position, tick_id: 2, x_ground: -0.2, y_ground: 0.5 }],
        }),
    });
    await viewer._loadPositions();
    assert.equal(viewer.positionCount, 3);
    assert.equal(viewer.tracks.length, 1);
    assert.equal(viewer.tracks[0].points.length, 1);
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

test('includes both ends of the selected trail window', () => {
    const viewer = makeViewer(load('tracks.js', 'settings.js', 'viewer.js'));
    const points = Array.from({ length: 11 }, (_, i) => ({ t: i * 1000 }));
    viewer.setTrail(3);
    assert.deepEqual(Array.from(viewer._visibleRange(points, 10000)), [7, 10]);
    assert.deepEqual(Array.from(viewer._visibleRange(points, 9500)), [7, 9]);
    viewer.setTrail(0);
    assert.deepEqual(Array.from(viewer._visibleRange(points, 9500)), [0, 9]);
});

test('advances playback at the chosen speed and stops at the end', () => {
    const context = load('tracks.js', 'viewer.js');
    context.cancelAnimationFrame = () => {};
    const viewer = makeViewer(context, { maxTimestamp: 10000, timelinePosition: 0.5, isPlaying: true, speed: 10 });
    viewer._advancePlayback(100);
    assert.equal(viewer.timelinePosition, 0.6);
    assert.equal(viewer.isPlaying, true);
    viewer.timelinePosition = 0.95;
    viewer._advancePlayback(100);
    assert.equal(viewer.timelinePosition, 1);
    assert.equal(viewer.isPlaying, false);
});

test('restarts playback from the end and cancels the pending frame on pause', () => {
    const context = load('tracks.js', 'viewer.js');
    const stateChanges = [];
    let scheduled;
    let cancelled;
    context.requestAnimationFrame = callback => {
        scheduled = callback;
        return 7;
    };
    context.cancelAnimationFrame = id => { cancelled = id; };
    const viewer = makeViewer(context, {
        maxTimestamp: 10000,
        speed: 10,
        onPlayStateChange(isPlaying) { stateChanges.push(isPlaying); },
    });
    viewer.play();
    assert.equal(viewer.timelinePosition, 0);
    scheduled(0);
    scheduled(100);
    assert.equal(viewer.timelinePosition, 0.1);
    viewer.pause();
    assert.equal(cancelled, 7);
    assert.deepEqual(stateChanges, [true, false]);
});

test('fade bands cover the visible range from faint to opaque', () => {
    const viewer = makeViewer(load('tracks.js', 'settings.js', 'viewer.js'), { trail: 30 });
    const points = Array.from({ length: 31 }, (_, i) => ({ t: i * 1000 }));
    const bands = viewer._fadeBands(points, 0, 30, 0);
    assert.equal(bands.length, 20);
    assert.equal(bands[0].from, 0);
    assert.equal(bands.at(-1).to, 30);
    assert.ok(bands[0].alpha < 0.1);
    assert.ok(bands.at(-1).alpha > 0.9);
    for (let i = 0; i < bands.length - 1; i++) assert.equal(bands[i].to, bands[i + 1].from);
});

test('no fade when the trail shows everything', () => {
    const viewer = makeViewer(load('tracks.js', 'settings.js', 'viewer.js'), { trail: 0 });
    const points = Array.from({ length: 11 }, (_, i) => ({ t: i * 1000 }));
    assert.deepEqual(JSON.parse(JSON.stringify(viewer._fadeBands(points, 0, 10, 0))), [{ from: 0, to: 10, alpha: 1 }]);
});

test('blip size and line scale clamp and are saved', () => {
    const context = load('tracks.js', 'settings.js', 'viewer.js');
    const viewer = makeViewer(context);
    viewer.setBlipSize(5);
    assert.equal(viewer.blipSize, 1.5);
    viewer.setBlipSize(0.1);
    assert.equal(viewer.blipSize, 0.25);
    viewer.setLineScale(5);
    assert.equal(viewer.lineScale, 2);
    viewer.setLineScale(0.1);
    assert.equal(viewer.lineScale, 0.5);
    assert.equal(JSON.parse(context.localStorage.getItem('wtp.viewer')).lineScale, 0.5);
});

test('playback uses the speed setting', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), { maxTimestamp: 100000, timelinePosition: 0, speed: 20 });
    viewer._advancePlayback(1000);
    assert.equal(viewer.timelinePosition, 0.2);
});

test('play keeps the current position unless at the end', () => {
    const context = load('tracks.js', 'viewer.js');
    context.requestAnimationFrame = () => 1;
    const viewer = makeViewer(context, { maxTimestamp: 10000, timelinePosition: 0.5 });
    viewer.play();
    assert.equal(viewer.timelinePosition, 0.5);
});

test('speed clamps to 5x-40x and is saved', () => {
    const context = load('tracks.js', 'settings.js', 'viewer.js');
    const viewer = makeViewer(context);
    viewer.setSpeed(100);
    assert.equal(viewer.speed, 40);
    viewer.setSpeed(1);
    assert.equal(viewer.speed, 5);
    assert.equal(JSON.parse(context.localStorage.getItem('wtp.viewer')).speed, 5);
});

test('air map uses raw coordinates of air-view points only', () => {
    const base = { type: 'ground_model', color: '#174DFF', timestamp: 0 };
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        battleType: 'air_in_ground',
        mapKind: 'air',
        positions: [
            { ...base, x: 0.3, y: 0.4, is_player_air_view: 1 },
            { ...base, x: 0.8, y: 0.8, is_player_air_view: 0 },
        ],
    });
    viewer._buildTracks();
    assert.equal(viewer.tracks.length, 1);
    assert.deepEqual([viewer.tracks[0].points[0].x, viewer.tracks[0].points[0].y], [0.3, 0.4]);
    assert.equal(viewer.isAirMap, true);
});

test('ground map prefers ground coordinates and drops unmapped air-view points', () => {
    const base = { type: 'ground_model', color: '#174DFF', timestamp: 0, is_player_air_view: 1 };
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        battleType: 'air_in_ground',
        positions: [
            { ...base, x: 0.3, y: 0.4, x_ground: 0.6, y_ground: 0.7 },
            { ...base, x: 0.9, y: 0.9 },
        ],
    });
    viewer._buildTracks();
    assert.equal(viewer.tracks.length, 1);
    assert.deepEqual([viewer.tracks[0].points[0].x, viewer.tracks[0].points[0].y], [0.6, 0.7]);
    assert.equal(viewer.isAirMap, false);
});

test('drops unit icons that are not displayed', async () => {
    const context = load('tracks.js', 'viewer.js');
    const viewer = makeViewer(context);
    const base = { tick_id: 1, x: 0.5, y: 0.5, type: 'ground_model', color: '#174DFF', is_poi: 0 };
    context.fetch = async () => ({
        json: async () => ({
            ticks: [{ id: 1, timestamp: 1000 }],
            positions: ['Artillery', 'Pillbox', 'Airdefence', 'Mystery', 'MediumTank', 'Player']
                .map(icon => ({ ...base, icon }))
                .concat({ ...base, type: 'respawn_base_tank', icon: 'respawn_base_tank', is_poi: 1 }),
        }),
    });
    await viewer._loadPositions();
    assert.deepEqual(viewer.positions.map(pos => pos.icon), ['MediumTank', 'Player']);
    assert.equal(viewer.pois.length, 1);
    assert.equal(viewer.positionCount, 6);
});

test('tracks keep the unit icon', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        positions: [{ type: 'ground_model', icon: 'HeavyTank', color: '#174DFF', x: 0.5, y: 0.5, timestamp: 0 }],
    });
    viewer._buildTracks();
    assert.equal(viewer.tracks[0].points.at(-1).icon, 'HeavyTank');
});

test('finds the marker under the pointer', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        markers: [{ sx: 100, sy: 100, r: 4, icon: 'MediumTank' }],
    });
    assert.equal(viewer._markerAt(103, 100).icon, 'MediumTank');
    assert.equal(viewer._markerAt(140, 100), null);
});

test('visible events are newest first up to the cutoff', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        events: [{ timestamp: 1000, msg: 'a' }, { timestamp: 2000, msg: 'b' }, { timestamp: 5000, msg: 'c' }],
    });
    assert.deepEqual(viewer._visibleEvents(3000).map(e => e.timestamp), [2000, 1000]);
});

test('loading events advances the cursor', async () => {
    const context = load('tracks.js', 'viewer.js');
    const urls = [];
    context.fetch = async url => {
        urls.push(url);
        return { json: async () => [{ timestamp: 1500, msg: 'm' }] };
    };
    const viewer = makeViewer(context, { events: [], lastEventTimestamp: 0 });
    await viewer._loadEvents();
    assert.equal(viewer.lastEventTimestamp, 1501);
    await viewer._loadEvents();
    assert.match(urls[1], /since=1501/);
    assert.equal(viewer.events.length, 2);
});

test('reset view centers the square map in a wide canvas', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        width: 500, height: 500, viewWidth: 1000, viewHeight: 500, zoom: 3, panX: 7, panY: 7,
        _updateZoomDisplay() {},
    });
    viewer.resetView();
    assert.deepEqual([viewer.zoom, viewer.panX, viewer.panY], [1, 250, 0]);
});

test('panning is limited by the canvas, not the map', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        width: 500, height: 500, viewWidth: 1000, viewHeight: 500, zoom: 1, panX: 990, panY: 0,
    });
    viewer._clampPan();
    assert.equal(viewer.panX, 950);
});

test('marker label shows the exact vehicle when known', () => {
    const context = load('tracks.js', 'viewer.js');
    context.t = key => key;
    const viewer = makeViewer(context);
    assert.equal(viewer._markerLabel({ icon: 'Player', vehicle: 'germ_pzkpfw_IV_ausf_F2' }), 'unit.Player · germ pzkpfw IV ausf F2');
    assert.equal(viewer._markerLabel({ icon: 'Fighter', vehicle: '' }), 'unit.Fighter');
});

test('death marks only for always-visible sides and only once a track cannot resume', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), { maxTimestamp: 100000 });
    const points = Array.from({ length: 20 }, (_, i) => ({ t: 10000 + i * 250 }));
    const last = points.at(-1).t;
    assert.equal(viewer._isDeath('ally', points, 19, last + 3000), false);
    assert.equal(viewer._isDeath('ally', points, 19, last + 7000), true);
    assert.equal(viewer._isDeath('enemy', points, 19, last + 7000), false);
    assert.equal(viewer._isDeath('ally', points.slice(0, 10), 9, last + 7000), false);
});

test('gaps in a track are not drawn as lines', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'));
    assert.equal(viewer._isGap({ t: 0 }, { t: 250 }), false);
    assert.equal(viewer._isGap({ t: 0 }, { t: 2000 }), true);
});
