const assert = require('node:assert/strict');
const test = require('node:test');
const { load } = require('./load.cjs');

function makeViewer(context, properties = {}) {
    return Object.assign(Object.create(context.window.MatchViewer.prototype), {
        matchId: 1,
        isLive: false,
        battleType: 'ground',
        mapKind: 'ground',
        selectedTime: null,
        selectedEvent: null,
        isPlaying: false,
        lastTimestamp: 0,
        maxTimestamp: 0,
        lastEventTimestamp: 0,
        events: [],
        ticks: [],
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
        ok: true,
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

test('live rewind keeps a fixed timestamp as new positions arrive and can return to live', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), { isLive: true, maxTimestamp: 10000 });
    assert.equal(viewer.getTimelineTime(), 10000);
    viewer.setTimelineTime(5000);
    viewer.maxTimestamp = 17000;
    assert.equal(viewer.getTimelineTime(), 5000);
    assert.equal(viewer.isAtLatest, false);
    viewer.returnToLive();
    assert.equal(viewer.getTimelineTime(), 17000);
    viewer.maxTimestamp = 18000;
    assert.equal(viewer.getTimelineTime(), 18000);
});

test('playing from behind live rejoins the live edge when it catches up', () => {
    const context = load('tracks.js', 'viewer.js');
    let frame;
    context.requestAnimationFrame = callback => { frame = callback; return 1; };
    context.cancelAnimationFrame = () => {};
    const viewer = makeViewer(context, { isLive: true, maxTimestamp: 10000, speed: 10 });
    viewer.play();
    assert.equal(viewer.isPlaying, false);
    viewer.setTimelineTime(9000);
    viewer.play();
    frame(0);
    viewer.maxTimestamp = 11000;
    frame(100);
    assert.equal(viewer.isPlaying, true);
    assert.equal(viewer.getTimelineTime(), 10000);
    frame(200);
    assert.equal(viewer.isPlaying, false);
    assert.equal(viewer.isAtLatest, true);
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
    const viewer = makeViewer(context, { maxTimestamp: 10000, selectedTime: 5000, isPlaying: true, speed: 10 });
    viewer._advancePlayback(100);
    assert.equal(viewer.getTimelineTime(), 6000);
    assert.equal(viewer.isPlaying, true);
    viewer.setTimelineTime(9500);
    viewer._advancePlayback(100);
    assert.equal(viewer.getTimelineTime(), 10000);
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
    assert.equal(viewer.getTimelineTime(), 0);
    scheduled(0);
    scheduled(100);
    assert.equal(viewer.getTimelineTime(), 1000);
    viewer.pause();
    assert.equal(cancelled, 7);
    assert.deepEqual(stateChanges, [true, false]);
});

// 记录画线调用的 Path2D 替身。
class FakePath {
    constructor() { this.ops = []; }
    moveTo(x, y) { this.ops.push(['M', x, y]); }
    lineTo(x, y) { this.ops.push(['L', x, y]); }
}

test('older trail segments fade towards a visible minimum', () => {
    const viewer = makeViewer(load('tracks.js', 'settings.js', 'viewer.js'));
    assert.equal(viewer._fadeAlpha({ t: 0 }, { t: 0 }, 0, 30000), 0.1);
    assert.equal(viewer._fadeAlpha({ t: 14000 }, { t: 16000 }, 0, 30000), 0.55);
    assert.equal(viewer._fadeAlpha({ t: 29000 }, { t: 31000 }, 0, 30000), 1);
});

test('each segment joins the path of its fade level', () => {
    const context = load('tracks.js', 'settings.js', 'viewer.js');
    context.Path2D = FakePath;
    const viewer = makeViewer(context, { trail: 10, width: 100, height: 100 });
    const points = Array.from({ length: 11 }, (_, i) => ({ t: i * 1000, x: i / 10, y: 0 }));
    const levels = [];
    viewer._addTrack(levels, points, 0, 10, 0, 10000);
    assert.deepEqual(Object.keys(levels).map(Number), [6, 9, 13, 17, 20, 24, 27, 31, 35, 38]);
    assert.deepEqual(levels[6].ops, [['M', 0, 0], ['L', 10, 0]]);
    assert.deepEqual(levels[38].ops, [['M', 90, 0], ['L', 100, 0]]);
});

test('segments of one level form a continuous line and gaps are skipped', () => {
    const context = load('tracks.js', 'settings.js', 'viewer.js');
    context.Path2D = FakePath;
    const viewer = makeViewer(context, { trail: 0, width: 100, height: 100 });
    const points = [0, 250, 500, 5000, 5250].map((t, i) => ({ t, x: i / 10, y: 0 }));
    const levels = [];
    viewer._addTrack(levels, points, 0, 4, -10000, 10000);
    assert.deepEqual(Object.keys(levels).map(Number), [40]);
    assert.deepEqual(levels[40].ops, [['M', 0, 0], ['L', 10, 0], ['L', 20, 0], ['M', 30, 0], ['L', 40, 0]]);
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
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), { maxTimestamp: 100000, selectedTime: 0, speed: 20 });
    viewer._advancePlayback(1000);
    assert.equal(viewer.getTimelineTime(), 20000);
});

