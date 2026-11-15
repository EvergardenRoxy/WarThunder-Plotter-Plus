# Changelog

[简体中文](CHANGELOG.zh-CN.md)

## 0.3.1

- Fixed the viewer failing on long matches: the timeline and live cursor no longer break once a match holds more than roughly a hundred thousand positions.
- The live view now polls one request at a time, which removes duplicated positions, and fetches the final positions when a match ends.
- Matches on air battle maps are now drawn. Ground matches still hide aircraft and air-view positions that have no ground coordinates.
- The first frame after returning from the air view to the ground is no longer converted a second time.
- Spawn points and airfields that appear after the first frame are now recorded, once per location.
- Only one capture can record into a data folder. A second `watch` or `capture` exits with an error, and starting `watch` while a `serve` instance is running logs a warning.
- `serve` reports the vehicle type of the active match from the latest recorded tick.
- Deleting a match now returns its disk space, and matches closed after a crash get a local end time.
- The update script works when the EXE or the temp folder path contains non-ASCII characters.
- Languages are discovered from the locale files, and the selector shows each language's own name.

## 0.3.0

- Rebuilt the upstream recorder as the `wt_plotter` package, with independently testable capture, storage, map, web, and desktop modules.
- Added English and Chinese interfaces, a persisted application language, and bilingual documentation. Map names use the upstream English labels.
- Kept the upstream SQLite schema, map hashes, position precision, and viewer color rules. The server now opens a connection per request and uses incremental vacuum after deleting a match.
- Replaced the capture loop with a sequential Requests client and a state machine that can run against injected telemetry. Air-view fitting uses Python standard-library arithmetic.
- Added graceful server shutdown and a warning in the live view when capture stops.
- Changed portable updates to the EvergardenRoxy/WarThunder-Plotter-Plus repository and included maps alongside templates and translations in the EXE.
