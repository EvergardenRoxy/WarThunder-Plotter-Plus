[← Back to README](../../README.md) · [简体中文](../zh/viewer.md)

# Match viewer

Matches in the navigation bar lists every recorded match; click one to open its replay. Live shows the match in progress. Both pages share the same map and sidebar.

![Ground battle replay](../images/match_ground.png)

## Reading the map

- **Color is the team**: yellow is you, green is your squad, blue is allies, red is enemies, gray is everything else.
- **Shape is the unit class**: diamond for light tanks, circle for medium tanks, square for heavy tanks, triangle for tank destroyers, crossed circle for SPAA, pentagon for wheeled vehicles and IFVs, arrow for aircraft (fighters, attackers and bombers in growing size). You are a dot with a white ring. The sidebar has a legend.
- **Lines are trails**: drawn back from the current position and fading with age. Arrows point along the last piece of the trail.
- **× marks a crew knock-out.** The viewer uses interrupted trails to place these marks for you, your squad and allies.
- **Large circles are capture zones**, colored by current owner (blue, red, or white for neutral). **Small squares are respawns.**
- Hover over a unit to see its class. Hovering over yourself also shows your vehicle model.

Artillery, pillboxes, ships and fixed air defence are not shown yet.

Enemy units are on the minimap only while spotted. One that reappears within 6 seconds rejoins its old trail, with no line drawn across the gap. An enemy that disappears is not necessarily dead, so enemies get no ×.

## Replay

The playback bar is under the map:

- **Play / Pause**: playback stops at the end. Pressing Play at the end restarts from the beginning.
- **Timeline**: drag to any moment.
- **Speed** has 11 steps from 0.5× to 50×, with 10× selected by default.

On the map, scroll to zoom (50%–500%), drag to pan, and double-click to reset. The zoom buttons sit at the lower right of the map.

## Sidebar settings

| Setting | Notes |
| --- | --- |
| Trail duration | 10, 30, 60 or 120 seconds, or all. The default is 30 seconds. Older segments fade in every mode. |
| Blip size | 0.25–1.5, default 0.5 |
| Line width | 0.5×–2×, default 1 |
| Filters | Show or hide each team, capture zones and respawns |

These settings and the playback speed are saved in the browser and are still there next time. A different browser, or clearing site data, brings back the defaults.

Map display controls stay at the top of the sidebar. Choose **You and squad** for a focused view. Expand **Advanced display** to adjust line width and marker size or see the unit legend and statistics.

In live view and replay, **Show all teammate death locations** keeps squad and allied crew knockout markers on the selected map after their trails fade. The squad and ally filters still apply. Hover over a × marker to see the unit type. The **My vehicle** label beside the map title shows your vehicle at the current timeline position.

## Ground map and air map

A ground battle in which you flew has two maps. Switch between them under **Map display**.

- **Ground map**: ground units. Units seen from the air are drawn here with converted coordinates.
- **Air map**: a larger area, showing only data from the time you spent in the air, aircraft included.

A match whose first sortie was an aircraft (an air battle) opens on the air map.

![Air battle replay](../images/match_air.png)

## Battle feed

The battle feed shows every recorded message, newest first, in a scrollable list below the map display controls. Select a message to pause and seek to its timestamp. Enable **Auto-scroll** to follow playback or clear it to scroll manually. Marks under the timeline show when messages arrived.

Matches recorded before 0.4.0 have no feed.

## Live match

If no match is in progress, the Live page waits and refreshes when one starts. During a battle it follows the newest moment and checks for updates every 0.5 seconds.

Drag the timeline back to inspect an earlier moment. The map stays at the selected time and the feed continues receiving messages. Select **Play** or press Space to resume or select **Back to live** to jump directly to the latest moment.

When the match ends, the badge changes to **Ended**. If you are rewound, the page stays on that match until you return to live. If the capture program stops, **Capture stopped** appears above the map.

## Match list

Matches are grouped by their local start date, newest first. Combine the map name, start date and battle type filters to find a match. Each row shows its stable number, start time, duration and map. Use the bin button to delete a finished match and its positions and feed.
