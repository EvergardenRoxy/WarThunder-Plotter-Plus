[← Back to README](../../README.md) · [简体中文](../zh/data.md)

# Data, settings and updates

## Data folder

The portable build keeps its data in a `data/` folder next to the EXE. A source checkout uses `data/` in the repository root.

| File | Contents |
| --- | --- |
| `matches.db` | Every match: positions, battle feed and match details (SQLite). While the program runs there are also `-wal` and `-shm` files beside it |
| `maps/` | Minimap images. Recognized maps are named by map ID, unrecognized ones by hash |
| `settings.json` | Interface language |
| `wt_plotter.log` | Run log |
| `missing_map_hashes.log` | Hashes of unrecognized maps, see [Capture and map recognition](capture.md#unrecognized-maps) |
| `capture.lock` | Marks a capture in progress, so only one program captures into the folder |

On first run the portable build unpacks its bundled map images into `data/maps/`. Existing files are left alone.

## Backup and moving

Quit the program, then copy the whole `data/` folder. To move to another computer or folder, put it next to the EXE again.

The database schema is the one from upstream WarThunder-Plotter v0.2.0, so a `matches.db` and map images from that version can be copied in and used directly. Back up before replacing a database.

An hour of matches takes roughly 10–20 MB. Deleting matches from the match list frees the space.

## Interface language

The drop-down in the navigation bar switches between English and Chinese, and the choice is saved in `settings.json`. The first launch follows the Windows display language. Map names are shown in English in both languages.

Trail duration, marker size and the other replay settings are saved in the browser, not in `data/`. See [Match viewer](viewer.md#sidebar-settings).

## Web address

By default the page is served on this computer only, at `127.0.0.1:5000`. To view it from another device on your local network, such as a tablet:

```text
WarThunderPlotterPlus-portable.exe watch --host 0.0.0.0 --port 5000
```

Then open `http://<this computer's LAN address>:5000` on the other device. The page has no login: anyone who can reach the address can view and delete matches and quit the program. Only do this on a network you trust.

Starting the program while it is already running just opens the browser. No second instance is started.

## Automatic updates

On startup the portable build checks this project's [GitHub Releases](https://github.com/EvergardenRoxy/WarThunder-Plotter-Plus/releases). If there is a newer version it downloads it and replaces the EXE; `data/` is not touched. If GitHub cannot be reached the check is skipped and the program runs as usual.

To skip the check, set the environment variable `WT_PLOTTER_SKIP_UPDATE=1` before starting. A source checkout never checks for updates.