test('play keeps the current position unless at the end', () => {
    const context = load('tracks.js', 'viewer.js');
    context.requestAnimationFrame = () => 1;
    const viewer = makeViewer(context, { maxTimestamp: 10000, selectedTime: 5000 });
    viewer.play();
    assert.equal(viewer.getTimelineTime(), 5000);
});

test('rounds playback speeds to a supported step and saves the choice', () => {
    const context = load('tracks.js', 'settings.js', 'viewer.js');
    const viewer = makeViewer(context);
    viewer.setSpeed(100);
    assert.equal(viewer.speed, 50);
    viewer.setSpeed(0.1);
    assert.equal(viewer.speed, 0.5);
    viewer.setSpeed(12);
    assert.equal(viewer.speed, 10);
    assert.equal(JSON.parse(context.localStorage.getItem('wtp.viewer')).speed, 10);
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
        ok: true,
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

test('death markers expose their unit type at their zoomed and panned position', () => {
    const context = load('tracks.js', 'viewer.js');
    context.Path2D = class { moveTo() {} lineTo() {} };
    const viewer = makeViewer(context, {
        width: 400, height: 400, zoom: 2, panX: -100, panY: -50, blipSize: 0.5, markers: [],
        _strokeMark() {},
    });
    viewer._drawDeath('ally', { x: 0.25, y: 0.5, icon: 'HeavyTank' });
    assert.equal(viewer._markerAt(102, 352).icon, 'HeavyTank');
    assert.equal(viewer._markerAt(90, 350), null);
});

test('loading events advances the cursor and publishes new messages even during rewind', async () => {
    const context = load('tracks.js', 'viewer.js');
    const urls = [];
    context.fetch = async url => {
        urls.push(url);
        const events = urls.length === 1 ? [{ timestamp: 1500, msg: 'm' }] : [];
        return { ok: true, json: async () => events };
    };
    const delivered = [];
    const viewer = makeViewer(context, {
        isLive: true, selectedTime: 1000,
        onEvents(events) { delivered.push(...events); },
    });
    await viewer._loadEvents();
    assert.equal(viewer.lastEventTimestamp, 1501);
    await viewer._loadEvents();
    assert.match(urls[1], /since=1501/);
    assert.equal(viewer.events.length, 1);
    assert.deepEqual(delivered, [{ timestamp: 1500, msg: 'm' }]);
    assert.equal(viewer.getTimelineTime(), 1000);
});

test('includes a later battle feed entry at the end of live and replay timelines', () => {
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        isLive: true,
        maxTimestamp: 1000,
        events: [{ timestamp: 1250, msg: 'Final event' }],
    });
    assert.equal(viewer.getTimelineMax(), 1250);
    viewer.isLive = false;
    assert.equal(viewer.getTimelineTime(), 1250);
    viewer.setTimelineTime(1000);
    assert.equal(viewer.getTimelineTime(), 1000);
    assert.equal(viewer.events.length, 1);
});

test('selecting a feed entry pauses at its exact time even when it was at the live edge', () => {
    const context = load('tracks.js', 'viewer.js');
    context.cancelAnimationFrame = () => {};
    const first = { timestamp: 2000, msg: 'First at this time' };
    const second = { timestamp: 2000, msg: 'Second at this time' };
    const selections = [];
    const viewer = makeViewer(context, {
        isLive: true,
        isPlaying: true,
        events: [first, second],
        _render() { selections.push(this.selectedEvent); },
    });
    viewer.seekToEvent(first);
    assert.equal(viewer.isPlaying, false);
    assert.equal(viewer.isAtLatest, false);
    viewer.events.push({ timestamp: 3100, msg: 'New event' });
    assert.equal(viewer.getTimelineTime(), 2000);
    viewer.seekToEvent(second);
    assert.deepEqual(selections, [first, second]);
    viewer.returnToLive();
    assert.equal(viewer.selectedEvent, null);
    assert.equal(viewer.getTimelineTime(), 3100);
});

test('an events request failure leaves live polling scheduled', async () => {
    const context = load('tracks.js', 'viewer.js');
    context.console = { error() {} };
    const scheduled = [];
    context.setTimeout = callback => scheduled.push(callback);
    context.fetch = async () => { throw new TypeError('Disconnected'); };

    let statusChecks = 0;
    const viewer = makeViewer(context, {
        isLive: true,
        polling: true,
        mapImage: {},
        async _loadPositions() {},
        async _checkMatchStatus() { statusChecks++; },
    });
    await viewer._poll();
    assert.equal(statusChecks, 1);
    assert.equal(scheduled.length, 1);

    context.fetch = async () => ({ ok: true, json: async () => [{ timestamp: 1250, msg: 'Recovered' }] });
    await scheduled.shift()();
    assert.equal(statusChecks, 2);
    assert.equal(viewer.events[0].msg, 'Recovered');
    assert.equal(scheduled.length, 1);
});

