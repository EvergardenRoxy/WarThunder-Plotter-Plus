[← Back to README](../../README.md) · [简体中文](../zh/replay.md)

# Game replays

Besides live 8111 capture, the app reads the game's own `.wrpl` replays to fill in what 8111 cannot provide: every player's name, squadron, team, score and kill counts, the player kill log (who destroyed whom with which vehicle), and chat. Replays also yield aircraft tracks (air battles) or ground unit tracks (ground battles), so matches without an 8111 recording get a playback too.

| Source | Location | Coverage |
| :--- | :--- | :--- |
| Local replay | `Replays\#date time.wrpl` in the game folder | From the start until you leave the battle |
| Server replay | Replay CDN, downloaded by session id in parts | The whole battle, with final results |

A local replay and the server replay share the session id, so they land on the same match; the report prefers the server replay.

## Usage

Expand **Import game replays** at the top of the match history:

- **Local replay folder**: enter the game's `Replays` folder and click **Import new replays**. This step reads only each replay's header and final results, so a hundred replays take under a second; sessions already imported are skipped. The kill log, chat and tracks are parsed in full the first time you open a match (about 2–6 seconds per match, a few long ones take over ten), and later opens are immediate. After an update to the replay parser, opening a match parses it again with the new version. A file the game is still writing, or a damaged one, fails on its own and is listed in the result without stopping the others. If the full parse fails (file deleted, moved or not understood), the match still opens, the report states why at the top, and the same parser version does not retry it.
- **Server replay**: enter the 16-digit hex session id or a link ending in it, then click **Download and import**. Parts are saved under `replays\<session>\` in the data folder. The server keeps replays only for a while; after that it reports that the replay is not available.

Matches with a replay carry a **Replay** badge, and the match page shows a **Report** button.

The command line works too and parses in full right away (re-importing replaces that replay's data):

```powershell
.\.venv\Scripts\python -m wt_plotter import-replay "D:\WarThunder\Replays"
.\.venv\Scripts\python -m wt_plotter download-replay 72c412c1002817ae
```

## Linking to recorded matches

1. The session id was imported before → reuse that match.
2. Otherwise pick the finished match whose start is within 120 seconds of the replay start and that is not linked to another session (an 8111 recording).
3. Otherwise create a finished match. Its map comes from the level name (`<level>_tankmap` for ground battles, `<level>_map` or the level name for air battles).

When the replay runs longer than the recording (server replays), the match end time moves to the replay end.

## Replay tracks

Replays are turned into unit tracks and stored as the same ticks and positions as an 8111 recording, so the viewer plays them back directly. The replay author is **me**, real squadmates are **squad**, everyone else is ally or enemy by team. The kill log also goes into the battle feed.

- **Air battles** (battle class not `air_ground_*`): one track per aircraft, including the author's own and AI aircraft (type 2).
- **Ground battles** (`air_ground_*`): tracks for every ground unit (ground sync messages) and for aircraft flown by players (type 2). Units are sampled at different moments, so they are interpolated onto 1-second frames; gaps longer than 15 seconds are left empty. Ground units use the medium tank icon. Units with no owner that never move (less than 30 m in a life) are static map objects and are not drawn. Ground battle playbacks rebuilt from replays also draw aircraft on the ground map (8111 ground recordings do not).
- Tracks are written only for matches **without 8111 positions**; recorded matches are left alone. Replay-written tracks can be replaced by a server replay (whole battle), never the other way round.
- A server replay does not know who recorded it, so it reuses the author of the local replay of the same session; with neither, team 1 is treated as allies.
- Positions carry the player name and vehicle (shown on hover in the viewer): the vehicle reported when that life fired, or the player's only known vehicle (including server lineups) when it never fired; AI units have no name.
- A destroyed unit is cut at its death: falling wrecks in air battles and wrecks sitting in place in ground battles are not drawn. When the same unit id reappears after a gap or away from the wreck, that is a new life after respawn.
- **Map bounds**: placing world coordinates on the minimap needs the map's world bounds. 8111's `map_info.json` reports them (`map_min` / `map_max`); capture stores them per map in the `map_bounds` table. Once a map has been captured, replays on that map draw over the map image. Until then the match shows no map image and the tracks fill the canvas by their own extent. Re-import from the command line after capturing the map to get the image.
- Orientation: map x grows with world x to the right; map y grows upward with world z (image y points down). Checked against 8111 recordings of 3 air and 10 ground battles.

Known limits:

- Unit ids are reused; ownership is decided per "life" (see below). Aircraft not owned by a player (AI) are numbered in runs per team: one shot down by a player belongs to the killer's opponent, a run shares one team, and a run without evidence takes the opposite of the adjacent run. Units whose team is still unknown (mostly respawned ground vehicles that never fired) join the nearest known team by their start point. Against 8111 colors, about 96–99% (ground) and 92–95% (air) of matched positions get the right relation.
- The author's own tank is marked **me** only in the lives whose owner is known.

## File format

A `.wrpl` holds a header, a settings BLK, a zstd packet stream and a results BLK. The code is in `wt_plotter/replay/`; key points (verified on version 101421):

| Offset | Content |
| :--- | :--- |
| 0 | Magic `E5 AC 00 10` |
| 8 / 136 / 396 | Level, mission file, mission name (fixed C strings) |
| 684 | Results BLK offset (u32, 0 when absent) |
| 732 | Session id (u64) |
| 740 | Server part number; 742 is `0x5A` for server replays |
| 748 | Settings BLK size (u16) |
| 908 | Start time (Unix seconds) |
| 968 | Battle class, e.g. `air_ground_Dom` (ground) or `base_dom` (air) |
| 1234 | Settings BLK, then the zstd packet stream up to the results BLK |

- **BLK**: FAT format with first byte `0x01`: name table, parameter data, parameter table (u32 name id and type, u32 value or offset), block table (name id, parameter count, child count, first child).
- **Packet stream**: each packet is a size prefix plus payload. The prefix's high bits give its length (`10` one byte, `01` two, `001` three, `0001` four, `0000` followed by a u32). The first payload byte is the type; without the `0x10` flag a u32 timestamp in 1/256 ms follows, with the flag the previous timestamp applies.
- **Type 3**: chat: flag byte, sender, text (each with a one-byte length), channel.
- **Type 4**: game messages. The first 5 bytes are a signature (`00 02 58` + the low byte of the message id + `F0`/`F1`). Most messages are **field-serialized**: a u16 byte offset of the size table, a varint field bit mask, the field data (an MSB-first bit stream), then the size table (a 3-bit header per field: 1/8/16/32/64/96/128 bits, 0 means a varint bit count follows). Unit ids are the low 11 bits of a u16; `7FF` means none.
  - `00 02 58 58` kill: field 1 killer slot (u32, `FFFFFFFF` for none), 2 killer vehicle, 3 victim unit id, 4 killer unit id, 10 weapon.
  - `00 02 58 57` severe damage: field 1 target unit id, 2 attacker slot, 3 attacker vehicle, 4 attacker unit id.
  - Player records (possibly inside embedded zstd blocks): slot, `70`, two bytes, `30 60`, userId (u32), four zero bytes, name.
- **Server parts**: part 0 carries the settings; odd parts continue the packet stream, even parts are seek snapshots and are skipped; the last part carries the final results.

Unit-to-player mapping comes from the acting side of kill and severe-damage messages (slot + unit id). Unit ids are reused: after a vehicle is destroyed the same id may go to another player's next vehicle, so each id is split into "lives" at its death times and ownership is only inferred within one life. Every player's first vehicle has unit id = slot + a fixed offset (throughout the battle in air battles), which fills in first lives that never fired. Player vehicles come from the same messages plus the lineups listed in server results.

- **Type 2 (aircraft state)**: after the first byte, an **MSB-first** bit-packed entry list. Each entry starts with one bit: 1 means a varint unit id follows (low 11 bits), 0 means the previous id plus one; `7FF` ends the list. Then come an "id only" flag, a few flags and a count table, the position (3 little-endian float32: x, altitude, z), packed Euler angles, and variable-length engine, sensor, countermeasure and target tables (skipped when parsing). The author's own aircraft is included.
- `00 02 58 73` / `00 02 58 74` ground sync (client / server replay): after the signature, a varint bit length and a bit-stream body holding a unit id range (two u16), sync time and sequence, then per unit a set of flags, a packet number and a state body. A state body is either full or a delta against one of 32 history slots (2-bit RLE, then XOR with the base). The position inside is 3 float32 or two quantized u32 (22 bits each for x and z, covering ±36000 m). Server replays skip the even parts, so deltas whose base is missing are dropped.

The type 2 entry, ground sync, field serialization and kill field layouts follow [WTACRP](https://github.com/ShioUmiusi/WTACRP)'s (MIT) write-up of the wrpl-acmi parser; this project implements them from the format description.
