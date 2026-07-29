from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from stillhem.admin.app import create_app
from stillhem.auth import set_password


@pytest.fixture
def authed_client(db_path: Path):
    set_password("testpass", db_path)
    client = TestClient(create_app(db_path=db_path))
    client.post("/login", data={"password": "testpass"})
    return client


def test_router_page_requires_auth(db_path: Path):
    client = TestClient(create_app(db_path=db_path))
    set_password("testpass", db_path)
    resp = client.get("/router", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["location"]


def test_router_page_shows_ip_and_a_brand(authed_client: TestClient):
    with patch("stillhem.admin.routes.router_routes.primary_ip", return_value="192.168.1.50"):
        resp = authed_client.get("/router")
    assert resp.status_code == 200
    assert "192.168.1.50" in resp.text
    assert "Telia" in resp.text  # at least one per-brand section renders
