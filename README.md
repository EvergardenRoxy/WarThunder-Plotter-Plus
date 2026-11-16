<a id="ai-statement"></a>

[![AI Assisted](https://img.shields.io/badge/AI-Claude%20Fable%205.2%20%2B%20Claude%20Opus%205.5-D97757?style=for-the-badge&logo=anthropic&logoColor=white)](#ai-statement)

This project is a ground-up rebuild of ElBartt/WarThunder-Plotter. Fable 5.2 did the design, data checks and review; Opus 5.5 wrote most of the implementation.

# WT Plotter Plus

[简体中文](README.zh-CN.md)

Records what happens on the battlefield in every War Thunder match on Windows: who was where, where they went, and who destroyed whom. Afterwards you can scrub through the whole match in a browser, or watch it live while you play.

All data comes from the game client's own local interface (`localhost:8111`, the built-in web map). Nothing reads game memory or touches game files, and recordings stay on your computer.

## Features

- **[Automatic capture](docs/en/capture.md)**: recording starts when you enter a battle and stops when you leave. The map is recognized from the minimap, and ground, air and naval battles are told apart.
- **[Match replay](docs/en/viewer.md)**: every unit's trail is drawn on the map in its team color and fades with age. Play at 5×–40×, drag the timeline, zoom, pan, and filter by team.
- **[Live match](docs/en/viewer.md#live-match)**: the same view, updating during the battle. Handy on a second screen.
- **[Unit classes and death marks](docs/en/viewer.md#reading-the-map)**: light, medium and heavy tanks, tank destroyers, SPAA and aircraft each have their own shape. A × marks where you, your squad and your allies died.
- **[Air map switch](docs/en/viewer.md#ground-map-and-air-map)**: when you fly in a ground battle the air map is recorded too, and the replay can switch between the two.
- **[Battle feed](docs/en/viewer.md#battle-feed)**: the game's kill, shoot-down and fire messages are recorded and follow the timeline during replay.
- **English and Chinese interface**: switch in the navigation bar. The first launch follows the Windows display language.

## Examples

| Ground battle replay | Air battle replay |
| --- | --- |
| ![Ground battle replay](docs/images/match_ground.png) | ![Air battle replay](docs/images/match_air.png) |

The screenshots show the Chinese interface, and the battle feed in them uses made-up player names. See also the [match list](docs/images/match_list.png).

## Install

- **Portable EXE**: download `WarThunderPlotterPlus-portable.exe` from [Releases](https://github.com/EvergardenRoxy/WarThunder-Plotter-Plus/releases), put it in a writable folder and run it.
- **From source**: install Python 3.11 with the Windows Python Launcher, then run `scripts\setup.bat` in the repository root.

## Use

Start the program, then play a match. It opens your browser on the Live page, which starts drawing as soon as you are in a battle. Finished matches are listed under Matches.

```text
WarThunderPlotterPlus-portable.exe            capture and open the live page (default, same as watch)
WarThunderPlotterPlus-portable.exe serve      browse recorded matches without capturing
WarThunderPlotterPlus-portable.exe capture    capture only, no web page
```

From source, replace the EXE with `.\.venv\Scripts\python -m wt_plotter`. The web page is at `http://127.0.0.1:5000` by default; change it with `--host` and `--port`. Click Quit in the top right of the page or in the system tray to close the program.

## Documentation

- [Capture and map recognition](docs/en/capture.md)
- [Match viewer](docs/en/viewer.md)
- [Data, settings and updates](docs/en/data.md)
- [Architecture](docs/en/architecture.md)
- [Database](docs/en/database.md)
- [Development guide](docs/en/development.md)
- [Translation](docs/en/translation.md)
- [Changelog](CHANGELOG.md)

## Origins and credits

This project was rebuilt from [ElBartt/WarThunder-Plotter](https://github.com/ElBartt/WarThunder-Plotter) and keeps its database schema and map hash table. Many thanks. Thanks also to Sgambe33 for [WT-Plotter](https://github.com/Sgambe33/WT-Plotter) (trail plotting and map hashes) and to ValerieOSD for [WarThunderRPC](https://github.com/ValerieOSD/WarThunderRPC).

This project is not affiliated with Gaijin Entertainment.

## License

Distributed under the [MIT License](LICENSE).
