import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import stillhem.netmode as netmode


def _completed(stdout=""):
    return MagicMock(stdout=stdout, returncode=0)


def test_home_wifi_configured_true_for_non_ap_wifi_profile():
    out = "Stillhem Setup:802-11-wireless\nHomeNet:802-11-wireless\n"
    with patch("subprocess.run", return_value=_completed(out)) as run:
        assert netmode.home_wifi_configured() is True
    args = run.call_args[0][0]
    assert args[:2] == ["nmcli", "-t"]


def test_home_wifi_configured_false_when_only_ap_profile():
    out = "Stillhem Setup:802-11-wireless\nWired connection 1:802-3-ethernet\n"
    with patch("subprocess.run", return_value=_completed(out)):
        assert netmode.home_wifi_configured() is False


def test_should_enter_setup_false_when_wired_connected():
    def fake_run(args, **kw):
        if "connection" in args:
            return _completed("Stillhem Setup:802-11-wireless\n")  # no home wifi
        return _completed("eth0:ethernet:connected\nwlan0:wifi:disconnected\n")
    with patch("subprocess.run", side_effect=fake_run):
        assert netmode.should_enter_setup() is False


def test_should_enter_setup_true_when_nothing_connected():
    def fake_run(args, **kw):
        if "connection" in args:
            return _completed("Stillhem Setup:802-11-wireless\n")  # no home wifi
        return _completed("wlan0:wifi:disconnected\neth0:ethernet:unavailable\n")
    with patch("subprocess.run", side_effect=fake_run):
        assert netmode.should_enter_setup() is True


def test_scan_networks_parses_dedupes_and_sorts():
    out = "\n".join([
        "42:WPA2:HomeNet",
        "88:WPA2:HomeNet",   # duplicate, stronger signal wins
        "17:--:OpenCafe",
        "0::",               # empty ssid dropped
    ]) + "\n"
    with patch("subprocess.run", return_value=_completed(out)):
        nets = netmode.scan_networks()
    assert nets == [
        {"ssid": "HomeNet", "signal": 88, "secured": True},
        {"ssid": "OpenCafe", "signal": 17, "secured": False},
    ]


def test_start_ap_issues_expected_nmcli_calls():
    with patch("subprocess.run", return_value=_completed()) as run:
        netmode.start_ap()
    calls = [c.args[0] for c in run.call_args_list]
    assert calls[0][:6] == ["nmcli", "connection", "add", "type", "wifi", "ifname"]
    assert "ap" in calls[1] and "shared" in calls[1]
    assert calls[2] == ["nmcli", "connection", "up", "Stillhem Setup"]


def test_save_home_wifi_sets_psk_when_present():
    with patch("subprocess.run", return_value=_completed()) as run:
        netmode.save_home_wifi("HomeNet", "s3cret")
    calls = [c.args[0] for c in run.call_args_list]
    assert calls[0][:3] == ["nmcli", "connection", "add"]
    assert "wifi-sec.psk" in calls[1] and "s3cret" in calls[1]


def test_save_home_wifi_open_network_skips_psk():
    with patch("subprocess.run", return_value=_completed()) as run:
        netmode.save_home_wifi("OpenCafe", "")
    calls = [c.args[0] for c in run.call_args_list]
    assert len(calls) == 1  # only the add, no wifi-sec modify


def test_read_mode_defaults_to_setup_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "MODE_PATH", tmp_path / "mode")
    assert netmode.read_mode() == "setup"


def test_write_then_read_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "STATE_DIR", tmp_path)
    monkeypatch.setattr(netmode, "MODE_PATH", tmp_path / "mode")
    netmode.write_mode("normal")
    assert netmode.read_mode() == "normal"


def test_cache_and_read_scan_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "STATE_DIR", tmp_path)
    monkeypatch.setattr(netmode, "SCAN_CACHE_PATH", tmp_path / "wifi_scan.json")
    nets = [{"ssid": "HomeNet", "signal": 88, "secured": True}]
    netmode.cache_scan(nets)
    assert netmode.read_cached_scan() == nets


def test_boot_normal_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "STATE_DIR", tmp_path)
    monkeypatch.setattr(netmode, "MODE_PATH", tmp_path / "mode")
    with patch.object(netmode, "should_enter_setup", return_value=False):
        netmode.boot()
    assert netmode.read_mode() == "normal"


def test_boot_setup_brings_up_ap_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "STATE_DIR", tmp_path)
    monkeypatch.setattr(netmode, "MODE_PATH", tmp_path / "mode")
    monkeypatch.setattr(netmode, "SCAN_CACHE_PATH", tmp_path / "wifi_scan.json")
    with patch.object(netmode, "should_enter_setup", return_value=True), \
         patch.object(netmode, "scan_networks", return_value=[{"ssid": "X", "signal": 1, "secured": False}]), \
         patch.object(netmode, "start_ap") as start:
        netmode.boot()
    start.assert_called_once()
    assert netmode.read_mode() == "setup"
    assert netmode.read_cached_scan() == [{"ssid": "X", "signal": 1, "secured": False}]
