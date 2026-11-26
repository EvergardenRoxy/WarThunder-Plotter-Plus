import pytest

from wt_plotter.replay import download


@pytest.mark.parametrize("text", [
    "72c412c1002817ae", "72C412C1002817AE", " 8269755435899688878 ",
    "https://example.com/replay/72c412c1002817ae/",
])
def test_parse_session(text):
    assert download.parse_session(text) == "72c412c1002817ae"


def test_parse_session_rejects_garbage():
    with pytest.raises(ValueError):
        download.parse_session("not-a-session")


class FakeResponse:
    def __init__(self, status, content=b""):
        self.status_code = status
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, parts):
        self.parts = parts
        self.urls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, timeout):
        self.urls.append(url)
        index = len(self.urls) - 1
        return FakeResponse(200, self.parts[index]) if index < len(self.parts) else FakeResponse(404)


def test_download_saves_parts_until_404(tmp_path, monkeypatch):
    session = FakeSession([b"a", b"b"])
    monkeypatch.setattr(download.requests, "Session", lambda: session)
    folder = download.download_server_replay("72c412c1002817ae", tmp_path)
    assert sorted(p.name for p in folder.iterdir()) == ["0000.wrpl", "0001.wrpl"]
    assert session.urls[0].endswith("/72c412c1002817ae/0000.wrpl")
    assert len(session.urls) == 3


def test_download_missing_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(download.requests, "Session", lambda: FakeSession([]))
    with pytest.raises(FileNotFoundError):
        download.download_server_replay("72c412c1002817ae", tmp_path)


def test_download_stops_on_server_error(tmp_path, monkeypatch):
    session = FakeSession([])
    session.get = lambda url, timeout: FakeResponse(500)
    monkeypatch.setattr(download.requests, "Session", lambda: session)
    with pytest.raises(RuntimeError):
        download.download_server_replay("72c412c1002817ae", tmp_path)
