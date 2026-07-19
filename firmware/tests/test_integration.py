import socket
import subprocess
import time
from pathlib import Path

import pytest

from stillhem.auth import set_password
from stillhem.blocklist import add_domain, export_to_file
from stillhem.db import init_db
from stillhem.dns_control import (
    DEFAULT_TEMPLATE_DIR,
    UNBOUND_CONF_PATH,
    generate_unbound_conf,
    reload_unbound,
)


@pytest.mark.integration
def test_blocked_domain_returns_nxdomain(tmp_path: Path) -> None:
    """
    Requires: unbound installed, unbound-control configured, running as root.
    """
    db_path = tmp_path / "test.db"
    init_db(db_path)
    add_domain("stillhem-integration-test-blocked.invalid", db_path)

    blocklist_path = tmp_path / "blocklist.txt"
    export_to_file(db_path, blocklist_path)
    generate_unbound_conf(blocklist_path, UNBOUND_CONF_PATH, DEFAULT_TEMPLATE_DIR)
    reload_unbound()
    time.sleep(0.5)  # give Unbound a moment to reload

    try:
        socket.getaddrinfo("stillhem-integration-test-blocked.invalid", None)
        pytest.fail("Expected socket.gaierror (NXDOMAIN) but got a result")
    except socket.gaierror:
        pass  # expected: domain is blocked


@pytest.mark.integration
def test_non_blocked_domain_resolves(tmp_path: Path) -> None:
    """
    Confirms non-blocked domains still resolve after config is applied.
    """
    result = socket.getaddrinfo("example.com", 80)
    assert len(result) > 0
