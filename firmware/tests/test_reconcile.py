from pathlib import Path
from unittest.mock import patch

from stillhem.db import init_db
from stillhem.blocklist import add_domain


def test_reconcile_main_runs(tmp_path: Path, monkeypatch, capsys) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    add_domain("reddit.com", db)

    monkeypatch.setenv("STILLHEM_DB_PATH", str(db))
    monkeypatch.setenv("STILLHEM_BLOCKLIST_PATH", str(tmp_path / "blocklist.txt"))
    monkeypatch.setenv("STILLHEM_UNBOUND_CONF", str(tmp_path / "stillhem.conf"))
    monkeypatch.setenv(
        "STILLHEM_DNS_TEMPLATE_DIR", str(Path(__file__).parent.parent / "dns")
    )

    import stillhem.reconcile as reconcile
    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound"):
        reconcile.main()  # first run writes the blocklist and reloads
    out = capsys.readouterr().out
    assert "reconciled: reloaded" in out
    assert (tmp_path / "blocklist.txt").read_text().strip() != ""

    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound"):
        reconcile.main()  # nothing changed, nothing pending
    assert "reconciled: no change" in capsys.readouterr().out


def test_reconcile_retries_reload_when_unbound_comes_back(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """A change applied while Unbound is down is reloaded once it returns."""
    db = tmp_path / "test.db"
    init_db(db)
    add_domain("reddit.com", db)

    monkeypatch.setenv("STILLHEM_DB_PATH", str(db))
    monkeypatch.setenv("STILLHEM_BLOCKLIST_PATH", str(tmp_path / "blocklist.txt"))
    monkeypatch.setenv("STILLHEM_UNBOUND_CONF", str(tmp_path / "stillhem.conf"))
    monkeypatch.setenv(
        "STILLHEM_DNS_TEMPLATE_DIR", str(Path(__file__).parent.parent / "dns")
    )

    import stillhem.reconcile as reconcile
    # Tick 1: change written while Unbound down -> not reloaded, but pending.
    with patch("stillhem.dns_control.is_unbound_running", return_value=False):
        reconcile.main()
    assert "reconciled: no change" in capsys.readouterr().out

    # Tick 2: content identical, Unbound back -> pending marker forces a reload.
    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
        reconcile.main()
        mock_reload.assert_called_once()
    assert "reconciled: reloaded" in capsys.readouterr().out
