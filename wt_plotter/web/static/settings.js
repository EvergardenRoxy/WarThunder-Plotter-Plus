// 用 localStorage 存取 JSON 设置，读出时与默认值浅合并。
function load(key, defaults) {
    return { ...defaults, ...JSON.parse(localStorage.getItem(key) ?? '{}') };
}

function save(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

window.Settings = { load, save };
