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
    with patch("stillhem.dns_control.is_unbound_running", return_value=False):
        reconcile.main()  # first run writes the blocklist -> reloaded
    out = capsys.readouterr().out
    assert "reconciled: reloaded" in out
    assert (tmp_path / "blocklist.txt").read_text().strip() != ""

    with patch("stillhem.dns_control.is_unbound_running", return_value=False):
        reconcile.main()  # nothing changed
    assert "reconciled: no change" in capsys.readouterr().out
