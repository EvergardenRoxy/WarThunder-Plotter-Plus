const assert = require('node:assert/strict');
const test = require('node:test');
const { load } = require('./load.cjs');

const { linkTracks, clusterPoints, lastIndexAtMost } = load('tracks.js').window.Tracks;
const options = { maxSpeed: 0.008, jitter: 0.002, maxGap: 2000 };

test('links parallel movement without crossing lanes', () => {
    const frames = Array.from({ length: 10 }, (_, i) => ({
        t: i * 1000,
        points: [{ x: 0.4, y: 0.5 + i * 0.005 }, { x: 0.5, y: 0.5 + i * 0.005 }],
    }));
    const tracks = linkTracks(frames, options);
    assert.deepEqual(Array.from(tracks, track => track.length), [10, 10]);
    assert.ok(tracks.every(track => track.every(point => point.x === track[0].x)));
});

test('starts a new track after a jump', () => {
    const frames = Array.from({ length: 10 }, (_, i) => ({
        t: i * 1000,
        points: [{ x: i < 5 ? 0.4 : 0.6, y: 0.5 }],
    }));
    assert.deepEqual(Array.from(linkTracks(frames, options), track => track.length), [5, 5]);
});

test('starts a new track after a long gap', () => {
    const frames = [0, 4000].map(t => ({ t, points: [{ x: 0.5, y: 0.5 }] }));
    assert.equal(linkTracks(frames, options).length, 2);
});

test('keeps steps short when points cross', () => {
    const frames = Array.from({ length: 6 }, (_, i) => ({
        t: i * 1000,
        points: [{ x: 0.40 + i * 0.008, y: 0.5 }, { x: 0.448 - i * 0.008, y: 0.5 }],
    }));
    const tracks = linkTracks(frames, options);
    assert.deepEqual(Array.from(tracks, track => track.length), [6, 6]);
    assert.ok(tracks.every(track => track.slice(1).every((point, i) =>
        Math.hypot(point.x - track[i].x, point.y - track[i].y) <= options.jitter + options.maxSpeed + 1e-9
    )));
});

test('preserves point fields and assigns the frame timestamp', () => {
    const point = { x: 0.5, y: 0.5, id: 7, t: 0 };
    const [[linked]] = linkTracks([{ t: 1000, points: [point] }], options);
    assert.deepEqual({ ...linked }, { ...point, t: 1000 });
    assert.equal(point.t, 0);
});

test('clusters nearby points and returns the selected points', () => {
    const points = [{ x: 0.1, y: 0.1 }, { x: 0.105, y: 0.1 }, { x: 0.5, y: 0.5 }];
    assert.deepEqual(Array.from(clusterPoints(points, 0.02, group => group[0])), [points[0], points[2]]);
});

test('finds the last item at or below the given value', () => {
    const items = [1, 3, 5];
    assert.deepEqual([0, 3, 4, 9].map(value => lastIndexAtMost(items, value, item => item)), [-1, 1, 1, 2]);
});

test('does not join a vanished track to a point beyond its reachable distance', () => {
    // 一架飞机消失后，0.5 秒内在 0.03 外出现的点属于另一架，应另起一条轨迹。
    const frames = [
        { t: 0, points: [{ x: 0.4, y: 0.5 }] },
        { t: 500, points: [{ x: 0.43, y: 0.5 }] },
    ];
    assert.equal(linkTracks(frames, options).length, 2);
});

test('allows longer steps after longer gaps', () => {
    const frames = [
        { t: 0, points: [{ x: 0.4, y: 0.5 }] },
        { t: 1500, points: [{ x: 0.413, y: 0.5 }] },
    ];
    assert.equal(linkTracks(frames, options).length, 1);
});
