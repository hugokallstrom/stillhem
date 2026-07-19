import pytest
from pathlib import Path
from stillhem.db import init_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(path)
    return path
