# Translation

[简体中文](../zh/translation.md)

The UTF-8 JSON catalogs in `wt_plotter/i18n/locales/` use flat keys such as `nav.matches`. Keep the English and Chinese key sets and named placeholders in sync. Map keys use `map.<map_id>` and the same English display name in both catalogs. The generic `map.unknown` label is translated.

For new text, add the same key to both catalogs under the appropriate prefix. Use `{{ t('match.title', id=match.id) }}` in Jinja and `t('viewer.stats', { positions: total, pois: count })` in JavaScript. The browser receives the selected catalog as `window.I18N`. HTTP errors use stable codes, which the browser displays through the corresponding `error.<code>` key.

To add a language, copy `en.json` to `<code>.json` in the same folder and translate its values. Set `nav.language_name` to the language's own name, which the selector displays. Every JSON file in the folder becomes a supported language, and the tests compare each one against `en.json`. To select the language automatically on first launch, add its Windows primary language ID to `i18n.WINDOWS_LANGUAGES`; other systems start in English. Build the EXE again to bundle the file. If `settings.json` names a language this version lacks, the app falls back to the system language. The current release ships `en` and `zh`.
