from pathlib import Path

import pytest
from starlette.testclient import TestClient

from stillhem.admin.app import create_app
from stillhem.auth import is_password_set


@pytest.fixture
def fresh_app(db_path: Path):
    # db_path is initialized by the conftest fixture but no password is set
    assert not is_password_set(db_path)
    return create_app(db_path=db_path)


@pytest.fixture
def fresh_client(fresh_app):
    return TestClient(fresh_app)


def test_get_setup_renders_form_when_no_password(fresh_client: TestClient) -> None:
    resp = fresh_client.get("/setup")
    assert resp.status_code == 200
    assert 'name="password"' in resp.text
    assert 'name="confirm"' in resp.text


def test_post_setup_valid_saves_password_and_redirects(
    fresh_client: TestClient, db_path: Path
) -> None:
    resp = fresh_client.post(
        "/setup",
        data={"password": "secret123", "confirm": "secret123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"
    assert is_password_set(db_path)


def test_post_setup_mismatched_passwords_shows_error(fresh_client: TestClient) -> None:
    resp = fresh_client.post(
        "/setup",
        data={"password": "secret123", "confirm": "different"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "Passwords do not match" in resp.text


def test_post_setup_short_password_shows_error(fresh_client: TestClient) -> None:
    resp = fresh_client.post(
        "/setup",
        data={"password": "ab", "confirm": "ab"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "at least 5" in resp.text


def test_post_setup_when_already_configured_redirects_to_login(
    fresh_client: TestClient, db_path: Path
) -> None:
    fresh_client.post(
        "/setup", data={"password": "secret123", "confirm": "secret123"}
    )
    resp = fresh_client.post(
        "/setup",
        data={"password": "newpass", "confirm": "newpass"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"
