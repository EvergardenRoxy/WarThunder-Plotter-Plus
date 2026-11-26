const assert = require('node:assert/strict');
const test = require('node:test');
const { load } = require('./load.cjs');

// 记录路径顶点的假 ctx。
function recorder() {
    const points = [];
    return {
        points,
        beginPath() {},
        closePath() {},
        moveTo(x, y) { points.push([x, y]); },
        lineTo(x, y) { points.push([x, y]); },
        rect(x, y, w, h) { points.push([x, y], [x + w, y + h]); },
        arc(x, y, r) { points.push([x - r, y - r], [x + r, y + r]); },
    };
}

const bounds = points => {
    const xs = points.map(p => p[0]);
    const ys = points.map(p => p[1]);
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)].map(v => Math.round(v * 1000) / 1000);
};

test('shapes fit the requested size', () => {
    const { Shapes } = load('shapes.js').window;
    for (const shape of ['circle', 'square', 'diamond', 'triangle', 'pentagon', 'circle-cross', 'arrow', 'ship']) {
        const ctx = recorder();
        Shapes.path(ctx, shape, 10, 10, 4);
        const [x0, y0, x1, y1] = bounds(ctx.points);
        assert.ok(x0 >= 8 && y0 >= 8 && x1 <= 12 && y1 <= 12, shape);
    }
    const ctx = recorder();
    Shapes.path(ctx, 'square', 10, 10, 4);
    assert.deepEqual(bounds(ctx.points), [8, 8, 12, 12]);
});

test('arrow and ship point along the given angle', () => {
    const { Shapes } = load('shapes.js').window;
    const tip = (shape, angle) => {
        const ctx = recorder();
        Shapes.path(ctx, shape, 0, 0, 10, angle);
        return ctx.points[0].map(v => Math.round(v * 1000) / 1000);
    };
    for (const shape of ['arrow', 'ship']) {
        assert.deepEqual(tip(shape, 0), [5, 0], shape);
        assert.deepEqual(tip(shape, Math.PI / 2), [0, 5], shape);
    }
});
