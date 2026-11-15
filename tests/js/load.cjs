const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// 内存版 localStorage，测试可直接替换 context.localStorage。
function memoryStorage() {
    const items = new Map();
    return {
        getItem: key => (items.has(key) ? items.get(key) : null),
        setItem: (key, value) => items.set(key, String(value)),
    };
}

function load(...files) {
    const context = vm.createContext({
        window: {},
        document: { getElementById: () => ({ hidden: true }) },
        console,
        localStorage: memoryStorage(),
    });
    for (const file of files) {
        const source = path.join(__dirname, '../../wt_plotter/web/static', file);
        vm.runInContext(fs.readFileSync(source, 'utf8'), context, { filename: source });
    }
    return context;
}

module.exports = { load };
