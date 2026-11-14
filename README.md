# WT Plotter Plus

[简体中文](README.zh-CN.md)

WT Plotter Plus records match telemetry from the local War Thunder client on Windows. Open the web interface to watch a match live, browse recorded matches, or replay positions with the timeline, filters, zoom, and pan.

## Install

- **Portable EXE** — Put `WarThunderPlotterPlus-portable.exe` in a writable folder and run it. Build it from source with `scripts\build_windows.bat` after setup.
- **Source** — Install Python 3.11 with the Windows Python Launcher, then run `scripts\setup.bat` from the repository root. It creates `.venv` and installs the dependencies for development and packaging.

## Run

```powershell
.\.venv\Scripts\python -m wt_plotter watch
.\.venv\Scripts\python -m wt_plotter serve --port 5057
.\.venv\Scripts\python -m wt_plotter capture
```

`watch` is the default and opens the live view. `serve` opens the recorded-match list and runs the web server without collecting telemetry. `capture` records in the background until interrupted. For the EXE, pass the same subcommands directly. Both web modes default to `127.0.0.1:5000` and accept `--host` and `--port`.

Use the language selector in the navigation bar to switch between English and Chinese. The first launch follows the Windows interface language. Map names are displayed in English in both languages. Use **Quit** in the web page or tray, or press Ctrl+C in a terminal.

## Data and updates

The `data/` folder sits next to the EXE or at the root of a source checkout. It contains `matches.db`, `maps/`, `settings.json`, `wt_plotter.log`, and any `missing_map_hashes.log` entries. With both instances stopped, you can copy an upstream v0.2.0 database and its map images into this folder. Back up `data/` before replacing a database.

The portable build checks this project's GitHub Releases on startup and can replace the EXE when a newer portable build is available. Launch with `WT_PLOTTER_SKIP_UPDATE=1` in the process environment to skip the check.

## Development

Run `.venv\Scripts\python -m pytest -q` from the repository root. The server tests use the Windows loopback interface. See [architecture](docs/en/architecture.md), [development](docs/en/development.md), [database](docs/en/database.md), [translation](docs/en/translation.md), and [changes](CHANGELOG.md).

## Credits and license

Thanks to ElBartt/WarThunder-Plotter for the original recorder and map data, Sgambe33 for the earlier plotting work and map hashes, and ValerieOSD for WarThunderRPC. [Upstream](https://github.com/ElBartt/WarThunder-Plotter) · [WT-Plotter](https://github.com/Sgambe33/WT-Plotter) · [WarThunderRPC](https://github.com/ValerieOSD/WarThunderRPC)

Distributed under the [MIT License](LICENSE).
