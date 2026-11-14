# Development

[简体中文](../zh/development.md)

From the repository root on Windows with Python 3.11 and the launcher installed, run:

```powershell
.\scripts\setup.bat
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m wt_plotter --help
.\scripts\build_windows.bat
```

The build writes `dist/WarThunderPlotterPlus-portable.exe`. To smoke-test it without checking for updates, set `$env:WT_PLOTTER_SKIP_UPDATE = '1'` and start the EXE with `serve --port 5057`. Check `GET /api/status`, then send `POST /shutdown` and confirm the process exits.

Use `reference/upstream/` as read-only reference material. With an upstream checkout present, `.venv\Scripts\python scripts/port_map_table.py` regenerates the map hash table and English name fixture. After regenerating, update both catalogs if any map IDs or names changed.

Unit tests construct telemetry and temporary SQLite databases. The optional upstream replay test uses `reference/upstream/data/raw/match_*.json` and its matching `reference/upstream/data/matches.db`. The replay compares tick and position counts and stored coordinate transforms. The CLI integration tests require loopback HTTP access.
