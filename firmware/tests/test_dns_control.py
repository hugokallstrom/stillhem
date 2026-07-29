from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from stillhem.dns_control import (
    generate_unbound_conf,
    is_unbound_running,
    reload_unbound,
    reload_dns,
)

TEMPLATE_DIR = Path(__file__).parent.parent / "dns"


def test_generate_conf_includes_blocked_domains(tmp_path: Path) -> None:
    blocklist = tmp_path / "blocklist.txt"
    blocklist.write_text("instagram.com\ntiktok.com\n")
    out = tmp_path / "stillhem.conf"
    generate_unbound_conf(blocklist, out, template_dir=TEMPLATE_DIR)
    conf = out.read_text()
    assert 'local-zone: "instagram.com." always_nxdomain' in conf
    assert 'local-zone: "tiktok.com." always_nxdomain' in conf


def test_generate_conf_empty_blocklist_has_no_local_zones(tmp_path: Path) -> None:
    blocklist = tmp_path / "blocklist.txt"
    blocklist.write_text("")
    out = tmp_path / "stillhem.conf"
    generate_unbound_conf(blocklist, out, template_dir=TEMPLATE_DIR)
    assert "local-zone" not in out.read_text()


def test_generate_conf_skips_blank_lines(tmp_path: Path) -> None:
    blocklist = tmp_path / "blocklist.txt"
    blocklist.write_text("facebook.com\n\nreddit.com\n\n")
    out = tmp_path / "stillhem.conf"
    generate_unbound_conf(blocklist, out, template_dir=TEMPLATE_DIR)
    conf = out.read_text()
    assert conf.count("local-zone") == 2


def test_reload_unbound_runs_correct_command() -> None:
    with patch("subprocess.run") as mock_run:
        reload_unbound()
        mock_run.assert_called_once_with(["unbound-control", "reload"], check=True)


def test_is_unbound_running_true() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="active\n")
        assert is_unbound_running() is True


def test_is_unbound_running_false() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="inactive\n")
        assert is_unbound_running() is False


def test_reload_dns_calls_all_three_steps(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    from stillhem.db import init_db
    from stillhem.blocklist import add_domain
    init_db(db_path)
    add_domain("reddit.com", db_path)

    blocklist_path = tmp_path / "blocklist.txt"
    conf_path = tmp_path / "stillhem.conf"

    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
        reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR)
        mock_reload.assert_called_once()

    assert "reddit.com" in blocklist_path.read_text()
    assert 'local-zone: "reddit.com." always_nxdomain' in conf_path.read_text()


def test_reload_dns_skips_reload_when_unbound_not_running(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    from stillhem.db import init_db
    from stillhem.blocklist import add_domain
    init_db(db_path)
    add_domain("reddit.com", db_path)

    blocklist_path = tmp_path / "blocklist.txt"
    conf_path = tmp_path / "stillhem.conf"

    with patch("stillhem.dns_control.is_unbound_running", return_value=False), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
        reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR)
        mock_reload.assert_not_called()

    # Conf is still written so it's picked up when Unbound starts
    assert 'local-zone: "reddit.com." always_nxdomain' in conf_path.read_text()


def test_reload_dns_returns_false_and_skips_when_unchanged(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    from stillhem.db import init_db
    from stillhem.blocklist import add_domain
    init_db(db_path)
    add_domain("reddit.com", db_path)

    blocklist_path = tmp_path / "blocklist.txt"
    conf_path = tmp_path / "stillhem.conf"

    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound"):
        assert reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR) is True  # first

    with patch("stillhem.dns_control.generate_unbound_conf") as mock_gen, \
         patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
        # Nothing changed -> no-op.
        assert reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR) is False
        mock_gen.assert_not_called()
        mock_reload.assert_not_called()


def test_reload_dns_returns_true_when_schedule_flips(tmp_path: Path) -> None:
    from datetime import datetime
    from stillhem.db import init_db
    from stillhem.blocklist import set_schedule
    db_path = tmp_path / "test.db"
    init_db(db_path)
    set_schedule(db_path, "social", [0], 540, 1320)  # Mon 09:00-22:00

    blocklist_path = tmp_path / "blocklist.txt"
    conf_path = tmp_path / "stillhem.conf"
    outside = datetime(2026, 7, 27, 0, 30)  # Mon 00:30
    inside = datetime(2026, 7, 27, 12, 0)   # Mon 12:00

    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound"):
        reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR, now=outside)
        assert "instagram.com" in blocklist_path.read_text()
        # Crossing into the window flips the file, so Unbound is reloaded.
        assert reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR, now=inside) is True
        assert "instagram.com" not in blocklist_path.read_text()


def test_reload_dns_retries_reload_after_unbound_was_down(tmp_path: Path) -> None:
    """A change made while Unbound is down must be applied once it comes back.

    reload_dns gates on file-content change. If the blocklist flips while Unbound
    is down, the conf is regenerated but the reload is skipped. Next minute the
    content is identical, so without a pending marker reload_dns would return
    early and Unbound would never pick up the change.
    """
    db_path = tmp_path / "test.db"
    from stillhem.db import init_db
    from stillhem.blocklist import add_domain
    init_db(db_path)
    add_domain("reddit.com", db_path)

    blocklist_path = tmp_path / "blocklist.txt"
    conf_path = tmp_path / "stillhem.conf"

    # Tick 1: content changes but Unbound is down -> reload skipped, marker set.
    with patch("stillhem.dns_control.is_unbound_running", return_value=False), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
        assert reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR) is False
        mock_reload.assert_not_called()

    # Tick 2: content is now identical, but Unbound is back -> must reload.
    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
        assert reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR) is True
        mock_reload.assert_called_once()

    # Tick 3: nothing pending, content unchanged, Unbound up -> genuine no-op.
    with patch("stillhem.dns_control.generate_unbound_conf") as mock_gen, \
         patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
        assert reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR) is False
        mock_gen.assert_not_called()
        mock_reload.assert_not_called()


def test_reload_dns_retries_reload_after_reload_failure(tmp_path: Path) -> None:
    """If reload_unbound raises, the pending marker must survive so the next tick retries."""
    db_path = tmp_path / "test.db"
    from stillhem.db import init_db
    from stillhem.blocklist import add_domain
    init_db(db_path)
    add_domain("reddit.com", db_path)

    blocklist_path = tmp_path / "blocklist.txt"
    conf_path = tmp_path / "stillhem.conf"

    # Tick 1: content changes, Unbound up, but reload raises.
    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR)

    # Tick 2: content identical, Unbound up -> retry the reload.
    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
        assert reload_dns(db_path, blocklist_path, conf_path, TEMPLATE_DIR) is True
        mock_reload.assert_called_once()


from unittest.mock import MagicMock, patch as _patch

from stillhem.dns_control import total_queries


def test_total_queries_parses_stat():
    out = "thread0.num.queries=5\ntotal.num.queries=1234\ntotal.num.cachehits=9\n"
    with _patch("subprocess.run", return_value=MagicMock(stdout=out)):
        assert total_queries() == 1234


def test_total_queries_zero_when_line_missing():
    with _patch("subprocess.run", return_value=MagicMock(stdout="total.num.cachehits=9\n")):
        assert total_queries() == 0


def test_total_queries_zero_on_control_error():
    import subprocess
    with _patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "unbound-control")):
        assert total_queries() == 0
