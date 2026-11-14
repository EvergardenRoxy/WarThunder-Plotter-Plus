# 翻译

[English](../en/translation.md)

`wt_plotter/i18n/locales/` 下的 UTF-8 JSON 采用 `nav.matches` 这样的扁平键。确保中英文键集和命名占位符一致。`map.<map_id>` 在两种语言中使用相同的上游英文地图名，通用的 `map.unknown` 译为中文。

添加界面文案时，将同一个键加入两份语言文件，按用途选择前缀。在 Jinja 中可写 `{{ t('match.title', id=match.id) }}`，在 JavaScript 中可写 `t('viewer.stats', { positions: total, pois: count })`。浏览器通过 `window.I18N` 获取所选语言文件。HTTP 错误使用稳定的错误码，浏览器通过对应的 `error.<code>` 显示文字。

新增语言时，复制 `en.json` 并以新语言代码命名，翻译值后将代码加入 `i18n.LANGUAGES`。在语言文件和下拉框中加入选项标签，更新枚举受支持语言的测试，重新构建 EXE 以打包新文件。本版本支持 `en` 和 `zh`。
