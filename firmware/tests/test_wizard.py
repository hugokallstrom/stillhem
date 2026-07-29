from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from stillhem.admin.app import create_app
from stillhem.auth import is_password_set
from stillhem.blocklist import list_domains
from stillhem.db import get_config


@pytest.fixture
def setup_client(db_path: Path):
    return TestClient(create_app(db_path=db_path, setup_mode=True))


@pytest.fixture
def normal_client(db_path: Path):
    from stillhem.auth import set_password
    set_password("done", db_path)  # a configured device has a password
    return TestClient(create_app(db_path=db_path, setup_mode=False))


@pytest.fixture
def no_wifi():
    """Ethernet-only hardware, as netmode records it at boot (e.g. Pi B+)."""
    with patch("stillhem.admin.routes.wizard_routes.netmode.wifi_present",
               return_value=False):
        yield


def test_captive_probe_redirects_to_wizard(setup_client):
    resp = setup_client.get("/generate_204", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard"


def test_wizard_index_sends_browser_to_first_step(setup_client):
    resp = setup_client.get("/wizard", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/wifi"


def test_wizard_starts_at_preset_without_wifi_hardware(setup_client, no_wifi):
    # No radio means no network to choose: the Wi-Fi step is skipped entirely.
    resp = setup_client.get("/wizard", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/preset"


def test_wifi_page_bounces_to_preset_without_wifi_hardware(setup_client, no_wifi):
    resp = setup_client.get("/wizard/wifi", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/preset"


def test_finish_without_wifi_hardware_skips_profile_save(setup_client, db_path, no_wifi):
    from stillhem.auth import set_password
    from stillhem.db import set_config
    set_config(db_path, "wizard_preset", "social_only")  # no home_wifi_ssid ever set
    set_password("hunter2", db_path)
    with patch("stillhem.admin.routes.wizard_routes.netmode.save_home_wifi") as save, \
         patch("stillhem.admin.routes.wizard_routes.netmode.mark_setup_complete") as mark, \
         patch("stillhem.admin.routes.wizard_routes.delete_config") as purge, \
         patch("stillhem.admin.routes.wizard_routes.subprocess.Popen") as popen:
        resp = setup_client.post("/wizard/finish", follow_redirects=False)
    # nmcli would fail against a wlan0 that does not exist.
    save.assert_not_called()
    # No profile saved means no PSK to purge — the DB is left untouched.
    purge.assert_not_called()
    mark.assert_called_once()
    popen.assert_called_once()
    assert resp.status_code == 200


def test_wifi_page_lists_cached_networks(setup_client):
    with patch("stillhem.admin.routes.wizard_routes.netmode.read_cached_scan",
               return_value=[{"ssid": "HomeNet", "signal": 80, "secured": True}]):
        resp = setup_client.get("/wizard/wifi")
    assert resp.status_code == 200
    assert "HomeNet" in resp.text


def test_wifi_submit_saves_profile_and_advances(setup_client, db_path):
    with patch("stillhem.admin.routes.wizard_routes.netmode.save_home_wifi") as save:
        resp = setup_client.post("/wizard/wifi",
                                 data={"ssid": "HomeNet", "password": "s3cret"},
                                 follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/preset"
    save.assert_not_called()
    assert get_config(db_path, "home_wifi_ssid") == "HomeNet"
    assert get_config(db_path, "home_wifi_psk") == "s3cret"


def test_wifi_submit_prefers_manual_ssid(setup_client, db_path):
    with patch("stillhem.admin.routes.wizard_routes.netmode.save_home_wifi") as save:
        resp = setup_client.post(
            "/wizard/wifi",
            data={"ssid": "", "ssid_manual": "HiddenNet", "password": "pw"},
            follow_redirects=False)
    assert resp.status_code == 302
    save.assert_not_called()
    assert get_config(db_path, "home_wifi_ssid") == "HiddenNet"
    assert get_config(db_path, "home_wifi_psk") == "pw"


def test_wifi_submit_rejects_empty_ssid(setup_client):
    resp = setup_client.post("/wizard/wifi", data={"ssid": "", "ssid_manual": "  ", "password": ""},
                             follow_redirects=False)
    assert resp.status_code == 200
    assert "choose or enter" in resp.text.lower()


def test_preset_submit_imports_and_advances(setup_client, db_path):
    from stillhem.db import set_config
    set_config(db_path, "home_wifi_ssid", "HomeNet")  # wifi step already done
    with patch("stillhem.admin.routes.wizard_routes.reload_dns"):
        resp = setup_client.post("/wizard/preset", data={"preset": "social_only"},
                                 follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/password"
    assert get_config(db_path, "wizard_preset") == "social_only"
    assert any(d["domain"] == "instagram.com" for d in list_domains(db_path))


def test_preset_rejects_unknown(setup_client, db_path):
    from stillhem.db import set_config
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    resp = setup_client.post("/wizard/preset", data={"preset": "bogus"}, follow_redirects=False)
    assert resp.status_code == 200


def test_password_submit_sets_password_and_advances(setup_client, db_path):
    from stillhem.db import set_config
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    set_config(db_path, "wizard_preset", "social_only")
    resp = setup_client.post("/wizard/password",
                             data={"password": "hunter2", "confirm": "hunter2"},
                             follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/done"
    assert is_password_set(db_path)


def test_password_submit_rejects_mismatch(setup_client, db_path):
    from stillhem.db import set_config
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    set_config(db_path, "wizard_preset", "social_only")
    resp = setup_client.post("/wizard/password",
                             data={"password": "hunter2", "confirm": "nope"},
                             follow_redirects=False)
    assert resp.status_code == 200
    assert not is_password_set(db_path)


def test_wizard_step_guard_snaps_forward(setup_client):
    # Landing on /wizard/preset before wifi is done bounces back to wifi.
    resp = setup_client.get("/wizard/preset", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/wifi"


def test_finish_schedules_reboot(setup_client, db_path):
    from stillhem.db import set_config
    from stillhem.auth import set_password
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    set_config(db_path, "home_wifi_psk", "pw")
    set_config(db_path, "wizard_preset", "social_only")
    set_password("hunter2", db_path)
    with patch("stillhem.admin.routes.wizard_routes.netmode.save_home_wifi") as save, \
         patch("stillhem.admin.routes.wizard_routes.netmode.mark_setup_complete") as mark, \
         patch("stillhem.admin.routes.wizard_routes.subprocess.Popen") as popen:
        resp = setup_client.post("/wizard/finish", follow_redirects=False)
    save.assert_called_once_with("HomeNet", "pw")
    mark.assert_called_once()
    popen.assert_called_once()
    assert resp.status_code in (200, 302)


def test_finish_purges_plaintext_psk_from_db(setup_client, db_path):
    from stillhem.db import set_config
    from stillhem.auth import set_password
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    set_config(db_path, "home_wifi_psk", "s3cret")
    set_config(db_path, "wizard_preset", "social_only")
    set_password("hunter2", db_path)
    with patch("stillhem.admin.routes.wizard_routes.netmode.save_home_wifi"), \
         patch("stillhem.admin.routes.wizard_routes.netmode.mark_setup_complete"), \
         patch("stillhem.admin.routes.wizard_routes.subprocess.Popen"):
        setup_client.post("/wizard/finish", follow_redirects=False)
    # PSK must not linger in the DB once NetworkManager owns the profile.
    assert get_config(db_path, "home_wifi_psk") is None
    # SSID is non-sensitive and still shown on the done page.
    assert get_config(db_path, "home_wifi_ssid") == "HomeNet"


def test_finish_guard_redirects_when_incomplete(setup_client, db_path):
    from stillhem.db import set_config
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    with patch("stillhem.admin.routes.wizard_routes.subprocess.Popen") as popen:
        resp = setup_client.post("/wizard/finish", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/preset"
    popen.assert_not_called()


def test_normal_mode_wizard_redirects_home(normal_client):
    resp = normal_client.get("/wizard/wifi", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