test('retries the final updates before marking a live match ended', async () => {
    const context = load('tracks.js', 'viewer.js');
    context.fetch = async url => ({
        ok: true,
        json: async () => {
            if (url.endsWith('/api/active')) return null;
            if (url.endsWith('/api/status')) return { capturing: true };
            return { ended_at: '2026-11-18T00:00:00', battle_type: 'ground', default_map: 'ground' };
        },
    });
    let eventsLoaded = false;
    let finished = false;
    const viewer = makeViewer(context, {
        isLive: true,
        async _loadPositions() { return true; },
        async _loadEvents() { return eventsLoaded; },
        _showMatchEnded() { finished = true; },
    });
    await viewer._checkMatchStatus();
    assert.equal(viewer.isLive, true);
    assert.equal(finished, false);
    eventsLoaded = true;
    await viewer._checkMatchStatus();
    assert.equal(viewer.isLive, false);
    assert.equal(finished, true);
});

test('a finished match stays open while rewound and follows the next match on return to live', async () => {
    const context = load('tracks.js', 'viewer.js');
    context.window.location = { href: '/match/1' };
    let activeChecks = 0;
    context.fetch = async url => ({
        ok: true,
        json: async () => {
            if (url.endsWith('/api/active')) {
                activeChecks++;
                return { id: 2 };
            }
            if (url.endsWith('/api/status')) return { capturing: true };
            return { ended_at: '2026-11-18T00:00:00', battle_type: 'ground', default_map: 'ground' };
        },
    });
    const viewer = makeViewer(context, {
        isLive: true,
        maxTimestamp: 20000,
        selectedTime: 10000,
        async _loadPositions() { return true; },
        async _loadEvents() { return true; },
        _showMatchEnded() {},
    });
    await viewer._checkMatchStatus();
    assert.equal(viewer.isLive, false);
    assert.equal(viewer.getTimelineTime(), 10000);
    assert.equal(activeChecks, 0);
    assert.equal(context.window.location.href, '/match/1');
    viewer.returnToLive();
    await viewer._checkMatchStatus();
    assert.equal(context.window.location.href, '/live');
});

test('live map metadata follows the default until the viewer selects a map', () => {
    const images = [];
    const updates = [];
    const viewer = makeViewer(load('tracks.js', 'viewer.js'), {
        _loadMap() { images.push(this.mapKind); },
        onMapUpdate(view, match) { updates.push([view.mapKind, match.air_map]); },
    });
    const match = { battle_type: 'ground', default_map: 'air', air_map: { map_id: 'air_map' } };
    viewer._applyMapMetadata(match);
    assert.equal(viewer.mapKind, 'air');
    viewer.setMapKind('ground');
    viewer._applyMapMetadata(match);
    assert.equal(viewer.mapKind, 'ground');
    assert.deepEqual(images, ['air', 'ground']);
    assert.deepEqual(updates, [['air', match.air_map], ['ground', match.air_map]]);
});

test('keeps old squad and allied death markers in replay without showing future deaths', () => {
    const context = load('tracks.js', 'settings.js', 'viewer.js');
    const points = Array.from({ length: 20 }, (_, i) => ({ t: i * 500 }));
    const deaths = [];
    const trails = [];
    const viewer = makeViewer(context, {
        maxTimestamp: 100000,
        trail: 30,
        filters: { squad: true, ally: true, player: true, enemy: true },
        tracks: ['squad', 'ally', 'player', 'enemy'].map(category => ({ category, points })),
        visiblePois: [],
        mapImage: {},
        ctx: {
            setTransform() {}, fillRect() {}, save() {}, translate() {}, scale() {}, drawImage() {}, restore() {},
        },
        _render: context.window.MatchViewer.prototype._render,
        _addTrack() {},
        _drawFades(fades) { trails.push(fades.size); },
        _drawDeath(category) { deaths.push(category); },
    });
    viewer._render();
    assert.deepEqual(deaths, []);
    viewer.setShowAllFriendlyDeaths(true);
    assert.deepEqual(deaths, ['squad', 'ally']);
    assert.deepEqual(trails, [0, 0]);
    assert.equal(JSON.parse(context.localStorage.getItem('wtp.viewer')).showAllFriendlyDeaths, true);
    deaths.length = 0;
    viewer.setFilters({ ally: false });
    assert.deepEqual(deaths, ['squad']);
    deaths.length = 0;
    viewer.setTimelineTime(14000);
    assert.deepEqual(deaths, []);
    viewer.setTimelineTime(100000);
    assert.deepEqual(deaths, ['squad']);
    viewer.setShowAllFriendlyDeaths(false);
    assert.deepEqual(deaths, ['squad']);
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
