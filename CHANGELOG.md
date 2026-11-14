# Changelog

[简体中文](CHANGELOG.zh-CN.md)

## 0.3.0

- Rebuilt the upstream recorder as the `wt_plotter` package, with independently testable capture, storage, map, web, and desktop modules.
- Added English and Chinese interfaces, a persisted application language, and bilingual documentation. Map names use the upstream English labels.
- Kept the upstream SQLite schema, map hashes, position precision, and viewer color rules. The server now opens a connection per request and uses incremental vacuum after deleting a match.
- Replaced the capture loop with a sequential Requests client and a state machine that can run against injected telemetry. Air-view fitting uses Python standard-library arithmetic.
- Added graceful server shutdown and a warning in the live view when capture stops.
- Changed portable updates to the EvergardenRoxy/WarThunder-Plotter-Plus repository and included maps alongside templates and translations in the EXE.
