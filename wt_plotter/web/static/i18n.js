function t(key, params = {}) {
    if (!Object.hasOwn(window.I18N, key)) {
        throw new Error(`Missing translation: ${key}`);
    }
    return window.I18N[key].replace(/\{(\w+)\}/g, (_, name) => {
        if (!Object.hasOwn(params, name)) {
            throw new Error(`Missing translation parameter: ${name}`);
        }
        return params[name];
    });
}
