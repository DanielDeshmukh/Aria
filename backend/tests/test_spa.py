from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import DIST, app

pytestmark = pytest.mark.skipif(
    not (DIST / "index.html").exists(),
    reason="frontend not built — run: cd frontend && npm run build",
)

client = TestClient(app)


def test_root_serves_index_html() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert '<div id="root">' in r.text


def test_clean_route_falls_back_to_index() -> None:
    r = client.get("/lens")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_api_route_is_not_swallowed_by_catch_all() -> None:
    assert client.get("/api/health").status_code == 200
