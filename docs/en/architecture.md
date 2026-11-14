# Architecture

[简体中文](../zh/architecture.md)

`wt_plotter.cli` starts the selected mode. In `watch` mode, the CLI starts a capture thread and a threaded Werkzeug server. The web and tray quit actions call the same HTTP shutdown route. When the server returns, the CLI waits for capture to finish, closes the match, and stops the tray.

```mermaid
flowchart LR
    Game[Local War Thunder telemetry] --> Client[TelemetryClient]
    Client --> Tracker[MatchTracker]
    Tracker --> SQLite[(SQLite)]
    Tracker --> Maps[Map PNGs]
    SQLite --> Web[Flask routes]
    Maps --> Web
    Web --> Viewer[MatchViewer canvas]
    Locale[Language catalogs and settings] --> Web
    Locale --> Tray[Windows tray]
```

- `capture/client.py` requests map validity first. The capture thread reads indicators and objects on valid ticks, and the tracker requests map images for starts, air views, and map changes.
- `capture/tracker.py` receives time, telemetry, a database connection, and an image callback. It can record synthetic ticks without the game. `air_transform.py` fits the air-to-ground mapping from paired map objects.
- `maps/lookup.py` resolves map IDs and battle types by exact or fuzzy dHash. Display names are resolved from the current catalog when the web response is built.
- `storage/db.py` owns the database schema and query shapes. The capture thread and each HTTP request open their own connections.
- `web/` renders pages through Jinja. The browser combines tick metadata with positions by `tick_id` for real-time display and replay.
