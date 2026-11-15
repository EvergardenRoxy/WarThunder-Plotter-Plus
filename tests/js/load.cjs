const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load(...files) {
    const context = vm.createContext({
        window: {},
        document: { getElementById: () => ({ hidden: true }) },
        console,
    });
    for (const file of files) {
        const source = path.join(__dirname, '../../wt_plotter/web/static', file);
        vm.runInContext(fs.readFileSync(source, 'utf8'), context, { filename: source });
    }
    return context;
}

module.exports = { load };
