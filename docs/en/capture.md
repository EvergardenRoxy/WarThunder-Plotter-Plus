[← Back to README](../../README.md) · [简体中文](../zh/capture.md)

# Capture and map recognition

Every 0.2 seconds the program reads the game client's local interface at `http://127.0.0.1:8111` (the built-in web map) and stores the unit positions shown on the minimap. There is nothing to set up in the game and nothing to start or stop by hand.

## When a match starts and ends

- **Start**: a match is created when the interface reports a valid map (you are in a battle and can see the minimap). The minimap image is saved at the same time.
- **End**: the map has been invalid for 20 seconds (you are back in the hangar), the map changed to a different one, or the program quit.
- **Test drives and the firing range** are recorded as matches too. Delete them from the match list if you do not want them.
- A match left open by a crash is closed the next time capture starts.

Only one program can capture into a data folder at a time. A second capturing instance exits with an error. `serve` mode does not capture and can run alongside.

## What is recorded

- **Unit positions**: coordinates, color (team), type and icon (unit class) of every minimap marker.
- **Capture zones and respawns**: capture zones are stored every time, so ownership changes can be shown. Respawns and airfields are stored once per location.
- **Your own vehicle**: ground or air, and the model. The game interface does not give other players' models, only their class.
- **Battle feed**: kills, shoot-downs, fires, awards, disconnects and similar messages, saved as the game shows them in its current language.

Enemy units appear on the minimap only while your team has spotted them, so enemy trails have gaps. That is a limit of the game itself.

## Flying in a ground battle

When you switch to an aircraft in a ground battle, the game's minimap changes to a larger air map. The program then:

1. saves the air map as well;
2. uses markers visible on both maps to work out how air-map coordinates convert to ground-map coordinates;
3. stores both the raw and the converted coordinates for ground units seen from the air.

This keeps ground trails in place on the ground map while you fly. The conversion needs at least 3 markers that can be paired. Without it, data from that air view is shown on the air map only.

If the ground map is replaced by the air map of the same location, the match is flagged as having had a nuke.

## Map recognition

The program computes a perceptual hash (dHash) of the minimap image and compares it with the built-in map table. An exact match, or a difference of 42 bits or fewer, counts as the same map. The result gives the map name and the battle type (ground, air or naval).

On combined maps an air battle starts with the game reporting the ground map, so these matches are classified by the first sortie: if you first spawn in an aircraft, the match is shown as an air battle.

### Unrecognized maps

When the game updates a map, the minimap image changes, the hash no longer matches, and the match is shown as "Unknown Map". Trails are recorded as usual; only the name is missing. In that case:

- the minimap image is saved in `data/maps/` under its hash;
- `data/missing_map_hashes.log` records the hash and the closest known map.

Send the hash and the map it belongs to to the developer, or add it to the map table yourself (see the [development guide](development.md#adding-maps)), and the next version will recognize it. The most reliable way to tell which map an image is: check the game replay of the same match (`.wrpl` files in the `Replays` folder carry the level name near the start of the file).

## Battle feed

The feed comes from the `/hudmsg` endpoint and matches the messages scrolling in the top right of the game screen. The first batch received in each match is only used to find the starting point (it may hold messages from the previous match); everything after it is saved. If the endpoint is unavailable there is simply no feed, and trails are still captured.

When a player disconnects, the game also sends an untranslated raw message (`…NET_PLAYER_DISCONNECT_FROM_GAME`). It is kept in the database and hidden in the viewer.
