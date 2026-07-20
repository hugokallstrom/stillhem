import os
from pathlib import Path

from stillhem import netmode
from stillhem.admin.app import create_app


def build():
    return create_app(
        db_path=Path(os.environ.get("STILLHEM_DB_PATH", "/var/lib/stillhem/stillhem.db")),
        setup_mode=netmode.read_mode() == "setup",
    )


def main() -> None:
    import uvicorn

    uvicorn.run(build(), host="0.0.0.0", port=80)


if __name__ == "__main__":
    main()
