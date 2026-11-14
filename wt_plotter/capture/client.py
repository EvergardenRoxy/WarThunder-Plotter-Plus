import requests

from wt_plotter.config import CAPTURE_ENDPOINTS, CAPTURE_TIMEOUTS


class TelemetryClient:
    def __init__(self):
        self.session = requests.Session()

    def _get(self, url: str, timeout: float) -> requests.Response | None:
        try:
            response = self.session.get(url, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout):
            return None
        return response if response.status_code == 200 else None

    def fetch_map_info(self) -> dict | None:
        response = self._get(CAPTURE_ENDPOINTS.map_info_url, CAPTURE_TIMEOUTS.async_map_info)
        return response.json() if response is not None else None

    def fetch_indicators(self) -> dict | None:
        response = self._get(CAPTURE_ENDPOINTS.indicators_url, CAPTURE_TIMEOUTS.async_indicators)
        return response.json() if response is not None else None

    def fetch_objects(self) -> list[dict] | None:
        response = self._get(CAPTURE_ENDPOINTS.map_obj_url, CAPTURE_TIMEOUTS.async_map_obj)
        if response is None:
            return None
        data = response.json()
        return data if isinstance(data, list) else None

    def fetch_map_image(self) -> bytes | None:
        response = self._get(CAPTURE_ENDPOINTS.map_img_url, CAPTURE_TIMEOUTS.map_image)
        return response.content if response is not None else None
