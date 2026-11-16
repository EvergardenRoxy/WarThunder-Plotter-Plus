[← Back to README](../../README.md) · [简体中文](../zh/development.md)

# Development

From the repository root on Windows with Python 3.11 and the launcher installed, run:

```powershell
.\scripts\setup.bat
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m wt_plotter --help
.\scripts\build_windows.bat
```

The build writes `dist/WarThunderPlotterPlus-portable.exe`. To smoke-test it without checking for updates, set `$env:WT_PLOTTER_SKIP_UPDATE = '1'` and start the EXE with `serve --port 5057`. Check `GET /api/status`, then send `POST /shutdown` and confirm the process exits.

Use `reference/upstream/` as read-only reference material. With an upstream checkout present, `.venv\Scripts\python scripts/port_map_table.py` regenerates the map hash table and English name fixture. After regenerating, update both catalogs if any map IDs or names changed.

## Adding maps

When the game updates a map its minimap hash changes and matches show up as "Unknown Map" (see [Capture and map recognition](capture.md#unrecognized-maps)). To add one:

1. Take the hash from `data/missing_map_hashes.log`, or from the image named by its hash in `data/maps/`.
2. Work out which map it is. The replay of the same match is the most reliable source: the `.wrpl` in the `Replays` folder saved a few seconds after the match ended has a level name such as `levels/avg_poland.bin` near the start of the file.
3. Add a row to `LOCAL_MAPS` in `scripts/port_map_table.py` (hash, map ID, battle type, location) and rerun the script to regenerate `wt_plotter/maps/table.py`.
4. If the map ID is new, add `map.<map ID>` to both locale files.

Recorded matches need no change: the map name is looked up from the hash when a match is viewed. The saved image is named by its hash, so copy it to `<map ID>.png` for old matches to show the map.

## Tests

Unit tests construct telemetry and temporary SQLite databases. The optional upstream replay test uses `reference/upstream/data/raw/match_*.json` and its matching `reference/upstream/data/matches.db`. The replay compares tick and position counts and stored coordinate transforms. The CLI integration tests require loopback HTTP access.

JavaScript tests require Node.js 18 or later and run through `tests/web/test_js.py`.
