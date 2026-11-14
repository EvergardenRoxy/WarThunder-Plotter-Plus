# Translation

[简体中文](../zh/translation.md)

The UTF-8 JSON catalogs in `wt_plotter/i18n/locales/` use flat keys such as `nav.matches`. Keep the English and Chinese key sets and named placeholders in sync. Map keys use `map.<map_id>` and the same English display name in both catalogs. The generic `map.unknown` label is translated.

For new text, add the same key to both catalogs under the appropriate prefix. Use `{{ t('match.title', id=match.id) }}` in Jinja and `t('viewer.stats', { positions: total, pois: count })` in JavaScript. The browser receives the selected catalog as `window.I18N`. HTTP errors use stable codes, which the browser displays through the corresponding `error.<code>` key.

To add a language, copy `en.json` to the new language code, translate its values, and register the code in `i18n.LANGUAGES`. Add its option label to the catalogs and language selector, update the tests that enumerate supported languages, and build the EXE again to bundle the file. The current release supports `en` and `zh`.
