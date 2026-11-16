[← 返回 README](../../README.zh-CN.md) · [English](../en/translation.md)

# 翻译

`wt_plotter/i18n/locales/` 下的 UTF-8 JSON 采用 `nav.matches` 这样的扁平键。确保中英文键集和命名占位符一致。`map.<map_id>` 在两种语言中使用相同的上游英文地图名，通用的 `map.unknown` 译为中文。

添加界面文案时，将同一个键加入两份语言文件，按用途选择前缀。在 Jinja 中可写 `{{ t('match.title', id=match.id) }}`，在 JavaScript 中可写 `t('viewer.stats', { positions: total, pois: count })`。浏览器通过 `window.I18N` 获取所选语言文件。HTTP 错误使用稳定的错误码，浏览器通过对应的 `error.<code>` 显示文字。

新增语言时，在同一目录把 `en.json` 复制为 `<语言代码>.json` 并翻译各值。`nav.language_name` 填该语言的自称，下拉框显示的就是它。目录里的每个 JSON 文件都是一种受支持的语言，测试会把每个文件与 `en.json` 比较。若要在首次启动时自动选中该语言，在 `i18n.WINDOWS_LANGUAGES` 中加入它的 Windows 主语言 ID，其它系统默认使用英文。重新构建 EXE 以打包新文件。`settings.json` 中的语言在当前版本不存在时，程序改用系统语言。本版本自带 `en` 和 `zh`。
