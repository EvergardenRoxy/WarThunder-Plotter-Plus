import json
import re

import pytest

from wt_plotter.i18n import load_catalog
from wt_plotter.storage import db

from test_routes import MAP_HASH, app, client, conn


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_pages_render_both_languages(client, conn, lang):
    ended = db.start_match(conn, MAP_HASH)
    db.end_match(conn, ended)
    active = db.start_match(conn, MAP_HASH)
    assert client.post("/api/language", json={"language": lang}).status_code == 204
    for path in ("/", "/live", f"/match/{active}", f"/match/{ended}"):
        response = client.get(path)
        assert response.status_code == 200
        assert f'<html lang="{lang}">' in response.text
        if lang == "zh":
            assert load_catalog(lang)["nav.matches"] in response.text


def test_i18n_injected(client):
    response = client.get("/")
    match = re.search(r"window\.I18N\s*=\s*(\{.*?\})\s*;", response.text, re.DOTALL)
    assert match
    assert json.loads(match.group(1)).keys() == load_catalog("en").keys()
