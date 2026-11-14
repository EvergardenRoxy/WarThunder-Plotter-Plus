from contextlib import closing
from pathlib import Path
from threading import Event, Thread, current_thread
import time

from wt_plotter.capture.client import TelemetryClient
from wt_plotter.capture.tracker import MatchTracker
from wt_plotter.config import CAPTURE_DEFAULTS, CAPTURE_SETTINGS
from wt_plotter.storage import db


class Capturer:
    def __init__(self, db_path: Path, maps_dir: Path, client: TelemetryClient):
        self.db_path = db_path
        self.maps_dir = maps_dir
        self.client = client
        self._stop = Event()
        self._thread: Thread | None = None
        self._tracker: MatchTracker | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def army_type(self) -> str:
        return self._tracker.army_type if self._tracker is not None else CAPTURE_DEFAULTS.army_type

    @property
    def vehicle_type(self) -> str:
        return self._tracker.vehicle_type if self._tracker is not None else CAPTURE_DEFAULTS.vehicle_type

    def start(self) -> None:
        if self.is_running:
            return
        self.stop()
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="WT Plotter Capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self._tracker is not None:
            if self._tracker.match_id is not None:
                with closing(db.connect(self.db_path)) as conn:
                    db.end_match(conn, self._tracker.match_id)
            self._tracker = None

    def _loop(self) -> None:
        with closing(db.connect(self.db_path)) as conn:
            db.close_orphaned_matches(conn)
            self._tracker = MatchTracker(conn, self.client.fetch_map_image, self.maps_dir)
            while not self._stop.is_set():
                self.run_once(time.time())
                self._stop.wait(CAPTURE_SETTINGS.poll_interval)

    def run_once(self, now: float) -> None:
        if current_thread() is self._thread:
            self._capture_tick(now)
            return
        if self.is_running:
            raise RuntimeError("Manual ticks require a stopped capture thread")
        with closing(db.connect(self.db_path)) as conn:
            if self._tracker is None:
                db.close_orphaned_matches(conn)
                self._tracker = MatchTracker(conn, self.client.fetch_map_image, self.maps_dir)
            else:
                self._tracker.conn = conn
            self._capture_tick(now)

    def _capture_tick(self, now: float) -> None:
        map_info = self.client.fetch_map_info()
        map_valid = bool(map_info and map_info.get("valid"))
        indicators = self.client.fetch_indicators() if map_valid else None
        objects = self.client.fetch_objects() if map_valid else None
        self._tracker.tick(now, map_valid, indicators, objects)
