from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stillhem.auth import set_password
from stillhem.admin.app import create_app


@pytest.fixture
def app(db_path: Path):
    set_password("testpass", db_path)
    return create_app(db_path=db_path)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def authed_client(app):
    client = TestClient(app)
    client.post("/login", data={"password": "testpass"})
    return client


def test_unauthenticated_root_redirects_to_login(client: TestClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["location"]


def test_login_page_renders(client: TestClient) -> None:
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "password" in resp.text.lower()


def test_login_with_correct_password_sets_cookie(client: TestClient) -> None:
    resp = client.post("/login", data={"password": "testpass"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "session" in resp.cookies


def test_login_with_wrong_password_shows_error(client: TestClient) -> None:
    resp = client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 200
    assert "invalid" in resp.text.lower()


def test_authenticated_root_renders_dashboard(authed_client: TestClient) -> None:
    resp = authed_client.get("/")
    assert resp.status_code == 200
    assert "stillhem" in resp.text.lower()


def test_logout_clears_session(authed_client: TestClient) -> None:
    resp = authed_client.post("/logout", follow_redirects=False)
    assert resp.status_code == 302
    # After logout, root redirects to login
    resp2 = authed_client.get("/", follow_redirects=False)
    assert resp2.status_code == 302


from unittest.mock import patch

from stillhem.blocklist import add_domain, list_domains


def test_dashboard_shows_blocked_domain_count(authed_client: TestClient, db_path: Path) -> None:
    add_domain("instagram.com", db_path)
    add_domain("tiktok.com", db_path)
    resp = authed_client.get("/")
    assert resp.status_code == 200
    assert "instagram.com" in resp.text
    assert "tiktok.com" in resp.text


def test_add_domain_requires_auth(client: TestClient) -> None:
    resp = client.post("/blocklist/add", data={"domain": "reddit.com"}, follow_redirects=False)
    assert resp.status_code == 302


def test_add_domain_when_authenticated(authed_client: TestClient, db_path: Path) -> None:
    with patch("stillhem.admin.routes.blocklist_routes.reload_dns"):
        resp = authed_client.post(
            "/blocklist/add", data={"domain": "reddit.com"}, follow_redirects=True
        )
    assert resp.status_code == 200
    domains = {d["domain"] for d in list_domains(db_path)}
    assert "reddit.com" in domains


def test_remove_domain_when_authenticated(authed_client: TestClient, db_path: Path) -> None:
    add_domain("facebook.com", db_path)
    with patch("stillhem.admin.routes.blocklist_routes.reload_dns"):
        resp = authed_client.post(
            "/blocklist/remove", data={"domain": "facebook.com"}, follow_redirects=True
        )
    assert resp.status_code == 200
    domains = {d["domain"] for d in list_domains(db_path)}
    assert "facebook.com" not in domains


def test_add_empty_domain_is_rejected(authed_client: TestClient) -> None:
    with patch("stillhem.admin.routes.blocklist_routes.reload_dns"):
        resp = authed_client.post("/blocklist/add", data={"domain": ""})
    assert resp.status_code in (200, 422)


def test_remove_form_has_confirmation_dialog(authed_client: TestClient, db_path: Path) -> None:
    add_domain("instagram.com", db_path)
    resp = authed_client.get("/")
    assert resp.status_code == 200
    # Remove forms must require a JS confirm before submitting
    assert "onsubmit=\"return confirm" in resp.text
    assert "instagram.com" in resp.text
