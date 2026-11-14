from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from wt_plotter.capture.tracker import MatchTracker
from wt_plotter.storage import db


UPSTREAM_DATA = Path(__file__).resolve().parents[2] / "reference" / "upstream" / "data"
REPLAYS = sorted((UPSTREAM_DATA / "raw").glob("match_*.json"))


@pytest.mark.parametrize("path", REPLAYS, ids=[path.stem for path in REPLAYS])
def test_replay_matches_upstream(path, conn, map_png, tmp_path):
    recording = json.loads(path.read_text(encoding="utf-8"))
    responses = recording["raw_responses"]
    indicators = {
        item["timestamp"]: item["data"] for item in responses if item["endpoint"] == "indicators"
    }
    image = map_png("avg_normandy_tankmap")
    tracker = MatchTracker(conn, lambda: image, tmp_path / "maps")
    for item in sorted(responses, key=lambda response: response["timestamp"]):
        if item["endpoint"] == "map_obj.json":
            timestamp = item["timestamp"]
            tracker.tick(1000 + timestamp, True, indicators.get(timestamp), item["data"])
    match_id = tracker.match_id
    assert match_id is not None
    tracker.end_match()

    upstream_id = recording["match_id"]
    upstream_uri = (UPSTREAM_DATA / "matches.db").as_uri() + "?mode=ro"
    with closing(sqlite3.connect(upstream_uri, uri=True)) as upstream:
        for table in ("ticks", "positions"):
            query = f"SELECT COUNT(*) FROM {table} WHERE match_id = ?"
            actual_count = conn.execute(query, (match_id,)).fetchone()[0]
            expected_count = upstream.execute(query, (upstream_id,)).fetchone()[0]
            assert actual_count == expected_count, table
        transform = upstream.execute(
            "SELECT air_transform_a, air_transform_b, air_transform_c, air_transform_d FROM matches WHERE id = ?",
            (upstream_id,),
        ).fetchone()
    if transform[0] is not None:
        match = db.get_match(conn, match_id)
        assert (match.air_transform_a, match.air_transform_b, match.air_transform_c, match.air_transform_d) == (
            pytest.approx(transform, abs=1e-6, rel=0)
        )
