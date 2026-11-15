"""审查复现：断言当前缺陷表现，不是修复后的回归测试。只使用临时数据库。"""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from wt_plotter.capture.capturer import Capturer
from wt_plotter.capture.tracker import MatchTracker
from wt_plotter.storage import db
from wt_plotter.web.app import create_app
from wt_plotter import cli


def obj(x, y, kind="ground_model"):
    return dict(x=x, y=y, type=kind, icon="Tank", color="#fa0C00")


with TemporaryDirectory(prefix="wt-review-") as directory:
    root = Path(directory)
    with closing(db.connect(root / "poi.db")) as conn:
        tracker = MatchTracker(conn, lambda: None, root / "maps")
        zone = obj(.2, .3, "capture_zone")
        tracker.tick(0, True, {"army": "tank"}, [zone])
        tracker.tick(1, True, {"army": "tank"}, [zone, obj(.7, .8, "respawn_base_tank")])
        bundle = db.get_positions_bundle(conn, tracker.match_id, 0)
        assert not any(p["type"] == "respawn_base_tank" for p in bundle["positions"])
        print("late_respawn: 0 respawn rows after respawn appeared")

    with closing(db.connect(root / "transform.db")) as conn:
        tracker = MatchTracker(conn, lambda: None, root / "maps")
        points = [(.2, .2), (.4, .3), (.6, .7), (.8, .5)]
        ground = [obj(x, y, "capture_zone") for x, y in points]
        air = [obj(.25*x+.1, .25*y+.2, "capture_zone") for x, y in points]
        tracker.tick(0, True, {"army": "tank"}, ground)
        tracker.tick(1, True, {"army": "air"}, air)
        tracker.tick(2, True, {"army": "tank"}, ground)
        bundle = db.get_positions_bundle(conn, tracker.match_id, 2000)
        assert bundle["ticks"][0]["is_player_air"] == 0
        assert bundle["ticks"][0]["is_player_air_view"] == 1
        last = bundle["positions"][-1]
        assert last["x"] == .8 and last["x_ground"] == 2.8
        print("ground_return: x=0.8 transformed to x_ground=2.8; ground tick marked air view")

    path = root / "multi.db"
    client = Mock()
    client.fetch_map_info.return_value = {"valid": True}
    client.fetch_map_image.return_value = None
    client.fetch_indicators.return_value = {"army": "tank"}
    client.fetch_objects.return_value = [obj(.3, .4)]
    first = Capturer(path, root / "maps", client)
    second = Capturer(path, root / "maps", client)
    first.run_once(0)
    with closing(db.connect(path)) as conn:
        first_id = db.get_active_match(conn).id
    second.run_once(1)
    first.run_once(2)
    with closing(db.connect(path)) as conn:
        assert db.get_match(conn, first_id).ended_at is not None
        assert db.count_positions(conn, first_id) == 2
        print("multiple_capturers: second closes first match; first still writes to ended match")
    first.stop()
    second.stop()

    path = root / "status.db"
    with closing(db.connect(path)) as conn:
        match_id = db.start_match(conn, "")
        db.add_tick(conn, match_id, db.TickRecord(0, "air", "test_plane", 1, 1),
                    [db.PositionRecord(.3, .4, "#fff", "aircraft", "player", 0)])
    app = create_app(path, root / "maps", root / "settings.json", None)
    status = app.test_client().get("/api/status").json
    assert status["army_type"] == "tank" and status["vehicle_type"] == "test_plane"
    print("serve_status: air tick reported as tank with vehicle test_plane")

    with patch.object(cli, "another_instance_running", return_value=True), \
         patch.object(cli.webbrowser, "open"), patch.object(cli, "Capturer") as capture:
        cli._run_web_mode("127.0.0.1", 5000, capture_enabled=True)
        capture.assert_not_called()
        print("serve_then_watch: existing HTTP listener prevents starting capture")
