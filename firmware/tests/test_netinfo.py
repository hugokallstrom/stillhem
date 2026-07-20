from unittest.mock import MagicMock, patch

from stillhem import netinfo


def test_primary_ip_returns_socket_name():
    sock = MagicMock()
    sock.getsockname.return_value = ("192.168.1.42", 51234)
    with patch("socket.socket", return_value=sock):
        assert netinfo.primary_ip() == "192.168.1.42"
    sock.connect.assert_called_once()
    sock.close.assert_called_once()


def test_primary_ip_falls_back_on_error():
    sock = MagicMock()
    sock.connect.side_effect = OSError("no route")
    with patch("socket.socket", return_value=sock):
        assert netinfo.primary_ip() == "127.0.0.1"
    sock.close.assert_called_once()
