const assert = require('node:assert/strict');
const test = require('node:test');
const { load } = require('./load.cjs');

test('settings merge defaults', () => {
    const context = load('settings.js');
    context.localStorage = { getItem: () => '{"trail":60}' };
    assert.deepEqual({ ...context.window.Settings.load('k', { trail: 30, blipSize: 0.5 }) }, { trail: 60, blipSize: 0.5 });
});

test('settings load empty', () => {
    const context = load('settings.js');
    context.localStorage = { getItem: () => null };
    assert.deepEqual({ ...context.window.Settings.load('k', { trail: 30 }) }, { trail: 30 });
});

test('settings save', () => {
    const context = load('settings.js');
    const calls = [];
    context.localStorage = { setItem: (...args) => calls.push(args) };
    context.window.Settings.save('k', { a: 1 });
    assert.deepEqual(calls, [['k', '{"a":1}']]);
});
