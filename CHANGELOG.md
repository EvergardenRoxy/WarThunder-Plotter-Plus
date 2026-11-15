# Changelog

[简体中文](CHANGELOG.zh-CN.md)

## 0.4.0

- The match page now fits on one screen: the map fills the available height, the playback bar sits under it, match details move into the header, and header items are vertically centered.
- New "Trail duration" setting (10/30/60/120 s or all, default 30 s). Older parts of a trail fade out, on the live page too.
- Blip size now ranges from 0.25 to 1.5 (default 0.5), and line width can be scaled from 0.5× to 2×.
- Playback speed is a slider from 5× to 40×, default 10×.
- Trail duration, blip size, line width, speed and filters are remembered in the browser.
- Matches with an air map can switch between the ground and air maps, and open on the air map when the first sortie is an aircraft. Air battles no longer show an empty ground map.
- Each unit's latest position is drawn as a shape for its class, with a legend and a hover name. Artillery, pillboxes and ships are hidden for now.
- New battle feed: kill and damage messages from the 8111 `/hudmsg` endpoint are stored verbatim and listed in the sidebar in step with the timeline. The message format follows community docs and has not yet been checked against a live game.

## 0.3.2

- Air-view detection uses map evidence so ground coordinates stay correct when the player takes to the air.
- Match maps show color-coded tracks, each unit's latest position, and crosses where tracks appear to end in a death.
- Nearby spawn and capture markers are grouped, and capture markers show their team ownership.
- The live and replay pages offer selectable trail lengths, and replays can be played at 10× speed.
- Maps and overlays render at the screen's pixel density.

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
