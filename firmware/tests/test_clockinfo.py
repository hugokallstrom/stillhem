from unittest.mock import patch

from stillhem.clockinfo import ClockStatus, clock_status, parse_timedatectl


def test_parse_synced():
    out = "Timezone=Europe/Stockholm\nNTPSynchronized=yes\n"
    tz, synced = parse_timedatectl(out)
    assert tz == "Europe/Stockholm"
    assert synced is True


def test_parse_unsynced():
    out = "Timezone=Europe/Stockholm\nNTPSynchronized=no\n"
    tz, synced = parse_timedatectl(out)
    assert tz == "Europe/Stockholm"
    assert synced is False


def test_parse_missing_ntp_key_is_unknown():
    # timedatectl absent/garbled output: no NTP line -> unknown (None)
    tz, synced = parse_timedatectl("")
    assert tz is None
    assert synced is None


def test_clock_status_when_timedatectl_absent():
    # On a Mac / non-systemd host, timedatectl is missing: status must still
    # render — a real local time, tz may be None, ntp_synced unknown (None).
    with patch("stillhem.clockinfo._run_timedatectl", return_value=None):
        status = clock_status()
    assert isinstance(status, ClockStatus)
    assert status.now  # a non-empty formatted local time string
    assert status.ntp_synced is None


def test_clock_status_synced():
    with patch(
        "stillhem.clockinfo._run_timedatectl",
        return_value="Timezone=Europe/Stockholm\nNTPSynchronized=yes\n",
    ):
        status = clock_status()
    assert status.timezone == "Europe/Stockholm"
    assert status.ntp_synced is True


def test_clock_status_unsynced():
    with patch(
        "stillhem.clockinfo._run_timedatectl",
        return_value="Timezone=Europe/Stockholm\nNTPSynchronized=no\n",
    ):
        status = clock_status()
    assert status.ntp_synced is False
