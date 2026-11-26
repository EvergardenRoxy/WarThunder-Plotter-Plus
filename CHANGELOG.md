# Changelog

[简体中文](CHANGELOG.zh-CN.md)

## 0.5.2

- Naval battle replays now rebuild ship tracks (plus aircraft), including enemy ships 8111 never shows. Replay-only naval matches use the naval map and are listed as naval battles. Matches already opened are parsed again the next time they are opened.
- Recognized three more maps: Falklands (air), the updated Karpaty Passage ground map, and Mediterranean Port (naval).

## 0.5.1

- Match history opens much faster (about 3x on a large database) and shows a loading overlay while pages load; opening a long replay now draws tracks in a couple of seconds instead of showing an empty map. The match data the viewer downloads is about 60% smaller.
- Matches with a replay have a **Scores** dropdown in Match history: result, mission, duration and both teams' score, kills, AI kills, assists, captures, zone damage and deaths, without opening the match. The replay report uses the same table.
- Import replays from anywhere: pick `.wrpl` files or a server replay folder in the browser (copies are kept in the data folder), or type the path of a single replay. Importing one replay opens its match directly.
- Empty slots in a replay's results are no longer listed as players.
- The first start after updating takes a few extra seconds to build new database indexes.

## 0.5.0

- Added game replay import: read local `.wrpl` replays, or download server replays by session id or link. Each match gets a replay report with every player's team, squadron, score, kills, assists, deaths and vehicles, the player kill log (who destroyed whom with which vehicle), and chat.
- Replays rebuild tracks: every aircraft in air battles (including your own and AI, with AI teams inferred from kills), and every ground unit plus player-flown aircraft in ground battles. Matches without an 8111 recording can be played back, and hovering a unit shows the player name and vehicle. Static map objects are not drawn.
- Folder import reads only each replay's header and final results, so a hundred replays take under a second; the kill log, chat and tracks are parsed the first time a match is opened. Damaged files or files still being written are only listed as failures; if a full parse fails the match still opens and the report states why.
- 8111 capture now records each minimap's world bounds so replay tracks land precisely on the map, and 8111 recordings are linked to replays of the same match automatically.
- Improved air-view detection (based on the main map's capture zones); all spawn point types (naval included) count as static markers, ships are drawn as hull shapes pointing along their heading, and naval matches without a map hash are recognized by their spawn points.

## 0.4.7

- Refined the dark UI with tactical amber-gold accents, frosted-glass map overlays, a pulsing live badge, and aligned Start/Duration column headers in Match history.
- Match history now shows lazy-loaded map thumbnails, actual spawned sortie vehicle chips (ignoring spawn-screen clicks), highlighted nuke badges, and auto-submitting date/mode filters.
- Added focus mode (collapsible sidebar, shortcut `B`), Follow me camera lock (`F`, auto-releases on drag), an adjustable map darken slider (0%–60%), and a compact playback speed stepper with full keyboard shortcuts (`←/→` ±5s / `Shift` ±15s, `[/]` speed, `R`/`0` reset zoom, `L` back to live).
- Added clickable sortie timeline pills below the playbar, battle feed filters (`All / Combat / Awards / Hide leaves`) with zero-width-space handling for Chinese HUD messages, color-coded timeline event markers, and richer tooltips for death markers (knockout time) and capture zones (owner and time).
- Fixed ground/air map toggle visibility on matches with air-view data (including nuke flights), nuke detection from battle feed events, and player icon categorization when the game temporarily flashes the player marker blue or green.

## 0.4.6

- The dark match viewer keeps map controls above the scrollable battle feed. The timeline marks battle events, and tracks fade with age even when the full trail is shown.
- The **My vehicle** label beside the map title shows the recorded model at the selected time in replay or rewind and the current model when following live. Hover over a teammate's crew knockout marker to see the unit type.
- The battle feed keeps every recorded message visible when you seek to an older entry. **Auto-scroll** follows playback, and turning it off keeps your place as new messages arrive. Player departure messages also appear in older recordings.
- Press Space to play or pause after dragging the timeline or clicking the map. The longer speed slider has 11 steps from 0.5× to 50×.
- Match history filters by map name, date, and battle type.

## 0.4.5

- Match replays can show all inferred teammate death locations up to the selected time, including markers whose trails have faded.
- The Live page now has a timeline. Drag back to inspect an earlier moment, play forward, or use **Back to live** to resume following the newest data while recording continues.

## 0.4.4

- Match history groups records by local start date and supports filtering by day. Each match shows its stable record number.
- The Live page can keep inferred squad and allied death locations visible after their trails fade. A failed battle feed request no longer freezes the live view, and the timeline includes late feed entries.
- The recorder retries missing or incomplete map images, keeps tracking after malformed battle feed responses, and avoids treating partially loaded capture zones as a map switch. The Live page shows the air map switch as soon as the air map is recorded.
- Portable updates preserve the original startup arguments, stage each download separately, and restore and start the previous EXE if replacement or launch fails.

## 0.4.3

- Fixed black or half-black maps. At the start of a match the game sometimes returns a map image that is not fully drawn yet; that image was saved and also made the map show as unknown or "Unknownmap". The recorder now waits for the full image before recording the map, and the live page picks it up as soon as it arrives. Matches already recorded with a black map cannot be repaired.

## 0.4.2

- Trails now fade continuously. They are no longer stroked in 20 bands, so the dark dots at the joints and the visible brightness steps are gone.
- Battle feed: long text wraps and the horizontal scrollbar is gone, scrollbars and drop-downs are dark, and the untranslated raw line the game sends on a disconnect is no longer shown.
- Chinese navigation labels changed to "历史战局" and "实时战局".
- Five maps updated by the game are recognized again: Karelia, European Fortress, Falklands, Ireland (ground and air map) and Poland. Checked against match replays.
- IFVs are now drawn on the map (they were ignored before).
- Documentation rewritten: new pages for capture and map recognition, the match viewer, and data and settings; the README gains a feature overview and screenshots.

## 0.4.1

- Air battles on combined maps, where the game first reports the ground map, are now identified by the first sortie and shown as air battles in the match list and page header. Checked against the match replay.

## 0.4.0

- The match page now fits on one screen: the map fills the available height, the playback bar sits under it, match details move into the header, and header items are vertically centered.
- The map canvas fills the whole map area, so zooming in no longer leaves empty side bands.
- Track linking now limits each step by speed (tuned on seven recorded matches). Different aircraft are no longer joined into long straight lines with false death marks. Units that drop off the map for up to 6 s while unspotted rejoin their track, with no line across the gap. Enemies only appear while spotted, so death crosses are drawn for you, your squad and allies only.
- The updated Krymsk ground map is now recognized (previously recorded as unknown), checked against the match replay.
- Hovering your own marker shows your exact vehicle. 8111 does not report other units' models, so they show their class only.
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
