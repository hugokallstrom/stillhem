from unittest.mock import patch

from stillhem import launch


def test_build_setup_mode(monkeypatch):
    with patch("stillhem.launch.netmode.read_mode", return_value="setup"):
        app = launch.build()
    assert app.state.setup_mode is True


def test_build_normal_mode(monkeypatch):
    with patch("stillhem.launch.netmode.read_mode", return_value="normal"):
        app = launch.build()
    assert app.state.setup_mode is False
