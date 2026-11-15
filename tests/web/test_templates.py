import json
import re

import pytest

from wt_plotter.i18n import LANGUAGES, language_names, load_catalog
from wt_plotter.storage import db

from test_routes import MAP_HASH, app, client, conn


@pytest.mark.parametrize("lang", LANGUAGES)
def test_pages_render_every_language(client, conn, lang):
    ended = db.start_match(conn, MAP_HASH)
    db.end_match(conn, ended)
    active = db.start_match(conn, MAP_HASH)
    assert client.post("/api/language", json={"language": lang}).status_code == 204
    for path in ("/", "/live", f"/match/{active}", f"/match/{ended}"):
        response = client.get(path)
        assert response.status_code == 200
        assert f'<html lang="{lang}">' in response.text
        assert load_catalog(lang)["nav.matches"] in response.text
        # 下拉框列出每种语言的自称。
        for code, name in language_names().items():
            assert re.search(rf'<option value="{code}"[^>]*>{name}</option>', response.text)


def test_i18n_injected(client):
    response = client.get("/")
    match = re.search(r"window\.I18N\s*=\s*(\{.*?\})\s*;", response.text, re.DOTALL)
    assert match
    assert json.loads(match.group(1)).keys() == load_catalog("en").keys()
