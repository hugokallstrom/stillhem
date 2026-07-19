import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from stillhem.admin.routes.auth_routes import router as auth_router
from stillhem.admin.routes.blocklist_routes import router as blocklist_router
from stillhem.admin.routes.setup_routes import router as setup_router
from stillhem.blocklist import ACTIVE_BLOCKLIST_PATH
from stillhem.dns_control import DEFAULT_TEMPLATE_DIR, UNBOUND_CONF_PATH

STATIC_DIR = Path(__file__).parent.parent.parent.parent / "static"


def create_app(
    db_path: Path,
    blocklist_path: Path = ACTIVE_BLOCKLIST_PATH,
    unbound_conf_path: Path = UNBOUND_CONF_PATH,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None)
    app.state.db_path = db_path
    app.state.blocklist_path = blocklist_path
    app.state.unbound_conf_path = unbound_conf_path
    app.state.template_dir = template_dir

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(auth_router)
    app.include_router(blocklist_router)
    app.include_router(setup_router)

    return app


app = create_app(
    db_path=Path(os.environ.get("ALGORO_DB_PATH", "/var/lib/algoro/algoro.db")),
    blocklist_path=Path(os.environ.get("ALGORO_BLOCKLIST_PATH", str(ACTIVE_BLOCKLIST_PATH))),
    unbound_conf_path=Path(os.environ.get("ALGORO_UNBOUND_CONF", str(UNBOUND_CONF_PATH))),
    template_dir=Path(os.environ.get("ALGORO_DNS_TEMPLATE_DIR", str(DEFAULT_TEMPLATE_DIR))),
)
