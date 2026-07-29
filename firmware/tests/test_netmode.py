import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def test_should_enter_setup_true_when_no_wifi_device():
    # Ethernet-only hardware (e.g. Pi B+): Ethernet being up must not suppress setup.
    def fake_run(args, **kw):
        if "connection" in args:
            return _completed("")  # no profiles
        return _completed("eth0:ethernet:connected\n")  # no wlan0 at all
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


def test_scan_networks_unescapes_colon_in_ssid():
    # nmcli -t escapes a literal ':' inside a field as '\:'. Because
    # scan_networks splits on ':' with maxsplit=2, the SSID (last field)
    # keeps its escape and must be unescaped back to a real colon.
    out = "90:WPA2:My\\:Net\n"
    with patch("subprocess.run", return_value=_completed(out)):
        nets = netmode.scan_networks()
    assert nets == [
        {"ssid": "My:Net", "signal": 90, "secured": True},
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


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """Redirect every netmode state path at a temp dir."""
    monkeypatch.setattr(netmode, "STATE_DIR", tmp_path)
    monkeypatch.setattr(netmode, "MODE_PATH", tmp_path / "mode")
    monkeypatch.setattr(netmode, "SCAN_CACHE_PATH", tmp_path / "wifi_scan.json")
    monkeypatch.setattr(netmode, "SETUP_COMPLETE_PATH", tmp_path / "setup_complete")
    monkeypatch.setattr(netmode, "WIFI_PRESENT_PATH", tmp_path / "wifi_present")
    return tmp_path


def test_boot_normal_when_configured(state_dir):
    with patch.object(netmode, "has_wifi_device", return_value=True), \
         patch.object(netmode, "should_enter_setup", return_value=False):
        netmode.boot()
    assert netmode.read_mode() == "normal"


def test_boot_setup_brings_up_ap_and_caches(state_dir):
    with patch.object(netmode, "has_wifi_device", return_value=True), \
         patch.object(netmode, "should_enter_setup", return_value=True), \
         patch.object(netmode, "scan_networks", return_value=[{"ssid": "X", "signal": 1, "secured": False}]), \
         patch.object(netmode, "start_ap") as start:
        netmode.boot()
    start.assert_called_once()
    assert netmode.read_mode() == "setup"
    assert netmode.read_cached_scan() == [{"ssid": "X", "signal": 1, "secured": False}]
    assert netmode.wifi_present() is True


def test_boot_without_wifi_hardware_skips_ap(state_dir):
    # Pi B+ over Ethernet: no radio to scan with, no AP to raise. Setup has to
    # run over the wire, and attempting the AP would fail the unit.
    with patch.object(netmode, "has_wifi_device", return_value=False), \
         patch.object(netmode, "should_enter_setup", return_value=True), \
         patch.object(netmode, "scan_networks") as scan, \
         patch.object(netmode, "start_ap") as start:
        netmode.boot()
    scan.assert_not_called()
    start.assert_not_called()
    assert netmode.read_mode() == "setup"
    assert netmode.wifi_present() is False


def test_boot_records_wifi_presence_in_normal_mode(state_dir):
    with patch.object(netmode, "has_wifi_device", return_value=False), \
         patch.object(netmode, "should_enter_setup", return_value=False):
        netmode.boot()
    assert netmode.wifi_present() is False


def test_boot_assumes_wifi_when_probe_fails(state_dir):
    with patch.object(netmode, "has_wifi_device", side_effect=RuntimeError("nmcli gone")), \
         patch.object(netmode, "should_enter_setup", return_value=False):
        netmode.boot()
    assert netmode.wifi_present() is True


def test_boot_writes_mode_even_if_ap_fails(state_dir):
    with patch.object(netmode, "has_wifi_device", return_value=True), \
         patch.object(netmode, "should_enter_setup", return_value=True), \
         patch.object(netmode, "scan_networks", return_value=[]), \
         patch.object(netmode, "start_ap", side_effect=RuntimeError("no AP")), \
         patch.object(netmode.time, "sleep"):
        with pytest.raises(RuntimeError):
            netmode.boot()
    assert netmode.read_mode() == "setup"


def test_boot_retries_ap_after_transient_failure(state_dir):
    # A transient nmcli failure on the first attempt must not leave the device
    # without an AP: boot() retries and the AP comes up on a later attempt.
    start = MagicMock(side_effect=[RuntimeError("nmcli busy"), None])
    with patch.object(netmode, "has_wifi_device", return_value=True), \
         patch.object(netmode, "should_enter_setup", return_value=True), \
         patch.object(netmode, "scan_networks", return_value=[]), \
         patch.object(netmode, "start_ap", start), \
         patch.object(netmode, "stop_ap") as stop, \
         patch.object(netmode.time, "sleep") as sleep:
        netmode.boot()
    assert start.call_count == 2
    # The failed first attempt is torn down before the retry, so the retry's
    # `connection add` doesn't collide with a stale con-name.
    assert stop.call_count == 1
    sleep.assert_called()  # backed off between attempts
    assert netmode.read_mode() == "setup"


def test_boot_exhausts_ap_retries_then_raises(state_dir, caplog):
    # Every attempt fails: boot() must exhaust the bounded retries, log loudly,
    # then re-raise so the unit surfaces the failure rather than sitting silent.
    start = MagicMock(side_effect=RuntimeError("no AP"))
    with patch.object(netmode, "has_wifi_device", return_value=True), \
         patch.object(netmode, "should_enter_setup", return_value=True), \
         patch.object(netmode, "scan_networks", return_value=[]), \
         patch.object(netmode, "start_ap", start), \
         patch.object(netmode, "stop_ap"), \
         patch.object(netmode.time, "sleep"):
        with caplog.at_level("ERROR"):
            with pytest.raises(RuntimeError):
                netmode.boot()
    assert start.call_count == netmode.AP_START_ATTEMPTS
    assert any(r.levelname == "ERROR" for r in caplog.records)
    assert netmode.read_mode() == "setup"


def test_wifi_present_defaults_true_when_unrecorded(state_dir):
    assert netmode.wifi_present() is True


def test_should_enter_setup_false_when_setup_complete(tmp_path, monkeypatch):
    complete_path = tmp_path / "setup_complete"
    complete_path.write_text("1")
    monkeypatch.setattr(netmode, "SETUP_COMPLETE_PATH", complete_path)
    with patch("subprocess.run") as run:
        assert netmode.should_enter_setup() is False
    run.assert_not_called()


def test_boot_setup_survives_scan_failure(state_dir):
    with patch.object(netmode, "has_wifi_device", return_value=True), \
         patch.object(netmode, "should_enter_setup", return_value=True), \
         patch.object(netmode, "scan_networks", side_effect=RuntimeError("scan failed")), \
         patch.object(netmode, "read_cached_scan", return_value=[]), \
         patch.object(netmode, "start_ap") as start:
        netmode.boot()
    start.assert_called_once()
    assert netmode.read_mode() == "setup"
